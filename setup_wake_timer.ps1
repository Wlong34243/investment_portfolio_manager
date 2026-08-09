<#
=============================================================================
 setup_wake_timer.ps1

 Purpose : Create a weekday Windows scheduled task that wakes the machine from
           sleep/hibernate, and enable the wake-timer power settings it
           depends on (both AC and battery). The task's action is
           wake_and_run.ps1, which holds the awake lock, launches keepawake,
           and runs the morning pipeline (morning_auto.bat -> pm morning --live).

 Inputs  : -Time  (default "06:00")  -TaskName (default "DailyWake")
           -Script (default wake_and_run.ps1 beside this file)
           -Daily (switch: Sat/Sun too; default is Mon-Fri only)
           -Unattended (RECOMMENDED): run whether logged on or not. Prompts
             once for password. On Microsoft-account-linked PCs, use the
             Microsoft account email + MSA password (not DOMAIN\user, not PIN).
           -RunNow: fire once after registering (LIVE pipeline)

 Outputs : Registered scheduled task + modified active power scheme.
 Deps    : Windows 10/11, PowerShell 5.1+, MUST run elevated (Administrator).
 Usage   : Right-click Start > Terminal (Admin), then:
             Set-ExecutionPolicy -Scope Process Bypass -Force
             C:\Dev\Investment_Portfolio\setup_wake_timer.ps1 -Unattended

 Note    : Pipeline needs YOUR profile (gcloud ADC, Schwab token) - never SYSTEM.
           Machine must be powered on or sleeping at 6am - full shutdown cannot
           run anything. ASCII-ONLY FILE, keep the BOM.
=============================================================================
#>

[CmdletBinding()]
param(
    [string]$Time     = "06:00",
    [string]$TaskName = "DailyWake",
    [string]$Script   = "",   # set below; $PSScriptRoot is empty in -File param defaults
    [switch]$Daily,       # include Sat/Sun; default is Mon-Fri weekdays only
    [switch]$Unattended,  # Password logon: runs signed-out (recommended)
    [switch]$RunNow       # opt-in: fire the task once after registering (LIVE)
)

$ErrorActionPreference = 'Stop'

# $PSScriptRoot is reliable in the body; empty during param-default eval under -File.
if (-not $Script) {
    $Script = Join-Path $PSScriptRoot "wake_and_run.ps1"
}

