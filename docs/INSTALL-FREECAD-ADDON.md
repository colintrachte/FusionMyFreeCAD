# Install FusionMyFreeCAD as a FreeCAD add-on

FusionMyFreeCAD is packaged as a normal directory-based FreeCAD add-on. It requires FreeCAD 1.1.0
or newer and Python 3.11 or newer, as declared in `package.xml`.

## Install the packaged archive

1. Close FreeCAD.
2. Back up your FreeCAD user-data directory if it contains a profile you care about.
3. Open `FusionMyFreeCAD-3.1.0.zip` and copy its top-level `FusionMyFreeCAD` folder into the `Mod`
   directory under your FreeCAD user-data directory.
4. Confirm the resulting layout is exactly:

   ```text
   <FreeCAD user data>/
     Mod/
       FusionMyFreeCAD/
         Init.py
         InitGui.py
         package.xml
         fusion_bootstrap.py
         Resources/
         bundled-addons/
   ```

5. Start FreeCAD and allow one complete startup. Restart FreeCAD once more if the Ribbon does not
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
`Mod/FusionMyFreeCAD/FusionMyFreeCAD/InitGui.py` is one level too deep and FreeCAD will not load it.

## Verify the installation

After startup:

1. Open Part Design, Part, Sketcher, or Surface.
2. Confirm the Fusion-style Ribbon panels appear.
3. In an **INSPECT** panel, choose **Verify UI**.
4. Exercise command search and one harmless command such as **Fit All**.

The bundled FreeCAD-Ribbon and SearchBar code is already inside this add-on. Separate installations
are not required. If standalone copies are already installed, FusionMyFreeCAD reuses the active
copy to avoid duplicate Ribbon docks or search toolbars; disable those standalone copies first if
you want to test the exact bundled versions.

## Update

1. In FreeCAD, choose **Restore UI** if the update notes request a clean UI reset.
2. Close FreeCAD.
3. Replace the entire `Mod/FusionMyFreeCAD` folder with the folder from the newer archive. Do not
   merge old and new files, because removed runtime files could otherwise remain installed.
4. Start FreeCAD and run **Verify UI**.

## Remove

1. While the add-on is still installed, choose **Restore UI** to restore the Ribbon layout and
   preferences saved before FusionMyFreeCAD was first applied.
2. Close FreeCAD.
3. Remove only the `Mod/FusionMyFreeCAD` directory.
4. Start FreeCAD and confirm the prior UI is active.

## Install through Addon Manager after publication

Once FusionMyFreeCAD is published to FreeCAD's add-on catalog, open **Tools → Addon Manager**,
select **FusionMyFreeCAD**, choose **Install**, and restart FreeCAD. Until then, a maintainer can add
the repository URL and `main` branch under the Addon Manager's custom repositories preferences;
that method installs the repository package rather than the local release archive.

Installing or updating the UI does not validate CAD geometry, toolpaths, or manufacturing output.
