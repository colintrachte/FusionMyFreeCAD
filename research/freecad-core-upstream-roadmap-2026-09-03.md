# Roadmap: FreeCAD Core Upstream Parity & Superiority Over Fusion 360

**Status:** Upstream Architecture Proposal & PR Blueprint  
**Date:** 2026-09-03  
**Target Platform:** FreeCAD Core (C++17/20, PlanGCS, OpenCASCADE, App::Document, Qt/Coin3D Gui)  
**Scope:** Official Pull Requests to `FreeCAD/FreeCAD` (Targeting FreeCAD 1.2+)

---

## 1. Executive Summary & Why Upstream Matters

While interface and intent wrappers can be prototyped rapidly in Python add-ons (such as FusionMyFreeCAD), the core limitations of FreeCAD compared to Autodesk Fusion 360 stem from foundational C++ systems:
1. **PlanGCS Constraint Solver**: Operates on flat scalar equation matrices rather than semantic feature entities.
2. **OpenCASCADE B-Rep API Wrappers**: Atomic failure modes in filleting, sweeping, and shelling.
3. **Data Storage & Document Architecture**: Monolithic zip containers that prevent version control.

Maintaining a private C++ fork of FreeCAD is unviable for an independent developer due to merge friction with rapid upstream development. Instead, this document specifies targeted, self-contained C++ pull request proposals designed for acceptance into the official `FreeCAD/FreeCAD` repository.

---

## 2. PlanGCS & Sketcher Core PR Proposals

### 2.1 Native In-Sketch Pattern Entities (Rectangular & Polar Arrays)
* **The Fusion Standard**: In-sketch rectangular and circular patterns driven by count and spacing parameters without solver slowdown.
* **Why FreeCAD Currently Fails**: Simulating a 50-hole array in Sketcher by adding 50 circles with hundreds of `Equal` and `Distance` constraints expands the PlanGCS Levenberg-Marquardt Jacobian matrix to $O(n^3)$ solve complexity, freezing the UI.
* **The C++ PR Architecture**:
  1. Implement `Sketcher::ConstraintPattern` as a first-class entity in PlanGCS.
  2. The solver computes degrees of freedom *only* for the seed geometry ($\mathbf{P}_0$) and the array basis vectors ($\mathbf{v}_1, \mathbf{v}_2$):
     $$\mathbf{P}_{i,j} = \mathbf{P}_0 + i \cdot \mathbf{v}_1 + j \cdot \mathbf{v}_2$$
  3. Instance geometry is evaluated parametrically post-solve. Instances maintain an immutable link to the seed; individual instance suppression is supported via bitmask.
  4. Solver complexity remains $O(1)$ relative to array count.

### 2.2 Parametric Interval Trimming & Coincident Re-binding
* **The Fusion Standard**: Trimming a line preserves attached dimensions, constraints, and construction status.
* **Why FreeCAD Currently Fails**: `Sketcher_Trimming` physically deletes the underlying OpenCASCADE curve and constructs new curves, invalidating all constraint pointers keyed to the original `GeoId`.
* **The C++ PR Architecture**:
  1. Refactor trimming to perform **parametric interval re-parameterization**: modify the curve’s parameter bounds $[u_{\min}, u_{\max}]$ rather than deleting the geometric entity.
  2. For split curves, maintain a persistent parent-child ID map (`GeoId.child_0`, `GeoId.child_1`).
  3. Traverse attached constraints: automatically remap coincident constraints from the trimmed-away endpoint to the intersection parameter $u_{\text{intersect}}$.

### 2.3 Minimal Conflicting Cycle Visualization (Solver Diagnostics)
* **The Fusion Standard**: When a user adds an over-defining dimension, conflicting constraints light up red, and the user is prompted to make it driven.
* **The C++ PR Architecture**:
  1. When PlanGCS encounters a rank-deficient Jacobian, extract the zero pivot rows.
  2. Use Tarjan’s cycle-finding algorithm on the constraint bipartite incidence graph to isolate the **minimal unsatisfied cycle**.
  3. In `ViewProviderSketch`, render only the participating geometry and constraints in bright red.
  4. Intercept the dimension creation event: if rank deficiency is triggered, display an in-viewport button: `[Make Reference / Driven (Enter)]` or `[Cancel (Esc)]`.

