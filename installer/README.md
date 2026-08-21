# FreeCAD launcher and graphical installer

Double-click `D:\Git\FusionMyFreeCAD\FusionMyFreeCAD Setup.exe`. The application now opens on a
launcher that detects normal FreeCAD installations and common source-build outputs. Double-click a
detected build or select it and choose **Launch FreeCAD**. Use **Add Build…** to remember a
`FreeCAD.exe` in an unusual location; launcher choices are stored separately under the user's
application-data folder and do not modify a FreeCAD profile.

The **Install & Repair** tab retains the setup workflow. Close FreeCAD before installing, repairing,
upgrading, or restoring the UI.

The setup application detects whether the original release is already installed. Use **Upgrade to
3.0** for an existing installation, **Repair** to reapply managed files, **Verify** to inspect the
installed state, or **Restore Previous UI** to return to the state before the first installation.

The installer automatically:

- finds the FreeCAD 1.1 profile under `%APPDATA%\FreeCAD\v1-1`;
- creates a timestamped backup;
- replaces the earlier incorrectly copied `Mod\prototype` folder;
- installs FreeCAD-Ribbon, SearchBar, SaveAndRestore, and FusionMyFreeCAD;
- installs the complete v3 Ribbon layout with primary modeling, sketch, and surface buttons visible;
- configures Smart Dimension, centered rectangle, the navigation cube, and Fusion-like shortcuts;
- learns a separate FREQUENT command group for each supported workbench.

The launcher detects FreeCAD through Windows installed-app records, `PATH`, common application and
portable-program folders, Windows shortcuts (including pinned taskbar shortcuts), the neighboring
`D:\Git\FreeCAD` source workspace, and user-added executable paths. Source builds are launched with
their executable directory as the working directory so adjacent debug or locally built runtime files
can be found. Detection and launching are read-only; installation still targets the displayed
FreeCAD profile and never assumes that every detected executable is safe to modify.

After it says the operation succeeded, start FreeCAD normally. FreeCAD writes a runtime status
report after loading the add-on; reopening Setup shows whether FreeCAD loaded layout 3.0.

To undo the installation, use **Restore Previous UI** in Setup. Rollback restores the previous
addons, Ribbon data, macro, and `user.cfg`. Removed installer files are preserved inside the
timestamped backup rather than deleted.

The installer stops safely if FreeCAD is running or required payload files are missing. Existing
FusionMyFreeCAD installations are upgraded in place while retaining their original rollback point.
