[CmdletBinding()]
param(
    [string]$FreeCADUserDir = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Resolve-FreeCADUserDirectory {
    param([string]$Requested)
    if ($Requested) {
        return [System.IO.Path]::GetFullPath($Requested)
    }
    $base = Join-Path $env:APPDATA "FreeCAD"
    $preferred = Join-Path $base "v1-1"
    if (Test-Path -LiteralPath $preferred) {
        return $preferred
    }
    if (Test-Path -LiteralPath $base) {
        $profiles = Get-ChildItem -LiteralPath $base -Directory -ErrorAction SilentlyContinue |
            Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName "FusionMyFreeCAD-install-state.json") } |
            Sort-Object LastWriteTime -Descending
        if ($profiles.Count -gt 0) {
            return $profiles[0].FullName
        }
    }
    throw "No FusionMyFreeCAD installation state was found."
}

function Assert-FreeCADClosed {
    $running = Get-Process -Name "FreeCAD", "FreeCADCmd" -ErrorAction SilentlyContinue
    if ($running) {
        throw "FreeCAD is running. Close FreeCAD completely, then run the uninstaller again."
    }
}

function Preserve-Current {
    param([string]$Path, [string]$Destination)
    if (Test-Path -LiteralPath $Path) {
        New-Item -ItemType Directory -Path (Split-Path -Parent $Destination) -Force | Out-Null
        Move-Item -LiteralPath $Path -Destination $Destination
    }
}

$FreeCADUserDir = Resolve-FreeCADUserDirectory -Requested $FreeCADUserDir
Assert-FreeCADClosed

$statePath = Join-Path $FreeCADUserDir "FusionMyFreeCAD-install-state.json"
if (-not (Test-Path -LiteralPath $statePath -PathType Leaf)) {
    throw "Installation state is missing: $statePath"
}

$state = Get-Content -Raw -LiteralPath $statePath | ConvertFrom-Json
$resolvedStateDir = [System.IO.Path]::GetFullPath([string]$state.UserDir)
if ($resolvedStateDir -ne [System.IO.Path]::GetFullPath($FreeCADUserDir)) {
    throw "The installation state belongs to a different FreeCAD profile: $resolvedStateDir"
}

$backupRoot = [string]$state.BackupRoot
if (-not (Test-Path -LiteralPath $backupRoot -PathType Container)) {
    throw "The backup needed for rollback is missing: $backupRoot"
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$removedRoot = Join-Path $backupRoot "RemovedOnUninstall-$timestamp"
$modDir = Join-Path $FreeCADUserDir "Mod"
$macroDir = Join-Path $FreeCADUserDir "Macro"
$ribbonDir = Join-Path $FreeCADUserDir "RibbonUI_Data"
$userCfg = Join-Path $FreeCADUserDir "user.cfg"

foreach ($entry in $state.Addons) {
    $target = Join-Path $modDir ([string]$entry.Name)
    Preserve-Current -Path $target -Destination (Join-Path $removedRoot ("Mod\" + [string]$entry.Name))
    if ($entry.HadExisting -and (Test-Path -LiteralPath ([string]$entry.BackupPath))) {
        Move-Item -LiteralPath ([string]$entry.BackupPath) -Destination $target
    }
}

Preserve-Current -Path $ribbonDir -Destination (Join-Path $removedRoot "RibbonUI_Data")
if ($state.RibbonHadExisting -and (Test-Path -LiteralPath (Join-Path $backupRoot "RibbonUI_Data"))) {
    Move-Item -LiteralPath (Join-Path $backupRoot "RibbonUI_Data") -Destination $ribbonDir
}

$macroTarget = Join-Path $macroDir "AuditFusionProfile.FCMacro"
Preserve-Current -Path $macroTarget -Destination (Join-Path $removedRoot "Macro\AuditFusionProfile.FCMacro")
if ($state.MacroHadExisting -and (Test-Path -LiteralPath (Join-Path $backupRoot "Macro\AuditFusionProfile.FCMacro"))) {
    Move-Item -LiteralPath (Join-Path $backupRoot "Macro\AuditFusionProfile.FCMacro") -Destination $macroTarget
}

if ($state.LegacyPrototypeHadExisting -and (Test-Path -LiteralPath (Join-Path $backupRoot "Mod\prototype"))) {
    Move-Item -LiteralPath (Join-Path $backupRoot "Mod\prototype") -Destination (Join-Path $modDir "prototype")
}

Preserve-Current -Path $userCfg -Destination (Join-Path $removedRoot "Config\user.cfg")
if ($state.UserCfgHadExisting -and (Test-Path -LiteralPath (Join-Path $backupRoot "Config\user.cfg"))) {
    Copy-Item -LiteralPath (Join-Path $backupRoot "Config\user.cfg") -Destination $userCfg
}

Move-Item -LiteralPath $statePath -Destination (Join-Path $removedRoot "FusionMyFreeCAD-install-state.json")

Write-Host ""
Write-Host "FusionMyFreeCAD was removed and the previous FreeCAD state was restored." -ForegroundColor Green
Write-Host "The removed installation remains recoverable at: $removedRoot"
