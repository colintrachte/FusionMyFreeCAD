# FreeCAD Core Suggestions Box

**Architectural Proposals for Upstream FreeCAD (v1.1 / v1.2+)**  
*Derived from the FusionMyFreeCAD (FMF) Modernization Initiative*

> [!NOTE]
> **Internal Repository Documentation**: These architectural proposals and problem analyses are cataloged internally within the FusionMyFreeCAD repository for future architectural reference and are NOT submitted to upstream FreeCAD issue trackers or forums without explicit direction.

---

## Executive Summary & Design Philosophy

Add-ons like **FusionMyFreeCAD (FMF)** excel at opinionated workflow assembly: organizing ribbon tabs, wiring high-leverage geometric shortcuts, providing fast in-canvas utilities, and establishing clean defaults.

However, when an add-on attempts to compensate for foundational CAD engine limitations through Python hooks, it inevitably encounters fragility:
- **Scene graph hacking**: Custom Coin3D/OpenGL shaders in Python cause driver-dependent crashes, memory leaks, and viewport flicker.
- **TaskPanel shadowing**: Overriding FreeCAD's native TaskPanel for modeling operations bypasses core multi-step modeling features (taper, two dimensions, up to face).
- **Transient state leakage**: Toggling transparencies across the tree for "ghosted" in-context sketching risks leaving models permanently translucent if an undo or crash occurs.
- **Preference pollution**: Overwriting global `BaseApp/Preferences` without host-level sandboxing risks corrupting the user's base installation.

The following **6 proposals** represent features that are best removed from add-on scope and implemented directly in **FreeCAD Core**.

---

## Proposal 1: Unified Interactive Extrude (Merging Pad & Pocket)

### The Problem in FreeCAD Today
FreeCAD strictly bifurcates extrusion into two separate C++ features: `PartDesign::Pad` (additive) and `PartDesign::Pocket` (subtractive).
- When a designer sketches on an existing solid face with the intention of making a cut, clicking "Pad" fails or creates self-intersecting solids.
- The user must cancel, close the dialog, and find the Pocket command.
- Extrusions lack direct 3D canvas manipulator arrows (push/pull handles) and must be driven purely via numeric entry in the TaskPanel.

### Core Recommendation
1. **Single Extrude Feature**: Unify `PartDesign::Pad` and `PartDesign::Pocket` into a unified `PartDesign::Extrude` feature.
2. **Operation Mode Enum**: Provide a standard boolean operation parameter:
   - `Join` (Additive)
   - `Cut` (Subtractive)
   - `Intersect` (Intersection with active body)
   - `New Body` (Creates independent body container)
3. **Automatic Normal & Bounding Inference**: FreeCAD core should inspect the sketch normal relative to the solid body. If the extrusion vector penetrates the existing solid, default the operation to `Cut`; if it points away, default to `Join`.
4. **Native Coin3D Dragger**: Attach an interactive distance arrow dragger directly in the 3D viewport that updates the length parameter dynamically.

---

## Proposal 2: First-Class Native Parameters Property Table

### The Problem in FreeCAD Today
Parametric modeling in FreeCAD currently relies on the `Spreadsheet` workbench:
- Opening a spreadsheet opens a separate 2D tab, completely hiding the 3D model view.
- To use variables in sketches, users must manually set cell aliases (with strict regex requirements).
- Spreadsheets incur noticeable recompute latency and lack row identity tracking (leaving gaps that break external consumers).
- There is no native parameter inspector in `PartDesign::Body`.

### Core Recommendation
1. **Document-Level Property Map**: Implement a native `App::PropertyMap` or `App::ParameterGroup` on `App::Document` and `PartDesign::Body` in C++.
2. **In-Canvas Dock Widget in Core**: Provide a native Qt dockable widget (e.g. `Model Parameters`) accessible across all workbenches without switching tabs.
3. **Direct Expression Binding**: Allow sketches and features to bind directly to `doc.Params.Length` or `body.Params.WallThickness` without requiring an auxiliary spreadsheet object in the tree.

---

## Proposal 3: Core-Level Ghosted / In-Context Geometry Dimming

### The Problem in FreeCAD Today
When editing a sketch on a face deep inside an existing model:
- The user either sees the entire opaque solid (which obscures sketch geometry, construction lines, and background references), or toggles "view sketch flat" (which hides all 3D context).
- Add-on workarounds that walk `doc.Objects` and toggle `ViewObject.Transparency = 70` are unsafe: if FreeCAD crashes, encounters an unhandled exception, or performs an undo, the body remains stuck in a semi-transparent state.

