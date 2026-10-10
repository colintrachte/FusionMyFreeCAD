# FusionMyFreeCAD 1.3.2

This release adds a safer sketch-mirroring workflow. **Mirror + Constraints** preserves compatible
endpoint attachments to unchanged border geometry, fixing the common case where mirrored dividers
look connected but leave a profile open. It sits beside FreeCAD's original **Mirror**, with a
different label, size, and icon so both workflows remain obvious and immediately accessible. The
original Mirror remains the choice when persistent live symmetry links are wanted.

The Sketcher Constraints panel now also exposes distinct **Coincident** and **Point on Object**
buttons with their verified native icons. Use Point on Object to attach a line endpoint to the
middle of another line, arc, curve, or axis.

Mirror + Constraints is intentionally conservative: unsupported relations are reported for review,
and solver-rejected copies are removed. It was validated headlessly against FreeCAD 1.1.3 with the
3×5-card-box pattern: six mirrored dividers retained all twelve boundary constraints without solver
conflicts.

## Install or update

Download `FusionMyFreeCAD-1.3.2.zip` and `FusionMyFreeCAD-1.3.2.zip.sha256` from this release. Replace the entire existing `Mod/FusionMyFreeCAD` folder; do not merge it with an older version.

See the [installation guide](https://github.com/colintrachte/FusionMyFreeCAD/blob/v1.3.2/docs/INSTALL-FREECAD-ADDON.md) and [full changelog](https://github.com/colintrachte/FusionMyFreeCAD/blob/v1.3.2/CHANGELOG.md).
