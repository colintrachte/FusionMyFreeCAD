# FusionMyFreeCAD: Constraint-Aware Sketch Mirroring

## Goal

Make sketch mirroring preserve all compatible constraints, including constraints between mirrored geometry and geometry outside the mirrored selection. Also expose clear, reliable controls for:

- Point-to-point coincidence.
- Attaching a line endpoint or point anywhere along another line, arc, or axis.

## Current behavior

The Sketch ribbon’s **Coincident** button currently invokes `Sketcher_ConstrainCoincident`, which only handles point-to-point coincidence. It cannot attach an endpoint to the body of another line.

FreeCAD 1.0 and newer provide:

- `Sketcher_ConstrainCoincidentUnified`: automatically selects point-to-point or point-on-object behavior from the selection.
- `Sketcher_ConstrainPointOnObject`: explicitly attaches a selected point to a line, arc, curve, or axis.

The current configuration is visible in [layout-v3.json](D:\Git\FusionMyFreeCAD\Resources\FusionMyFreeCAD\layout-v3.json:1197). FreeCAD documents Coincident and Point-on-Object as distinct constraint types, with the unified command selecting between them contextually: [Coincident documentation](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Sketcher_ConstrainCoincident.md), [Point-on-Object documentation](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Sketcher_ConstrainPointOnObject.md).

FreeCAD’s native Symmetry tool processes constraints restricted to the selected geometry. Constraints connecting selected geometry to unselected borders—such as the twelve missing endpoint constraints in `3x5CardBox`—can therefore be omitted. [FreeCAD Symmetry documentation](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Sketcher_Symmetry.md).

## User-interface changes

### Constraints panel

Replace the existing top-level Coincident command with:

1. **Coincident**
   - Command: `Sketcher_ConstrainCoincidentUnified`
   - Tooltip: “Join two points, or place a point on an edge based on the selection.”
   - Keep it top-level and adjacent to Horizontal/Vertical.

2. **Point on Object**
   - Command: `Sketcher_ConstrainPointOnObject`
   - Tooltip: “Attach a selected point or line endpoint anywhere along a line, arc, curve, or axis.”
   - Keep it top-level beside Coincident, not hidden in the generic Constraint Tools menu.

Retain the legacy point-to-point-only command in overflow only if compatibility testing finds a reason to keep it.

### Modify panel

Replace FusionMyFreeCAD’s primary **Mirror** button with:

- **Mirror + Constraints**
  - Command: `FusionMyFreeCAD_MirrorWithConstraints`
  - Uses Sketcher's synchronous symmetry API, then copies compatible omitted constraints.
  - Requires geometry plus an explicit mirror line or sketch axis to be preselected.

Keep the native `Sketcher_Symmetry` command immediately beside it as **Mirror** for the original
interactive workflow, point symmetry, troubleshooting, and unsupported cases.

## Implementation plan

### 1. Validate the native FreeCAD interfaces

Perform a short FreeCAD 1.1.x integration spike before writing the wrapper:

- Confirm that both new constraint command IDs are registered.
- Probe their actual icon names.
- Determine how Sketcher-selected geometry and the mirror axis appear through `Gui.Selection`.
- Record geometry and constraint ordering before and after native symmetry.
- Confirm whether an outer document transaction can make mirroring plus constraint copying a single Undo action.
- Confirm how cancellation of the native mirror tool can be detected.

Do not proceed with inferred command or icon names if the probe disagrees.

### 2. Add the constraint-aware mirror command

Create a focused first-party module such as `fusion_sketch_tools.py` rather than expanding the already-large bootstrap module.

`FusionMyFreeCAD_MirrorWithConstraints` should:

1. Verify that a sketch is actively being edited.
2. Capture:
   - Selected source geometry IDs.
   - Existing geometry and constraints.
   - Construction state.
   - Constraint driving/reference and active state.
   - Constraint names and expressions where applicable.
3. Invoke `SketchObject.addSymmetric` with the explicit mirror reference.
4. Build the source-to-mirror map from the returned geometry IDs.
5. Identify constraints FreeCAD did not reproduce.
6. Copy compatible constraints using mapped geometry IDs.
7. Recompute and check for redundant or conflicting constraints.
8. Finish as one Undo operation where the FreeCAD transaction API permits it.
9. Show a non-modal result such as:
   - “Mirrored 6 elements; copied 12 boundary constraints; skipped 1 unsupported angle constraint.”

Cancellation must leave the sketch unchanged.

### 3. Apply a conservative compatibility policy

| Constraint case | Initial behavior |
|---|---|
| Constraint entirely within mirrored selection | Leave to native Symmetry |
| Point-on-Object from mirrored endpoint to unchanged border | Copy when the reflected point lies on that border |
| Coincident with a point on the mirror axis | Copy |
| Horizontal/Vertical, Equal, Parallel, Perpendicular within selection | Leave to native Symmetry |
| Constraint to external geometry | Copy only after geometric validation |
| Global X/Y dimensions under an angled mirror | Skip and report |
| Named dimensions or expressions | Copy only when semantics and names remain valid |
| Constraint that becomes redundant/conflicting | Remove the attempted copy and report it |
| Unsupported geometry or constraint type | Preserve the native mirror result and report the omission |

