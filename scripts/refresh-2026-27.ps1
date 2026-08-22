param(
    [switch]$FullModelRefresh,
    [switch]$FinalNewsReviewed,
    [string[]]$FinalNewsSource = @(),
    [int]$TeamId = 0
)

$ErrorActionPreference = "Stop"
$RepositoryRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepositoryRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    throw "Python environment is missing: $Python"
}

$Arguments = @(
    "-m",
    "fpl_intelligence.post_gameweek_refresh",
    "--season",
    "2026-27"
)
if ($FullModelRefresh) {
    $Arguments += "--force-model-refresh"
}

Push-Location $RepositoryRoot
try {
    & $Python @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "2026/27 artifact refresh failed with exit code $LASTEXITCODE"
    }
    & $Python "-m" "fpl_intelligence.p10_calibration" | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "P10 robustness refresh failed with exit code $LASTEXITCODE"
    }
    $P11Arguments = @("-m", "fpl_intelligence.p11_deadline_finalization")
    if ($FinalNewsReviewed) {
        if ($FinalNewsSource.Count -eq 0) {
            throw "-FinalNewsReviewed requires at least one -FinalNewsSource URL"
        }
        $P11Arguments += "--final-news-reviewed"
        foreach ($Source in $FinalNewsSource) {
            $P11Arguments += @("--final-news-source", $Source)
        }
    }
    & $Python @P11Arguments | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "P11 deadline finalization failed with exit code $LASTEXITCODE"
    }
    & $Python "-m" "fpl_intelligence.p12_set_piece_report" | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "P12 set-piece audit failed with exit code $LASTEXITCODE"
    }
    $BootstrapPath = Join-Path $RepositoryRoot "data\raw\bootstrap-static.json"
    $Bootstrap = Get-Content -LiteralPath $BootstrapPath -Raw | ConvertFrom-Json
    $FirstDeadline = $Bootstrap.events |
        Sort-Object { [int]$_.id } |
        Select-Object -First 1 -ExpandProperty deadline_time
    if ($FirstDeadline -is [DateTimeOffset]) {
        $FirstDeadlineUtc = $FirstDeadline
    }
    elseif ($FirstDeadline -is [DateTime]) {
        # ConvertFrom-Json may materialize ISO timestamps as DateTime values. Casting
        # the typed value avoids a locale-dependent DateTime -> string -> parse cycle.
        $FirstDeadlineUtc = [DateTimeOffset]$FirstDeadline
    }
    else {
        $FirstDeadlineUtc = [DateTimeOffset]::Parse(
            [string]$FirstDeadline,
            [Globalization.CultureInfo]::InvariantCulture,
            [Globalization.DateTimeStyles]::AssumeUniversal
        )
    }
    $SeasonStarted = [DateTimeOffset]::UtcNow -ge $FirstDeadlineUtc.ToUniversalTime()
    if (-not $SeasonStarted) {
        & $Python "-m" "scripts.capture_gw1_shadow"
        if ($LASTEXITCODE -ne 0) {
            throw "GW1 shadow capture failed with exit code $LASTEXITCODE"
        }
    }
    if (-not $SeasonStarted -or $TeamId -gt 0) {
        $EvidenceArguments = @(
            "-m",
            "fpl_intelligence.live_decision_evidence",
            "capture"
        )
        if ($TeamId -gt 0) {
            $EvidenceArguments += @("--team-id", "$TeamId")
        }
        & $Python @EvidenceArguments
        if ($LASTEXITCODE -ne 0) {
            throw "Live deadline evidence capture failed with exit code $LASTEXITCODE"
        }
    }
    else {
        Write-Warning (
            "Official data and models were refreshed, but post-GW1 decision evidence " +
            "was not captured because -TeamId was not supplied."
        )
    }
}
finally {
    Pop-Location
}
