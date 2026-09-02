<#
.SYNOPSIS
    Build FusionMyFreeCAD and install it into a FreeCAD Mod directory.

.DESCRIPTION
    Builds a fresh release archive (unless -NoBuild), removes any existing
    <ModDir>\FusionMyFreeCAD, then extracts the archive there so the add-on lands
    at <ModDir>\FusionMyFreeCAD (never one level too deep). Restart FreeCAD after.

    The Mod directory is NOT guessed. Get it from FreeCAD's Python console:
        import os; print(os.path.join(App.getUserAppDataDir(), "Mod"))

.PARAMETER ModDir
    FreeCAD's Mod directory, e.g. C:\Users\you\AppData\Roaming\FreeCAD\Mod
    Created if it does not exist.

.PARAMETER NoBuild
    Install the newest existing dist\FusionMyFreeCAD-*.zip without rebuilding.

.EXAMPLE
    .\tools\install-dev.ps1 -ModDir "$env:APPDATA\FreeCAD\Mod"
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ModDir,
    [switch]$NoBuild
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot

if (-not $NoBuild) {
    Write-Host "Building the release archive..." -ForegroundColor Cyan
    & python (Join-Path $repo 'tools\build_addon_package.py')
    if ($LASTEXITCODE -ne 0) { throw "build_addon_package.py failed" }
}

$zip = Get-ChildItem (Join-Path $repo 'dist') -Filter 'FusionMyFreeCAD-*.zip' |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $zip) { throw "No dist\FusionMyFreeCAD-*.zip found. Build first (drop -NoBuild)." }

New-Item -ItemType Directory -Force -Path $ModDir | Out-Null
$target = Join-Path $ModDir 'FusionMyFreeCAD'

if (Test-Path $target) {
    Write-Host "Removing old $target" -ForegroundColor DarkGray
    Remove-Item -Recurse -Force $target
}

Write-Host "Extracting $($zip.Name) into $ModDir" -ForegroundColor Cyan
Expand-Archive -Path $zip.FullName -DestinationPath $ModDir -Force

$initgui = Join-Path $target 'InitGui.py'
if (-not (Test-Path $initgui)) {
    throw "Install looks wrong: $initgui is missing."
}
Write-Host "Installed FusionMyFreeCAD to $target" -ForegroundColor Green
Write-Host "Restart FreeCAD to load it." -ForegroundColor Green
