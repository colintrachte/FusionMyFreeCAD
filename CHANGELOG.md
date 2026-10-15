# Changelog

All notable user-visible changes to FMF are recorded here.

## 1.8.0 — 2026-10-09

### Regression hardening

- FMF-owned workbenches and ribbon panels now consistently use the FMF name: **FMF Design**,
  **FMF Part**, **FMF Sketch**, and **FMF Surface**. Saved workbench IDs, panel customization,
  adaptive pins, usage history, and autoload preferences from development builds are migrated.
- The Preferences page is again registered as **FMF**. The development installer now ignores a
  saved `ai_poop` test-profile destination instead of silently updating the wrong FreeCAD profile.
- Disabling FMF in a running session now disconnects its workbench callback, event filter, feature
  observers, dress-up enhancer, and Parameters dock. The bundled Ribbon also checks FMF's enabled
  state before showing itself, preventing late callbacks from taking native chrome back over.
- Native workbench activation is now considered healthy when the native menu and central view are
  usable; it no longer fails merely because FMF intentionally hid its Ribbon outside an FMF-owned
  workbench.
- FMF sketch commands remain active in the owned FMF Sketch workbench as well as stock Sketcher.
- Failures while rebuilding selectable sketch regions or assigning a selected region to a Pad are
  now recorded for **Verify UI** instead of being silently ignored. A failed Pad assignment also
  restores the previous profile and sketch visibility.
- Behavior-sensitive ribbon commands now have explicit layout contracts, including unified
  Coincident, native Mirror, Create Sketch, Pad, and Pocket. CI rejects accidental substitutions.
- Local and GitHub release checks now share one metadata validator, including duplicate changelog
  detection. GitHub Actions dependencies are monitored for runtime deprecations.

### Faster workbench transitions

- Repeated workbench activations now supersede older pending copies of the same deferred UI task.
  Entering or leaving a sketch no longer leaves redundant shortcut, navigation-cube, or model-tree
  retry chains scanning the main window while FreeCAD is redrawing it.
- Adaptive command usage now uses a cached command-to-workbench index instead of walking every
  adaptive panel whenever a tracked command is clicked.

### Coincident constraint button

- The Sketcher ribbon's **Coincident** controls now invoke FreeCAD's unified coincident command.
  Selecting two endpoints applies a point-to-point Coincident constraint, while selecting an
  endpoint and an edge applies Point-on-Object instead of leaving the button with no applicable
  action.

### Update Model

- A new command in **UTILITIES**, in every workbench: rebuild every feature so
  a change to one carries down to everything that depends on it.
- The reason it is needed: FreeCAD's own Refresh rebuilds only what is marked
  as needing it, and accepting a PartDesign feature dialog clears that mark
  across the whole document -- the Python console shows
  `App.getDocument(...).purgeTouched()` immediately before its recompute. A pad
  changes; the pocket cut out of it is told it is already current. Opening that
  pocket and pressing OK is the usual way back, one feature at a time, down the
  whole tree.
- `recompute(force=True)` is not the answer on its own, whatever its name
  suggests: the flag only bypasses the document's SkipRecompute, and each
  object is then still asked whether it needs rebuilding and skipped if it says
  no. Measured against a real document it rebuilt *nothing*. Every object is
  now marked first, and then the document is recomputed.
- When something does not come back, the report separates the feature that
  actually failed from the ones below it that were never reached -- a failed
  recompute takes its whole downstream out of the queue, so one broken sketch
  shows up as seven broken features unless someone says which is which.

## 1.7.2 — 2026-09-20

### Entering and leaving a sketch

- The shortcut sweep ran on the thread that draws the window, every time a
  workbench was activated -- which is once on the way into a sketch and once on
  the way out. It asked every action in the main window for its shortcut once
  per shortcut FMF sets, so a tree of several thousand actions was
  walked thirteen times over, twice per edit. It now reads each action once and
  runs after the window is up rather than in front of it.

