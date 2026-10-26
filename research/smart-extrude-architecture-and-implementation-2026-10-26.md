# Smart Extrude Architecture & Implementation Summary

**Target Audience:** Codex / AI Coding Assistants & Core Maintainers  
**Date:** 2026-10-26  
**Module:** `fmf_extrude.py`  
**Registered Command:** `FMF_SmartExtrude`  
**Test Suite:** `tests/test_smart_extrude.py`  
**Status:** Implemented, verified, and deployed to FreeCAD v1.1 Mod tree  

---

## 1. High-Level Overview & UX Intent

Smart Extrude brings Autodesk Fusion 360's signature extrusion interaction into FreeCAD PartDesign:
1. **Intelligent Operation Detection (`auto`)**: Analyzes profile geometry against candidate solids in real-time. If the extrusion penetrates an existing solid, it automatically resolves to **Cut** (`PartDesign::Pocket`). If it abuts or fuses cleanly into a solid, it resolves to **Join** (`PartDesign::Pad`). If it contacts nothing, it resolves to **New Body** (`PartDesign::Body`).
2. **Elimination of Legacy FreeCAD Dialogs**: No "Flip" buttons, no "Reversed" checkboxes, and no separate Pad vs. Pocket tools. Direction is strictly controlled via signed distance (positive = forward, negative = reversed past zero) and interactive 3D arrow dragging.
3. **Interactive 3D Viewport Manipulation**: A bidirectional Coin3D dragger arrow updates live in the 3D viewport, switching arrowheads dynamically across zero and changing color according to the active operation (**Blue** = Join, **Red** = Cut, **Green** = New Body).
4. **100% Native Output**: Generates pure FreeCAD `PartDesign::Pad`, `PartDesign::Pocket`, and `PartDesign::Body` objects. Models remain 100% portable and fully editable in stock FreeCAD installations without FMF installed.

---

## 2. Architectural Components

```
SmartExtrudeCommand (FMF_SmartExtrude)
       │
       ▼
SmartExtrudeSession ──────────────► SmartExtrudeTaskPanel (Gui.Control.showDialog)
  ├── _extract_world_face_frame()
  ├── classify_operation()
  └── SmartExtrudeDragger (Coin3D SoTranslate1Dragger)
        │
        ▼ (mouse drag)
     _on_motion_cb() [Read-Only] ──► QTimer.singleShot(0, _dispatch_motion)
                                          │
                                          ▼
                                      evaluate() ──► active_view.redraw()
```

### Component Breakdown

1. **`SmartExtrudeCommand` (`fmf_extrude.py`)**:
   - Registered as `FMF_SmartExtrude` in FreeCAD's GUI command registry.
   - Positioned as the primary first tool in the "Create" section of the FMF ribbon.
   - If invoked while inside Sketcher edit mode, it automatically calls `gui_doc.resetEdit()` and uses the active sketch as the extrusion profile (matching Fusion 360 behavior).
   - Opens `SmartExtrudeTaskPanel` via `Gui.Control.showDialog(panel)`.

2. **`SmartExtrudeSession` (`fmf_extrude.py`)**:
   - Pure state coordinator decoupling geometric evaluation from Qt and Coin3D display logic.
   - Tracks: `profile_obj`, `sub_elements`, `signed_distance`, `symmetric`, `taper_angle`, `operation_mode` (`auto`, `join`, `cut`, `new_body`), and `target_body`.
   - Maintains cached 3D face frames and live preview shapes (`prism_shape` and `result_shape`).
   - `commit()` executes within an atomic transaction (`fmf_common.transaction`), creating standard FreeCAD features and transferring sketch ownership cleanly.

