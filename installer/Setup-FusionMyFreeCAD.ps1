[CmdletBinding()]
param(
    [ValidateSet("Install", "Repair", "Verify")]
    [string]$Action = "Install",
    [string]$FreeCADUserDir = "",
    [string]$SetupExecutable = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$PackageVersion = "3.1.0"

function Resolve-SetupExecutable {
    param([string]$Requested, [string]$ProjectRoot)
    if ($Requested) {
        $resolved = [System.IO.Path]::GetFullPath($Requested)
        if (Test-Path -LiteralPath $resolved -PathType Leaf) { return $resolved }
        throw "The requested graphical setup application is missing: $resolved"
    }
    $candidates = @(Get-ChildItem -LiteralPath $ProjectRoot -Filter "FusionMyFreeCAD Setup*.exe" -File -ErrorAction SilentlyContinue |
        Sort-Object { try { [version]$_.VersionInfo.FileVersion } catch { [version]"0.0.0.0" } } -Descending)
    if ($candidates.Count -gt 0) { return $candidates[0].FullName }
    throw "No graphical setup application was found in $ProjectRoot"
}

function Resolve-FreeCADUserDirectory {
    param([string]$Requested)
    if ($Requested) { return [System.IO.Path]::GetFullPath($Requested) }
    $base = Join-Path $env:APPDATA "FreeCAD"
    $preferred = Join-Path $base "v1-1"
    if (Test-Path -LiteralPath (Join-Path $preferred "user.cfg")) { return $preferred }
    if (Test-Path -LiteralPath $base) {
        $profiles = @(Get-ChildItem -LiteralPath $base -Directory -ErrorAction SilentlyContinue |
            Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName "user.cfg") } |
            Sort-Object LastWriteTime -Descending)
        if ($profiles.Count -gt 0) { return $profiles[0].FullName }
        if (Test-Path -LiteralPath (Join-Path $base "user.cfg")) { return $base }
    }
    throw "No FreeCAD profile was found. Start FreeCAD once, close it, and try again."
}

function Assert-FreeCADClosed {
    if (Get-Process -Name "FreeCAD", "FreeCADCmd" -ErrorAction SilentlyContinue) {
        throw "FreeCAD is running. Close it completely before installing or repairing the UI."
    }
}

function Move-Aside {
    param([string]$Path, [string]$Destination)
    if (-not (Test-Path -LiteralPath $Path)) { return $false }
    New-Item -ItemType Directory -Path (Split-Path -Parent $Destination) -Force | Out-Null
    Move-Item -LiteralPath $Path -Destination $Destination
    return $true
}

function Add-OrReplaceProperty {
    param([object]$Target, [string]$Name, [object]$Value)
    $Target | Add-Member -MemberType NoteProperty -Name $Name -Value $Value -Force
}

function Build-RibbonStructure {
    param([string]$BasePath, [string]$SpecPath, [string]$Destination)
    $mergeTool = $script:SetupExecutable
    if (-not (Test-Path -LiteralPath $mergeTool -PathType Leaf)) {
        throw "The graphical setup application is missing: $mergeTool"
    }
    $process = Start-Process -FilePath $mergeTool -ArgumentList @("--merge-ribbon", $BasePath, $SpecPath, $Destination) -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $Destination -PathType Leaf)) {
        throw "The case-sensitive ribbon layout merge failed."
    }
}