The command should be explicitly best-effort. It must never silently leave failed constraint copies undisclosed.

### 4. Update the layout and packaged resources

Modify:

- `fusion_bootstrap.py`: register the new command.
- `Resources/FusionMyFreeCAD/layout-v3.json`:
  - Add Mirror with Constraints.
  - Add Unified Coincident.
  - Add Point on Object.
  - Preserve the original Mirror as an adjacent top-level button.
- `Resources/FusionMyFreeCAD/layout-manifest.json`: add the new native and custom command IDs.
- `command-map.md`: document the distinction between Coincident and Point on Object.
- `README.md`: mention constraint-aware mirroring and the dedicated point-on-edge control.
- `source-icons.json` and `verified-icons.json`: update only after probing a real FreeCAD 1.1 installation.
- Curated icon payload: regenerate with the existing icon-sync tool rather than copying icons manually.

### 5. Automated tests

Extend the fake Sketcher environment to cover geometry, constraints, selections, and transactions.

Required regression tests:

- Unified Coincident is top-level.
- Point on Object is top-level and adjacent to Coincident.
- The legacy Coincident command is no longer the primary button.
- Mirror with Constraints is the primary Mirror action.
- Native Mirror remains accessible.
- Source-to-mirror geometry mapping is correct.
- Eligible cross-boundary Point-on-Object constraints are copied.
- Unsupported constraints are skipped and reported.
- Redundant constraints are removed rather than left conflicting.
- Cancel produces no changes.
- Undo removes geometry and copied constraints together.
- Layout, manifest, icons, package contents, and version data remain synchronized.

### 6. Interactive acceptance tests

Use a disposable FreeCAD profile and test at least:

1. **`3x5CardBox` reproduction**
   - Mirror six vertical dividers across the vertical axis.
   - Expect twelve Point-on-Object constraints to be added.
   - Every endpoint remains attached when the top or bottom border moves.
   - The pad recomputes without “Wire is not closed.”

2. **Point-to-point**
   - Select two endpoints and press Coincident.
   - Expect a standard coincident constraint.

3. **Point-to-line**
   - Select one endpoint and the body of another line.
   - Press either Coincident or Point on Object.
   - Expect a Point-on-Object constraint, with the point still free to slide along the line.

4. **Diagonal mirror**
   - Verify unsafe global dimensions are skipped and reported.

5. **Construction and external geometry**
   - Preserve construction state.
   - Copy external-reference constraints only when geometrically valid.

6. **Workflow behavior**
   - Test cancellation, restart, Reapply UI, Restore UI, narrow-window overflow, command search, and one-step Undo.

## Completion criteria

The feature is ready when:

- The `3x5CardBox` scenario works without manual endpoint repair.
- Both endpoint-to-endpoint and endpoint-to-line workflows have obvious top-level buttons.
- Constraint omissions are reported instead of silently ignored.
- Offline tests, linting, formatting, package validation, and a real FreeCAD 1.1.x session pass.
- A human visually verifies the resulting sketch and recomputed solid; automated UI checks do not establish fabrication correctness.

---

## Progress (completed 2026-09-02)

- Replaced the asynchronous native-command wrapper after a FreeCAD 1.1.3 spike proved that
  `Sketcher_Symmetry` returns before the user chooses an axis. The advanced command now requires an
  explicit preselection and calls `SketchObject.addSymmetric` synchronously; its returned geometry
  IDs provide the source-to-mirror mapping without ordering guesses.
- **Mirror + Constraints** is a large top-level button with the `Constraint_Symmetric` icon. The
  original **Mirror** remains immediately beside it as a small top-level button with FreeCAD's
  `Sketcher_Symmetry` icon, preserving the familiar interactive, live-link, and point-symmetry
  workflows. FreeCAD 1.1.3's Python binding does not expose the native option that creates live
  Symmetric constraints, so the advanced command deliberately preserves copied constraints while
  directing live-link use to the original button.
- Unified **Coincident** and **Point on Object** are adjacent top-level controls using the verified
  `Constraint_Coincident` and `Constraint_PointOnObject` icons. The legacy point-only Coincident
  command remains in the panel menu.
- Live API checks confirmed the command IDs, selection spellings, axis IDs, synchronous symmetry
  call, constraint-state properties, and solver diagnostic fields. The official FreeCAD 1.1.3 icon
  probe verified all 156 layout icons with zero missing.
- A headless FreeCAD 1.1.3 acceptance run reproduced the 3×5-card-box pattern: six dividers were
  mirrored, twelve Point-on-Object boundary constraints were copied, and the final sketch had no
  conflicting, redundant, or malformed constraints.
- Automated tests cover mapping, every compatibility-policy branch, solver rejection cleanup,
  explicit selection validation, the twelve-constraint regression, one-step transactions, button
  placement, distinct icons, registration, packaging, and metadata. Release metadata is prepared
  locally as 1.3.2; commit, tag, upload, and publication are handled by the release runbook.