### Mirror stops adding constraints the mirror already implies

- A mirrored arc was given an `Equal` on top of symmetry links for its centre
  and both endpoints, which already fix its radius. Every mirrored arc
  therefore reported a redundant constraint, and the one the solver named was
  rarely the one worth deleting -- so removing it tended to take a real
  constraint with it. `Equal` is now added only for a circle, which is linked
  by its centre alone and so has nothing else to say how big it is.

## 1.7.1 — 2026-09-20

Repair References, corrected against a real document instead of a test double.

- **A sketch on an origin plane is no longer reported as broken.** It links to
  the Origin object by the plane's *name*, and an Origin has no shape at all,
  so asking its shape for a subelement condemned the commonest attachment
  there is. On the document this was measured against, two of three findings
  were this false positive.
- **Sharing a plane is no longer enough to be the face.** The object's origin
  has to fall within the face as well. Two bosses of the same height share a
  plane, and so does the surface they stand on.
- **An attachment whose placement was reset is offered, not applied.** The
  repair rested on the idea that a broken object still carries the plane of
  the face it lost. It does not: measured against a real file, a sketch that
  had been on the side of a pad came back sitting at the origin, unrotated,
  with nothing left to measure. Where the placement is the untouched default
  the likely face is named in the Report view and nothing is moved.
- A "?" marker over a name that can mean exactly one thing again is cleared.
- FreeCAD's own "?" prefix is read as the answer it is, and not repeated back.

## 1.7.0 — 2026-09-19

### A region keeps its number

- FMF divides a multi-region sketch into faces so each region can be
  padded, and a Pad that uses one records it by index -- `InternalFace2`. Those
  faces came out in whatever order OpenCASCADE's boolean produced them, which
  reshuffles on almost any edit, so a Pad built on a region could start reporting
  `Sub shape not found` after an unrelated trim. Because everything downstream
  hangs off the Pad, one unstable reference took the chamfer and the sketch
  attached to its face with it.
- The faces are now ordered by where the regions are, so moving a dimension
  leaves the numbering alone. Adding or removing a region still renumbers from
  the point it appears -- nothing short of a real element map could prevent that
  -- but that is a deliberate edit rather than incidental churn.
- **On upgrade, check any Pad that uses a specific region of a sketch.** The
  order has changed, so a Pad may need its profile re-picked once. After that it
  stays put.

### Repair References

- A new command in **UTILITIES**, in every workbench. It scans the document for
  face and edge references that no longer resolve -- the breakage behind
  `missing element reference`, `Invalid edge link` and `subshape not found` in
  the Report view -- and reattaches the ones it can identify.
- A sketch or datum attached to a face that has been renumbered is reattached to
  the face it is sitting on. This is a measurement, not a guess: the object's
  Placement was computed from the missing face, so it still describes the plane
  that face was on. Where two faces share that plane, the one the object
  actually covers wins.
- Everything else is named in the Report view and left alone. Nothing in the
  document records where `Edge28` used to be, and a chamfer silently moved to
  the wrong edge is worse than one that admits it is broken.
- The whole repair is one transaction, so a single Undo puts it back.

## 1.6.0 — 2026-09-13

### A section stops at the width its icons need

- Dragging a divider sets a ceiling rather than a target. Inside it the fullest
  set of commands that fits is shown, and the section is then held at the width
  *that* set needs -- so dragging past the point where everything already fits
  does nothing, instead of leaving a stretch of empty space with commands still
  in the drawer.
- How much fits is now settled by building the section and asking it how wide it
  wants to be, rather than by multiplying a representative column width by a
  count. A column budget was never a number of columns on screen: three small
  commands share one, a half-filled stack takes one without being counted, and a
  large button's column is nothing like a small one's. MODIFY, which mixes the
  two, was the section that showed it worst.
- A width recorded by an earlier build is retired rather than honoured, so
  sections measured the old way size themselves again on first use.

