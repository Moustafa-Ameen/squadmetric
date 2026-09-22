[CmdletBinding()]
param(
    [ValidateRange(1, 65535)]
    [int]$BackendPort = 8000,

    [ValidateRange(1, 65535)]
    [int]$FrontendPort = 3000,

    [switch]$NoBrowser,

    [switch]$Dev,

    [switch]$SkipDataRefresh
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$projectRoot = $PSScriptRoot
$frontendRoot = Join-Path $projectRoot "frontend"
$venvRoot = Join-Path $projectRoot ".venv"
$pythonExe = Join-Path $venvRoot "Scripts\python.exe"
$nextEntry = Join-Path $frontendRoot "node_modules\next\dist\bin\next"
$runtimeRoot = Join-Path $projectRoot ".runtime\squadmetric"
$backendProcess = $null
$frontendProcess = $null
$localWorkspaceMode = $false

function Get-CommandPath {
    param([Parameter(Mandatory)][string]$Name)

    $command = Get-Command $Name -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $command) {
        return $null
    }
    return $command.Source
}

function Get-ActiveSeason {
    if (-not [string]::IsNullOrWhiteSpace($env:FPL_ACTIVE_SEASON)) {
        return $env:FPL_ACTIVE_SEASON
    }

    $today = Get-Date
    $startYear = if ($today.Month -ge 6) { $today.Year } else { $today.Year - 1 }
    $endYear = (($startYear + 1) % 100).ToString("00")
    return "$startYear-$endYear"
}

function Test-PortAvailable {
    param([Parameter(Mandatory)][int]$Port)

    $listener = [System.Net.Sockets.TcpListener]::new(
        [System.Net.IPAddress]::Loopback,
        $Port
    )
    try {
        $listener.Start()
        return $true
    }
    catch {
        return $false
    }
    finally {
        $listener.Stop()
    }
}

function Get-LogTail {
    param([Parameter(Mandatory)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return "No error log was written."
    }
    $lines = Get-Content -LiteralPath $Path -Tail 20 -ErrorAction SilentlyContinue
    if ($null -eq $lines -or $lines.Count -eq 0) {
        return "The error log is empty."
    }
    return ($lines -join [Environment]::NewLine)
}

function Get-DotEnvValue {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Name
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return $null
    }

    $escapedName = [Regex]::Escape($Name)
    $line = Get-Content -LiteralPath $Path | Where-Object {
        $_ -match "^\s*$escapedName\s*="
    } | Select-Object -Last 1
    if ($null -eq $line) {
        return $null
    }

    $value = ($line -split "=", 2)[1].Trim()
    if ($value.Length -ge 2) {
        $quotedWithDouble = $value.StartsWith('"') -and $value.EndsWith('"')
        $quotedWithSingle = $value.StartsWith("'") -and $value.EndsWith("'")
        if ($quotedWithDouble -or $quotedWithSingle) {
            $value = $value.Substring(1, $value.Length - 2)
        }
    }
    return $value
}

function Test-ServiceHostReachable {
    param([Parameter(Mandatory)][string]$Url)

    try {
        $uri = [Uri]$Url
        if (-not $uri.IsAbsoluteUri) {
            return $false
        }
        $addresses = [System.Net.Dns]::GetHostAddresses($uri.DnsSafeHost)
        return $addresses.Count -gt 0
    }
    catch {
        return $false
    }
}

function Test-FrontendBuildRequired {
    param(
        [Parameter(Mandatory)][string]$FrontendRoot,
        [Parameter(Mandatory)][string]$Mode
    )

    $buildId = Join-Path $FrontendRoot ".next\BUILD_ID"
    $modeMarker = Join-Path $FrontendRoot ".next\squadmetric-launch-mode.txt"
    if (-not (Test-Path -LiteralPath $buildId -PathType Leaf) -or
        -not (Test-Path -LiteralPath $modeMarker -PathType Leaf)) {
        return $true
    }
    if ((Get-Content -LiteralPath $modeMarker -Raw).Trim() -ne $Mode) {
        return $true
    }

    $buildTime = (Get-Item -LiteralPath $buildId).LastWriteTimeUtc
    $sourceFiles = @()
    foreach ($directory in @("app", "components", "context", "lib", "public")) {
        $sourceDirectory = Join-Path $FrontendRoot $directory
        if (Test-Path -LiteralPath $sourceDirectory -PathType Container) {
            $sourceFiles += Get-ChildItem -LiteralPath $sourceDirectory -File -Recurse
        }
    }
    foreach ($name in @(
        "package.json",
        "package-lock.json",
        "next.config.ts",
        "postcss.config.mjs",
        "proxy.ts",
        "tsconfig.json"
    )) {
        $sourceFile = Join-Path $FrontendRoot $name
        if (Test-Path -LiteralPath $sourceFile -PathType Leaf) {
            $sourceFiles += Get-Item -LiteralPath $sourceFile
        }
    }
    return [bool]($sourceFiles | Where-Object { $_.LastWriteTimeUtc -gt $buildTime } | Select-Object -First 1)
}

