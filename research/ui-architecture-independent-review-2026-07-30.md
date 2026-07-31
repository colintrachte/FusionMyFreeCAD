# Research brief: Fusion-like UI architecture for FreeCAD 1.1

**Status:** Independent research pass for implementation
**Date:** 2026-07-30
**Question:** Which parts of the supplied Fusion-style UI references should be reused, revised, or rejected for a dependable FreeCAD 1.1 prototype?
**Decision boundary:** Prefer a reversible user-profile/addon solution. Do not require a custom FreeCAD build unless native commands and supported addon interfaces cannot deliver the workflow.
**Method:** Compared the user's screenshots and downloaded source trees with FreeCAD 1.1.3 source and documentation, current upstream addon files, and the live UniCAD repository. Checked native commands, ribbon schema, command search, rollback behavior, and the source behind UniCAD's advertised unified operations.

## Executive finding

Build the first prototype as a configuration layer on FreeCAD 1.1.3:

1. FreeCAD-Ribbon supplies the grouped top-level shell and supports custom panels and dropdown buttons in its real JSON schema.[6]
2. SearchBar supplies the closest existing match for Fusion's `S` command search and already defaults its mouse-adjacent search mode to `S`.[7]
3. Native FreeCAD 1.1.3 commands cover the high-frequency sketch and Part Design loop, including grouped rectangle, arc, conic, slot, dimension, constraint, transform, Pad, Pocket, Hole, dress-up, and feature-pattern commands.[3][5]
4. The first Extrude control should be a clearly labeled dropdown containing **Join (Pad)**, **Cut (Pocket)**, and **New Body**. It must not pretend to be one parametric feature.
5. Do not port UniCAD's unified feature code yet. The live README and live/local source disagree on PressPull and drag-through-zero behavior, and the `NewBody` implementation does not create a new `PartDesign::Body`.[8][9]

This route captures the user's preferred Create / Modify / Construct / Inspect grouping, sketch-mode Create / Modify / Constraints grouping, shortcut visibility, and prominent Finish Sketch action without replacing FreeCAD's modeling kernel or document semantics.

## What already exists / key findings

### 1. Native FreeCAD is a strong base for the everyday loop

FreeCAD's Part Design documentation defines Pad as adding an extruded sketch to the developing solid and Pocket as subtracting one. The workbench also exposes Hole, additive/subtractive loft and pipe, fillet, chamfer, thickness, draft, mirror, and linear/polar patterns.[3]

The official 1.1.3 source registers the command identifiers needed by this project. Examples include:

- `PartDesign_NewSketch`, `PartDesign_Pad`, `PartDesign_Pocket`, `PartDesign_Hole`
- `PartDesign_Fillet`, `PartDesign_Chamfer`, `PartDesign_Draft`, `PartDesign_Thickness`
- `PartDesign_Mirrored`, `PartDesign_LinearPattern`, `PartDesign_PolarPattern`, `PartDesign_MultiTransform`
- `Sketcher_CompCreateRectangles`, `Sketcher_CompCreateArc`, `Sketcher_CompCreateConic`, `Sketcher_CompSlot`
- `Sketcher_Dimension`, `Sketcher_CompDimensionTools`, `Sketcher_CompConstrainTools`
- `Sketcher_Offset`, `Sketcher_Translate`, `Sketcher_Rotate`, `Sketcher_Symmetry`, and `Sketcher_RectangularArray`.[5]

FreeCAD 1.1's official release notes also confirm meaningful Sketcher improvements relevant to a Fusion-like workflow: face-based external geometry, defining/construction modes for external geometry, array/offset use of external geometry, and group dragging.[2]

### 2. The screenshots describe an information architecture, not merely a theme

The user's eight screenshots consistently show:

- model mode: Create, Modify, Construct, Inspect, and Insert groups;
- sketch mode: Create, Modify, Constraints, Inspect, and a prominent Finish Sketch action;
- common commands pinned in the ribbon with longer-tail commands in dropdown menus;
- shortcut hints displayed beside menu items;
- mirror and pattern tools included in sketch creation, not hidden as advanced features.

These relationships can be reproduced with Ribbon panels and dropdown buttons. Exact pixel matching is neither necessary nor desirable for the first prototype because FreeCAD task panels and command activation rules remain native.

### 3. FreeCAD-Ribbon is suitable, but only through its actual schema

