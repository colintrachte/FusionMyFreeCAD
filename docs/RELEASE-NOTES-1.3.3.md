# FusionMyFreeCAD 1.3.3

**1.3.3 withdraws 1.3.2.** On FreeCAD 1.1.3, version 1.3.2 could intermittently freeze and then
crash with an "Access violation" while the Sketcher ribbon was being built — typically on the first
launch after updating, before any of the new commands were used. It did not always reproduce on a
later restart. 1.3.3 restores the 1.3.1 Sketcher ribbon exactly and is a safe update from either
1.3.1 or a 1.3.2 install.

## What changed

- Removed the 1.3.2 Sketcher ribbon additions: **Mirror + Constraints**, the swap of **Coincident**
  to `Sketcher_ConstrainCoincidentUnified`, and the new **Point on Object** button. **Mirror**
  (`Sketcher_Symmetry`) and point-to-point **Coincident** (`Sketcher_ConstrainCoincident`) are back
  as they were in 1.3.1.
- `fusion_sketch_tools.py` still ships and keeps its own tests, but nothing registers it or puts it
  on the ribbon. The constraint-aware mirror workflow returns in a later release after it has been
  verified against a running FreeCAD 1.1.3.

## Install or update

Download `FusionMyFreeCAD-1.3.3.zip` and `FusionMyFreeCAD-1.3.3.zip.sha256` from this release.
Replace the entire existing `Mod/FusionMyFreeCAD` folder; do not merge it with an older version.
Restart FreeCAD. No sketch or document data is affected.

See the [installation guide](https://github.com/colintrachte/FusionMyFreeCAD/blob/v1.3.3/docs/INSTALL-FREECAD-ADDON.md) and [full changelog](https://github.com/colintrachte/FusionMyFreeCAD/blob/v1.3.3/CHANGELOG.md).
