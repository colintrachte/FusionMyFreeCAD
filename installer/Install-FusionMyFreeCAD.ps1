[CmdletBinding()]
param(
    [string]$FreeCADUserDir = "",
    [string]$ReferenceSource = ""
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
    if (Test-Path -LiteralPath (Join-Path $preferred "user.cfg")) {
        return $preferred
    }

    if (Test-Path -LiteralPath $base) {
        $profiles = Get-ChildItem -LiteralPath $base -Directory -ErrorAction SilentlyContinue |
            Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName "user.cfg") } |
            Sort-Object LastWriteTime -Descending
        if ($profiles.Count -gt 0) {
            return $profiles[0].FullName
        }
        if (Test-Path -LiteralPath (Join-Path $base "user.cfg")) {
            return $base
        }
    }

    throw "No FreeCAD user profile was found. Start FreeCAD once, close it, and run this installer again."
}

function Assert-FreeCADClosed {
    $running = Get-Process -Name "FreeCAD", "FreeCADCmd" -ErrorAction SilentlyContinue
    if ($running) {
        throw "FreeCAD is running. Close FreeCAD completely, then run the installer again."
    }
}

function Assert-SourceDirectory {
    param([string]$Path, [string]$RequiredFile)
    if (-not (Test-Path -LiteralPath (Join-Path $Path $RequiredFile))) {
        throw "Required installer source is missing: $Path ($RequiredFile)"
    }
}

