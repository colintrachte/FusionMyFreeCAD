# FreeCAD 1.1.1 configured for a Fusion-like workflow

Research date: 2026-07-30  
Target: FreeCAD 1.1.1, primarily Sketcher and Part Design

## Conclusion

FreeCAD 1.1.1 can be made close enough to Fusion for the high-frequency part-creation loop that most muscle memory transfers:

1. Use **Part Design** as the normal home workbench.
2. Select FreeCAD's **Revit navigation style**. It matches Fusion's mouse navigation:
   - wheel = zoom
   - middle-drag = pan
   - Shift+middle-drag = orbit
3. Put a small, ordered custom toolbar at the top:
   - New Body
   - Create Sketch / Close Sketch
   - Line
   - Rectangle
   - Circle
   - Dimension
   - Mirror
   - Move/Array Transform
   - Rotate/Polar Transform
   - Pad
   - Pocket
   - Hole
   - Part Design Mirror
   - Linear Pattern
   - Polar Pattern
4. Rebind only the commands for which Fusion has strong, memorable defaults: `L`, `R`, `C`, `D`, `E`, `H`, `T`, `O`, `P`, and `X`.
5. Treat **Pad** as Fusion's additive Extrude and **Pocket** as its cutting Extrude. FreeCAD does not have a single native Part Design command that chooses Join/Cut/New Body the way Fusion's Extrude dialog does.
6. Optionally use the community **PieMenu** addon as a substitute for Fusion's `S` Model Toolbox and right-click marking menu. Do not make this a prerequisite for the base setup.

This approach targets motor memory and command location. A theme alone will not reduce retraining nearly as much.

## What can and cannot be matched

| Fusion behavior | Closest FreeCAD 1.1.1 equivalent | Match |
|---|---|---|
| Browser at left | Combo View / Tree View docked left | Close |
| Parametric timeline at bottom | Ordered features inside a Body in the tree | Conceptually close, visually different |
| Design workspace | Part Design workbench | Close |
| Contextual Sketch tab | Sketch edit mode and Sketcher toolbars/task panel | Close |
| `L`, `R`, `C`, `D` sketch commands | Rebind FreeCAD Line, Rectangle, Circle; Dimension is already `D` | Excellent |
| `E` Extrude with Join/Cut/New Body | Pad, Pocket, and New Body are separate commands | Partial |
| Feature and sketch mirror/pattern | Separate Sketcher and Part Design commands | Close, but context matters |
| `S` searchable Model Toolbox | Optional PieMenu; otherwise custom toolbar/menu | Partial |
| Fusion mouse navigation | FreeCAD Revit navigation style | Excellent |
| Ribbon/panel layout | Movable/custom Qt toolbars | Partial |
| Marking menu | Optional PieMenu addon | Close |

FreeCAD's feature tree is not a Fusion-style horizontal timeline. Trying to force a ribbon or timeline clone through old UI addons would add maintenance risk without improving the core modeling loop.

## Recommended modeling vocabulary

Use these translations consistently:

| Think in Fusion | Do in FreeCAD |
|---|---|
| Component / active component | Body / active Body |
| Create Sketch | Create Sketch |
| Extrude: Join | Pad |
| Extrude: Cut | Pocket |
| Extrude: New Body | New Body, Create Sketch, then Pad |
| Sketch Dimension | Dimension |
| Sketch Mirror | Sketcher Mirror |
| Rectangular Pattern in sketch | Move/Array Transform |
| Circular Pattern in sketch | Rotate/Polar Transform |
| Feature Mirror | Part Design Mirror |
| Rectangular Pattern of feature | Linear Pattern |
| Circular Pattern of feature | Polar Pattern |
| Browser | Tree View / Combo View |
| Timeline feature | Feature under the Body in the tree |

## Recommended level of customization

Start with native FreeCAD functionality:

- Revit navigation style
- Part Design as the home workbench
- a compact custom toolbar
- Fusion-like shortcuts
- a light or neutral built-in theme with medium 24 px icons

Add PieMenu only after the native setup is stable. Avoid starting with Modern UI/ribbon replacements: the research found no sufficiently current, first-party evidence that they are the best-supported route for FreeCAD 1.1.1, while FreeCAD 1.1 already has a new theme system and improved native UI.

## Files in this folder

- [setup-guide.md](setup-guide.md) — exact setup sequence
- [command-map.md](command-map.md) — command and shortcut decisions
- [open-source-projects.md](open-source-projects.md) — reusable addons, porting assessment, and recommended stack
- [sources.md](sources.md) — researched sources and evidence