### FREQUENT, in every workbench, populated however you like

- **Sketcher now has a FREQUENT section**, so every workbench has one.
- **Anything you use can rise into it.** The candidate pool was a dozen or so
  hand-picked commands per workbench, which meant almost everything you actually
  clicked was invisible to the ranking and the section never changed. The pool
  is now every command that workbench's ribbon offers.
- **Anything you drag into it stays.** The section rewrites itself from what gets
  used, so a command dropped in was swept away at the next workbench switch.
  What you put there is now remembered and kept ahead of anything the counters
  suggest -- and a command you drag back out stays out. A command dragged in
  from another workbench keeps the label and icon it arrived with.
- A FREQUENT section keeps a fixed shape -- two large slots, then small ones --
  so buttons do not move out from under the hand that learned where they were.

### Notes

- A FREQUENT section is rewritten when you switch to its workbench, so a
  promotion from usage appears the next time you come back to that tab.
  Something you drag in appears immediately.

## 1.5.0 — 2026-09-13

### The ribbon sections are yours to arrange

- Dragging the divider between two sections now resizes the section to its left.
  The drag previews where the edge will land, is measured in pixels against the
  section's real width, and the commands that no longer fit move into that
  section's drawer. **Reset this panel** clears a width along with everything else.
- Clicking a section's title opens its drawer, aligned under the section rather
  than under the small icon at the end of the title bar.
- **UTILITIES** replaces the Ribbon add-on's global Tools panel. It holds the
  same standard commands but belongs to the layout, so it can be ordered,
  resized and reset like every other section.
- The **EXPORT** section is now the right-hand bookend of Part Design, Part and
  Surface, as
  Create Sketch is the left-hand one. It reads the selection and opens the save
  dialog already set to the format that suits it: STEP for solids and bodies,
  STL for meshes, PDF for drawing pages, DXF for sketches.

### The sketcher stays responsive as a sketch grows

- FMF rebuilds a sketch's internal faces so multi-region profiles are
  selectable and padable. That rebuild runs an OpenCASCADE boolean, and it was
  running on every solve -- which means every frame of a drag. It is now skipped
  while a sketch is open for editing, skipped when the shape has not changed
  since the last rebuild, and runs on leaving the sketch instead.

### Mirror + Constraints refuses rather than half-finishing

- A tangency sitting on the mirror line cannot be carried across. The command
  used to skip it, report success, and leave a profile that would not close --
  so the pad failed later, far from the cause. It now leaves the sketch
  untouched and names the joins it could not make.

### Fixes

- Icons could not be dragged to reorder them. Qt 6 removed `QDrag.exec_()`, which
  every icon drag used, and the error went to a stream FreeCAD does not display.
- A ribbon rebuild no longer enables every button in the window, which made
  unavailable commands look usable after resizing a section.
- A layout change now reaches an existing installation. A saved panel order was
  replayed over the shipped one, and because the result matched what was already
  on disk, nothing was regenerated.

## 1.4.0 — 2026-09-07

### Added
- **Sketcher workflow commands**:
  - `FMF_AddMidline`: Generates construction centerlines between symmetric elements.
  - `FMF_ConstrainMidpoint`: One-step midpoint constraint on vertex and edge.
  - `FMF_CreateSlot`: Parameterized center-to-center slot with tangent arcs.
  - `FMF_SmartOffset`: Directional profile offset tool.
  - `FMF_SolverDiagnostics`: Plain-language solver diagnostics for under-constrained sketches.
- **Datum Plane tools**:
  - `FMF_DatumMidplane`: Constructs a parametric midplane bisecting two selected faces.
- **In-Canvas Parameters Dock**:
  - `FMF_ParameterDock`: In-canvas dock widget for creating and editing variables and aliases. Multi-document safe with observer-driven synchronization and gap-tolerant spreadsheet reading.
