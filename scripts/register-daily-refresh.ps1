param(
    [string]$TaskName = "FPL Intelligence 2026-27 Daily Refresh",
    [string]$At = "08:00",
    [int]$TeamId = 0
)

$ErrorActionPreference = "Stop"
$RefreshScript = Join-Path $PSScriptRoot "refresh-2026-27.ps1"
if (-not (Test-Path -LiteralPath $RefreshScript)) {
    throw "Refresh script is missing: $RefreshScript"
}

$ActionArguments = "-NoProfile -ExecutionPolicy Bypass -File `"$RefreshScript`""
if ($TeamId -gt 0) {
    $ActionArguments += " -TeamId $TeamId"
}
$Action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument $ActionArguments
$Trigger = New-ScheduledTaskTrigger -Daily -At $At
$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "Refresh official FPL data, ingest finalized Gameweeks, retrain safely, and capture deadline evidence." `
    -Force

Write-Host "Registered '$TaskName' to run daily at $At."
if ($TeamId -le 0) {
    Write-Warning "No TeamId supplied; post-GW1 decision-evidence capture will be skipped."
}
