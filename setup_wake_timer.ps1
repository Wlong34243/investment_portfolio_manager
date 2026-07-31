<#
=============================================================================
 setup_wake_timer.ps1

 Purpose : Create a daily Windows scheduled task that wakes the machine from
           sleep/hibernate, and enable the wake-timer power settings it
           depends on (both AC and battery). The task's action is
           wake_and_run.ps1, which holds the awake lock, launches keepawake,
           and runs the morning pipeline.
 Inputs  : -Time  (default "06:00")  -TaskName (default "DailyWake")
           -Script (default wake_and_run.ps1 beside this file)
 Outputs : Registered scheduled task + modified active power scheme.
           Prints a verification block at the end.
 Deps    : Windows 10/11, PowerShell 5.1+, MUST run elevated (Administrator).
           wake_and_run.ps1 + morning_auto.bat in the same folder.
 Usage   : Right-click Start > Terminal (Admin), then:
             Set-ExecutionPolicy -Scope Process Bypass -Force
             C:\Users\WLong\Investment_Portfolio\setup_wake_timer.ps1
 Note    : Task runs as the CURRENT USER via Interactive logon, not SYSTEM.
           The pipeline needs the user profile (gcloud ADC, Schwab token) and
           the keepawake shortcut lives under a user OneDrive path.
           S4U was tried first and fails with 1311 ERROR_NO_LOGON_SERVERS
           off the corporate network. ASCII-ONLY FILE, keep the BOM.
=============================================================================
#>

[CmdletBinding()]
param(
    [string]$Time     = "06:00",
    [string]$TaskName = "DailyWake",
    [string]$Script   = (Join-Path $PSScriptRoot "wake_and_run.ps1"),
    [switch]$RunNow   # opt-in: fire the task once after registering (LIVE pipeline)
)

$ErrorActionPreference = 'Stop'

# --- 0. Elevation check -----------------------------------------------------
$isAdmin = ([Security.Principal.WindowsPrincipal] `
            [Security.Principal.WindowsIdentity]::GetCurrent()
           ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Error "Must run as Administrator. Re-launch Terminal via 'Run as administrator'."
    return
}

# --- 1. Report which sleep states this machine actually supports -------------
Write-Host "`n=== Sleep states available (powercfg /a) ===" -ForegroundColor Cyan
powercfg /a

# --- 2. Enable wake timers on AC and DC -------------------------------------
# SUB_SLEEP subgroup GUID / "Allow wake timers" setting GUID
$SUB_SLEEP   = '238c9fa8-0aad-41ed-83f4-97be242c8f20'
$WAKE_TIMERS = 'bd3b718a-0680-4d9d-8ab2-e1d2b4ac806d'   # 0=Disable 1=Enable 2=Important only

# Unhide the setting in the GUI too (some OEM images hide it)
powercfg -attributes $SUB_SLEEP $WAKE_TIMERS -ATTRIB_HIDE | Out-Null

powercfg /SETACVALUEINDEX SCHEME_CURRENT $SUB_SLEEP $WAKE_TIMERS 1
powercfg /SETDCVALUEINDEX SCHEME_CURRENT $SUB_SLEEP $WAKE_TIMERS 1
powercfg /SETACTIVE SCHEME_CURRENT
Write-Host "Wake timers enabled on AC and battery." -ForegroundColor Green

# --- 3. Create / replace the scheduled task ---------------------------------
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Replaced existing task '$TaskName'." -ForegroundColor Yellow
}

if (-not (Test-Path $Script)) {
    Write-Error "Action script not found: $Script"
    return
}

$action = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$Script`"" `
    -WorkingDirectory (Split-Path $Script)

$trigger = New-ScheduledTaskTrigger -Daily -At $Time

$settings = New-ScheduledTaskSettingsSet `
    -WakeToRun `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

# Run as the current user, not SYSTEM: the pipeline needs this profile for
# gcloud ADC + the Schwab token, and keepawake.lnk sits under user OneDrive.
#
# LogonType Interactive, NOT S4U. S4U calls LogonUserS4U, which requires a
# reachable domain controller for a domain/Entra account - off the corporate
# network that fails with 1311 ERROR_NO_LOGON_SERVERS and the task never runs.
# Interactive uses the existing logged-on session: no DC, no stored password.
#
# Trade-off: requires Bill to be LOGGED ON (locked/asleep is fine - the session
# survives sleep). It will NOT run after a reboot where nobody has logged in.
$me = "$env:USERDOMAIN\$env:USERNAME"
$principal = New-ScheduledTaskPrincipal -UserId $me `
                                        -LogonType Interactive `
                                        -RunLevel Highest
Write-Host "Task will run as: $me (Interactive)" -ForegroundColor Cyan

Register-ScheduledTask -TaskName  $TaskName `
                       -Action    $action `
                       -Trigger   $trigger `
                       -Settings  $settings `
                       -Principal $principal `
                       -Description "Wakes the machine daily at $Time, holds it awake, runs the portfolio morning pipeline." | Out-Null

Write-Host "Task '$TaskName' registered for $Time daily." -ForegroundColor Green

# --- 4. Verification --------------------------------------------------------
Write-Host "`n=== Verification ===" -ForegroundColor Cyan

$t = Get-ScheduledTask -TaskName $TaskName
[PSCustomObject]@{
    TaskName   = $t.TaskName
    State      = $t.State
    RunAs      = $t.Principal.UserId
    LogonType  = $t.Principal.LogonType
    WakeToRun  = $t.Settings.WakeToRun
    Action     = "$($t.Actions[0].Execute) $($t.Actions[0].Arguments)"
    NextRun    = (Get-ScheduledTaskInfo -TaskName $TaskName).NextRunTime
} | Format-List

# Firing the task runs morning_auto.bat --live, so it is OPT-IN only.
# Registering the task should never trigger a live pipeline as a side effect.
if ($RunNow) {
    Write-Host "--- -RunNow: launching the task once (LIVE pipeline) ---" -ForegroundColor Yellow
    Start-Sleep -Seconds 5
    Start-ScheduledTask -TaskName $TaskName
    Write-Host "Started. Watch: Get-Content .\logs\wake_and_run.log -Tail 20 -Wait"
} else {
    Write-Host "Not fired. To test the chain without a live pipeline run:" -ForegroundColor Cyan
    Write-Host "  .\wake_and_run.ps1 -SkipPipeline" -ForegroundColor Cyan
    Write-Host "To fire the real thing: .\setup_wake_timer.ps1 -RunNow" -ForegroundColor Cyan
}

Write-Host "--- Active power scheme, wake timer setting ---"
powercfg /QUERY SCHEME_CURRENT $SUB_SLEEP $WAKE_TIMERS

Write-Host "--- Armed wake timers (empty until the machine sleeps) ---"
powercfg /waketimers

Write-Host "`nDone. Test it: sleep the machine tonight and check Task Scheduler" -ForegroundColor Green
Write-Host "history, or run: Get-ScheduledTaskInfo -TaskName $TaskName" -ForegroundColor Green