- **Studio Viewport & Theme**:
  - `FMF_StudioViewport`: Clean canvas viewport preset with subtle NaviCube positioning.
  - `FMF_ModernZincTheme`: Sleek Zinc stylesheet.
  - `FMF_RestoreViewport`: One-click viewport and style restoration.
- **FreeCAD Core Suggestions Box**:
  - Cataloged core-bound features (e.g. dynamic Heads-Up Display and Ghost Sketches) in `docs/dev-guide/freecad_core_suggestions_box.md` to keep FMF runtime strictly focused on reliable add-on enhancements.

### Reliability & Infrastructure
- **Shared Infrastructure (`fmf_common.py`)**: Centralized `RUNTIME_MODULES` canonical manifest, unified atomic `transaction(doc, label)` context manager, standard `notify()`, base `SketcherCommand`, and swallowed exception logging (`log_swallowed`).
- **Release Packaging Gate**: `tools/build_addon_package.py` and `validate_addon.py` now import `RUNTIME_MODULES` from `fmf_common.py` as single source of truth, and verify that all packaged runtime modules and assets are tracked in git.
- **Test Suite Hardening**: Fixed test-induced global state mutation by dynamic module eviction; 100% pass across all 198 tests with zero flakiness.
- **Repository Hygiene**: Replaced the 15.7 MB static PDF in `docs/` with official web documentation links (`docs/user-guide/FREECAD-MANUAL-LINK.md`) and made agent guide paths portable.

## 1.3.3 — 2026-09-03

### Replaces the withdrawn 1.3.2

- **1.3.2 is withdrawn.** On FreeCAD 1.1.3 it could intermittently freeze and then crash
  with an "Access violation" while the Sketcher ribbon was being built — typically on the
  first launch after updating, before any command was used. It did not always reproduce
  on a later restart.
- Root cause: the new **Mirror + Constraints** command's `IsActive()` check, which FreeCAD
  polls on a timer for every visible button, reached into live GUI edit state
  (`getInEdit()`). When a sketch opens, that poll could run while FreeCAD was still
  mid-`setEdit` and hand back a half-built object whose C++ access faulted uncatchably.
- Fixes: `IsActive()` is now cheap and side-effect free (open document + Sketcher
  workbench, nothing more). The workbench switch on sketch-open is also deferred out of
  the document-observer callback so it can no longer re-enter an in-progress edit.

### Mirror + Constraints — live symmetry on every mirrored pair

- **Mirror + Constraints** returns as a small button in front of native **Mirror**, which
  keeps its 1.3.1 size — the panel layout is barely changed from 1.3.1. Its icon is
  FreeCAD's Mirror glyph with a green "+" badge, so it reads as "Mirror, plus the
  constraints" next to the plain **Mirror**.
- Select geometry, then a mirror line or sketch axis. Every mirrored element now gets a
  live **Symmetric** link to its source across that line — including dividers and other
  geometry pinned to the borders, which the previous build left unlinked. Drag either
  element and the other follows; **Equal** keeps a mirrored circle or arc the same size.
  This is the Fusion 360 paradigm: the mirror tracks the source and takes no independent
  driving dimensions.
- Over-constraining is avoided rather than tolerated. `addSymmetric` auto-copies
  single-element **Vertical** / **Horizontal** / **Block** constraints onto the mirrored
  copy; with a Symmetric point link on both endpoints those are redundant, so the command
  removes them first. Boundary endpoint attachments (Point-on-Object / Coincident to
  unchanged edges or axes) are then added only for endpoints a Symmetric link does not
  already pin. On a bordered card-divider box the result is 0 DoF, 0 redundant, 0
  conflicting.
- After mirroring, `sketch.InternalShape` is rebuilt from a full planar-face decomposition
  (`BOPTools.SplitAPI.slice`) so every enclosed region — including the middle cells between
  dividers — is selectable and padable. FreeCAD's native `MakeInternals` drops interior
  faces that share an edge with a neighbour.