The current upstream Ribbon repository describes support for custom panels, cross-workbench buttons, button sizing, ordering, labels, and JSON-backed designs.[6] Its checked source uses these top-level structures:

- `dropdownButtons`: dropdown name ending in `_ddb`, mapped to `[command, workbench]` pairs;
- `newPanels`: workbench-scoped panels, also containing `[command, workbench]` pairs;
- `workbenches`: toolbar/panel order and per-command display metadata.

Local evidence: `D:/Git/FreeCAD UI Study/FreeCAD-Ribbon-main/CreateStructure.txt` and `LoadDesign_Ribbon.py:4104-4161`.

This confirms the earlier rejection of the externally supplied JSON files that used invented keys such as `custom_panels_global` and `workbench_layouts`.

Ribbon changes which toolbars are visible. Its own uninstall instructions therefore recommend SaveAndRestore or a toolbar-restoration macro.[6] Backup and rollback are part of the prototype, not optional cleanup.

### 4. SearchBar is the best current match for Fusion's `S` toolbox

SearchBar's upstream documentation says it searches commands, document objects, and preferences; it can appear beside the pointer; and its default activation key is `S`.[7] That is closer to the requested behavior than inventing a second command palette.

Limitations: SearchBar warns of historical Python/C++ lifetime crashes and says its cache initially contains commands only from loaded workbenches.[7] The test plan should therefore load/refresh the required workbenches, save a test document before stress testing, and treat SearchBar failure as non-blocking for core modeling.

### 5. UniCAD contains useful UI ideas but is not an implementation authority

Useful ideas worth translating into the configuration prototype are:

- stable task-oriented tabs rather than exposing every workbench toolbar;
- a prominent Finish Sketch control;
- grouped sketch geometry, transforms, and constraints;
- an optional bottom feature-history view as a later experiment;
- preserving native command activation rather than duplicating modeling code.

However, the live UniCAD README advertises Smart PressPull and automatic Join/Cut switching through zero.[8] The checked source says PressPull was removed (`src/Mod/PartDesign/Gui/Command.cpp:1476`) and compiles out the old automatic switch with `#if 0` (`src/Mod/PartDesign/Gui/TaskExtrudeParameters.cpp:654-703`).[9]

The README also advertises `NewBody` as an operation. In `FeatureUnifiedExtrude.cpp:91-145`, that mode omits the boolean and keeps a standalone shape, but the command still creates the feature through the active Part Design body and the implementation shown does not create a new `PartDesign::Body`.[9] This is not equivalent to Fusion's New Body operation.

The UI rollback implementation is also lossy: `FusionUIManager::hideTraditionalToolbars()` hides main-window toolbars, while `showTraditionalToolbars()` later shows all of them instead of restoring the previous per-toolbar visibility state (`src/Gui/FusionUIManager.cpp:289-332`).[9]

These are source-level contradictions, not matters of taste. UniCAD should remain a reference for interaction concepts until its features are independently built and tested against the intended FreeCAD release.

### 6. A custom C++ fork is disproportionate for the first prototype

The downloaded `FreeCAD-main` tree identifies itself as 26.3.0-dev, not the installed 1.1 line (`D:/Git/FreeCAD-main/version.json`). The downloaded UniCAD tree says it is based on 1.2.0-dev.[8] Neither tree is an appropriate binary-compatible patch base for FreeCAD 1.1.3.

FreeCAD's official customization guidance supports custom and global toolbars assembled from commands in existing workbenches.[4] That supported layer is sufficient to test the user's core workflow before accepting the maintenance and regression cost of a custom build.

## Ideas or implications

### Prototype layout

Part Design mode:

- **Start:** New Body, Create Sketch
- **Create:** Extrude dropdown (Join/Pad, Cut/Pocket, New Body), Hole, Revolve, Loft, Sweep, additive primitives
- **Modify:** Fillet, Chamfer, Thickness, Draft, Boolean
- **Construct:** Datum plane, line, point, coordinate system
- **Pattern:** Mirror, Linear Pattern, Polar Pattern, MultiTransform
- **Inspect:** Measure, Check Geometry, Fit All

Sketch edit mode:

