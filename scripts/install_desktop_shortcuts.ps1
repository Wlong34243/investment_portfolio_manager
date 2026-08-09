#Requires -Version 5.1
<#
.SYNOPSIS
  Install desktop .lnk shortcuts for Portfolio Manager BAT launchers,
  with custom icons from assets\icons\.

.DESCRIPTION
  Mirrors the RE Property Manager pattern: .lnk files point at the repo
  .bat files and use IconLocation from assets\icons\*.ico.

  Safe to re-run. Replaces matching .bat wrappers on the desktop with .lnk
  shortcuts of the same display name.

.EXAMPLE
  .\scripts\install_desktop_shortcuts.ps1
#>
[CmdletBinding()]
param(
    [string]$DesktopPath = ""
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not $DesktopPath) {
    $OneDriveDesktop = Join-Path $env:USERPROFILE "OneDrive\Desktop"
    $LocalDesktop = [Environment]::GetFolderPath("Desktop")
    if (Test-Path $OneDriveDesktop) {
        $DesktopPath = $OneDriveDesktop
    } else {
        $DesktopPath = $LocalDesktop
    }
}

$Icons = Join-Path $RepoRoot "assets\icons"
if (-not (Test-Path $Icons)) {
    throw "Icons folder missing: $Icons"
}

$Shortcuts = @(
    @{
        Name   = "Portfolio Manager"
        Target = Join-Path $RepoRoot "Portfolio_Manager.bat"
        Icon   = Join-Path $Icons "icon_portfolio_manager.ico"
    },
    @{
        Name   = "Morning Sync"
        Target = Join-Path $RepoRoot "run_morning_sync.bat"
        Icon   = Join-Path $Icons "icon_morning_sync.ico"
    },
    @{
        Name   = "Portfolio AI Briefing"
        Target = Join-Path $RepoRoot "make_ai_briefing.bat"
        Icon   = Join-Path $Icons "icon_ai_briefing.ico"
    },
    @{
        Name   = "Idea Generator"
        Target = Join-Path $RepoRoot "run_idea_generator.bat"
        Icon   = Join-Path $Icons "icon_idea_generator.ico"
    }
)

$shell = New-Object -ComObject WScript.Shell

foreach ($item in $Shortcuts) {
    if (-not (Test-Path $item.Target)) {
        Write-Warning "Skip '$($item.Name)': target missing $($item.Target)"
        continue
    }
    if (-not (Test-Path $item.Icon)) {
        Write-Warning "Skip '$($item.Name)': icon missing $($item.Icon)"
        continue
    }

    $lnkPath = Join-Path $DesktopPath "$($item.Name).lnk"
    $batPath = Join-Path $DesktopPath "$($item.Name).bat"

    # Prefer .lnk over thin .bat wrappers that always show cmd.exe icon
    if (Test-Path $batPath) {
        Remove-Item -LiteralPath $batPath -Force
        Write-Host "Removed desktop wrapper: $batPath"
    }

    $sc = $shell.CreateShortcut($lnkPath)
    $sc.TargetPath       = $item.Target
    $sc.WorkingDirectory = $RepoRoot
    $sc.IconLocation     = "$($item.Icon),0"
    $sc.Description      = $item.Name
    $sc.Save()
    Write-Host "Installed: $lnkPath"
    Write-Host "  -> $($item.Target)"
    Write-Host "  icon $($item.Icon)"
}

Write-Host ""
Write-Host "Done. If icons look stale, right-click Desktop -> Refresh (or sign out/in)."
