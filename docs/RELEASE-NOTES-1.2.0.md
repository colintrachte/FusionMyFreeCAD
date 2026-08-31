FusionMyFreeCAD 1.2.0 makes the ribbon complete, directly customizable, and safer to install or
remove.

Highlights:

- Every panel dropdown now exposes its complete command inventory, including tools not pinned to
  the ribbon face.
- Visible icons can be reordered at any time with click-hold-drag; no arrangement mode is required.
- Personalization survives restarts and layout updates, while **Reset this panel** restores only the
  selected panel.
- The release is a self-contained cross-platform FreeCAD add-on with bundled Ribbon and SearchBar
  runtimes and no external Python dependencies.
- New **Verify UI**, **Reapply UI**, **Restore UI**, immutable baseline recovery, preferences, and a
  standalone recovery macro make installation and removal recoverable.
- All 153 required command icons are curated from FreeCAD's official source and checked by content
  hash.

Upgrade by replacing the entire existing `Mod/FusionMyFreeCAD` directory with the folder from the
new archive. Do not merge files from older versions. Existing add-on-based panel arrangements are
reconciled with the new layout.

Download both `FusionMyFreeCAD-1.2.0.zip` and `FusionMyFreeCAD-1.2.0.zip.sha256`. See the
[installation guide](https://github.com/colintrachte/FusionMyFreeCAD/blob/v1.2.0/docs/INSTALL-FREECAD-ADDON.md)
and [full changelog](https://github.com/colintrachte/FusionMyFreeCAD/blob/v1.2.0/CHANGELOG.md).
