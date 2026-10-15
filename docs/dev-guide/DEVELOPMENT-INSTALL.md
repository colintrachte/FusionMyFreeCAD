# Update an installed add-on from this repository

Use `tools/install-dev.ps1` to build the current checkout and replace the copy of
FMF in a local FreeCAD profile. This is the development deployment path; it does not
publish a release or change the repository.

## Before running it

- Run the command from the repository root in PowerShell.
- Close FreeCAD first. FreeCAD loads add-on Python modules into the running process, so replacing
  files underneath an open session does not reliably update the active code.
- Ensure `python` is on `PATH`. A normal update invokes `tools/build_addon_package.py` before
  installing.
- Commit, copy, or otherwise preserve any edits made directly inside the installed
  `Mod/FMF` directory. The script removes that entire directory before extracting the
  new build.

The script changes only the selected FreeCAD `Mod` directory and the git-ignored
`.install-dev.local.json` file used to remember that directory.

## First update

From the repository root:

```powershell
.\tools\install-dev.ps1
```

The script searches the usual FreeCAD user-data locations. If it finds several `Mod` directories,
choose the one used by the FreeCAD installation you want to update. Entries already containing
FMF are labelled `[has FMF]`.

To avoid ambiguity, pass the directory explicitly:

```powershell
.\tools\install-dev.ps1 -ModDir "$env:APPDATA\FreeCAD\v1-1\Mod"
```

FreeCAD can report the authoritative path for the active installation. In **View → Panels →
Python console**, run:

```python
import os

print(os.path.join(App.getUserAppDataDir(), "Mod"))
```

Then close FreeCAD and pass the printed path to `-ModDir`.

If PowerShell's local execution policy blocks the script, run it explicitly through PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\install-dev.ps1
```

## Later updates

The selected path is stored in `.install-dev.local.json`, which is excluded from Git. Later updates
normally need only:

```powershell
.\tools\install-dev.ps1
```

That command:

1. builds `dist/FMF-<version>.zip` from the current checkout;
2. removes `<ModDir>/FMF`;
3. extracts the newly built archive directly into `<ModDir>`;
4. checks that `<ModDir>/FMF/InitGui.py` exists.

Restart FreeCAD after the script reports a successful installation. Run **Verify FMF** from an
**INSPECT** panel. If the ribbon still reflects an older layout, run **Reset FMF** and
restart once more; Reset intentionally clears ribbon personalisation.

## Useful options

Inspect the saved path and every autodetected candidate without changing anything:

```powershell
.\tools\install-dev.ps1 -List
```

Forget the saved path:

```powershell
.\tools\install-dev.ps1 -Reset
```

Install the newest existing ZIP under `dist/` without rebuilding:

```powershell
.\tools\install-dev.ps1 -NoBuild
```

Use `-NoBuild` only after checking the ZIP's version and modification time. The script selects the
newest matching archive, which may be stale relative to the current source checkout.

## Roll back

To roll back the add-on code, close FreeCAD and replace `Mod/FMF` with the folder from
a known-good archive. `-NoBuild` is suitable only when that archive is already the newest matching
ZIP under `dist/`; the script has no option for selecting a particular ZIP. Keep only one installed
FMF directory.

**Disable FMF** serves a different purpose: it removes FMF's interface
changes, returns to the first-run baseline, and remains disabled across restarts. Do not use it
merely to switch between development builds.

