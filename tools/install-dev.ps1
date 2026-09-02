<#
.SYNOPSIS
    Build FusionMyFreeCAD and install it into a FreeCAD Mod directory.

.DESCRIPTION
    Builds a fresh release archive (unless -NoBuild), removes any existing
    <ModDir>\FusionMyFreeCAD, then extracts the archive there so the add-on lands
    at <ModDir>\FusionMyFreeCAD (never one level too deep). Restart FreeCAD after.

    Resolving the Mod directory, in order:
      1. -ModDir on the command line (also saved for next time).
      2. The path saved in .install-dev.local.json (repo root, git-ignored).
      3. Autodetected FreeCAD Mod directories under %APPDATA% / %LOCALAPPDATA% /
         the home directory. One match is used directly; several are listed for
         you to pick; the choice is saved.

    Nothing about the location is hardcoded.

.PARAMETER ModDir
    FreeCAD's Mod directory, e.g. "$env:APPDATA\FreeCAD\Mod". Created if missing.
    Saved to the config file so later runs need no arguments.

.PARAMETER NoBuild
    Install the newest existing dist\FusionMyFreeCAD-*.zip without rebuilding.

.PARAMETER List
    Show the saved config and every autodetected candidate, then exit.

.PARAMETER Reset
    Forget the saved Mod directory.

.EXAMPLE
    .\tools\install-dev.ps1
    # first run: pick from the detected list; later runs: reuse the saved choice

.EXAMPLE
    .\tools\install-dev.ps1 -ModDir "$env:APPDATA\FreeCAD\Mod"
