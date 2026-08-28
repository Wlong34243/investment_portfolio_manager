<#
=============================================================================
 install_ui_service.ps1

 Purpose : Register a logon scheduled task that keeps the local portfolio UI
           running at http://127.0.0.1:8765 without a terminal window.

 Action  : .venv\Scripts\pythonw.exe manager.py ui serve
 Trigger : At logon (current user). No elevation required.
 Settings: Restart on failure (3 attempts, 1 min apart); no stop on idle/battery.

 Usage   : powershell -ExecutionPolicy Bypass -File scripts\install_ui_service.ps1
=============================================================================
#>

$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path $PSScriptRoot -Parent
$Pythonw = Join-Path $RepoRoot '.venv\Scripts\pythonw.exe'
$Manager = Join-Path $RepoRoot 'manager.py'
$TaskName = 'PortfolioUI'

if (-not (Test-Path $Pythonw)) {
    Write-Host "FAILED: pythonw not found at $Pythonw" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $Manager)) {
    Write-Host "FAILED: manager.py not found at $Manager" -ForegroundColor Red
    exit 1
}

$action = New-ScheduledTaskAction `
    -Execute $Pythonw `
    -Argument "`"$Manager`" ui serve" `
    -WorkingDirectory $RepoRoot

$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Hours 0)

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description 'Portfolio local UI (pythonw manager.py ui serve) at logon.' `
    -Force | Out-Null

Write-Host "Task '$TaskName' registered." -ForegroundColor Green

Write-Host "`n=== Verification ===" -ForegroundColor Cyan
$t = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
$info = Get-ScheduledTaskInfo -TaskName $TaskName
[PSCustomObject]@{
    TaskName  = $t.TaskName
    State     = $t.State
    RunAs     = $t.Principal.UserId
    LogonType = $t.Principal.LogonType
    Action    = "$($t.Actions[0].Execute) $($t.Actions[0].Arguments)"
    WorkingDir = $t.Actions[0].WorkingDirectory
    RestartCount = $t.Settings.RestartCount
    LastResult = $info.LastTaskResult
    NextRun   = $info.NextRunTime
} | Format-List

Write-Host "Browse: http://127.0.0.1:8765/  (starts at next logon, or run Start-ScheduledTask -TaskName $TaskName)" -ForegroundColor Cyan