function Move-Aside {
    param([string]$Path, [string]$BackupPath)
    if (-not (Test-Path -LiteralPath $Path)) {
        return $false
    }
    $backupParent = Split-Path -Parent $BackupPath
    New-Item -ItemType Directory -Path $backupParent -Force | Out-Null
    Move-Item -LiteralPath $Path -Destination $BackupPath
    return $true
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$assetRoot = Join-Path $PSScriptRoot "assets"
if (-not $ReferenceSource) {
    $ReferenceSource = Join-Path (Split-Path -Parent $projectRoot) "FreeCAD UI Study"
}
$ReferenceSource = [System.IO.Path]::GetFullPath($ReferenceSource)
$FreeCADUserDir = Resolve-FreeCADUserDirectory -Requested $FreeCADUserDir

Assert-FreeCADClosed

$statePath = Join-Path $FreeCADUserDir "FusionMyFreeCAD-install-state.json"
if (Test-Path -LiteralPath $statePath) {
    throw "FusionMyFreeCAD is already installed according to $statePath. Run UNINSTALL.cmd before reinstalling."
}

$sources = @(
    [ordered]@{ Name = "FreeCAD-Ribbon"; Path = Join-Path $ReferenceSource "FreeCAD-Ribbon-main"; Required = "InitGui.py" },
    [ordered]@{ Name = "SearchBar"; Path = Join-Path $ReferenceSource "SearchBar-main"; Required = "InitGui.py" },
    [ordered]@{ Name = "SaveAndRestore"; Path = Join-Path $ReferenceSource "SaveAndRestore-main"; Required = "InitGui.py" },
    [ordered]@{ Name = "FusionMyFreeCAD"; Path = Join-Path $assetRoot "FusionMyFreeCAD"; Required = "InitGui.py" }
)

foreach ($source in $sources) {
    Assert-SourceDirectory -Path $source.Path -RequiredFile $source.Required
}

$ribbonAsset = Join-Path $assetRoot "RibbonStructure.json"
$macroSource = Join-Path $projectRoot "prototype\AuditFusionProfile.FCMacro"
foreach ($file in @($ribbonAsset, $macroSource)) {
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) {
        throw "Required installer asset is missing: $file"
    }
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupRoot = Join-Path $FreeCADUserDir "FusionMyFreeCAD-Backups\$timestamp"
$modDir = Join-Path $FreeCADUserDir "Mod"
$macroDir = Join-Path $FreeCADUserDir "Macro"
$ribbonDir = Join-Path $FreeCADUserDir "RibbonUI_Data"
New-Item -ItemType Directory -Path $backupRoot, $modDir, $macroDir -Force | Out-Null

$state = [ordered]@{
    SchemaVersion = 1
    InstalledAt = (Get-Date).ToString("o")
    UserDir = $FreeCADUserDir
    BackupRoot = $backupRoot
    Addons = @()
    RibbonHadExisting = $false
    MacroHadExisting = $false
    LegacyPrototypeHadExisting = $false
    UserCfgHadExisting = $false
}

$installedTargets = [System.Collections.Generic.List[string]]::new()

try {
    $userCfg = Join-Path $FreeCADUserDir "user.cfg"
    if (Test-Path -LiteralPath $userCfg -PathType Leaf) {
        $userCfgBackup = Join-Path $backupRoot "Config\user.cfg"
        New-Item -ItemType Directory -Path (Split-Path -Parent $userCfgBackup) -Force | Out-Null
        Copy-Item -LiteralPath $userCfg -Destination $userCfgBackup
        $state.UserCfgHadExisting = $true
    }

    $legacyPrototype = Join-Path $modDir "prototype"
    $legacyBackup = Join-Path $backupRoot "Mod\prototype"
    $state.LegacyPrototypeHadExisting = Move-Aside -Path $legacyPrototype -BackupPath $legacyBackup

    foreach ($source in $sources) {
        $target = Join-Path $modDir $source.Name
        $backup = Join-Path $backupRoot ("Mod\" + $source.Name)
        $hadExisting = Move-Aside -Path $target -BackupPath $backup
        $state.Addons += [ordered]@{
            Name = $source.Name
            HadExisting = $hadExisting
            BackupPath = $backup
        }
        $installedTargets.Add($target)
        Copy-Item -LiteralPath $source.Path -Destination $target -Recurse
    }

    $ribbonBackup = Join-Path $backupRoot "RibbonUI_Data"
    $state.RibbonHadExisting = Move-Aside -Path $ribbonDir -BackupPath $ribbonBackup
    New-Item -ItemType Directory -Path $ribbonDir -Force | Out-Null
    $installedTargets.Add($ribbonDir)
    Copy-Item -LiteralPath $ribbonAsset -Destination (Join-Path $ribbonDir "RibbonStructure.json")

    $macroTarget = Join-Path $macroDir "AuditFusionProfile.FCMacro"
    $macroBackup = Join-Path $backupRoot "Macro\AuditFusionProfile.FCMacro"
    $state.MacroHadExisting = Move-Aside -Path $macroTarget -BackupPath $macroBackup
    $installedTargets.Add($macroTarget)
    Copy-Item -LiteralPath $macroSource -Destination $macroTarget

    $state.RibbonSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $ribbonAsset).Hash
    $state | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $statePath -Encoding UTF8
}
catch {
    $failedRoot = Join-Path $backupRoot "FailedInstall"
    New-Item -ItemType Directory -Path $failedRoot -Force | Out-Null

    foreach ($target in $installedTargets) {
        if (Test-Path -LiteralPath $target) {
            $failedTarget = Join-Path $failedRoot ([System.IO.Path]::GetFileName($target))
            Move-Item -LiteralPath $target -Destination $failedTarget -Force
        }
    }

    foreach ($entry in $state.Addons) {
        if ($entry.HadExisting -and (Test-Path -LiteralPath $entry.BackupPath)) {
            Move-Item -LiteralPath $entry.BackupPath -Destination (Join-Path $modDir $entry.Name)
        }
    }
    if ($state.RibbonHadExisting -and (Test-Path -LiteralPath (Join-Path $backupRoot "RibbonUI_Data"))) {
        Move-Item -LiteralPath (Join-Path $backupRoot "RibbonUI_Data") -Destination $ribbonDir
    }
    if ($state.MacroHadExisting -and (Test-Path -LiteralPath (Join-Path $backupRoot "Macro\AuditFusionProfile.FCMacro"))) {
        Move-Item -LiteralPath (Join-Path $backupRoot "Macro\AuditFusionProfile.FCMacro") -Destination (Join-Path $macroDir "AuditFusionProfile.FCMacro")
    }
    if ($state.LegacyPrototypeHadExisting -and (Test-Path -LiteralPath (Join-Path $backupRoot "Mod\prototype"))) {
        Move-Item -LiteralPath (Join-Path $backupRoot "Mod\prototype") -Destination (Join-Path $modDir "prototype")
    }
    throw
}

Write-Host ""
Write-Host "FusionMyFreeCAD installed successfully." -ForegroundColor Green
Write-Host "Profile: $FreeCADUserDir"
Write-Host "Backup:  $backupRoot"
Write-Host ""
Write-Host "Start FreeCAD normally. The Ribbon, S search, Revit navigation, and Fusion shortcuts configure themselves."
Write-Host "If you want to undo everything, close FreeCAD and double-click UNINSTALL.cmd."