---

## 3. PartDesign & OpenCASCADE Robustness PR Proposals

### 3.1 Fault-Tolerant Fillet & Chamfer Engine (Ribbon Decomposition)
* **The Fusion Standard**: If 1 out of 10 edges in a fillet selection fails, Fusion fillets the 9 valid edges, renders the failing edge in yellow, and explains why.
* **Why FreeCAD Currently Fails**: OpenCASCADE’s `BRepFilletAPI_MakeFillet` fails atomically on topological singularities or radius overflows, throwing a `Standard_Failure` and returning an empty shape.
* **The C++ PR Architecture**:
  1. Inside `PartDesign::Fillet`, pre-process the selected edge list into smooth $G^1$ continuous ribbons (chains).
  2. Wrap `BRepFilletAPI_MakeFillet::Build()` in a binary bisection fault isolator:
     - If the complete edge set fails, partition the ribbons.
     - Test ribbons independently to isolate the degenerate ribbon(s).
     - Execute the fillet on all valid ribbons.
  3. Populate a `FailedElements` property list on the `PartDesign::Fillet` object.
  4. Update the ViewProvider to highlight failed edges with warning markers, reporting: *"Fillet applied to 8 edges; Edge 3 failed due to corner self-intersection."*

### 3.2 Robust "To Face / To Object with Offset" Extrusion
* **The C++ PR Architecture**:
  1. Upgrade `PartDesign::Pad` and `PartDesign::Pocket` to accept a target face/surface with an optional offset distance $\Delta$.
  2. Use OCC's `BRepFeat_MakePrism` with a dynamic limiting face (`PerformUntilFace`) combined with topological parallel offset (`BRepOffsetAPI_MakeOffsetShape`).
  3. Bind target faces using TNP-compliant persistent element names to ensure stability when upstream geometry shifts.

---

## 4. Viewport & Interaction PR Proposals (Qt & Coin3D)

### 4.1 Native 3D In-Canvas Draggers (Interactive Manipulators)
* **The Fusion Standard**: Click an extrude face $\rightarrow$ an arrow dragger appears directly in 3D; drag to extrude with live numerical HUD feedback.
* **The C++ PR Architecture**:
  1. Integrate Coin3D's built-in `SoTranslate1Dragger` and `SoRotateDiscDragger` into the PartDesign ViewProvider edit modes.
  2. Bind dragger translation events directly to feature preview recalculation via an asynchronous throttling timer (16ms / 60 FPS cap).
  3. Render a lightweight Qt overlay input box near the cursor displaying the live distance.

### 4.2 Linear History Scrubber & DAG Rollback Bar
* **The C++ PR Architecture**:
  1. Add a dedicated timeline dock widget at the bottom of the main viewport (`Gui::TimelineBar`).
  2. Populate the bar from the active `PartDesign::Body` topological evaluation order.
  3. Implement a draggable rollback marker:
     - Dragging sets `Body->Tip` to the selected feature.
     - Features downstream of the tip are rendered using a specialized display mode: 30% alpha transparency, unpickable, no edge snapping.
  4. Entering Sketcher on an earlier feature automatically keeps downstream ghosted geometry visible, eliminating "blind editing."

---

## 5. Architectural Vectors: Where FreeCAD Can Beat Fusion 360

Matching Fusion 360 achieves parity with a 2013-era proprietary paradigm. FreeCAD has structural advantages that allow it to **leapfrog** Fusion entirely.

