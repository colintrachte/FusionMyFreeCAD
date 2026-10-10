# FusionMyFreeCAD 1.3.0

This release makes sketch creation and extrusion behave more like Fusion while using FreeCAD's
native modeling engine. Closed regions formed by ordinary sketch geometry are selectable for
extrusion, **Validate Sketch** is directly available in Part Design, and Enter now confirms active
modeling tasks.

The Sketcher ribbon now responds to the available window width. **Symmetric** is a top-level button,
and as many as 29 useful commands move out of panel menus and onto the ribbon at wider 1450 px and
1750 px tiers. **Create Sketch** stays at the far left, remains available after finishing a sketch,
and now presents a framed view of the selectable origin planes before sketch editing begins.

The release also adds tested preparation tooling and an automated GitHub build that validates the
source, produces the add-on archive and checksum, and attaches them to the tagged release.

## Install or update

Download `FusionMyFreeCAD-1.3.0.zip` and `FusionMyFreeCAD-1.3.0.zip.sha256` from this release. Replace the entire existing `Mod/FusionMyFreeCAD` folder; do not merge it with an older version.

Close FreeCAD before replacing the folder, then restart it. Existing ribbon panel arrangements are
retained and reconciled with the 1.3.0 layout.

See the [installation guide](https://github.com/colintrachte/FusionMyFreeCAD/blob/v1.3.0/docs/INSTALL-FREECAD-ADDON.md) and [full changelog](https://github.com/colintrachte/FusionMyFreeCAD/blob/v1.3.0/CHANGELOG.md).
