# Changelog

All notable user-visible changes to FusionMyFreeCAD are recorded here.

## 1.3.3 — 2026-09-02

### Withdrawn 1.3.2

- **1.3.2 is withdrawn.** On FreeCAD 1.1.3 it could intermittently freeze and then crash
  with an "Access violation" while the Sketcher ribbon was being built — typically on the
  first launch after updating, before any new command was used. It did not always
  reproduce on a later restart. 1.3.3 restores the 1.3.1 Sketcher ribbon exactly.
- Reverted the 1.3.2 Sketcher ribbon changes: the **Mirror + Constraints** button, the
  swap of **Coincident** to `Sketcher_ConstrainCoincidentUnified`, and the new
  **Point on Object** button are all removed from the ribbon. **Mirror**
  (`Sketcher_Symmetry`) and the point-to-point **Coincident** (`Sketcher_ConstrainCoincident`)
  are back as they were in 1.3.1.
- `fusion_sketch_tools.py` still ships in the package and keeps its own test coverage, but
  nothing registers it or places it on the ribbon. The constraint-aware mirror workflow will
  return in a later release once it has been verified against a running FreeCAD 1.1.3.

### Upgrade notes

- Replace the entire existing `Mod/FusionMyFreeCAD` folder; do not merge files from older
  versions. Restart FreeCAD after updating.
- If FreeCAD is currently crashing on the Sketcher tab after installing 1.3.2, installing 1.3.3
  over it resolves it. No sketch or document data is affected.

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

- Replace the entire existing `Mod/FusionMyFreeCAD` folder; do not merge files from older versions.
- Restart FreeCAD after updating. FMF applies the new selectable-region preference once for 1.3.0
  while retaining existing ribbon panel arrangements.

## 1.2.0 — 2026-08-31

### Ribbon access and personalization

- Added a complete dropdown menu to every FusionMyFreeCAD panel, keeping commands accessible even
  when they are not pinned to the ribbon face.
- Added direct click-hold-drag reordering for visible ribbon icons without a separate arrangement
  mode. Ordinary clicks continue to run commands using Qt's normal drag threshold.
- Persisted panel and command order across FreeCAD restarts and FusionMyFreeCAD layout updates.
- Added **Reset this panel** to each panel menu. It restores only that panel; **Reapply UI** remains
  the deliberate whole-interface reset.
- Expanded the Part Design, Part, and Sketcher command inventories so less-frequent native tools are
  no longer buried.

### Installation, recovery, and settings

- Replaced the retired Windows-specific installer with one self-contained FreeCAD add-on archive
  for Windows, macOS, and Linux.
- Added an immutable first-run baseline, **Verify UI**, **Reapply UI**, and **Restore UI** workflows.
- Added a standalone recovery macro for restoring the previous UI after the add-on was removed.
- Added FusionMyFreeCAD preferences for the startup workbench, navigation, shortcuts, and optional
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

- Replace the entire existing `Mod/FusionMyFreeCAD` folder; do not merge files from older versions.
- Existing add-on-based panel arrangements are retained and reconciled with the 1.2.0 layout.
- Users of the retired installer should remove its obsolete copy after installing the release
  archive in FreeCAD's active user `Mod` directory.

## 0.1 — 2026-08-01

- Published the first functional prototype and initial Fusion-style layout.