- **Finish:** Finish Sketch
- **Create:** Line, Rectangle, Circle/Conic, Arc, Slot, Point, B-spline
- **Modify:** Fillet/Chamfer, Trim/Split/Extend, Offset, Move, Rotate, Mirror, Rectangular Pattern, external projection/intersection
- **Constraints:** Dimension plus the common geometric constraints

### Extrude behavior

Use a dropdown whose item labels expose FreeCAD semantics. Assign `E` to Pad only after a collision audit, with `Shift+E` as the proposed Pocket binding. A future true unified Extrude should be considered only after the configuration prototype demonstrates that the separate native task panels are the dominant remaining friction.

### Shortcuts

Do not write shortcuts blindly into `user.cfg`. First enumerate registered `QAction` objects after loading Part Design and Sketcher, report unavailable commands and occupied keys, and apply changes through FreeCAD's Customize UI. FreeCAD's customization behavior depends on commands being loaded or visible.[4]

## Contradictions and uncertainty

- The local `FreeCAD-main` archive is a future development snapshot, while the product target is 1.1.3. It is useful for architectural context but not for command compatibility.
- The live GitHub release listing indexed by search lagged behind the official FreeCAD blog, which reports 1.1.3 on 2026-07-25.[1] Use the official blog and the `1.1.3` source tag for this prototype.
- FreeCAD-Ribbon's package metadata reports version `1.11.1` but a date of `2024-07-28`; the current upstream file and local copy agree. The inconsistent-looking date should not be interpreted as proof of release chronology.
- SearchBar's documented crash history makes it optional until exercised locally.
- No runnable FreeCAD executable was found in standard Program Files locations or on `PATH` during this pass, so command activation and visual layout cannot yet be tested in the actual GUI.

## Gaps and open questions

1. The exact location of the user's FreeCAD 1.1 installation or portable bundle.
2. Runtime availability of all target commands after loading Part Design and Sketcher.
3. Whether Ribbon 1.11.1 and SearchBar 1.8.1.1 behave correctly with the user's Qt/PySide build.
4. Which default shortcut collisions exist in the user's current profile.
5. Whether a bottom feature-history view adds enough value beyond the Body tree to justify a later addon.

## Suggested decision or next experiment

Proceed with a reversible Ribbon preset and a read-only runtime audit macro. Validate it against a clean or backed-up FreeCAD 1.1.3 profile using the mounting-plate workflow. Do not install or port UniCAD feature code in this phase.

A second independent AI pass is not needed now: the source contradictions and FreeCAD version mismatch make the first architecture choice clear, while the remaining uncertainty is best resolved by a local runtime experiment.

## Sources

1. FreeCAD, “FreeCAD 1.1.3 released” — https://blog.freecad.org/2026/07/25/freecad-1-1-3-released/
2. FreeCAD documentation, “Release notes 1.1” — https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Release_notes_1.1.md
3. FreeCAD documentation, “PartDesign Workbench” — https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/PartDesign_Workbench.md
4. FreeCAD News, “Tutorial: Custom Toolbars” — https://blog.freecad.org/2025/03/14/tutorial-custom-toolbars/
5. FreeCAD 1.1.3 source: https://raw.githubusercontent.com/FreeCAD/FreeCAD/1.1.3/src/Mod/PartDesign/Gui/Command.cpp ; https://raw.githubusercontent.com/FreeCAD/FreeCAD/1.1.3/src/Mod/Sketcher/Gui/CommandCreateGeo.cpp ; https://raw.githubusercontent.com/FreeCAD/FreeCAD/1.1.3/src/Mod/Sketcher/Gui/CommandConstraints.cpp ; https://raw.githubusercontent.com/FreeCAD/FreeCAD/1.1.3/src/Mod/Sketcher/Gui/CommandSketcherTools.cpp
6. APEbbers, FreeCAD-Ribbon — https://github.com/APEbbers/FreeCAD-Ribbon
7. APEbbers, SearchBar — https://github.com/APEbbers/SearchBar
8. UNITRONIX, UniCAD live repository and README — https://github.com/UNITRONIX/UniCAD
9. Local source audit: `D:/Git/FreeCAD UI Study/UniCAD-main/src/Mod/PartDesign/Gui/Command.cpp`; `TaskExtrudeParameters.cpp`; `FeatureUnifiedExtrude.cpp`; and `D:/Git/FreeCAD UI Study/UniCAD-main/src/Gui/FusionUIManager.cpp`.
