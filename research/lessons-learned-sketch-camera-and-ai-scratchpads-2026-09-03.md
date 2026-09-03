# Research & Lessons Learned: Sketch Camera Framing & AI Scratchpad Architecture

**Date:** 2026-09-03  
**Scope:** `fusion_bootstrap.py`, `tests/fake_freecad.py`, `tests/test_startup.py`, `ai_poop/`, and `~/Desktop/AI_Poop`  
**Status:** Completed and verified (154 tests passing; add-on hot-deployed to FreeCAD 1.1)

---

## 1. Executive Summary

This document captures findings, root causes, and architecture established during the resolution of two major areas:
1. **The Sketch Creation Camera Framing Regression:** Diagnosing and fixing the camera jumping up/right and over-zooming into an off-center ~15 mm view upon sketch creation and plane selection.
2. **The "AI Poop" Scratchpad Architecture:** Designing and implementing a dual-tier (project-local vs. portable global) snippet cache for agent-authored execution byproducts and transient tools, complete with discovery rules and cross-PC portability.

---

## 2. Topic 1: Sketch Creation Camera Framing & View Shifts

### 2.1 The Symptom
* When clicking **Create Sketch** in FusionMyFreeCAD, the 3D viewport immediately panned significantly **up and to the right**, and zoomed in excessively close.
* When subsequently picking an origin plane (e.g. XY, XZ, or YZ), the camera underwent a **second jarring shift**.
* The resulting sketch canvas was off-center and cramped (~15–20 mm visible span) instead of a standard CAD drawing canvas (~100x100 mm centered on the origin `(0, 0)`).

### 2.2 FreeCAD Shipped Baseline vs. FMF Intervention
We audited FreeCAD 1.1's native behavior against FusionMyFreeCAD:

| Attribute | FreeCAD 1.1 Native Baseline | FusionMyFreeCAD (Prior to Fix) | FusionMyFreeCAD (Fixed) |
| :--- | :--- | :--- | :--- |
| **Default Camera Scale** | `NewDocumentCameraScale = 100.0` (100 mm) | Overridden by `fitAll()` (~15 mm) | Restored to `NewDocumentCameraScale` (100 mm) |
| **New Sketch Command** | `PartDesign_NewSketch` displays origin planes, leaves camera completely untouched. | Dispatched `_frame_origin_planes()` calling `viewAxonometric()` and `view.fitAll()`. | Orients to axonometric and centers camera directly on `(0, 0, 0)` at 100 mm scale. |
| **Plane Selection (InEdit)** | Re-orients perpendicular to sketch plane; retains existing camera focal point. | Re-oriented perpendicular to sketch plane from the already-displaced focal point, causing a second jump. | `_SketchEditWorkbenchObserver` centers camera on sketch placement origin `(0, 0)` at 100 mm scale. |
| **Pre-selected Face** | Attaches sketch to face directly. | Ran `_frame_origin_planes()` unconditionally on a timer, knocking the view into axonometric. | Bypasses origin plane framing if geometry was already selected. |

### 2.3 The Root Cause: The OpenInventor / Coin3D Positive Octant Trap
In `fusion_bootstrap.py`, `CreateSketchCommand` called `_frame_origin_planes()`:
```python
def _frame_origin_planes():
    view.viewAxonometric()
    view.fitAll()
```
Why `fitAll()` fails on FreeCAD origin planes:
1. **Asymmetric Origin Plane Bounds:** In FreeCAD's PartDesign coordinate system, the temporary origin planes are drawn extending from `(0, 0, 0)` into the positive octant: `[0, size] x [0, size]`.
2. **Bounding Box Calculation:** `view.fitAll()` traverses visible Coin3D scene graph nodes to compute an axis-aligned bounding box. When only origin planes exist, the center of that bounding box is `(+size/2, +size/2, +size/2)`.
3. **Axonometric Projection Geometry:** In axonometric projection, $+X$ points right, $+Y$ points up/receding, and $+Z$ points up. The vector to `(+size/2, +size/2, +size/2)` points **significantly up and to the right**.
4. **Displacement:** `fitAll()` centers the camera on `(+size/2, +size/2, +size/2)`. The true model origin `(0, 0, 0)` is thrown down and to the left, which the user experiences as the camera panning up and right.
5. **Over-Zoom:** Because `size` is only ~15–20 mm, `fitAll()` fits the view tightly to that 20 mm box.
6. **The Secondary Shift:** When entering sketch edit mode, FreeCAD aligns the camera perpendicular to the sketch plane. Because the camera focal point was already displaced to `(+size/2, +size/2, +size/2)`, the rotation pivots around an offset center, causing the second visual jump.

### 2.4 The Fix Implemented
1. **Eliminated `fitAll()`** from `_frame_origin_planes()`.
2. **Added `_center_camera(view, center=(0.0, 0.0, 0.0), height=100.0)`**:
   - Accesses the active Coin3D camera node (`view.getCameraNode()`).
   - Supports both `SoOrthographicCamera` (setting `cam.height` and `cam.position`) and `SoPerspectiveCamera` (computing focal distance from `cam.heightAngle`).
   - Extracts orientation quaternion $Q$, computes eye direction $\vec{v}_{\text{eye}} = Q \cdot (0, 0, 1)$, and places the camera eye at $\vec{P} = \text{target} + \vec{v}_{\text{eye}} \times \text{focalDistance}$.
   - Guarantees the target point is positioned at the exact dead-center of the viewport.
