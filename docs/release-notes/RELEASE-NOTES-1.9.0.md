# FMF 1.9.0

FMF 1.9.0 is the new clean release baseline. It includes the complete feature set developed since
1.4.0 and publishes it from privacy-cleaned repository history.

## Four FMF-owned workbenches

FMF Design, FMF Part, FMF Sketch, and FMF Surface provide separate Fusion-familiar alternatives to
their stock FreeCAD counterparts. Enabling FMF shows the FMF family and can hide the corresponding
stock workbenches; disabling it immediately restores the native choices without unregistering or
blanking the FreeCAD interface.

The ribbon remains customizable: sections resize with draggable dividers, overflow commands stay
available from each section title, visible commands can be reordered directly, and every workbench
has an adaptive **FREQUENT** section that respects manually pinned and excluded commands.

## Sketching and modelling

- The unified **Coincident** control chooses point-to-point Coincident or Point-on-Object from the
  current selection.
- **Mirror + Constraints** creates linked mirrored geometry, rejects unsafe partial results, and
  keeps multi-region profiles selectable and padable.
- Selectable sketch regions use stable spatial ordering, reducing downstream Pad breakage after
  ordinary dimension edits.
- **Repair References** detects broken face and edge references and repairs only cases it can match
  safely.
- Create Sketch, Pad, Pocket, export, native Mirror, and sketch-context transitions are protected
  by behavior-sensitive layout contracts.

## Reliability and troubleshooting

Startup diagnostics now record session health, vendor-load timing, UI snapshots, FMF-owned signal
connections, event filters, adaptive usage callbacks, pending work, and teardown failures. FMF does
not report activation as healthy until its ribbon is usable; a failed activation rolls back to the
native interface.

The repository and release workflows now reject personal machine paths, known private addresses,
private-key markers, common credential formats, incomplete metadata, invalid layouts, formatting
drift, test failures, and undefined names in the bundled Ribbon and SearchBar payloads.

## Install or update

Download `FMF-1.9.0.zip` and `FMF-1.9.0.zip.sha256` from this release. Replace the entire existing
`Mod/FMF` folder; do not merge it with an older version, then restart FreeCAD.

See the [installation guide](https://github.com/colintrachte/FusionMyFreeCAD/blob/v1.9.0/docs/user-guide/INSTALL-FREECAD-ADDON.md)
and [full changelog](https://github.com/colintrachte/FusionMyFreeCAD/blob/v1.9.0/CHANGELOG.md).