function Wait-ForHttp {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][string]$Uri,
        [Parameter(Mandatory)][System.Diagnostics.Process]$Process,
        [Parameter(Mandatory)][string]$ErrorLog,
        [int]$TimeoutSeconds = 120
    )

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        $Process.Refresh()
        if ($Process.HasExited) {
            $tail = Get-LogTail -Path $ErrorLog
            throw "$Name stopped during startup.`n$tail"
        }

        try {
            $response = Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                return
            }
        }
        catch {
            Start-Sleep -Milliseconds 750
        }
    }

    $tail = Get-LogTail -Path $ErrorLog
    throw "$Name did not become ready at $Uri within $TimeoutSeconds seconds.`n$tail"
}

function Stop-ProcessTree {
    param([Parameter(Mandatory)][int]$ProcessId)

    $children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $ProcessId" `
        -ErrorAction SilentlyContinue
    foreach ($child in $children) {
        Stop-ProcessTree -ProcessId $child.ProcessId
    }
    Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
}

try {
    if (-not (Test-Path -LiteralPath $frontendRoot -PathType Container)) {
        throw "The frontend directory was not found at $frontendRoot."
    }

    if (-not (Test-Path -LiteralPath $pythonExe -PathType Leaf)) {
        Write-Host "Creating the Python 3.13 environment..." -ForegroundColor Cyan
        $pyLauncher = Get-CommandPath -Name "py.exe"
        if ($null -ne $pyLauncher) {
            & $pyLauncher -3.13 -m venv $venvRoot
        }
        else {
            $systemPython = Get-CommandPath -Name "python.exe"
            if ($null -eq $systemPython) {
                throw "Python 3.13 is required. Install it, then run .\start.cmd again."
            }
            & $systemPython -m venv $venvRoot
        }

        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $pythonExe)) {
            throw "Could not create the Python environment. Python 3.13 is required."
        }

        & $pythonExe -m pip install -e "${projectRoot}[dev]"
        if ($LASTEXITCODE -ne 0) {
            throw "Python dependency installation failed."
        }
    }

    $pythonVersion = & $pythonExe -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
    if ($LASTEXITCODE -ne 0 -or [version]$pythonVersion -lt [version]"3.13") {
        throw "SquadMetric requires Python 3.13 or newer; the local environment uses $pythonVersion."
    }

    $nodeExe = Get-CommandPath -Name "node.exe"
    if ($null -eq $nodeExe) {
        throw "Node.js 24 is required. Install it, then run .\start.cmd again."
    }

    $nodeMajor = [int]((& $nodeExe --version).TrimStart("v").Split(".")[0])
    if ($nodeMajor -lt 24) {
        throw "SquadMetric requires Node.js 24 or newer."
    }

    $npmExe = Get-CommandPath -Name "npm.cmd"
    if ($null -eq $npmExe) {
        throw "npm was not found. Install Node.js 24, then run .\start.cmd again."
    }

    if (-not $SkipDataRefresh) {
        $activeSeason = Get-ActiveSeason
        $refreshMutex = [System.Threading.Mutex]::new($false, "Local\SquadMetricDataRefresh")
        $refreshLockAcquired = $false
        try {
            try {
                $refreshLockAcquired = $refreshMutex.WaitOne(0)
            }
            catch [System.Threading.AbandonedMutexException] {
                $refreshLockAcquired = $true
            }

            if ($refreshLockAcquired) {
                Write-Host "Checking for finalized FPL data ($activeSeason)..." -ForegroundColor Cyan
                Write-Host "This refresh updates SquadMetric data only; it cannot change your FPL team." -ForegroundColor DarkGray
                & $pythonExe -m fpl_intelligence.post_gameweek_refresh --season $activeSeason
                if ($LASTEXITCODE -ne 0) {
                    Write-Warning (
                        "The prediction refresh did not complete. Starting with the last validated " +
                        "bundle; recommendation pages may remain unavailable."
                    )
                }
            }
            else {
                Write-Host "Another SquadMetric data refresh is already running; using its result when ready." -ForegroundColor Yellow
            }
        }
        finally {
            if ($refreshLockAcquired) {
                $refreshMutex.ReleaseMutex()
            }
            $refreshMutex.Dispose()
        }
    }

    if (-not (Test-Path -LiteralPath $nextEntry -PathType Leaf)) {
        Write-Host "Installing website dependencies..." -ForegroundColor Cyan
        & $npmExe ci --prefix $frontendRoot
        if ($LASTEXITCODE -ne 0) {
            throw "Website dependency installation failed."
        }
    }

    $localEnvFile = Join-Path $frontendRoot ".env.local"
    $supabaseUrl = $env:NEXT_PUBLIC_SUPABASE_URL
    if ([string]::IsNullOrWhiteSpace($supabaseUrl)) {
        $supabaseUrl = Get-DotEnvValue -Path $localEnvFile -Name "NEXT_PUBLIC_SUPABASE_URL"
    }
    if (-not [string]::IsNullOrWhiteSpace($supabaseUrl) -and
        -not (Test-ServiceHostReachable -Url $supabaseUrl)) {
        $localWorkspaceMode = $true
        Write-Warning (
            "The configured Supabase account service is unreachable. " +
            "Starting in local workspace mode; sign-in and account sync are disabled for this run."
        )
    }

    if ($BackendPort -eq $FrontendPort) {
        throw "The backend and website must use different ports."
    }
    if (-not (Test-PortAvailable -Port $BackendPort)) {
        throw "Port $BackendPort is already in use. Stop that process or choose -BackendPort PORT."
    }
    if (-not (Test-PortAvailable -Port $FrontendPort)) {
        throw "Port $FrontendPort is already in use. Stop that process or choose -FrontendPort PORT."
    }

    New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null
    $runStamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $backendOut = Join-Path $runtimeRoot "$runStamp-backend.log"
    $backendError = Join-Path $runtimeRoot "$runStamp-backend-error.log"
    $frontendOut = Join-Path $runtimeRoot "$runStamp-frontend.log"
    $frontendError = Join-Path $runtimeRoot "$runStamp-frontend-error.log"

    Write-Host "Starting SquadMetric API..." -ForegroundColor Cyan
    $backendProcess = Start-Process `
        -FilePath $pythonExe `
        -ArgumentList @(
            "-m", "uvicorn", "api.main:app",
            "--host", "127.0.0.1",
            "--port", "$BackendPort"
        ) `
        -WorkingDirectory $projectRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput $backendOut `
        -RedirectStandardError $backendError `
        -PassThru

    Wait-ForHttp `
        -Name "SquadMetric API" `
        -Uri "http://127.0.0.1:$BackendPort/api/health" `
        -Process $backendProcess `
        -ErrorLog $backendError

    Write-Host "Preparing fast page data..." -ForegroundColor Cyan
    foreach ($warmPath in @(
        "/api/fpl/season-state",
        "/api/predictions/overview",
        "/api/chip-opportunities"
    )) {
        try {
            Invoke-WebRequest `
                -Uri "http://127.0.0.1:$BackendPort$warmPath" `
                -UseBasicParsing `
                -TimeoutSec 60 | Out-Null
        }
        catch {
            Write-Warning "Could not pre-load $warmPath; the page will retry when opened."
        }
    }

    Write-Host "Starting SquadMetric website..." -ForegroundColor Cyan
    $previousSupabaseUrl = $env:NEXT_PUBLIC_SUPABASE_URL
    $previousSupabaseKey = $env:NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY
    $previousApiServer = $env:FPL_API_SERVER_URL
    try {
        $env:FPL_API_SERVER_URL = "http://127.0.0.1:$BackendPort"
        if ($localWorkspaceMode) {
            # Process-level variables take precedence over .env.local in Next.js.
            # The child receives these values; the caller's environment is restored below.
            $env:NEXT_PUBLIC_SUPABASE_URL = "disabled-for-local-launch"
            $env:NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY = "disabled-for-local-launch"
        }
        $frontendCommand = if ($Dev) { "dev" } else { "start" }
        if (-not $Dev) {
            $buildMode = if ($localWorkspaceMode) { "local" } else { "authenticated" }
            if (Test-FrontendBuildRequired -FrontendRoot $frontendRoot -Mode $buildMode) {
                Write-Host "Building the optimized website..." -ForegroundColor Cyan
                Push-Location $frontendRoot
                try {
                    & $npmExe run build
                    if ($LASTEXITCODE -ne 0) {
                        throw "The optimized website build failed."
                    }
                }
                finally {
                    Pop-Location
                }
                $modeMarker = Join-Path $frontendRoot ".next\squadmetric-launch-mode.txt"
                [System.IO.File]::WriteAllText($modeMarker, $buildMode)
            }
        }
        $frontendProcess = Start-Process `
            -FilePath $nodeExe `
            -ArgumentList @(
                "`"$nextEntry`"", $frontendCommand,
                "--hostname", "127.0.0.1",
                "--port", "$FrontendPort"
            ) `
            -WorkingDirectory $frontendRoot `
            -WindowStyle Hidden `
            -RedirectStandardOutput $frontendOut `
            -RedirectStandardError $frontendError `
            -PassThru
    }
    finally {
        if ($null -eq $previousSupabaseUrl) {
            Remove-Item Env:NEXT_PUBLIC_SUPABASE_URL -ErrorAction SilentlyContinue
        }
        else {
            $env:NEXT_PUBLIC_SUPABASE_URL = $previousSupabaseUrl
        }
        if ($null -eq $previousSupabaseKey) {
            Remove-Item Env:NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY -ErrorAction SilentlyContinue
        }
        else {
            $env:NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY = $previousSupabaseKey
        }
        if ($null -eq $previousApiServer) {
            Remove-Item Env:FPL_API_SERVER_URL -ErrorAction SilentlyContinue
        }
        else {
            $env:FPL_API_SERVER_URL = $previousApiServer
        }
    }

    Wait-ForHttp `
        -Name "SquadMetric website" `
        -Uri "http://127.0.0.1:$FrontendPort/login" `
        -Process $frontendProcess `
        -ErrorLog $frontendError

    $websitePath = if ($localWorkspaceMode) { "/dashboard" } else { "" }
    $websiteUrl = "http://localhost:$FrontendPort$websitePath"
    Write-Host ""
    Write-Host "SquadMetric is ready: $websiteUrl" -ForegroundColor Green
    Write-Host "API: http://localhost:$BackendPort"
    if ($localWorkspaceMode) {
        Write-Host "Mode: local workspace (browser data only)" -ForegroundColor Yellow
    }
    if ($Dev) {
        Write-Host "Frontend: development mode" -ForegroundColor Yellow
    }
    else {
        Write-Host "Frontend: optimized production build" -ForegroundColor Green
    }
    Write-Host "Logs: $runtimeRoot"
    Write-Host "Press Ctrl+C to stop both services."

    if (-not $NoBrowser) {
        Start-Process $websiteUrl
    }

    while ($true) {
        Start-Sleep -Seconds 1
        $backendProcess.Refresh()
        $frontendProcess.Refresh()
        if ($backendProcess.HasExited) {
            $tail = Get-LogTail -Path $backendError
            throw "SquadMetric API stopped unexpectedly.`n$tail"
        }
        if ($frontendProcess.HasExited) {
            $tail = Get-LogTail -Path $frontendError
            throw "SquadMetric website stopped unexpectedly.`n$tail"
        }
    }
}
catch {
    Write-Host ""
    Write-Error $_
    exit 1
}
finally {
    Write-Host ""
    Write-Host "Stopping SquadMetric..." -ForegroundColor Yellow
    if ($null -ne $frontendProcess -and -not $frontendProcess.HasExited) {
        Stop-ProcessTree -ProcessId $frontendProcess.Id
    }
    if ($null -ne $backendProcess -and -not $backendProcess.HasExited) {
        Stop-ProcessTree -ProcessId $backendProcess.Id
    }
}