```
                      THE OPEN HARDWARE REVOLUTION
 ┌────────────────────────────────────────────────────────────────────────┐
 │ 1. GIT-NATIVE CAD ENGINE                                               │
 │    Decomposed YAML/JSON + STEP • 3D Visual Branch Diffing • CI/CD PRs  │
 ├────────────────────────────────────────────────────────────────────────┤
 │ 2. DUAL CODE-CAD / GUI-CAD ENGINE                                      │
 │    Interactive Coin3D Mouse Sketching ◄──► Pure Python / Build123d Sync│
 ├────────────────────────────────────────────────────────────────────────┤
 │ 3. PROCEDURAL B-REP GEOMETRY NODES                                     │
 │    Graph-Driven Modeling (Lattices, Gyroids) + Parametric PartDesign   │
 ├────────────────────────────────────────────────────────────────────────┤
 │ 4. UNCAPPED MULTIPROCESSING & MULTIPHYSICS                             │
 │    Local CalculiX (FEA), OpenFOAM (CFD), 5-Axis CAM — Zero Paywalls    │
 └────────────────────────────────────────────────────────────────────────┘
```

### 5.1 Git-Native Decomposed Storage & Visual 3D Diffing
* **The Fusion Vulnerability**: Fusion stores CAD data in Autodesk’s closed cloud. There is no true branching, no merging, no pull requests, and no offline data sovereignty.
* **The FreeCAD Opportunity**:
  - Propose an official decomposed folder format (`.fcdecl`):
    - `meta.yaml`: Document properties, units, authors.
    - `parameters.yaml`: Global expression variables.
    - `features/*.yaml`: Individual feature definitions (sketches, pads, fillets).
    - `blobs/*.step`: B-Rep geometry caches for fast loading.
  - **Visual 3D Branch Diffing**: Compare two git branches visually:
    - Green = Added volume.
    - Red = Removed volume.
    - Yellow = Modified dimensions.
  - **Automated CI/CD for Hardware**: Run headless FreeCAD in GitHub Actions to check clearances, calculate mass, run FEA validation, and export manufacturing deliverables on every pull request.

### 5.2 Dual-Engine "Code-CAD + GUI-CAD" Bi-Directional Modeling
* FreeCAD's entire architecture is exposed to Python.
* Develop a bi-directional synchronizer between the graphical tree and a programmatic modeling syntax (such as Build123d or CadQuery).
* Draw a sketch with the mouse $\rightarrow$ generates clean Python in the editor.
* Edit a procedural Python loop generating complex aerodynamic fins $\rightarrow$ updates the graphical solid instantly.

### 5.3 Procedural B-Rep Geometry Nodes
* Combine history-based PartDesign with node-graph proceduralism (similar to Blender Geometry Nodes, but generating true analytical OpenCASCADE B-Rep solids).
* Enables complex conformal lattices, gyroids, and generative design locally without cloud tokens or mesh conversion errors.

### 5.4 Uncapped Local Compute & Zero-Token Multiphysics
* Autodesk intentionally throttles local compute to sell cloud tokens for simulation and generative design.
* FreeCAD can harness the full multi-core performance of modern workstations:
  - Parallel background meshing and assembly constraint solving across all CPU threads.
  - Seamless local simulation integration: **CalculiX** (non-linear FEA), **Elmer** (electromagnetics), and **OpenFOAM** (CFD).
  - Native 4-axis and 5-axis toolpathing (Path Workbench) with zero subscription fees.

---

## 6. Recommended Pull Request Sequencing

| Sequence | Upstream Target | PR Title / Focus | Impact |
| :--- | :--- | :--- | :--- |
| **PR 1** | `FreeCAD/FreeCAD` (Sketcher) | `PlanGCS: Add Semantic ConstraintPattern Array Entity` | Resolves in-sketch pattern lag; enables 100+ hole arrays. |
| **PR 2** | `FreeCAD/FreeCAD` (Sketcher) | `Sketcher: Non-destructive curve trimming & coincident rebinding` | Fixes broken constraints during sketch trim/split operations. |
| **PR 3** | `FreeCAD/FreeCAD` (PartDesign)| `PartDesign::Fillet: Ribbon decomposition and failure isolation` | Eliminates all-or-nothing fillet crashes on complex solids. |
| **PR 4** | `FreeCAD/FreeCAD` (Gui) | `Gui::Timeline: In-viewport history rollback bar with ghosting` | Introduces Fusion-style visual timeline and in-context editing. |
| **PR 5** | `FreeCAD/FreeCAD` (Base) | `App::Document: Decomposed directory storage format for Git` | Establishes FreeCAD as the standard for Git-native hardware design. |
