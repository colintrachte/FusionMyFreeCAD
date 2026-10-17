# Install FMF as a FreeCAD add-on

FMF is packaged as a normal directory-based FreeCAD add-on. It requires FreeCAD 1.1.0
or newer and Python 3.11 or newer, as declared in `package.xml`.

## Install the packaged archive

1. Close FreeCAD.
2. Back up your FreeCAD user-data directory if it contains a profile you care about.
3. Download `FMF-1.9.0.zip` and its `.sha256` file from the
   [1.9.0 release](https://github.com/colintrachte/FusionMyFreeCAD/releases/tag/v1.9.0). The
   repository's 1.9.0 state is the first release published from the privacy-cleaned history.
4. Optionally verify the archive against the published SHA-256 checksum.
5. Open the archive and copy its top-level `FMF` folder into the `Mod` directory under
   your FreeCAD user-data directory.
6. Confirm the resulting layout is exactly:

   ```text
   <FreeCAD user data>/
     Mod/
       FMF/
         Init.py
         InitGui.py
         package.xml
         fmf_bootstrap.py
         Resources/
         bundled-addons/
   ```

7. Start FreeCAD and allow one complete startup. Restart FreeCAD once more if the Ribbon does not
   appear on the first launch.

Typical user-data locations are:

- Windows: `%APPDATA%\FreeCAD\`
- macOS: `~/Library/Preferences/FreeCAD/`
- Linux: `~/.local/share/FreeCAD/`

FreeCAD can show the authoritative location for your installation. Open **View → Panels → Python
console** and enter:

```python
App.getUserAppDataDir()
```

Use the returned directory and create its `Mod` subdirectory if it does not already exist.

Do not leave an extra archive-version folder in the path. For example,
`Mod/FMF/FMF/InitGui.py` is one level too deep and FreeCAD will not load it.

## Verify the installation

After startup:

1. Open Part Design, Part, Sketcher, or Surface.
2. Confirm the Fusion-style Ribbon panels appear.
3. In an **INSPECT** panel, choose **Verify FMF**.
4. Exercise command search and one harmless command such as **Fit All**.

For a focused Sketcher check, select two endpoints and click **Coincident**. The unified control
adds point-to-point Coincident for two endpoints and Point-on-Object when the second selection is
an edge.

**Verify FMF** reports each check as OK or FAILED, lists the detail behind any failure, and names the
next step to try. It also lists every keyboard shortcut FMF took from another command,
so nothing about the rebinding is hidden.

If a check fails, try **Reset FMF** in the same panel and restart FreeCAD. Reset rebuilds the
ribbon layout, clears all panel personalization, and rewrites the managed preferences and shortcuts
to the shipped defaults.

## Use and personalize the Ribbon

Every panel dropdown contains the panel's complete command inventory, including tools not pinned to
the ribbon face. Click a visible icon normally to run it. Click, hold, and drag beyond the normal
system drag threshold to reorder it within the panel; there is no separate arrangement mode. The
order is saved automatically.

Choose **Reset this panel** at the bottom of a panel dropdown to restore only that panel. Other
panels retain their order and pinned commands. Use **Reset FMF** only when you intend to reset the
whole FMF interface.

## Settings

**Edit -> Preferences -> FMF** exposes activation plus four behavior switches: start
workbench, Fusion navigation and navigation cube, Fusion keyboard shortcuts, and the optional
starter design (off by default).

Managed preferences are applied once per installed version, not at every launch, so a change you make
afterwards in FreeCAD's own preferences dialog is preserved. Use **Reset FMF** to return to the
shipped defaults deliberately.

The bundled FreeCAD-Ribbon and SearchBar code is already inside this add-on. Separate installations
are not required. If standalone copies are already installed, FMF reuses the active
copy to avoid duplicate Ribbon docks or search toolbars; disable those standalone copies first if
you want to test the exact bundled versions.

## Update

1. Close FreeCAD. Updating from an earlier FMF add-on does not require disabling FMF;
   saved panel arrangements are reconciled with the new layout.
2. Replace the entire `Mod/FMF` folder with the folder from the newer archive. Do not
   merge old and new files, because removed runtime files could otherwise remain installed.
3. Start FreeCAD and run **Verify FMF**.

Version 1.2.0 replaces the retired Windows installer with the normal cross-platform add-on archive.
If an older installer-based copy exists elsewhere, remove that obsolete copy after confirming the
active `Mod/FMF` folder is the release archive described above.

## Remove

1. While the add-on is still installed, choose **Disable FMF**. This switches to the
   corresponding stock workbench, restores managed preferences and shortcuts, and hides FMF's
   workbenches without deleting their saved layout or personalization. It also disconnects FMF's
   live callbacks and closes its Parameters dock.
2. Confirm the selector immediately shows the stock workbenches, then close FreeCAD.
3. Remove only the `Mod/FMF` directory.
4. Start FreeCAD and confirm the prior UI is active.

### If you already removed the add-on

Removing `Mod/FMF` before disabling takes **Disable FMF** with it and can
leave managed preferences in place. Recover with the standalone macro:

1. Copy `tools/RestoreFMF.FCMacro` from the release archive into your FreeCAD macro
   directory (**Macro -> Macros...** shows its location).
2. Run it from that dialog.
3. Restart FreeCAD.

It reads the same first-run baseline the add-on wrote, restores the previous layout and preferences,
and moves FMF's machine-local files into a timestamped `removed-` folder under
`FMF-Backups`. Nothing is deleted outright, and running it twice is safe.

## Install through Addon Manager after publication

Once FMF is published to FreeCAD's add-on catalog, open **Tools → Addon Manager**,
select **FMF**, choose **Install**, and restart FreeCAD. Until then, a maintainer can add
the repository URL and `main` branch under the Addon Manager's custom repositories preferences;
that method installs the repository package rather than the local release archive.

Installing or updating the UI does not validate CAD geometry, toolpaths, or manufacturing output.