3. **Pre-selection Check**: `CreateSketchCommand.Activated()` checks `Gui.Selection.getSelection()`. If a face or datum plane was already selected, `_frame_origin_planes()` is skipped entirely.
4. **Sketch Edit Observer (`slotInEdit`)**:
   - When a newly created sketch (`len(sketch.Geometry) == 0`) enters edit mode, the camera is centered on `sketch.getGlobalPlacement().Base` at 100 mm height.
   - If opening an existing sketch that already contains geometry, camera framing is preserved.

---

## 3. Topic 2: AI Scratchpad Architecture ("AI Poop")

### 3.1 Motivation & Concept
AI coding agents frequently generate transient scripts, diagnostic one-liners, and environment workarounds during the course of fulfilling user commands. 
* These artifacts are **not project tools** (they are not meant for human end-users, CI/CD, or repository maintenance).
* These artifacts are **not formal agent skills** (they lack YAML frontmatter, input validation, and structured workflow documentation).
* Without a dedicated home, they either clutter the root directory, get lost in ephemeral scratchpads, or force future agents to repeatedly re-invent the same low-level boilerplate.

### 3.2 Prior Art & Industry Landscape
| Framework / Research | Mechanism | Relevance to "AI Poop" |
| :--- | :--- | :--- |
| **Voyager (Wang et al., 2023)** | *Iterative Skill Library* | First system to have an LLM agent write executable code blocks, test them, store them in a persistent library, and retrieve them via vector search. |
| **LATM (Cai et al., 2023)** | *LLMs as Tool Makers* | Formalized the split between the agent acting as a "Tool Maker" (creating lightweight utilities) and a "Tool User" (executing them). |
| **Cline / Roo Code** | *Memory Bank (`activeContext.md`)* | File-based workspace memory where agents persist patterns and background runbooks across session resets. |
| **Pieces for Developers** | *Pieces OS / MCP Engine* | Snippet engine with MCP integration to capture and retrieve micro-snippets and shell commands. |

### 3.3 Architecture & Guidelines Implemented

```
[ Developer Environment ]
       │
       ├── Project-Local: `FusionMyFreeCAD/ai_poop/` (Default Daily Driver)
       │     ├── README.md (Catalog & Header standard)
       │     ├── fc.py (FreeCAD dynamic runner)
       │     ├── dev_cycle.ps1 (Project-specific test & hot-deploy)
       │     └── .gitignore: /ai_poop/ (Never committed to project releases)
       │
       └── Global Portable: `C:\Users\Colin\Desktop\AI_Poop/` (Opt-in Vault)
             ├── README.md (Strict non-pollution rules)
             ├── freecad/
             │     ├── fc.py (100% portable FreeCAD runner)
             │     ├── coin3d_camera_calc.py (Pure Coin3D vector math)
             │     └── freecad_headless_query.py (Headless inspection)
             ├── powershell/ (Generic Windows execution)
             └── python/ (Generic Python utilities)
```

#### Rule 1: Default to Project-Local
All routine agent scratchpads and execution helpers belong in the project-local `ai_poop/`.

#### Rule 2: Global Folder is Strictly On-Demand
The global folder on the Desktop (`~/Desktop/AI_Poop`) is portable across PCs (via flash drive, cloud sync, or git repo). However, **agents must NEVER read from, write to, or modify the global folder unless the user explicitly requests it.**

#### Rule 3: Zero Project Pollution in Global Poop
No project-specific repositories, build scripts (such as `dev_cycle.ps1`), or hardcoded user paths are permitted in `Desktop/AI_Poop`. Everything in the global archive must be 100% standalone and portable.

#### Rule 4: Standardized `# POOP:` Header
Every snippet uses a 3-line header so agents can run a 1-second `grep` across the directory to review available capabilities without consuming context tokens:
```python
# POOP: <Title / Short description of problem solved>
# ENV: <Target runtime / OS requirements>
# PROVEN: <Date & validation context>
```

---

## 4. Key Verified Facts (Cheat Sheet)

1. **Windows GUI Subprocess Capture:**
   Windows GUI executables (such as `freecad.exe`) do not attach a console to standard output. Running `subprocess.run(["freecad.exe", ...])` directly in PowerShell or Python produces empty stdout. Capturing output requires redirecting via `cmd.exe /c ""freecad.exe" -c "..." > out.txt 2>&1"`.
2. **OpenCASCADE Null Shape Trap:**
   Calling `body.Shape.isNull()` or `body.Shape.isValid()` on a newly created `PartDesign::Body` before features are added raises `Part.OCCError: Standard_NullObject` or `RuntimeError: shape is invalid`. To safely check if a body contains solid geometry, inspect `len(body.Group) == 0` or check that elements in `body.Group` are derived from `PartDesign::FeatureAddSub`.
3. **Coin3D Camera Look Direction:**
   Coin3D cameras look down their local $-Z$ axis. For an orientation quaternion $Q$, the vector pointing from the target back toward the camera eye is $+Z$: $\vec{v}_{\text{eye}} = Q \cdot (0, 0, 1)$.
4. **Orthographic Camera Zoom in FreeCAD:**
   For `SoOrthographicCamera`, `cam.height` is the vertical span in millimeters. Setting `cam.height.setValue(100.0)` displays exactly 100 mm vertically, centered around `cam.position - v_eye * focalDistance`.