3. **`SmartExtrudeTaskPanel` (`fmf_extrude.py`)**:
   - Replaces FreeCAD's default Pad/Pocket panel with a compact, modern design.
   - Contains:
     - Live Operation Badge (`AUTO: JOIN`, `AUTO: CUT`, `NEW BODY`).
     - Profile selector with viewport selection observer (`_ProfileSelectionObserver`).
     - Direction mode (`One Side` vs. `Symmetric`).
     - Signed Distance `QDoubleSpinBox` (-100,000.00 mm to +100,000.00 mm).
     - Taper angle `QDoubleSpinBox` (-89.0° to +89.0°).
     - Operation override combo (`Auto`, `Join`, `Cut`, `New Body`).
     - Contextual 1-line reason label explaining why an operation was selected.
   - All Qt widget setters in `_sync_from_session` are wrapped in exception handlers to prevent deleted-widget runtime errors during dialog teardown.

4. **`SmartExtrudeDragger` (`fmf_extrude.py`)**:
   - Nodekit based on Coin3D's `pivy.coin.SoTranslate1Dragger`.
   - Dual-arrow visual parts pre-constructed inside an `SoSwitch` (`0` = +X forward, `1` = -X reverse) to avoid rebuilding geometry during dragging.
   - Arrow colors pre-allocated in `_mat_normal` and updated in-place via `diffuseColor.setValue()`:
     - Join: Blue `(0.18, 0.62, 0.98)`
     - Cut: Red `(0.92, 0.22, 0.21)`
     - New Body: Green `(0.13, 0.77, 0.37)`
   - Attached to FreeCAD's active 3D view scenegraph (`ActiveView.getSceneGraph()`).

---

## 3. Critical Algorithms & Invariants

### A. Dynamic World Frame Extraction (`_extract_world_face_frame`)
- **Problem**: In FreeCAD PartDesign, an object's `.Shape` inside a `PartDesign::Body` is expressed in **body-local coordinates**, while `body.Shape` is in **world coordinates**. Furthermore, sampling `face.normalAt(0, 0)` fails when (0, 0) is outside the trimmed parameter range of the face, and hardcoding `(0, 0, 1)` breaks sketches placed on XZ, YZ, or angled planes.
- **Solution** (`fmf_extrude.py`):
  1. **Sketch / 2D Objects**: World normal is derived from the sketch's global transformation:
     `normal = profile_obj.getGlobalPlacement().Rotation.multVec(Vector(0, 0, 1))`
  2. **Solid Faces**: Parametric midpoints are evaluated from `face.ParameterRange`:
     `u_mid = 0.5 * (u_min + u_max)`
     `v_mid = 0.5 * (v_min + v_max)`
     `normal = face.normalAt(u_mid, v_mid)`
  3. **Body Coordinate Transformation**: If `profile_obj` belongs to an owning `PartDesign::Body`, the parent body's global placement is multiplied onto the extracted face:
     `face.Placement = body.getGlobalPlacement().multiply(face.Placement)`
     This guarantees that boolean intersection checks (`cand.Shape.common(prism)`) and 3D preview geometry align in absolute world space.

### B. Stable Quaternion Orientation (`_rotation_from_x_to_vector`)
- **Problem**: Coin3D's `SoTranslate1Dragger` translates along the local +X axis `(1, 0, 0)`. Passing antiparallel vectors `(1, 0, 0)` and `(-1, 0, 0)` or non-unit vectors to `SbRotation(vec1, vec2)` causes numerical singularities, NaN quaternions, and frozen viewports.
- **Solution** (`fmf_extrude.py`):
  - If `v_x >= 0.999999`: Identity rotation `SbRotation(SbVec3f(0, 0, 1), 0.0)`.
  - If `v_x <= -0.999999`: 180° rotation around Z `SbRotation(SbVec3f(0, 0, 1), pi)`.
  - Otherwise: Rotation around cross product axis `(0, -v_z, v_y)` by angle `acos(v_x)`.