#>
[CmdletBinding()]
param(
    [string]$ModDir,
    [switch]$NoBuild,
    [switch]$List,
    [switch]$Reset
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$configPath = Join-Path $repo '.install-dev.local.json'

function Get-SavedModDir {
    if (-not (Test-Path $configPath)) { return $null }
    try { return (Get-Content $configPath -Raw | ConvertFrom-Json).modDir }
    catch { return $null }
}

function Save-ModDir([string]$path) {
    [pscustomobject]@{ modDir = $path } | ConvertTo-Json | Set-Content $configPath -Encoding UTF8
    Write-Host "Saved to $configPath (git-ignored)" -ForegroundColor DarkGray
}

function Get-Candidates {
    $bases = @()
    if ($env:APPDATA)      { $bases += (Join-Path $env:APPDATA 'FreeCAD') }
    if ($env:LOCALAPPDATA) { $bases += (Join-Path $env:LOCALAPPDATA 'FreeCAD') }
    $bases += (Join-Path $HOME '.local/share/FreeCAD')
    $bases += (Join-Path $HOME '.FreeCAD')

    $paths = [System.Collections.Generic.List[string]]::new()
    foreach ($b in $bases) {
        if (-not (Test-Path $b)) { continue }
        $paths.Add((Join-Path $b 'Mod'))
        Get-ChildItem $b -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match '^v?\d+([._-]\d+)*$' } |
            ForEach-Object { $paths.Add((Join-Path $_.FullName 'Mod')) }
    }

    $seen = @{}
    $rows = foreach ($p in $paths) {
        $key = $p.ToLowerInvariant()
        if ($seen.ContainsKey($key)) { continue }
        $seen[$key] = $true
        [pscustomobject]@{
            Path     = $p
            Exists   = Test-Path $p
            HasAddon = Test-Path (Join-Path $p 'FusionMyFreeCAD/InitGui.py')
            Parented = Test-Path (Split-Path $p -Parent)
        }
    }
    $rows | Sort-Object `
        @{ Expression = { -[int]$_.HasAddon } },
        @{ Expression = { -[int]$_.Exists } },
        @{ Expression = { -[int]$_.Parented } }
}

function Format-Tag($row) {
    if ($row.HasAddon) { return '[has FusionMyFreeCAD]' }
    if ($row.Exists)   { return '[exists]' }
    if ($row.Parented) { return '[would be created]' }
    return '[parent missing]'
}

if ($Reset) {
    if (Test-Path $configPath) { Remove-Item $configPath; Write-Host "Removed $configPath" -ForegroundColor Green }
    else { Write-Host "No saved config." }
    return
}

if ($List) {
    $saved = Get-SavedModDir
    Write-Host ("Saved: {0}" -f ($(if ($saved) { $saved } else { '(none)' })))
    Write-Host "Detected candidates:"
    $i = 0
    foreach ($row in Get-Candidates) {
        $i++
        Write-Host ("  [{0}] {1}  {2}" -f $i, $row.Path, (Format-Tag $row))
    }
    if ($i -eq 0) { Write-Host "  (none)" }
    return
}

# --- resolve the Mod directory -------------------------------------------------
if (-not $ModDir) { $ModDir = Get-SavedModDir }

if (-not $ModDir) {
    $cands = @(Get-Candidates)
    if ($cands.Count -eq 0) {
        throw @"
No FreeCAD Mod directory found automatically. Get it from FreeCAD's Python console:
    import os; print(os.path.join(App.getUserAppDataDir(), "Mod"))
then re-run:  .\tools\install-dev.ps1 -ModDir "<that path>"
"@
    }
    if ($cands.Count -eq 1) {
        $ModDir = $cands[0].Path
        Write-Host "Using the only detected Mod directory: $ModDir" -ForegroundColor Cyan
    }
    else {
        Write-Host "Multiple FreeCAD Mod directories detected:" -ForegroundColor Cyan
        for ($i = 0; $i -lt $cands.Count; $i++) {
            Write-Host ("  [{0}] {1}  {2}" -f ($i + 1), $cands[$i].Path, (Format-Tag $cands[$i]))
        }
        try {
            $answer = Read-Host "Pick a number, or paste a full path"
        }
        catch {
            throw "This shell cannot prompt. Re-run with -ModDir set to one of the paths above."
        }
        if ($answer -match '^\d+$' -and [int]$answer -ge 1 -and [int]$answer -le $cands.Count) {
            $ModDir = $cands[[int]$answer - 1].Path
        }
        elseif ($answer) {
            $ModDir = $answer
        }
        else {
            throw "Nothing selected."
        }
    }
}

$ModDir = [System.Environment]::ExpandEnvironmentVariables($ModDir)
if ((Get-SavedModDir) -ne $ModDir) { Save-ModDir $ModDir }

# --- build -------------------------------------------------------------------
if (-not $NoBuild) {
    Write-Host "Building the release archive..." -ForegroundColor Cyan
    & python (Join-Path $repo 'tools/build_addon_package.py')
    if ($LASTEXITCODE -ne 0) { throw "build_addon_package.py failed" }
}

$zip = Get-ChildItem (Join-Path $repo 'dist') -Filter 'FusionMyFreeCAD-*.zip' -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $zip) { throw "No dist\FusionMyFreeCAD-*.zip found. Build first (drop -NoBuild)." }

# --- install ---------------------------------------------------------------
New-Item -ItemType Directory -Force -Path $ModDir | Out-Null
$target = Join-Path $ModDir 'FusionMyFreeCAD'

if (Test-Path $target) {
    Write-Host "Removing old $target" -ForegroundColor DarkGray
    Remove-Item -Recurse -Force $target
}

Write-Host "Extracting $($zip.Name) into $ModDir" -ForegroundColor Cyan
Expand-Archive -Path $zip.FullName -DestinationPath $ModDir -Force

if (-not (Test-Path (Join-Path $target 'InitGui.py'))) {
    throw "Install looks wrong: $target\InitGui.py is missing."
}
Write-Host "Installed FusionMyFreeCAD to $target" -ForegroundColor Green
Write-Host "Restart FreeCAD to load it." -ForegroundColor Green