- A constraint touching only a sketch axis or the origin, with nothing mirrored, is left
  alone rather than reported as skipped. The whole operation is one Undo step; anything it
  cannot reproduce safely is still reported in the Report view.
- The 1.3.2 **Coincident**/`Sketcher_ConstrainCoincidentUnified` swap and the new
  **Point on Object** button are **not** included. Point-to-point **Coincident**
  (`Sketcher_ConstrainCoincident`) stays as it was in 1.3.1.

### Selectable regions and Fusion-style profile picking

- A sketch's complete face decomposition is now kept current on every recompute, not just
  right after a mirror, so multi-region sketches stay fully selectable as they are edited.
- Pick the profile after the command: click **Pad**, then click an enclosed region in the
  3D view and it is assigned to that Pad. Multi-region sketches no longer show a misleading
  all-green whole-sketch highlight when editing ends.
- New empty sketches open centred on the sketch-plane origin at a ~100 mm range. Creating a
  sketch on a pre-selected face keeps that framing; the origin-plane view no longer drifts
  up and to the right the way `fitAll` did on the asymmetric plane bounds. A sketch that
  already has geometry keeps whatever camera you left it at.

### Quieter startup

- The ~20 per-launch "moved the *X* shortcut from …" lines are now one summary line in the
  Report view (`reassigned N keyboard shortcuts …`), with the per-shortcut detail kept in the
  log and in **Verify FMF**.
- The "updated FREQUENT …" and "replaced a ribbon layout that changed outside the add-on"
  lines move to the log; the ribbon backup is still written and still surfaced by Verify UI.

### Upgrade notes

- Replace the entire existing `Mod/FMF` folder; do not merge files from older
  versions. Restart FreeCAD after updating.
- If FreeCAD is currently crashing on the Sketcher tab after installing 1.3.2, installing
  1.3.3 over it resolves it. No sketch or document data is affected.

## 1.3.2 — 2026-09-02 (withdrawn)

> Withdrawn: caused a startup/Sketcher-ribbon crash on FreeCAD 1.1.3. Superseded by 1.3.3.

### Constraint-aware sketch mirroring

- Added a visually distinct **Mirror + Constraints** button beside FreeCAD's original **Mirror**.
  Select geometry and then a mirror line or sketch axis; the advanced command mirrors it and copies
  compatible endpoint constraints to unchanged borders or axes so profiles remain closed.
- The command is explicitly best-effort: every constraint it cannot reproduce safely (global X/Y
  dimensions under an angled mirror, dimensions and unsupported relations across the mirror
  boundary, copies the solver then rejects as redundant) is reported in the Report view, never
  dropped silently. The mirror and copied constraints are one Undo step.
- Kept FreeCAD's original `Sketcher_Symmetry` as an adjacent top-level **Mirror** button for its
  familiar interactive workflow, live symmetry links, point symmetry, and unsupported cases.

### Coincident and Point on Object

- Replaced the point-to-point-only **Coincident** button with `Sketcher_ConstrainCoincidentUnified`,
  which picks point-to-point or point-on-edge from the selection, kept top-level beside
  Horizontal / Vertical.
- Added a dedicated top-level **Point on Object** button (`Sketcher_ConstrainPointOnObject`) for
  attaching a point or line endpoint anywhere along a line, arc, curve, or axis.
- Assigned the verified native Coincident and Point-on-Object icons so the two controls are easy to
  distinguish visually.
- The legacy point-to-point-only Coincident command remains in the Constraints panel menu.

## 1.3.1 — 2026-09-01

### Sketcher ribbon fix

- Removed **Mirror Sketch** (`Sketcher_MirrorSketch`) from the Sketcher ribbon. It called FreeCAD's
  underlying mirror operation without linking the copy back to the original, so mirrored geometry
  could end up under-constrained with no warning. **Mirror** (`Sketcher_Symmetry`) remains and
  correctly links mirrored geometry to the source by default.

### Upgrade notes

