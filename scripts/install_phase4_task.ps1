param(
    [string]$TaskName = "Nostradamus Phase 4 Daily",
    [string]$DailyAt = "18:55"
)

$ErrorActionPreference = "Stop"
$runner = Join-Path $PSScriptRoot "run_phase4_daily.ps1"
if (-not (Test-Path -LiteralPath $runner)) {
    throw "No existe el ejecutor: $runner"
}

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$runner`""
$trigger = New-ScheduledTaskTrigger -Daily -At $DailyAt
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 20)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Recolecta y analiza titulares BTC/ETH para Nostradamus V4." `
    -Force

Write-Output "Tarea '$TaskName' instalada para las $DailyAt (hora local)."
