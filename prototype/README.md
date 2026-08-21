# FusionMyFreeCAD prototype 1

> **Simpler path:** This manual procedure is retained for troubleshooting. For normal use, close
> FreeCAD and double-click `D:\Git\FusionMyFreeCAD\INSTALL.cmd`.

This is a reversible FreeCAD 1.1.3 UI prototype based on native Part Design and Sketcher commands.

It does **not** modify FreeCAD source, create new modeling feature types, write shortcuts, or edit `user.cfg`.

## Files

- `fusion-ribbon-freecad-1.1.3.json` — FreeCAD-Ribbon layout for Part Design and Sketcher.
- `freecad-1.1.3-command-manifest.json` — command identifiers checked against the official FreeCAD 1.1.3 source tag.
- `shortcut-proposals.json` — proposed Fusion-like bindings; this file is documentation, not an installer.
- `AuditFusionProfile.FCMacro` — read-only runtime check for registered commands and occupied shortcuts.
- `validate_prototype.py` — offline schema and command-reference validator.

## What the layout provides

### Part Design

- **START:** New Body, Create Sketch
- **CREATE:** large Extrude and Hole controls, plus a broader Create dropdown
- **MODIFY:** Fillet, Chamfer, Thickness, Draft, Boolean
- **CONSTRUCT:** datum plane, line, point, coordinate system
- **PATTERN:** Mirror, Rectangular, Circular, Multi-Transform
- **INSPECT:** Measure, Check Geometry, Fit All

The Extrude dropdown contains:

1. Pad — Fusion **Join** behavior
2. Pocket — Fusion **Cut** behavior
3. New Body — creates a body; it does not perform an extrusion by itself

This is intentionally not described as a unified parametric Extrude feature.

### Sketch edit mode

- a large **Finish Sketch** control;
- large Line, Rectangle, and Circle controls;
- broader Create and Modify dropdowns;
- Mirror, Rectangular Pattern, and Project / Include kept visible;
- Dimension and common constraints grouped together;
- Measure and Fit All retained under Inspect.

## Safe trial sequence

### 1. Use FreeCAD 1.1.3

The preset targets the stable 1.1.3 command set. Do not validate it against the downloaded `FreeCAD-main` tree: that archive identifies itself as 26.3.0-dev.

### 2. Back up the current profile

Close important documents. Install and use **SaveAndRestore** before enabling FreeCAD-Ribbon. Save the toolbar/layout state and separately copy FreeCAD's `user.cfg` while FreeCAD is closed.

The reference repositories under `D:\Git\FreeCAD UI Study` are source material; they are not installed by this prototype.

### 3. Install the UI addons through FreeCAD

Use **Tools > Addon Manager**:

1. Install SaveAndRestore first.
2. Install FreeCAD-Ribbon.
3. Install SearchBar if the `S` command search is wanted for the first test.
4. Restart FreeCAD when prompted.

SearchBar is optional. A SearchBar problem must not block testing the Ribbon or native shortcuts.

### 4. Run the read-only audit

In **Macro > Macros**, add or run `AuditFusionProfile.FCMacro`.

Review the Report view output:

- If any Ribbon command is missing, stop and do not import the preset.
- If a proposed shortcut reports a conflict, decide which command should keep the key.
- The macro loads Part Design and Sketcher so their commands register, then restores the previously active workbench when possible.
- The macro does not apply any shortcut or preference.

### 5. Import the Ribbon sections

In the FreeCAD-Ribbon design dialog, open the initial setup/import area. Use the same file for these imports, in this order:

1. Choose **Import dropdown buttons**.
2. Choose **Import custom panels**.
3. In the workbench importer, select **Part Design** and choose **Import workbench**.
4. Repeat the workbench import with **Sketcher** selected.

For every import, select:

`D:\Git\FusionMyFreeCAD\prototype\fusion-ribbon-freecad-1.1.3.json`

Apply the design, then reload the workbenches or restart FreeCAD if Ribbon requests it.

Do **not** use **Import layout** with this file. It is deliberately a sectioned preset rather than a copy of every Ribbon workbench. The workbench imports replace the Ribbon definitions for Part Design and Sketcher, and the custom-panel import replaces Ribbon's custom-panel dictionary. That is why the backup in step 2 is mandatory.

### 6. Apply only reviewed shortcuts

Use **Tools > Customize > Keyboard**. Apply the conflict-free subset from `shortcut-proposals.json` manually.

Suggested first tier:

| Key | Command | Meaning |
|---|---|---|
| `L` | Line | Fusion Line |
| `R` | 2-point rectangle | Fusion Rectangle |
| `C` | Center circle | Fusion Circle |
| `D` | Dimension | Already native in FreeCAD 1.1 |
| `E` | Pad | Extrude — Join |
| `Shift+E` | Pocket | Extrude — Cut |
| `H` | Hole | Hole |
| `T` | Trim | Trim |
| `O` | Offset | Offset |
| `P` | Projection | Project / Include |
| `X` | Construction geometry | Normal / Construction |
| `I` | Measure | Inspect |

SearchBar manages its own `S` key. Do not also assign `S` through the Keyboard page.

### 7. Set navigation and exercise the validation part

Set **Edit > Preferences > Display > Navigation > 3D Navigation** to **Revit** for wheel zoom, middle-button pan, and Shift+middle-button orbit.

Then build the mounting-plate test from the root setup guide:

1. New document, New Body, XY sketch.
2. Rectangle and dimensions.
3. Circle and dimensions; mirror or pattern the holes.
4. Finish Sketch; Extrude > Pad.
5. Add a top-face sketch; Extrude > Pocket.
6. Test Hole, Fillet, feature Mirror, Linear Pattern, and Polar Pattern.
7. Search for at least three commands with `S` if SearchBar is installed.

Record missing commands, disabled buttons in valid contexts, incorrect icons/text, and any Ribbon or SearchBar instability.

## Rollback

1. Close open documents or save them somewhere safe.
2. Use SaveAndRestore to restore the saved toolbar/layout state.
3. If needed, disable or uninstall FreeCAD-Ribbon through Addon Manager and restart.
4. Restore the copied `user.cfg` only while FreeCAD is closed.

Do not delete the active FreeCAD profile as a first-line rollback action.

## Offline validation

From this directory:

```powershell
python .\validate_prototype.py
```

Expected output:

```text
VALID: FreeCAD 1.1.3 prototype; 8 dropdowns, 11 panels, 47 verified commands
```

Offline validation proves JSON consistency and source-checked identifiers. It does not prove that FreeCAD-Ribbon renders the layout correctly or that CAD operations are correct.

## Deferred ideas

- A true Join/Cut/Intersect/New Body feature panel
- Smart PressPull for selected profiles and faces
- A bottom feature-history strip
- A marking menu
- Direct-face tools such as Offset Face, Replace Face, and Move Face

These are deferred until the configuration prototype has been tested. UniCAD's current source does not provide sufficient evidence to copy these features as-is.
