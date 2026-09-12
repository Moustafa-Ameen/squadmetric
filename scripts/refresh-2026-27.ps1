param(
    [switch]$FullModelRefresh,
    [switch]$FinalNewsReviewed,
    [string[]]$FinalNewsSource = @(),
    [int]$TeamId = 0,
    [int]$ModelTeamId = 0
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
        & $Python "-m" "fpl_intelligence.p10_calibration" | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "Opening-squad robustness refresh failed with exit code $LASTEXITCODE"
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
            throw "Opening-squad deadline finalization failed with exit code $LASTEXITCODE"
        }
        & $Python "-m" "scripts.capture_gw1_shadow"
        if ($LASTEXITCODE -ne 0) {
            throw "GW1 shadow capture failed with exit code $LASTEXITCODE"
        }
    }
    else {
        Write-Host (
            "Season is in progress: preserved immutable pre-GW1 opening-squad " +
            "and shadow " +
            "artifacts instead of regenerating them with post-deadline information."
        )
    }
    & $Python "-m" "fpl_intelligence.p12_set_piece_report" | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Set-piece audit failed with exit code $LASTEXITCODE"
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
    if ($ModelTeamId -gt 0) {
        & $Python "-m" "fpl_intelligence.model_team_performance" `
            "--team-id" "$ModelTeamId"
        if ($LASTEXITCODE -ne 0) {
            throw "Model-team performance capture failed with exit code $LASTEXITCODE"
        }
        & $Python "-m" "fpl_intelligence.live_decision_evidence" "capture" `
            "--team-id" "$ModelTeamId"
        if ($LASTEXITCODE -ne 0) {
            throw "Model-team deadline evidence capture failed with exit code $LASTEXITCODE"
        }
    }
}
finally {
    Pop-Location
}
