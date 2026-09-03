# Roadmap: FusionMyFreeCAD (FMF) Intent Preservation & Fusion-Familiar UX

**Status:** Architecture & Implementation Plan  
**Date:** 2026-09-03  
**Target Platform:** FreeCAD 1.1+ / Python 3.11+  
**Scope:** FusionMyFreeCAD Add-on (Pure Python, PySide/Qt, Coin3D `pivy`, FreeCAD App/Gui APIs)

---

## 1. Executive Summary & Design Philosophy

FreeCAD 1.0 and 1.1 resolved fundamental architectural hurdles (notably the Topological Naming Phase 1 merge). However, the day-to-day difference between Autodesk Fusion and FreeCAD is **intent preservation versus raw geometry**.

Fusion assumes that when a user creates or transforms geometry (mirroring, offsetting, projecting, trimming), they intend to preserve parametric relationships, equality, symmetry, and construction states. FreeCAD historically assumed the user only wanted the resulting geometric primitives, leaving constraints to be manually reconstructed.

**FusionMyFreeCAD (FMF)** is a self-contained configuration and workflow orchestration layer. It does not modify FreeCAD's C++ core or document formats. This roadmap outlines how FMF can bridge the intent gap directly inside Python, delivering a seamless, Fusion-familiar modeling experience without maintaining a separate C++ fork.

---

## 2. Sketcher: Intent Preservation Wrappers (Python Level)

FreeCAD's Python API exposes full read/write access to `SketchObject.Geometry` and `SketchObject.Constraints`. FMF can intercept transformations, capture the pre-operation constraint topology, and synthesize missing intent relationships in a single undo transaction.

### 2.1 Constraint-Aware Mirroring (`Mirror + Constraints`)
*Building on work started in `Sketch Mirroring.md` and `fusion_sketch_tools.py`.*
* **Mechanism**:
  1. Capture selected source geometry indices and existing constraints involving them.
  2. Invoke `SketchObject.addSymmetric` against the selected mirror axis or line.
  3. Map source geometry IDs to their mirrored counterparts.
  4. Detect external boundary connections (e.g., lines coincident to points on the mirror axis or border geometry).
  5. Apply deduplicated constraints:
     - Equal radius / diameter for circles and arcs.
     - Symmetry constraints for line endpoints across the mirror axis.
     - Coincident constraints for endpoints meeting the mirror axis.
  6. Filter out redundant internal constraints that would over-constrain PlanGCS.
  7. Wrap the entire sequence in an `App.ActiveDocument.openTransaction("Mirror with Constraints")` block for atomic Undo.

### 2.2 Smart Loop Offset Wrapper
*FreeCAD's native offset tool creates disconnected segments and drops tangencies/equalities.*
* **FMF Implementation**:
  1. **Contour Chain Detection**: Walk selected sketch edges to identify closed continuous loops or connected open chains.
  2. **Parametric Offset Generation**: Compute offset segments using `Part::Geom2d` offsets.
  3. **Intent Injection**:
     - Automatically re-apply `Tangent` constraints at all smooth transitions.
     - Apply `Equal Length` / `Equal Radius` constraints linking child segments to parent segments where applicable.
     - Insert a single driving dimension constraint ($\delta$) between one parent edge and one child edge.
  4. **Result**: Editing that single offset dimension scales the entire offset loop uniformly, matching Fusion's single-dimension offset behavior.

### 2.3 Non-Destructive Trimming & Coincident Repair
*FreeCAD's native trim deletes geometry and destroys coincident constraints.*
* **FMF Implementation**:
  1. Pre-trim: Record all coincident and point-on-object constraints linked to the target curve.
  2. Perform trim via standard Sketcher command.
  3. Post-trim: Inspect the newly created intersection vertex and reconnect the recorded constraints to the new endpoint.

### 2.4 Auto-Construction Midlines & Symmetry Axes
*In Fusion, sketching symmetric shapes or slots automatically creates construction midlines.*
* **FMF Implementation**:
  1. Provide a one-click **Add Symmetry Axis / Midline** tool.
  2. Select two points or two parallel lines $\rightarrow$ click tool $\rightarrow$ automatically inserts a construction line with midpoint / equal-distance constraints.

### 2.5 Smart Slot & Arc-Slot Multi-Generators
* **FMF Implementation**:
  1. Provide an interactive 2-click slot tool in the ribbon.
  2. Generates two parallel lines, two tangent end-arcs, and a central construction line.
  3. Auto-applies internal equality and tangency constraints in a single step, exposing only length and slot-width dimensions to the user.

---

## 3. In-Canvas Ergonomics & HUD Diagnostics

### 3.1 Smart Dimensioning Defaults (`D` Shortcut)
* FreeCAD 1.0 introduced `Sketcher_Dimension` (unified dimensioning), but legacy separate tools remain default in many configurations.
* **FMF Configuration**:
  - Map shortcut `D` to `Sketcher_Dimension`.
  - Configure Sketcher preferences to auto-infer:
    - Single line selection $\rightarrow$ Length.
    - Two points $\rightarrow$ Distance (inferred horizontal/vertical by drag direction).
    - Line + Line $\rightarrow$ Angle (or Distance if parallel).
    - Arc/Circle $\rightarrow$ Radius/Diameter.

