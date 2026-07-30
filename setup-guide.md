# Setup guide

This procedure changes FreeCAD through its user interface only. It is intentionally reversible.

## 1. Establish the Fusion mouse model

In FreeCAD:

1. Open **Edit → Preferences** (`Ctrl+,` in 1.1).
2. Go to **Display → Navigation**.
3. Set **3D Navigation** to **Revit**.
4. Set **Orbit style** to **Turntable** as a predictable starting point.
5. Apply the changes.

You can also switch navigation style from the mouse/navigation control in the status bar or by right-clicking empty 3D space and choosing **Navigation styles**.

Why Revit, despite the name: FreeCAD documents it as wheel zoom, middle-button pan, and Shift+middle-button orbit. Autodesk documents those same inputs for Fusion. This is a direct behavioral match.

## 2. Make Part Design the normal home

Use **Part Design** for ordinary mechanical parts. Its Body contains cumulative additive and subtractive features, which is the closest FreeCAD equivalent to Fusion's parametric component workflow.

The normal new-part loop should become:

1. `Ctrl+N` — new document.
2. **New Body**.
3. **Create Sketch** and select a base plane or planar face.
4. Draw and dimension the profile.
5. Close the sketch.
6. **Pad** to add material, or **Pocket** to remove it.
7. Add another sketch or apply Mirror / Linear Pattern / Polar Pattern to an existing feature.

Important semantic difference: a FreeCAD Part Design Body is a single contiguous result built by cumulative features. It is the closest day-to-day analogue of a Fusion component/body workflow, but it is not identical to Fusion's component model.

## 3. Build one compact top toolbar

FreeCAD's **Tools → Customize → Toolbars** can create a toolbar containing commands from loaded workbenches. Load Part Design and enter Sketch edit mode at least once before opening Customize, because FreeCAD only exposes commands from workbenches loaded in the current session.

Create a toolbar named **Fusion Core** under the Part Design workbench. Put commands in this order:

| Group | Commands |
|---|---|
| Object start | New Body; Create Sketch |
| Sketch geometry | Line; Rectangle; Circle From Center |
| Sketch control | Dimension; Trim Edge; Offset; Toggle Construction Geometry; External Projection |
| Sketch repetition | Mirror; Move/Array Transform; Rotate/Polar Transform |
| Solid creation | Pad; Pocket; Hole |
| Feature repetition | Mirror; Linear Pattern; Polar Pattern |

The two Mirror entries are different commands. Rename is not necessary; their icons and active context distinguish them. If the toolbar becomes crowded, split it into **Fusion Sketch** and **Fusion Solid**, on adjacent rows.

Keep the Combo View or Tree View docked on the left. Hide panels that do not serve the core modeling loop using **View → Panels**. Leave the Tasks area available because FreeCAD uses it for active command parameters.

## 4. Apply the shortcut map

Open **Tools → Customize → Keyboard** in FreeCAD 1.1.1.

FreeCAD supports standalone shortcut keys. It will warn when a proposed shortcut is occupied. Load Part Design and Sketcher before assigning keys so their commands are listed.

Apply the Tier 1 bindings:

| Key | FreeCAD command | Fusion memory being preserved |
|---|---|---|
| `L` | Sketcher Line | Line |
| `R` | Sketcher Rectangle | 2-Point Rectangle |
| `C` | Sketcher Circle From Center | Center Diameter Circle |
| `D` | Sketcher Dimension | Sketch Dimension; already the FreeCAD default |
| `E` | Part Design Pad | Extrude; additive default |
| `Shift+E` | Part Design Pocket | Cutting Extrude |
| `H` | Part Design Hole | Hole |
| `T` | Sketcher Trim Edge | Trim |
| `O` | Sketcher Offset | Offset |
| `P` | Sketcher External Projection | Project |
| `X` | Sketcher Toggle Construction Geometry | Normal / Construction |
| `I` | Measure or Quick Measure, if assignable in this build | Measure |

Keep `Ctrl+N`, `Ctrl+O`, `Ctrl+S`, `Ctrl+Z`, `Ctrl+Y`, and `Delete`; FreeCAD and Fusion already agree on these common Windows bindings.

