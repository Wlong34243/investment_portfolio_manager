<#
=============================================================================
 wake_and_run.ps1

 Purpose : Action target for the DailyWake scheduled task. Holds the machine
           awake, launches the keepawake shortcut, runs the morning pipeline,
           then releases everything so the machine can sleep again.

           A -WakeToRun task wakes into UNATTENDED SLEEP; Windows returns to
           sleep once the action exits. This script owns an explicit
           SetThreadExecutionState lock for the full duration of the pipeline
           so the machine cannot doze off mid-run, independent of whether the
           keepawake utility launched successfully.

 Inputs  : -KeepAwakeLnk       path to keepawake shortcut
           -Pipeline           batch file to run during the awake window
           -TimeoutMinutes     hard cap on the pipeline (default 45)
           -LeaveAwakeRunning  switch: don't kill keepawake when done
 Outputs : logs\wake_and_run.log (rolling), plus whatever the pipeline writes.
           Exit 0 = pipeline succeeded. Non-zero = see log.
 Deps    : Windows 10/11, PowerShell 5.1+, morning_auto.bat in same folder.
 Note    : Runs as Bill's user (Interactive logon), NOT SYSTEM - the pipeline
           needs the user profile for gcloud ADC and the Schwab token.
           ASCII-ONLY FILE. PowerShell 5.1 reads BOM-less .ps1 as CP1252,
           where a UTF-8 em dash decodes to a smart quote and silently
           breaks string parsing. Keep it ASCII; keep the BOM.
=============================================================================
#>

[CmdletBinding()]
param(
    [string]$KeepAwakeLnk    = "C:\OneDrive-Personal\OneDrive\Desktop\keepawake.lnk",
    [string]$Pipeline        = (Join-Path $PSScriptRoot "morning_auto.bat"),
    [int]   $TimeoutMinutes  = 45,
    [switch]$LeaveAwakeRunning,
    [switch]$SkipPipeline      # diagnostics: test lock + shortcut, no live run
)

Set-Location $PSScriptRoot
$logDir = Join-Path $PSScriptRoot "logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
$LOG = Join-Path $logDir "wake_and_run.log"

# Rotate at ~1 MB, keep one prior generation (mirrors morning_auto.bat)
if ((Test-Path $LOG) -and ((Get-Item $LOG).Length -gt 1MB)) {
    $prev = "$LOG.1"
    if (Test-Path $prev) { Remove-Item $prev -Force }
    Rename-Item $LOG "wake_and_run.log.1"
}

function Log($msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg
    Write-Host $line   # console first, so a log failure never loses the message

    # A manual run and the scheduled run can overlap and collide on this file.
    # Add-Content opens exclusively and throws; open with FileShare::ReadWrite
    # and retry briefly instead of dying mid-script.
    for ($i = 0; $i -lt 10; $i++) {
        try {
            $fs = [System.IO.File]::Open($LOG,
                    [System.IO.FileMode]::Append,
                    [System.IO.FileAccess]::Write,
                    [System.IO.FileShare]::ReadWrite)
            $sw = New-Object System.IO.StreamWriter($fs)
            $sw.WriteLine($line)
            $sw.Flush(); $sw.Close(); $fs.Close()
            return
        } catch {
            Start-Sleep -Milliseconds 100
        }
    }
    Write-Host "  (WARN: log locked after 10 tries; console only)"
}

Log "===== wake_and_run start ====="

# --- 1. Take the awake lock FIRST -------------------------------------------
# Do this before anything that can fail, so a bad shortcut path can't leave
# the machine free to sleep mid-pipeline.
Add-Type -Namespace Win32 -Name Power -MemberDefinition @'
[DllImport("kernel32.dll", SetLastError = true)]
public static extern uint SetThreadExecutionState(uint esFlags);
'@

$ES_CONTINUOUS        = [uint32]'0x80000000'
$ES_SYSTEM_REQUIRED   = [uint32]'0x00000001'
$ES_AWAYMODE_REQUIRED = [uint32]'0x00000040'