### 3.2 Human-Readable Solver Diagnostic Interceptor
*PlanGCS solver errors like "Redundant constraints: 12, 19, 34" are confusing.*
* **FMF Implementation**:
  1. Monitor active sketch status through Python observers (`ViewProviderSketch`).
  2. When a sketch is over-constrained or has redundant constraints, parse the constraint indices into human-readable geometry names:
     - *"Constraint 12 (Horizontal on Line 3) conflicts with Constraint 19 (Perpendicular between Line 3 and Line 4)."*
  3. Display a non-modal HUD overlay or status notification with actionable buttons:
     - `[Convert to Reference Dimension]`
     - `[Remove Redundant Constraint]`

### 3.3 One-Click Construction Plane Helpers (Datum Helpers)
*Fusion provides 1-click presets for common construction planes; FreeCAD requires manual 4-step attachment mode configuration.*
* **FMF Implementation**:
  - **1-Click Midplane**: Select two parallel or non-parallel planar faces on a solid $\rightarrow$ creates a `PartDesign::Plane` configured with attachment mode `Plane between two faces` and auto-names it `Midplane`.
  - **Plane at Angle**: Select an edge and a face $\rightarrow$ auto-configures `Plane at angle`.
  - **Tangent to Face**: Select a cylindrical face and a point/plane $\rightarrow$ auto-configures tangent attachment.

---

## 4. Viewport Scene-Graph Enhancements (Coin3D / pivy)

### 4.1 In-Context Ghosted Sketching
* **The Problem**: Editing an earlier sketch inside a PartDesign Body rolls back the visible solid state to that point in history. The user cannot see downstream features or adjacent bodies they need to align with.
* **The FMF Solution**:
  1. When a sketch enters edit mode (`setEdit`), inspect the active PartDesign Body.
  2. Extract the OpenCASCADE shape of the final Tip feature.
  3. Using Coin3D (`pivy`), generate an `SoSeparator` containing the shape's visual mesh.
  4. Assign an `SoMaterial` with 30% transparency (ghosted glass/mesh effect) and set pick style to unpickable (`SoPickStyle.UNPICKABLE`).
  5. Inject this node into the active viewport's scene graph (`Gui.ActiveDocument.ActiveView.getSceneGraph()`).
  6. When the sketch closes, cleanly detach the ghost node.
  7. **Result**: Full visual context of the final part while editing an early sketch, exactly like Fusion's rollback ghosting.

---

## 5. In-Situ Parameters & Modeling Helpers

### 5.1 FMF Fast Parameters Dock
*Opening the Spreadsheet Workbench interrupts modeling flow.*
* **FMF Implementation**:
  1. Provide a lightweight Qt Dock Widget embedded in the FreeCAD sidebar or floating canvas: **FMF Parameters**.
  2. Writes directly to document dynamic properties (e.g., `App.ActiveDocument.addProperty("App::PropertyFloat", "WallThickness")`).
  3. Exposes a clean table: `Name | Expression / Value | Evaluated | Description`.
  4. Seamlessly integrates with FreeCAD’s native Expression engine: typing `WallThickness` or `Length / 2` in any Sketcher or PartDesign spinbox evaluates instantly without touching a spreadsheet.

### 5.2 Contextual Extrude Dialog (Pad / Pocket Merger)
* **FMF Implementation**:
  1. Provide a unified **Extrude** command in the FMF ribbon.
  2. Dialog analyzes the sketch orientation relative to the underlying solid body:
     - If extruding into existing solid $\rightarrow$ defaults to `Pocket` (Cut).
     - If extruding away from solid $\rightarrow$ defaults to `Pad` (Join).
  3. Exposes direct mode toggles in a single panel: `[Join | Cut | Intersect | New Body]`.

---

## 6. Implementation & Delivery Plan for FMF

| Stage | Target Version | Focus Areas | Deliverables |
| :--- | :--- | :--- | :--- |
| **Phase 1** | FMF 1.4 | Sketcher Intent Wrappers | Finalize `Mirror + Constraints` (`fusion_sketch_tools.py`), Smart Slot tool, and Auto-Midline macro. |
| **Phase 2** | FMF 1.5 | Ergonomics & Construction | 1-Click Midplane/Datum tools, unified Extrude dialog, and Solver Diagnostic HUD translator. |
| **Phase 3** | FMF 1.6 | Viewport & Parameters | Coin3D In-Context Ghosted Sketcher view, and Fast In-Canvas Parameters Dock. |

---

## 7. Boundary Rule: What Stays Out of FMF

To keep FMF stable, lightweight, and maintainable across FreeCAD releases, the following are strictly excluded from FMF and deferred to core FreeCAD upstream contributions:
1. Re-writing PlanGCS numerical solver loops.
2. Modifying native FreeCAD file formats or binary storage.
3. Patching OpenCASCADE C++ libraries directly.
4. Altering the core DAG dependency resolution engine.
