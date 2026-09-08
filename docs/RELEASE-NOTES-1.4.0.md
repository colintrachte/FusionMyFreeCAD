# FusionMyFreeCAD 1.4.0

FusionMyFreeCAD 1.4.0 is a major feature and reliability release. It introduces high-productivity sketcher workflows, one-click datum plane construction, an in-canvas parameters dock, sleek studio viewport styling, and hardened internal architecture.

## What's new in 1.4.0

### 1. Sketcher Workflow Enhancements
- **Smart Slot (`FusionMyFreeCAD_CreateSlot`)**: Dedicated parameterized center-to-center slot generator with tangent end arcs.
- **Smart Offset (`FusionMyFreeCAD_SmartOffset`)**: Directional profile offset tool for quickly expanding or contracting sketch geometry.
- **Centerline Midline (`FusionMyFreeCAD_AddMidline`)**: Generates construction centerlines between symmetric elements with a single click.
- **One-Step Midpoint Constraint (`FusionMyFreeCAD_ConstrainMidpoint`)**: Quick midpoint constraint between vertex and edge without multi-step menus.
- **Solver Diagnostics (`FusionMyFreeCAD_SolverDiagnostics`)**: Plain-language solver diagnostics that inspect sketch conflicts, report human-readable geometry names, and offer one-click automated cleanup of redundant constraints.

### 2. Parametric Datum Tools
- **Datum Midplane (`FusionMyFreeCAD_DatumMidplane`)**: Automatically constructs a parametric `PartDesign::Plane` bisecting two selected planar faces in one atomic step.

### 3. In-Canvas Parameters Dock (`FusionMyFreeCAD_ParameterDock`)
- An in-canvas dock widget for creating, viewing, and editing document variables and aliases directly inside the modeling view.
- **Multi-document safe**: Tracks active and inactive documents through document observers, switching parameter contexts cleanly.
- **Atomic Undo**: All table additions, edits, and deletions are wrapped in single-step undo transactions.
- **Gap-tolerant**: Handles non-contiguous row gaps in the backing spreadsheet without truncating or corrupting downstream parameters.

### 4. Studio Viewport & Modern Zinc Theme
- **Studio Viewport (`FusionMyFreeCAD_StudioViewport`)**: Clean canvas viewport preset with subtle NaviCube positioning and optimized default camera framing.
- **Modern Zinc Stylesheet (`Resources/Themes/modern_zinc.qss`)**: Contemporary dark zinc aesthetic tailored for FreeCAD 1.1+.
- **Restore UI (`FusionMyFreeCAD_RestoreViewport`)**: One-click restoration back to standard FreeCAD viewport and theme preferences.

### 5. Robust Multi-Region Extrusion
- Retains native `PartDesign_Pad` and `PartDesign_Pocket` commands as authoritative ribbon actions, avoiding brittle C++ solver monkey-patching.
- Maintains the delicate balance for multi-region sketches: sketches with interior dividers populate `InternalShape`, unhide during pad creation, and allow selecting internal face regions directly in the 3D viewport.

### 6. Shared Infrastructure & Reliability
- **Centralized Infrastructure (`fusion_common.py`)**: Canonical `RUNTIME_MODULES` manifest, atomic `transaction(doc, label)` context manager, standard notifications, and base `SketcherCommand`.
- **Packaging Integrity Gate**: Release builder and validator verify that all packaged runtime modules and assets are tracked in Git.
- **Deterministic Test Suite**: Clean dynamic module eviction eliminates cross-test state pollution across all 194 unit tests.
- **FreeCAD Core Suggestions Box**: Cleanly catalogs core-bound ideas (Heads-Up Display, Ghost Sketches, Unified Extrude) in `docs/freecad_core_suggestions_box.md`.

---

## Install or update

Download `FusionMyFreeCAD-1.4.0.zip` and `FusionMyFreeCAD-1.4.0.zip.sha256` from this release. Replace the entire existing `Mod/FusionMyFreeCAD` folder; do not merge it with an older version.

See the [installation guide](https://github.com/colintrachte/FusionMyFreeCAD/blob/v1.4.0/docs/INSTALL-FREECAD-ADDON.md) and [full changelog](https://github.com/colintrachte/FusionMyFreeCAD/blob/v1.4.0/CHANGELOG.md).