# Away mode is unsupported on many Modern Standby machines; fall back cleanly.
$r = [Win32.Power]::SetThreadExecutionState($ES_CONTINUOUS -bor $ES_SYSTEM_REQUIRED -bor $ES_AWAYMODE_REQUIRED)
if ($r -eq 0) {
    Log "Away mode rejected (normal on Modern Standby). Retrying without it."
    $r = [Win32.Power]::SetThreadExecutionState($ES_CONTINUOUS -bor $ES_SYSTEM_REQUIRED)
}
if ($r -eq 0) {
    Log "WARN: SetThreadExecutionState failed. Machine may sleep mid-run."
} else {
    Log "Awake lock acquired."
}

$keepAwakeProc = $null
$exitCode      = 1

try {
    # --- 2. Resolve the shortcut and launch its real target -----------------
    # Task Scheduler cannot execute a .lnk, and neither can Start-Process
    # reliably in a non-interactive session. Resolve to the actual binary.
    if (Test-Path $KeepAwakeLnk) {
        try {
            $sc     = (New-Object -ComObject WScript.Shell).CreateShortcut($KeepAwakeLnk)
            $target  = $sc.TargetPath
            $lnkArgs = $sc.Arguments   # NOT $args - that's a PS automatic variable
            $wd      = if ($sc.WorkingDirectory) { $sc.WorkingDirectory } else { Split-Path $target }
            Log "Shortcut resolves to: '$target' args='$lnkArgs'"

            if (-not (Test-Path $target)) {
                Log "WARN: shortcut target does not exist. Skipping keepawake launch."
            } else {
                $spArgs = @{ FilePath = $target; PassThru = $true; WindowStyle = 'Hidden' }
                if ($lnkArgs) { $spArgs.ArgumentList     = $lnkArgs }
                if ($wd)      { $spArgs.WorkingDirectory = $wd      }
                $keepAwakeProc = Start-Process @spArgs
                Log "keepawake launched (PID $($keepAwakeProc.Id))."
            }
        } catch {
            Log "WARN: could not resolve/launch shortcut: $($_.Exception.Message)"
            Log "Continuing - the awake lock above is the real guarantee."
        }
    } else {
        # Most likely cause: OneDrive cloud-only placeholder not hydrated,
        # or the path changed. Non-fatal.
        Log "WARN: keepawake shortcut not found at '$KeepAwakeLnk'."
    }

    # --- 3. Run the pipeline, with a hard timeout ---------------------------
    if ($SkipPipeline) {
        Log "SkipPipeline set - holding awake 10s instead of running pipeline."
        Start-Sleep -Seconds 10
        $exitCode = 0
    }
    elseif (-not (Test-Path $Pipeline)) {
        Log "FAIL: pipeline not found at '$Pipeline'."
        $exitCode = 2
    } else {
        Log "Running pipeline: $Pipeline (timeout ${TimeoutMinutes}m)"
        $p = Start-Process -FilePath $env:ComSpec `
                           -ArgumentList '/c', "`"$Pipeline`"" `
                           -WorkingDirectory $PSScriptRoot `
                           -WindowStyle Hidden -PassThru

        if ($p.WaitForExit($TimeoutMinutes * 60 * 1000)) {
            $exitCode = $p.ExitCode
            if ($exitCode -eq 0) { Log "Pipeline completed OK." }
            else { Log "FAIL: pipeline exited $exitCode. See logs\morning_auto.log." }
        } else {
            # A hung pipeline would otherwise hold the machine awake all day.
            Log "FAIL: pipeline exceeded ${TimeoutMinutes}m. Killing PID $($p.Id)."
            try { $p.Kill() } catch { Log "Could not kill pipeline: $($_.Exception.Message)" }
            $exitCode = 3
        }
    }
}
finally {
    # --- 4. Always release, even on error -----------------------------------
    if ($keepAwakeProc -and -not $LeaveAwakeRunning) {
        try {
            if (-not $keepAwakeProc.HasExited) {
                # Only ever kill the PID we started - never a pre-existing one.
                Stop-Process -Id $keepAwakeProc.Id -Force -ErrorAction Stop
                Log "keepawake stopped (PID $($keepAwakeProc.Id))."
            }
        } catch { Log "WARN: could not stop keepawake: $($_.Exception.Message)" }
    } elseif ($keepAwakeProc) {
        Log "keepawake left running per -LeaveAwakeRunning."
    }

    [Win32.Power]::SetThreadExecutionState($ES_CONTINUOUS) | Out-Null
    Log "Awake lock released. Machine free to sleep."
    Log "===== wake_and_run done (exit $exitCode) ====="
}

exit $exitCode
