# FusionMyFreeCAD 1.3.1

A small fix release. The Sketcher ribbon's **Mirror Sketch** button used FreeCAD's older mirror
operation, which never links the mirrored copy back to the original geometry — so mirrored
elements could end up unconstrained with no warning. That button has been removed. **Mirror**
(the large button in the Sketch Modify panel) already does the right thing by default and remains
the way to mirror sketch geometry.

## Install or update

Download `FusionMyFreeCAD-1.3.1.zip` and `FusionMyFreeCAD-1.3.1.zip.sha256` from this release. Replace the entire existing `Mod/FusionMyFreeCAD` folder; do not merge it with an older version.

See the [installation guide](https://github.com/colintrachte/FusionMyFreeCAD/blob/v1.3.1/docs/INSTALL-FREECAD-ADDON.md) and [full changelog](https://github.com/colintrachte/FusionMyFreeCAD/blob/v1.3.1/CHANGELOG.md).