- If a sketch was mirrored with the removed **Mirror Sketch** button, its existing geometry is
  unaffected. Re-mirror using **Mirror** if you want the copy properly linked to the original.

## 1.3.0 — 2026-09-01

### Sketch creation and extrusion

- Enabled FreeCAD's native selectable sketch regions so ordinary, non-construction lines can
  subdivide closed profiles for Fusion-style face selection and extrusion.
- Added **Validate Sketch** directly to Part Design so disconnected or invalid geometry can be
  checked without hunting through another workbench.
- Kept **Create Sketch** visible in Sketcher and fixed its position at the far-left edge of the
  ribbon, including when Ribbon initializes before FMF's commands finish registering.
- Preserved and framed FreeCAD's selectable origin planes during sketch creation, then switched to
  the Sketcher ribbon only after a plane has been chosen and sketch editing begins.
- Let Enter activate the enabled affirmative button in modeling task dialogs while preserving
  normal Enter behavior in multiline text editors.

### Responsive Sketcher ribbon

- Promoted Sketcher's **Symmetric** constraint to a top-level, independently movable button with
  its official FreeCAD icon.
- Made the Sketcher ribbon responsive: up to 29 useful overflow commands automatically occupy
  available space at 1450 px and 1750 px window widths and return to their panel menus when narrow.
- Preserved panel customization and complete dropdown access while responsive commands move on and
  off the ribbon face.

### Release maintenance

- Added a tested release-preparation helper and a manually dispatched GitHub Actions workflow that
  validates, builds, checksums, tags, and uploads a draft release.
- Added a human release runbook covering validation, archive review, publication, and rollback.

### Upgrade notes

- Replace the entire existing `Mod/FMF` folder; do not merge files from older versions.
- Restart FreeCAD after updating. FMF applies the new selectable-region preference once for 1.3.0
  while retaining existing ribbon panel arrangements.

## 1.2.0 — 2026-08-31

### Ribbon access and personalization

- Added a complete dropdown menu to every FMF panel, keeping commands accessible even
  when they are not pinned to the ribbon face.
- Added direct click-hold-drag reordering for visible ribbon icons without a separate arrangement
  mode. Ordinary clicks continue to run commands using Qt's normal drag threshold.
- Persisted panel and command order across FreeCAD restarts and FMF layout updates.
- Added **Reset this panel** to each panel menu. It restores only that panel; **Reapply UI** remains
  the deliberate whole-interface reset.
- Expanded the Part Design, Part, and Sketcher command inventories so less-frequent native tools are
  no longer buried.

### Installation, recovery, and settings

- Replaced the retired Windows-specific installer with one self-contained FreeCAD add-on archive
  for Windows, macOS, and Linux.
- Added an immutable first-run baseline, **Verify UI**, **Reapply UI**, and **Restore UI** workflows.
- Added a standalone recovery macro for restoring the previous UI after the add-on was removed.
- Added FMF preferences for the startup workbench, navigation, shortcuts, and optional
  starter design.
- Preserved user preference changes after initial setup by applying defaults only once per release.

### Reliability and packaging

- Bundled the Ribbon and SearchBar runtimes without external Python dependencies or startup dialogs.
- Curated all 153 layout icons directly from FreeCAD's official source and recorded their source
  paths and SHA-256 hashes.
- Added cross-platform CI, behavioral installation/recovery tests, archive validation, formatting,
  linting, and package-hygiene checks.
- Added adaptive FREQUENT panels and improved reporting for displaced keyboard shortcuts and runtime
  failures.

### Upgrade notes

- Replace the entire existing `Mod/FMF` folder; do not merge files from older versions.
- Existing add-on-based panel arrangements are retained and reconciled with the 1.2.0 layout.
- Users of the retired installer should remove its obsolete copy after installing the release
  archive in FreeCAD's active user `Mod` directory.

## 0.1 — 2026-08-01

- Published the first functional prototype and initial Fusion-style layout.