Do not force single-key bindings for sketch/feature Mirror and Pattern. Fusion does not publish universal defaults for those commands, so a pinned toolbar or an `S`-style menu transfers better than inventing new muscle memory.

### Why `E` maps to Pad

Most new material starts as an additive extrusion, making Pad the highest-value target for `E`. Pocket remains adjacent on the toolbar and receives `Shift+E`.

There is no exact native mapping for Fusion's Extrude operation selector:

- Fusion Extrude can select Join, Cut, Intersect, New Body, or New Component within one command.
- FreeCAD Part Design exposes Pad, Pocket, Boolean operations, and New Body as separate commands.

A context-sensitive macro could combine those actions, but that would be custom code requiring maintenance. It should be a later enhancement, not part of the dependable baseline.

## 5. Align the sketching behavior

FreeCAD 1.1's Sketcher is closer to Fusion than older FreeCAD tutorials imply:

- Line, rectangle, and circle tools offer on-view parameters.
- Rectangle has multiple creation modes.
- The `D` Dimension tool is context-sensitive.
- Auto constraints can infer coincident, horizontal, vertical, tangent, and other relations.
- Sketch Mirror can optionally retain symmetry constraints.
- Sketch copy/paste includes related constraints.

Recommended preferences:

1. Keep **Auto constraints** enabled.
2. Keep **Ask for value after creating a dimensional constraint** enabled.
3. Use the single **Dimension** tool instead of memorizing every dedicated distance/radius/angle constraint.
4. Keep on-view positional/dimensional input enabled if numerical entry during creation feels natural.
5. Use right-click or `Esc` to end a continuing sketch tool.

The FreeCAD `D` tool may propose different valid dimensions based on the selection. Watch its preview and use `M` to cycle alternatives where offered.

## 6. Align appearance without destabilizing the workflow

FreeCAD 1.1 includes a new Theme Editor and theme-token system. Begin with a built-in light or neutral theme and:

- use **Medium (24 px)** toolbar icons;
- keep the tree/Combo View left-docked;
- place core toolbars in one or two rows at the top;
- keep the status bar visible because FreeCAD 1.1 displays Sketcher input hints there;
- avoid visually dense toolbars unrelated to Part Design.

Fusion's most transferable visual structure is not its exact color palette; it is the left browser, top contextual commands, central canvas, ViewCube, and a visible feature history. FreeCAD can reproduce the first four closely. Its feature history remains vertical in the Body tree.

## 7. Optional `S` toolbox / marking-menu approximation

The community PieMenu addon is available through **Tools → Addon Manager** and is described by FreeCAD as a workflow acceleration tool. It is not part of FreeCAD core and is not supported by the core team.

If installed and confirmed compatible on the local 1.1.1 installation:

1. Bind its main menu to `S`.
2. Create a sketch-context pie containing Line, Rectangle, Circle, Dimension, Trim, Offset, Mirror, Move/Array, and Polar Transform.
3. Create a Part Design pie containing Create Sketch, Pad, Pocket, Hole, Fillet, Chamfer, Mirror, Linear Pattern, and Polar Pattern.

This best approximates both Fusion's `S` Model Toolbox and its right-click marking menu. Export or record its configuration once stable.

## 8. Validate the setup with one test part

Use a simple mounting plate as a repeatability test:

1. New document and New Body.
2. Create an XY-plane sketch.
3. `R` to make a plate outline.
4. `D` to dimension width and height.
5. `C` to make one mounting hole; `D` to dimension it and locate its center.
6. Sketch Mirror or Move/Array to create the other holes.
7. Close sketch and `E` to Pad.
8. Add a top-face sketch, create a slot or rectangle, close, then `Shift+E` to Pocket.
9. Select a feature and test Linear Pattern or Mirror.
10. Confirm wheel zoom, middle pan, and Shift+middle orbit behave identically in both applications.

If that loop can be completed without searching menus, the setup has achieved its purpose.

## 9. Preserve the configuration

Once satisfied:

- capture screenshots of the toolbar layout and Keyboard page;
- save a written list of bindings (the table above);
- back up FreeCAD's `user.cfg`;
- consider making a FreeCAD Preference Pack only after the configuration is proven.

Do not edit `user.cfg` while FreeCAD is running. The normal UI is safer for initial configuration.

