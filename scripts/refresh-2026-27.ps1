param(
    [switch]$FullModelRefresh
)

$ErrorActionPreference = "Stop"
$RepositoryRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepositoryRoot ".venv\Scripts\python.exe"
$ModelMetadata = Join-Path $RepositoryRoot "models\live_2026_27_models.json"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Python environment is missing: $Python"
}

$Arguments = @(
    "-m",
    "fpl_intelligence.refresh_current_season",
    "--season",
    "2026-27"
)
if (-not $FullModelRefresh -and (Test-Path -LiteralPath $ModelMetadata)) {
    $Arguments += "--skip-model-training"
}

Push-Location $RepositoryRoot
try {
    & $Python @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "2026/27 artifact refresh failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}