### C. Scene Graph Mid-Traversal Safety & Deferred Dispatch
- **Problem**: `Unhandled Base::Exception caught in GUIApplication::notify`.
  When a user drags the dragger arrow in FreeCAD's OpenGL viewport, Coin3D traverses the scene graph under `SoHandleEventAction`. Calling `self._switch_normal.whichChild.setValue()` or mutating nodes inside the dragger's motion callback corrupts Coin3D's active traversal state, throwing a C++ exception into Qt's event filter.
- **Solution** (`fmf_extrude.py`):
  - `_on_motion_cb()` is **strictly read-only**:
    ```python
    val = self.dragger.translation.getValue()
    self._latest_drag_val = float(val[0])
    if not self._motion_scheduled:
        self._motion_scheduled = True
        QTimer.singleShot(0, self._dispatch_motion)
    ```
  - `_dispatch_motion()` executes on the Qt event loop **outside** Coin3D's traversal, where toggling `_set_arrow_direction(val < 0.0)` and updating preview geometry is completely safe.

### D. Real-Time Viewport Repainting
- **Problem**: FreeCAD's OpenGL viewport does not automatically trigger an update when custom Coin nodes in `preview_sep` are repopulated during dragging. To the user, the arrow moves but the 3D shape appears frozen.
- **Solution** (`fmf_extrude.py`):
  - At the end of `update_preview()`, call `active_view.redraw()` directly. This forces an immediate viewport repaint on every motion event.

### E. Volumetric Boolean Classification (`classify_operation`)
- **Logic** (`fmf_extrude.py`):
  1. Extrudes a test prism from the world-space face along `dir = normal * (+/- length)`.
  2. **Penetration Test (Cut)**: Tests `cand.Shape.common(prism)` across candidate bodies. If overlap volume > 1e-4 and exceeds 1% of prism volume, operation is classified as **Cut**.
  3. **Abutment Test (Join)**: Tests `cand.Shape.fuse(prism)`. If the resulting compound contains exactly 1 solid, the extrusion abuts and joins the body solid, classified as **Join**.
  4. **Auto-Reverse**: If the initial direction penetrates or produces zero overlap, but the reverse direction fuses cleanly into a single solid, the direction is auto-reversed.
  5. **Disjoint (New Body)**: If the prism contacts no solid in either direction, operation defaults to **New Body**.

---

## 4. Test Coverage & Verification

- **Unit Test Suite**: `tests/test_smart_extrude.py` (29 tests, 100% passing).
  - Tests verify:
    - Parallel, antiparallel, orthogonal, and arbitrary 3D quaternion rotations.
    - Dynamic frame extraction across XZ, YZ, and angled sketch planes.
    - Global placement alignment for sketches inside positioned bodies.
    - Read-only motion callbacks and deferred Qt single-shot dispatch.
    - Elimination of HUD instantiation and deletion safety.
- **Full Test Suite**: 551 tests passing project-wide in 35.8s.
- **Branding Test**: `test_owned_paths_and_python_identifiers_use_fmf_branding` passing.
- **Live CAD Validation**: Verified against `Spool Holder.FCStd` across all sketches (`Sketch`, `Sketch001`, `Sketch002`, `Sketch004`, `Sketch005`) and 3D body faces under FreeCAD's native Python runtime.

---

## 5. Important Rules for Future Modifications

1. **Branding Invariant**: Never use the substring `"fusion"` in any Python identifier, attribute name, function name, or test name. Use `fmf_` prefixes.
2. **Vendor Directory Immutability**: Never edit files in `vendor/`.
3. **No Flip Buttons**: Direction is strictly signed distance. Never reintroduce a "Flip" button or "Reversed" checkbox into the UI.
4. **Scene Graph Discipline**: Never call `setValue()` on Coin3D nodes from within a Coin callback (`_on_motion_cb`, pick callbacks, event callbacks). Always defer to `QTimer.singleShot(0, ...)`.
5. **Always Redraw**: Any dynamic scene graph modifications intended for live feedback must end with `active_view.redraw()`.