# --- 0. Elevation check -----------------------------------------------------
$isAdmin = ([Security.Principal.WindowsPrincipal] `
            [Security.Principal.WindowsIdentity]::GetCurrent()
           ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "FAILED: Must run as Administrator. Re-launch Terminal via 'Run as administrator'." -ForegroundColor Red
    return
}

# --- 1. Report which sleep states this machine actually supports -------------
Write-Host "`n=== Sleep states available (powercfg /a) ===" -ForegroundColor Cyan
powercfg /a

# --- 2. Enable wake timers on AC and DC -------------------------------------
$SUB_SLEEP   = '238c9fa8-0aad-41ed-83f4-97be242c8f20'
$WAKE_TIMERS = 'bd3b718a-0680-4d9d-8ab2-e1d2b4ac806d'   # 0=Disable 1=Enable 2=Important only

powercfg -attributes $SUB_SLEEP $WAKE_TIMERS -ATTRIB_HIDE | Out-Null
powercfg /SETACVALUEINDEX SCHEME_CURRENT $SUB_SLEEP $WAKE_TIMERS 1
powercfg /SETDCVALUEINDEX SCHEME_CURRENT $SUB_SLEEP $WAKE_TIMERS 1
powercfg /SETACTIVE SCHEME_CURRENT
Write-Host "Wake timers enabled on AC and battery." -ForegroundColor Green

# --- 3. Create / replace the scheduled task ---------------------------------
# setup_wake_timer.ps1 v3: MSA-linked accounts must use email + MSA password.

if (-not (Test-Path $Script)) {
    Write-Host "FAILED: Action script not found: $Script" -ForegroundColor Red
    return
}

Write-Host "setup_wake_timer.ps1 v3 — Unattended=$Unattended" -ForegroundColor DarkGray

$action = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$Script`"" `
    -WorkingDirectory (Split-Path $Script)

if ($Daily) {
    $trigger = New-ScheduledTaskTrigger -Daily -At $Time
    $scheduleLabel = "daily"
} else {
    $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek `
        Monday,Tuesday,Wednesday,Thursday,Friday -At $Time
    $scheduleLabel = "weekdays (Mon-Fri)"
}

$settings = New-ScheduledTaskSettingsSet `
    -WakeToRun `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

$me = "$env:USERDOMAIN\$env:USERNAME"

# Detect linked Microsoft account (common on Win11 "Sign in with Microsoft").
$msaEmail = $null
$msaGroup = whoami /groups /fo csv | ConvertFrom-Csv |
    Where-Object { $_.'Group Name' -like 'MicrosoftAccount\*' } |
    Select-Object -First 1
if ($msaGroup) {
    $msaEmail = ($msaGroup.'Group Name' -split '\\', 2)[1]
}

$taskUser = $me
$logonLabel = $null

if ($Unattended) {
    $taskUser = if ($msaEmail) { $msaEmail } else { $me }

    Write-Host ""
    Write-Host "UNATTENDED mode: task will run even if you are signed out." -ForegroundColor Cyan
    if ($msaEmail) {
        Write-Host "This PC account is linked to Microsoft account: $msaEmail" -ForegroundColor Cyan
        Write-Host "Enter that Microsoft account PASSWORD (not PIN, not DOMAIN\user)." -ForegroundColor Cyan
    } else {
        Write-Host "Enter the Windows password for $taskUser (account password, NOT the PIN)." -ForegroundColor Cyan
    }

    $cred = Get-Credential -UserName $taskUser -Message "Password for unattended DailyWake as $taskUser"
    if (-not $cred) {
        Write-Host "FAILED: credential prompt cancelled. No task registered." -ForegroundColor Red
        return
    }
    $plain = $cred.GetNetworkCredential().Password
    if (-not $plain) {
        Write-Host "FAILED: empty password. Use the Microsoft/account password, not the PIN." -ForegroundColor Red
        return
    }

    $desc = "UNATTENDED: wakes $scheduleLabel at $Time, runs portfolio morning pipeline (works signed-out)."
    $logonLabel = "Password (unattended)"
    $registered = $false

    try {
        Register-ScheduledTask `
            -TaskName    $TaskName `
            -Action      $action `
            -Trigger     $trigger `
            -Settings    $settings `
            -User        $cred.UserName `
            -Password    $plain `
            -RunLevel    Highest `
            -Description $desc `
            -Force -ErrorAction Stop | Out-Null
        $registered = $true
    } catch {
        Write-Host ("Password register failed as '{0}': {1}" -f $cred.UserName, $_.Exception.Message) -ForegroundColor Yellow

        if ($msaEmail -and $cred.UserName -notlike 'MicrosoftAccount\*') {
            $altUser = "MicrosoftAccount\$msaEmail"
            Write-Host "Retrying as $altUser ..." -ForegroundColor Yellow
            try {
                Register-ScheduledTask `
                    -TaskName    $TaskName `
                    -Action      $action `
                    -Trigger     $trigger `
                    -Settings    $settings `
                    -User        $altUser `
                    -Password    $plain `
                    -RunLevel    Highest `
                    -Description $desc `
                    -Force -ErrorAction Stop | Out-Null
                $registered = $true
                $taskUser = $altUser
            } catch {
                Write-Host ("Retry failed: {0}" -f $_.Exception.Message) -ForegroundColor Yellow
            }
        }
    }

    if (-not $registered) {
        Write-Host ""
        Write-Host "Unattended Password logon did not work." -ForegroundColor Red
        Write-Host "Falling back to Interactive (stay logged in overnight: lock/sleep OK, do not sign out)." -ForegroundColor Yellow
        $principal = New-ScheduledTaskPrincipal -UserId $me `
                                                -LogonType Interactive `
                                                -RunLevel Highest
        try {
            Register-ScheduledTask `
                -TaskName    $TaskName `
                -Action      $action `
                -Trigger     $trigger `
                -Settings    $settings `
                -Principal   $principal `
                -Description "Interactive FALLBACK: wakes $scheduleLabel at $Time (requires logged-on session)." `
                -Force -ErrorAction Stop | Out-Null
            $logonLabel = "Interactive (fallback — stay logged in overnight)"
            $taskUser = $me
            $registered = $true
        } catch {
            Write-Host ("FAILED fallback: {0}" -f $_.Exception.Message) -ForegroundColor Red
            return
        }
    }
} else {
    Write-Host ""
    Write-Host "WARNING: Interactive mode. If you are signed out at $Time, the task SKIPS." -ForegroundColor Yellow
    Write-Host "For 'done before I arrive', re-run with: .\setup_wake_timer.ps1 -Unattended" -ForegroundColor Yellow

    $principal = New-ScheduledTaskPrincipal -UserId $me `
                                            -LogonType Interactive `
                                            -RunLevel Highest
    $logonLabel = "Interactive (session required)"
    try {
        Register-ScheduledTask `
            -TaskName    $TaskName `
            -Action      $action `
            -Trigger     $trigger `
            -Settings    $settings `
            -Principal   $principal `
            -Description "Interactive: wakes $scheduleLabel at $Time, runs portfolio morning pipeline." `
            -Force -ErrorAction Stop | Out-Null
    } catch {
        Write-Host ("FAILED: {0}" -f $_.Exception.Message) -ForegroundColor Red
        return
    }
}

$tCheck = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $tCheck) {
    Write-Host "FAILED: task '$TaskName' is not present after registration." -ForegroundColor Red
    return
}

Write-Host "Task '$TaskName' registered for $Time $scheduleLabel ($logonLabel)." -ForegroundColor Green
Write-Host "Task will run as: $taskUser ($logonLabel)  LogonType=$($tCheck.Principal.LogonType)" -ForegroundColor Cyan

# --- 4. Verification --------------------------------------------------------
Write-Host "`n=== Verification ===" -ForegroundColor Cyan

$t = Get-ScheduledTask -TaskName $TaskName
$trig = $t.Triggers[0]
$days = if ($trig.DaysOfWeek) { $trig.DaysOfWeek.ToString() } else { "Daily" }
[PSCustomObject]@{
    TaskName   = $t.TaskName
    State      = $t.State
    RunAs      = $t.Principal.UserId
    LogonType  = $t.Principal.LogonType
    WakeToRun  = $t.Settings.WakeToRun
    Schedule   = $days
    StartAt    = $trig.StartBoundary
    Action     = "$($t.Actions[0].Execute) $($t.Actions[0].Arguments)"
    NextRun    = (Get-ScheduledTaskInfo -TaskName $TaskName).NextRunTime
} | Format-List

if ($RunNow) {
    Write-Host "--- -RunNow: launching the task once (LIVE pipeline) ---" -ForegroundColor Yellow
    Start-Sleep -Seconds 5
    Start-ScheduledTask -TaskName $TaskName
    Write-Host "Started. Watch: Get-Content .\logs\wake_and_run.log -Tail 20 -Wait"
} else {
    Write-Host "Not fired. To test without a live pipeline:" -ForegroundColor Cyan
    Write-Host "  .\wake_and_run.ps1 -SkipPipeline" -ForegroundColor Cyan
}

Write-Host "--- Active power scheme, wake timer setting ---"
powercfg /QUERY SCHEME_CURRENT $SUB_SLEEP $WAKE_TIMERS

Write-Host "--- Armed wake timers (empty until the machine sleeps) ---"
powercfg /waketimers

Write-Host "`nOvernight habit for 'done when I arrive':" -ForegroundColor Green
Write-Host "  - Leave the PC powered on (sleep/lock OK). Do NOT shut down." -ForegroundColor Green
Write-Host "  - Password logon: sign-out OK. Interactive: stay logged in." -ForegroundColor Green
Write-Host "Check: Get-ScheduledTaskInfo -TaskName $TaskName" -ForegroundColor Green