function Test-Installation {
    param([string]$Profile, [string]$ExpectedVersion)
    $checks = [System.Collections.Generic.List[object]]::new()
    foreach ($name in @("FreeCAD-Ribbon", "SearchBar", "FusionMyFreeCAD")) {
        $path = Join-Path $Profile ("Mod\" + $name + "\InitGui.py")
        $checks.Add([pscustomobject]@{ Name = "Addon: $name"; Passed = (Test-Path -LiteralPath $path -PathType Leaf); Path = $path })
    }
    $ribbonPath = Join-Path $Profile "RibbonUI_Data\RibbonStructure.json"
    $layoutPassed = $false
    $partOrder = @("Fusion Sketch Entry_newPanel", "Fusion Create_newPanel", "Fusion Modify_newPanel", "Fusion Construct_newPanel", "Fusion Frequent_newPanel", "Fusion Inspect_newPanel")
    $sketchOrder = @("Fusion Sketch Create_newPanel", "Fusion Sketch Modify_newPanel", "Fusion Sketch Constraints_newPanel", "Fusion Sketch Configure_newPanel", "Fusion Sketch Inspect_newPanel", "Fusion Sketch Insert_newPanel", "Fusion Sketch Select_newPanel", "Fusion Finish_newPanel")
    if (Test-Path -LiteralPath $ribbonPath -PathType Leaf) {
        $mergeTool = $script:SetupExecutable
        if (Test-Path -LiteralPath $mergeTool -PathType Leaf) {
            $verifyProcess = Start-Process -FilePath $mergeTool -ArgumentList @("--verify-ribbon", $ribbonPath) -WindowStyle Hidden -Wait -PassThru
            $layoutPassed = $verifyProcess.ExitCode -eq 0
        }
    }
    $checks.Add([pscustomobject]@{ Name = "Fusion-familiar panel order"; Passed = $layoutPassed; Path = $ribbonPath })
    $statePath = Join-Path $Profile "FusionMyFreeCAD-install-state.json"
    $statePassed = $false
    if (Test-Path -LiteralPath $statePath -PathType Leaf) {
        try { $statePassed = ((Get-Content -Raw -LiteralPath $statePath | ConvertFrom-Json).PackageVersion -eq $ExpectedVersion) } catch {}
    }
    $checks.Add([pscustomobject]@{ Name = "Installer state $ExpectedVersion"; Passed = $statePassed; Path = $statePath })
    return [pscustomobject]@{
        Status = $(if (@($checks | Where-Object { -not $_.Passed }).Count -eq 0) { "passed" } else { "failed" })
        CheckedAt = (Get-Date).ToString("o")
        PackageVersion = $ExpectedVersion
        Profile = $Profile
        PartDesignPanelOrder = $partOrder
        SketcherPanelOrder = $sketchOrder
        SurfacePanelOrder = @("Fusion Surface Create_newPanel", "Fusion Surface Modify_newPanel", "Fusion Surface Frequent_newPanel", "Fusion Surface Inspect_newPanel")
        PartPanelOrder = @("Fusion Part Create_newPanel", "Fusion Part Boolean_newPanel", "Fusion Part Split_newPanel", "Fusion Part Repair_newPanel", "Fusion Part Frequent_newPanel", "Fusion Part Inspect_newPanel")
        Checks = $checks.ToArray()
    }
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$SetupExecutable = Resolve-SetupExecutable -Requested $SetupExecutable -ProjectRoot $projectRoot
$assetRoot = Join-Path $PSScriptRoot "assets"
$FreeCADUserDir = Resolve-FreeCADUserDirectory -Requested $FreeCADUserDir
$statePath = Join-Path $FreeCADUserDir "FusionMyFreeCAD-install-state.json"
$reportPath = Join-Path $FreeCADUserDir "FusionMyFreeCAD-install-report.json"

if ($Action -eq "Verify") {
    $report = Test-Installation -Profile $FreeCADUserDir -ExpectedVersion $PackageVersion
    $report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $reportPath -Encoding UTF8
    $report | ConvertTo-Json -Depth 8
    if ($report.Status -ne "passed") { exit 2 }
    exit 0
}

Assert-FreeCADClosed

$sources = @(
    [ordered]@{ Name = "FreeCAD-Ribbon"; Path = Join-Path $projectRoot "bundled-addons\FreeCAD-Ribbon"; Required = "InitGui.py" },
    [ordered]@{ Name = "SearchBar"; Path = Join-Path $projectRoot "bundled-addons\SearchBar"; Required = "InitGui.py" },
    [ordered]@{ Name = "FusionMyFreeCAD"; Path = Join-Path $assetRoot "FusionMyFreeCAD"; Required = "InitGui.py" }
)
foreach ($source in $sources) {
    if (-not (Test-Path -LiteralPath (Join-Path $source.Path $source.Required) -PathType Leaf)) {
        throw "Installer payload is incomplete: $($source.Path)"
    }
}

$baseRibbon = Join-Path $assetRoot "RibbonStructure.json"
$layoutSpec = Join-Path $assetRoot "layout-v2.json"
$macroSource = Join-Path $projectRoot "prototype\AuditFusionProfile.FCMacro"
foreach ($required in @($baseRibbon, $layoutSpec, $macroSource)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Required installer asset is missing: $required" }
}

$existing = $null
if (Test-Path -LiteralPath $statePath -PathType Leaf) {
    $existing = Get-Content -Raw -LiteralPath $statePath | ConvertFrom-Json
    if ([System.IO.Path]::GetFullPath([string]$existing.UserDir) -ne [System.IO.Path]::GetFullPath($FreeCADUserDir)) {
        throw "The recorded installation belongs to a different FreeCAD profile."
    }
}
else {
    # A failed upgrade from versions before 3.0.7 could restore the add-ons but
    # accidentally leave the state file inside FailedOperation. Recover the
    # newest compatible record so the original rollback chain is preserved.
    $failedStates = @(Get-ChildItem -LiteralPath (Join-Path $FreeCADUserDir "FusionMyFreeCAD-Backups") -Filter "FusionMyFreeCAD-install-state.json" -File -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -like "*\FailedOperation\FusionMyFreeCAD-install-state.json" } |
        Sort-Object LastWriteTime -Descending)
    foreach ($failedState in $failedStates) {
        try {
            $candidate = Get-Content -Raw -LiteralPath $failedState.FullName | ConvertFrom-Json
            if ([System.IO.Path]::GetFullPath([string]$candidate.UserDir) -eq [System.IO.Path]::GetFullPath($FreeCADUserDir)) {
                $existing = $candidate
                Write-Output "RECOVERED_STATE|$($failedState.FullName)"
                break
            }
        }
        catch { continue }
    }
}
$isUpgrade = $null -ne $existing
if ($Action -eq "Repair" -and -not $isUpgrade) { throw "Nothing is installed to repair. Choose Install instead." }

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupRoot = if ($isUpgrade) { [string]$existing.BackupRoot } else { Join-Path $FreeCADUserDir "FusionMyFreeCAD-Backups\$timestamp" }
$operationRoot = if ($isUpgrade) { Join-Path $backupRoot "Upgrades\$timestamp" } else { $backupRoot }
$currentRoot = if ($isUpgrade) { Join-Path $operationRoot "BeforeUpgrade" } else { $backupRoot }
$modDir = Join-Path $FreeCADUserDir "Mod"
$macroDir = Join-Path $FreeCADUserDir "Macro"
$ribbonDir = Join-Path $FreeCADUserDir "RibbonUI_Data"
New-Item -ItemType Directory -Path $operationRoot, $modDir, $macroDir -Force | Out-Null
$stateBackup = Join-Path $currentRoot "FusionMyFreeCAD-install-state.json"
if ($isUpgrade) {
    New-Item -ItemType Directory -Path $currentRoot -Force | Out-Null
    $existing | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $stateBackup -Encoding UTF8
}

if ($isUpgrade) {
    $state = [ordered]@{
        SchemaVersion = 2
        PackageVersion = $PackageVersion
        LayoutVersion = $PackageVersion
        InstalledAt = [string]$existing.InstalledAt
        UpdatedAt = (Get-Date).ToString("o")
        UserDir = [string]$existing.UserDir
        BackupRoot = [string]$existing.BackupRoot
        Addons = @($existing.Addons)
        RibbonHadExisting = [bool]$existing.RibbonHadExisting
        MacroHadExisting = [bool]$existing.MacroHadExisting
        LegacyPrototypeHadExisting = [bool]$existing.LegacyPrototypeHadExisting
        UserCfgHadExisting = [bool]$existing.UserCfgHadExisting
        UpgradeHistory = @()
    }
    if ($existing.PSObject.Properties.Name -contains "UpgradeHistory") { $state.UpgradeHistory = @($existing.UpgradeHistory) }
    $state.UpgradeHistory += [ordered]@{ UpdatedAt = (Get-Date).ToString("o"); Snapshot = $currentRoot }
}
else {
    $state = [ordered]@{
        SchemaVersion = 2
        PackageVersion = $PackageVersion
        LayoutVersion = $PackageVersion
        InstalledAt = (Get-Date).ToString("o")
        UpdatedAt = (Get-Date).ToString("o")
        UserDir = $FreeCADUserDir
        BackupRoot = $backupRoot
        Addons = @()
        RibbonHadExisting = $false
        MacroHadExisting = $false
        LegacyPrototypeHadExisting = $false
        UserCfgHadExisting = $false
        UpgradeHistory = @()
    }
}

$installedTargets = [System.Collections.Generic.List[string]]::new()
$stagedTargets = [System.Collections.Generic.List[object]]::new()
try {
    if (-not $isUpgrade) {
        $userCfg = Join-Path $FreeCADUserDir "user.cfg"
        if (Test-Path -LiteralPath $userCfg -PathType Leaf) {
            $userCfgBackup = Join-Path $backupRoot "Config\user.cfg"
            New-Item -ItemType Directory -Path (Split-Path -Parent $userCfgBackup) -Force | Out-Null
            Copy-Item -LiteralPath $userCfg -Destination $userCfgBackup
            $state.UserCfgHadExisting = $true
        }
        $state.LegacyPrototypeHadExisting = Move-Aside -Path (Join-Path $modDir "prototype") -Destination (Join-Path $backupRoot "Mod\prototype")
    }

    foreach ($source in $sources) {
        $target = Join-Path $modDir $source.Name
        $backup = Join-Path $currentRoot ("Mod\" + $source.Name)
        $hadExisting = Move-Aside -Path $target -Destination $backup
        $stagedTargets.Add([pscustomobject]@{ Target = $target; Backup = $backup; HadExisting = $hadExisting })
        if (-not $isUpgrade) {
            $state.Addons += [ordered]@{ Name = $source.Name; HadExisting = $hadExisting; BackupPath = $backup }
        }
        Copy-Item -LiteralPath $source.Path -Destination $target -Recurse
        $installedTargets.Add($target)
    }

    $ribbonBackup = Join-Path $currentRoot "RibbonUI_Data"
    $ribbonHadExisting = Move-Aside -Path $ribbonDir -Destination $ribbonBackup
    $stagedTargets.Add([pscustomobject]@{ Target = $ribbonDir; Backup = $ribbonBackup; HadExisting = $ribbonHadExisting })
    if (-not $isUpgrade) { $state.RibbonHadExisting = $ribbonHadExisting }
    New-Item -ItemType Directory -Path $ribbonDir -Force | Out-Null
    $installedTargets.Add($ribbonDir)
    $null = Build-RibbonStructure -BasePath $baseRibbon -SpecPath $layoutSpec -Destination (Join-Path $ribbonDir "RibbonStructure.json")

    $macroTarget = Join-Path $macroDir "AuditFusionProfile.FCMacro"
    $macroBackup = Join-Path $currentRoot "Macro\AuditFusionProfile.FCMacro"
    $macroHadExisting = Move-Aside -Path $macroTarget -Destination $macroBackup
    $stagedTargets.Add([pscustomobject]@{ Target = $macroTarget; Backup = $macroBackup; HadExisting = $macroHadExisting })
    if (-not $isUpgrade) { $state.MacroHadExisting = $macroHadExisting }
    Copy-Item -LiteralPath $macroSource -Destination $macroTarget
    $installedTargets.Add($macroTarget)

    $state.RibbonSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $ribbonDir "RibbonStructure.json")).Hash
    $state | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $statePath -Encoding UTF8
    $installedTargets.Add($statePath)
    $report = Test-Installation -Profile $FreeCADUserDir -ExpectedVersion $PackageVersion
    $report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $reportPath -Encoding UTF8
    $installedTargets.Add($reportPath)
    if ($report.Status -ne "passed") { throw "Files were copied, but post-install verification failed." }
}
catch {
    $failedRoot = Join-Path $operationRoot "FailedOperation"
    New-Item -ItemType Directory -Path $failedRoot -Force | Out-Null
    foreach ($target in $installedTargets) {
        if (Test-Path -LiteralPath $target) {
            Move-Item -LiteralPath $target -Destination (Join-Path $failedRoot ([System.IO.Path]::GetFileName($target))) -Force
        }
    }
    foreach ($entry in $stagedTargets) {
        if ($entry.HadExisting -and (Test-Path -LiteralPath $entry.Backup)) {
            Move-Item -LiteralPath $entry.Backup -Destination $entry.Target
        }
    }
    if ($isUpgrade -and (Test-Path -LiteralPath $stateBackup -PathType Leaf)) {
        Copy-Item -LiteralPath $stateBackup -Destination $statePath -Force
    }
    throw
}

Write-Output "SUCCESS|$PackageVersion|$FreeCADUserDir|$backupRoot"
