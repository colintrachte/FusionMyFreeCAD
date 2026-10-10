# FusionMyFreeCAD 1.4.0

1.4.0 is a feature release on top of 1.3.3. It adds a set of sketch and datum tools
that apply the constraints FreeCAD normally leaves to you, an in-canvas parameters
dock, an optional studio viewport and dark theme, and a shared internal core that the
release build now checks. FreeCAD 1.1.x, Python 3.11+. No document or sketch data is
affected by updating.

## Sketcher tools

- **Smart Slot** (`FusionMyFreeCAD_CreateSlot`, Sketch Create panel, behind native
  **Slot**) — builds a fully constrained center-to-center slot: two sides, two end
  arcs, tangent at every corner, with a construction midline and a single driving
  length and radius. Select two points or one line to lay it along existing geometry,
  or run it with nothing selected for a standard parametric slot.
- **Smart Offset** (`FusionMyFreeCAD_SmartOffset`, Sketch Modify panel) — offsets a
  connected chain of sketch edges in the direction you pick, keeping tangency across
  the chain, for quickly growing or shrinking a profile.
- **Add Midline** (`FusionMyFreeCAD_AddMidline`, Sketch Constrain panel) — drops a
  construction centerline between two parallel edges or two symmetric points in one
  click, ready to use as a mirror axis or symmetry reference.
- **Constrain Midpoint** (`FusionMyFreeCAD_ConstrainMidpoint`, Sketch Constrain
  panel) — pins a vertex to the midpoint of an edge in a single action instead of the
  usual select-point, select-line, pick-constraint sequence.
- **Solver Diagnostics** (`FusionMyFreeCAD_SolverDiagnostics`, Sketch Constrain
  panel) — reads the solver state and reports it in plain language, naming the
  geometry involved in conflicts or redundancy, and offers one-click removal of
  redundant constraints.

## Datum tools

- **Midplane** (`FusionMyFreeCAD_DatumMidplane`, Part Design Construct panel) —
  selects two planar faces and creates a parametric `PartDesign::Plane` centered
  between them in one atomic, undoable step.

## Parameters dock

- **Parameters Dock** (`FusionMyFreeCAD_ParameterDock`) — an in-canvas dock for
  creating, viewing, and editing document variables and their aliases without
  switching to the Spreadsheet workbench.
  - **Multi-document safe.** It follows the active document through document
    observers and switches parameter context cleanly when you change tabs.
  - **Atomic undo.** Every add, edit, and delete in the table is one undo step.
  - **Gap-tolerant.** Non-contiguous rows in the backing spreadsheet no longer
    truncate or corrupt the parameters below them.

<<<<<<< HEAD:docs/release-notes/RELEASE-NOTES-1.4.0.md
### 6. Shared Infrastructure & Reliability
- **Centralized Infrastructure (`fusion_common.py`)**: Canonical `RUNTIME_MODULES` manifest, atomic `transaction(doc, label)` context manager, standard notifications, and base `SketcherCommand`.
- **Packaging Integrity Gate**: Release builder and validator verify that all packaged runtime modules and assets are tracked in Git.
- **Deterministic Test Suite**: Clean dynamic module eviction eliminates cross-test state pollution across all 194 unit tests.
- **FreeCAD Core Suggestions Box**: Cleanly catalogs core-bound ideas (Heads-Up Display, Ghost Sketches, Unified Extrude) in `docs/dev-guide/freecad_core_suggestions_box.md`.
=======
## Studio viewport and Modern Zinc theme
>>>>>>> b2d41d6d8d7c2e26f1247876877d657c8a6fb36b:docs/RELEASE-NOTES-1.4.0.md

- **Fusion Studio Viewport** (`FusionMyFreeCAD_StudioViewport`) — a clean canvas
  preset: three-point lighting, a radial background, and a repositioned navigation
  cube.
- **Modern Zinc theme** (`FusionMyFreeCAD_ModernZincTheme`,
  `Resources/Themes/modern_zinc.qss`) — a flat dark zinc stylesheet tuned for
  FreeCAD 1.1+.
- **Restore Viewport Defaults** (`FusionMyFreeCAD_RestoreViewport`) — puts the
  viewport display, lighting, and theme back to your previous FreeCAD settings in
  one click. Both viewport commands are opt-in; nothing changes until you run them.

## Multi-region sketches and extrude

- Carried forward and firmed up from 1.3.3: sketches with interior dividers keep
  every enclosed region populated in `InternalShape`, the sketch unhides while a Pad
  or Pocket is being created, and you can select an interior face region directly in
  the 3D view. Native `PartDesign_Pad` and `PartDesign_Pocket` remain the actual
  ribbon commands — no solver patching.

## Under the hood

- **Shared core (`fusion_common.py`).** One canonical `RUNTIME_MODULES` manifest, one
  atomic `transaction(doc, label)` context manager, one `notify()` helper, and a
  common `SketcherCommand` base, used by every command module.
- **Packaging gate.** `tools/build_addon_package.py` and `validate_addon.py` now take
  the module list from `fusion_common.py` and fail the build if any packaged runtime
  module or asset is untracked in git.
- **Deterministic tests.** Modules are evicted cleanly between tests, removing
  cross-test state leakage across the suite.
- **Repository hygiene.** The 15.7 MB manual PDF in `docs/` is replaced with a link
  file (`docs/FREECAD-MANUAL-LINK.md`); agent-guide paths are now portable.
- **Core suggestions box.** Ideas that belong in FreeCAD itself rather than an add-on
  (heads-up display, ghost sketches, unified extrude) are catalogued in
  `docs/freecad_core_suggestions_box.md`.

## Upgrade notes

- Replace the entire existing `Mod/FusionMyFreeCAD` folder; do not merge it with an
  older version. Restart FreeCAD after updating.
- Your ribbon panel and command order is retained and reconciled with the 1.4.0
  layout. The new tools are added to existing panels (Sketch Create / Modify /
  Constrain, Part Design Construct); **Reapply UI** restores the shipped 1.4.0
  arrangement if you want a clean slate.
- The studio viewport and Modern Zinc theme do nothing until you invoke them, and
  **Restore Viewport Defaults** reverses them.
- No document or sketch data is changed by updating.

## Install or update

Download `FusionMyFreeCAD-1.4.0.zip` and `FusionMyFreeCAD-1.4.0.zip.sha256` from this
release. Replace the entire existing `Mod/FusionMyFreeCAD` folder; do not merge it
with an older version. Restart FreeCAD.

See the [installation guide](https://github.com/colintrachte/FusionMyFreeCAD/blob/v1.4.0/docs/INSTALL-FREECAD-ADDON.md) and [full changelog](https://github.com/colintrachte/FusionMyFreeCAD/blob/v1.4.0/CHANGELOG.md).
