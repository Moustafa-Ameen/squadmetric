param(
    [string]$TaskName = "FPL Intelligence 2026-27 Daily Refresh",
    [string]$At = "08:00"
)

$ErrorActionPreference = "Stop"
$RefreshScript = Join-Path $PSScriptRoot "refresh-2026-27.ps1"
if (-not (Test-Path -LiteralPath $RefreshScript)) {
    throw "Refresh script is missing: $RefreshScript"
}

$Action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$RefreshScript`""
$Trigger = New-ScheduledTaskTrigger -Daily -At $At
$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "Refresh official FPL bootstrap, fixtures, prices, rules, and serving manifests." `
    -Force

Write-Host "Registered '$TaskName' to run daily at $At."
