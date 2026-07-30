# Fusion-to-FreeCAD command map

## High-frequency sketch commands

| Fusion command | Fusion default | FreeCAD 1.1.1 command | FreeCAD documented default | Recommendation |
|---|---:|---|---:|---|
| Line | `L` | Sketcher Line | `G`, then `L` | Rebind to `L` |
| 2-Point Rectangle | `R` | Sketcher Rectangle | `G`, then `R` | Rebind to `R` |
| Center Diameter Circle | `C` | Sketcher Circle From Center | `G`, then `C` | Rebind to `C` |
| Sketch Dimension | `D` | Sketcher Dimension | `D` | Keep |
| Trim | `T` | Sketcher Trim Edge | command exists; verify local default | Rebind to `T` |
| Offset | `O` | Sketcher Offset | command exists; verify local default | Rebind to `O` |
| Project | `P` | Sketcher External Projection | command exists; verify local default | Rebind to `P` |
| Normal / Construction | `X` | Toggle Construction Geometry | command exists; verify local default | Rebind to `X` |
| Mirror | none in Autodesk's core shortcut list | Sketcher Mirror (internally/documented as Symmetry) | `Z`, then `S` | Pin to toolbar or `S` menu |
| Rectangular Pattern | none in core list | Move/Array Transform | varies / verify locally | Pin to toolbar or `S` menu |
| Circular Pattern | none in core list | Rotate/Polar Transform | varies / verify locally | Pin to toolbar or `S` menu |

FreeCAD's unified Dimension command was introduced in 1.0. It is context-sensitive and already uses `D`, making it one of the strongest direct workflow matches.

## High-frequency solid commands

| Fusion command/operation | Fusion default | FreeCAD 1.1.1 equivalent | Recommendation |
|---|---:|---|---|
| Extrude → Join | `E` | Part Design Pad | `E` |
| Extrude → Cut | `E`, then operation = Cut | Part Design Pocket | `Shift+E` |
| Extrude → New Body | `E`, then operation = New Body | New Body + Create Sketch + Pad | toolbar; no forced single key |
| Hole | `H` | Part Design Hole | `H` |
| Model Fillet | `F` | Part Design Fillet | Consider `F`; check sketch-filleting conflict |
| Mirror feature | no core default listed | Part Design Mirror | toolbar / `S` menu |
| Rectangular Pattern feature | no core default listed | Part Design Linear Pattern | toolbar / `S` menu |
| Circular Pattern feature | no core default listed | Part Design Polar Pattern | toolbar / `S` menu |
| New design | `Ctrl+N` | New Document | Keep `Ctrl+N` |
| New object/component | contextual | New Body | first toolbar button |
| Create Sketch | contextual toolbar | Create Sketch | second toolbar button |
| Measure | `I` | Measure / Quick Measure | Assign `I` if the desired command is exposed |

## Navigation

| Action | Fusion | FreeCAD Revit style |
|---|---|---|
| Select | left-click | left-click |
| Add to selection | `Ctrl`+left-click, context dependent | `Ctrl`+left-click |
| Zoom | mouse wheel | mouse wheel |
| Pan | middle-drag | middle-drag |
| Orbit | `Shift`+middle-drag | `Shift`+middle-drag |
| Orbit around point | `Shift`+middle-click/drag | behavior depends on rotation-center preference |
| Fit view | toolbar/navigation command | `V`, then `F` documented in FreeCAD's standard view scheme; keep toolbar accessible |
| Standard views | ViewCube | Navigation Cube |

Set the FreeCAD rotation-center mode to a cursor/scene-point option if orbit pivot behavior feels different. The button gestures are already an exact match.

## Semantic traps to avoid

### Part versus Part Design

Use **Part Design**, not the Part workbench, for the main Fusion-like workflow. Part Design supplies a Body and cumulative parametric features. The Part workbench is a separate constructive-solid-geometry workflow and will increase mode switching.

### Pad/Pocket versus Extrude/Cut

In Part Design:

- Pad adds a selected sketch to the active Body.
- Pocket subtracts a selected sketch from the active Body.

The Part workbench also has a generic **Extrude**, but using it for this goal would abandon the most Fusion-like Body/feature workflow.

### Sketch pattern versus feature pattern

Decide whether repetition belongs in the sketch or in 3D:

- repeat sketch curves with Move/Array or Rotate/Polar Transform;
- repeat an already-created Pad/Pocket/Hole with Part Design Linear/Polar Pattern.

Prefer feature patterns for repeated holes or pockets when practical. The feature tree stays clearer and edits resemble Fusion's feature-pattern workflow.

### Sketch Mirror versus Part Design Mirror

- Sketcher Mirror copies curves inside the active sketch and can add symmetry relationships.
- Part Design Mirror repeats one or more 3D features about a plane or planar face.

They should be adjacent but visually separated in any toolbar or pie menu.

## Shortcut design rationale

The proposed map is deliberately conservative:

- It preserves keys confirmed in Autodesk's current Fusion shortcut reference.
- It keeps FreeCAD's already-matching `D`.
- It assigns `E` to the most common additive case and uses `Shift+E` for the subtractive partner.
- It avoids inventing keys for commands Fusion normally exposes through toolbars or its `S` toolbox.
- It leaves common OS/document bindings unchanged.

This gives high transfer with few collisions and remains understandable if the setup must be rebuilt.