### Core Recommendation
1. **Quarter / Coin3D Render Pass**: Introduce a native viewport rendering pass in `Gui::View3DInventorViewer` that automatically dims inactive bodies and downstream features during `Sketcher::SketchObject` editing.
2. **X-Ray / Silhouette Shading**: Render the inactive solid with a subtle, non-intrusive wireframe or Fresnel X-ray silhouette so designers maintain spatial awareness without occlusion.

---

## Proposal 4: Direct 3D Canvas Solver Diagnostics & Conflict Highlighting

### The Problem in FreeCAD Today
When a sketch becomes overconstrained or has redundant constraints:
- The solver identifies conflicting constraint indices (e.g. `Constraint12`, `Constraint15`), but only outputs textual warnings in the TaskPanel solver box or `Report view`.
- The user must manually scan through the constraint list in the Tasks panel to guess which physical lines are conflicting.

### Core Recommendation
1. **Viewport Overlay for Solver Errors**: When the sketch solver detects redundancy or conflicts, highlight the conflicting geometric entities and constraint symbols directly in the 3D canvas with contrasting colors (e.g. Amber for redundant, Red for conflicting).
2. **Click-to-Resolve**: Clicking a highlighted red constraint on the canvas should offer an instant popup menu: `[Delete Constraint] [Convert to Reference Driving Dimension]`.

---

## Proposal 5: Scoped Preference Profiles & Add-On Configuration Sandboxing

### The Problem in FreeCAD Today
Add-ons that provide modern themes, viewport lighting presets, or ergonomic keymaps must write directly into global `BaseApp/Preferences/`:
- If an add-on modifies `View/BackgroundColor` or `General/StyleSheet`, uninstalling the add-on leaves those values behind.
- Restoring requires fragile custom diffing routines (like FMF's `_capture_preferences` and `restore_preference_keys`).

### Core Recommendation
1. **Layered Preferences Engine**: Enhance `App::ParameterGrp` to support hierarchical profile layers:
   - Layer 0: System Defaults
   - Layer 1: User Base Profile
   - Layer 2: Active Workspace / Add-on Overlay
2. **Ephemeral Overlays**: When a workspace profile or add-on is active, its preference overrides sit on Layer 2. When deactivated or uninstalled, Layer 2 is simply discarded, restoring the pristine base configuration instantly with zero cleanup logic required by the add-on.

---

## Proposal 6: Pre-Flight Selection Validation for PartDesign Commands

### The Problem in FreeCAD Today
In FreeCAD PartDesign, activating commands like Datum Plane, Subtractive Pipe, or Loft often creates a new `PartDesign::Body` *before* verifying whether the user's current selection contains the necessary geometric references.
- If the user misclicks or cancels because they lacked the required faces/edges, an empty, orphaned `Body` remains in the model tree.
- This creates tree pollution and confuses new users.

### Core Recommendation
1. **Pre-Flight Selection Gate**: Standardize all `Gui::Command` handlers in PartDesign to execute selection validation *before* opening transactions or instantiating containers.
2. **Non-Modal Visual Feedback**: If prerequisites are missing, show non-modal guidance in the status bar or on-canvas tooltip (e.g. *"Select 2 planar faces to create a midplane"*), without creating uncommitted document objects.

---

## Summary Matrix: Where Features Belong

| Feature Area | FMF Add-On Scope | FreeCAD Core Scope |
| :--- | :--- | :--- |
| **Ribbon UI & Layout** | **YES**: Curated tabs, streamlined grouping, Fusion-style ribbon | Provide extensible ribbon widget in `Gui` |
| **Ergonomic Sketch Tools** | **YES**: Midline, midpoint, slot, smart offset, mirror | Core sketch primitives in `Sketcher` |
| **Extrude Workflow** | **YES**: Smart dispatcher (`Join` vs `Cut` context inference) | **CORE**: Unified `Extrude` feature with 3D dragger |
| **Parameters** | **YES**: Fast in-canvas spreadsheet dock | **CORE**: Native `App::PropertyMap` on Body/Doc |
| **Viewport Appearance** | **YES**: Calibrated preset of native 1.1 3-point lighting | **CORE**: PBR shaders, ambient occlusion, shadows |
| **Sketch Dimming** | Minimal / Skip (avoid display corruption) | **CORE**: Native Quarter/Coin3D dimming render pass |
| **Preference Rollback** | **YES**: Strict baseline diffing and 1-click restore | **CORE**: Layered/sandboxed preference profiles |
