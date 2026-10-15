# Current feature and benefit inventory

This document defines FMF's current end-user value as a preservation baseline. A
packaging, architecture, or Addon Index refactor is not successful if it silently removes one of
these benefits. Intentional product changes require an explicit decision, updated documentation,
and regression coverage.

The inventory describes version 1.8.0. It distinguishes the user benefit from the present
implementation so implementation details can change without losing the product.

## Product contract

FMF gives a Fusion 360 user a familiar, coherent workflow across multiple modelling
contexts. It is deliberately not a single-purpose workbench. Part Design, Part, Sketcher, and
Surface each have their own purpose-built layout, while shared interaction conventions make them
feel like parts of one product.

The core experience is:

1. Install one self-contained add-on and restart FreeCAD.
2. Receive a coherent Fusion-familiar interface without manually assembling dependencies or
   importing configuration files.
3. Move among purpose-specific modelling contexts without losing the common ribbon vocabulary,
   command search, shortcuts, navigation, inspection, and export workflows.
4. Gain workflow capabilities that FreeCAD does not currently provide in the same direct form.
5. Preserve the ability to verify the installation, recover the shipped configuration, and restore
   the pre-installation profile.

FMF-owned workbenches are intended to be superior day-to-day replacements for the corresponding
stock FreeCAD workbenches, not reduced demonstration shells. They must provide enough command
coverage, context transitions, discoverability, personalization, and workflow enhancement that a
user can use the FMF replacements without losing access to necessary work. While FMF is enabled,
the corresponding stock workbenches are hidden from the selector; disabling FMF reverses that state.

An Index-readiness refactor may add one explicit first-run activation step, but should not turn
installation into a multi-package or manual configuration exercise.

## Multi-workbench Fusion layout

### User benefit

Users see commands grouped and named according to the task they are performing, with Fusion-like
large primary actions, smaller secondary actions, complete dropdown inventories, and consistent
shared panels. This reduces the relearning cost without collapsing different modelling modes into
one oversized workspace.

### Current support

`Resources/FMF/layout-v3.json` defines four independent layouts:

- **Part Design**: SKETCH, CREATE, MODIFY, CONSTRUCT, PARAMETERS, FREQUENT, INSPECT, UTILITIES, and
  EXPORT panels.
- **Part**: CREATE / IMPORT, BOOLEAN, SPLIT, REPAIR, FREQUENT, INSPECT, UTILITIES, and EXPORT.
- **Sketcher**: CREATE, MODIFY, CONSTRAINTS, CONFIGURE, FREQUENT, INSPECT, INSERT, SELECT, SKETCH,
  and UTILITIES.
- **Surface**: CREATE, MODIFY, FREQUENT, INSPECT, UTILITIES, and EXPORT.

`fmf_bootstrap.py` transforms that declarative specification into the Ribbon configuration.
`Resources/FMF/RibbonStructure.json` is the shipped Ribbon structure, and the bundled
FreeCAD-Ribbon runtime renders it.

### Preservation requirement

All four task-specific layouts, their panel order, command inventory, labels, icons, sizing, and
overflow access must survive an architectural refactor. Registering several FMF-owned workbenches
is compatible with this requirement; replacing everything with one FMF workbench is not.

Each FMF-owned workbench must be validated as a practical superset of the intended everyday user
journey for its stock counterpart. Commands that are deliberately relegated to dropdowns still
count as available; commands omitted entirely require a documented rationale and an alternate path.
The replacement must preserve access to native FreeCAD commands rather than forking their modelling
semantics unnecessarily.

Activation hides the four corresponding stock workbenches and exposes the FMF family. Disabling
performs the inverse. The stock implementations remain installed and structurally untouched.

## Immediate, self-contained installation

### User benefit

The add-on works after one archive/Add-on installation and one restart. Users do not separately
install Ribbon, SearchBar, Python packages, .NET components, or configuration files.

### Current support

`InitGui.py` registers recovery commands, prepares the profile, starts the FMF runtime, and loads
the tracked subsets of SearchBar and FreeCAD-Ribbon from `bundled-addons/`. The release archive
contains the layouts, runtime, icons, styles, and third-party notices.

### Preservation requirement

Any dependency or namespacing refactor must retain a one-package user experience. A first-run page
with a prominent **Activate FMF** action is an acceptable additional step if activation
is atomic, clearly explained, and followed by the complete working experience.

## First-run safety and recoverability

### User benefit

Users can try an opinionated interface without permanently losing the profile they had before it.
Startup failures should not remove access to verification and recovery commands.

### Current support

- `fmf_bootstrap.py` records an initial baseline once and does not overwrite it during later
  updates.
- `InitGui.py` registers recovery commands before installation and third-party runtime loading.
- **Verify FMF** checks layout, baseline, bundled payload, and startup/runtime failures.
- **Reset FMF** restores FMF defaults and intentionally clears FMF panel personalization.
- FMF owns four separate workbench identities: FMF Design, FMF Part, FMF Sketch, and FMF Surface.
  The curated ribbon is authoritative only in those workbenches.
- **Disable FMF** maps the active FMF workbench to its stock counterpart, restores
  managed preferences and shortcuts, hides FMF workbench entries, and persists across restarts.
- **Enable FMF** exposes the owned workbenches and preserves their saved layout and
  personalization. Stock workbench visibility is a separate reversible preference.
- `tools/RestoreFMF.FCMacro` provides recovery after the add-on itself has been removed.
- Startup steps fail independently and record actionable diagnostics instead of aborting the rest
  of initialization.

### Preservation requirement

The baseline, degraded-start recovery, Verify, Reset, Disable/Enable, and standalone recovery paths are
release-critical features. A refactor should strengthen disable/uninstall restoration, not replace
these protections.

## Ribbon completeness and personalization

### User benefit

The ribbon remains compact without hiding capability. Primary commands are visible; every panel's
full command inventory is available through its dropdown. Users can reorder commands, retain that
order across restarts and layout updates, and reset one panel without destroying customization
elsewhere.

### Current support

- `layout-v3.json` separates pinned commands from overflow commands.
- `fmf_bootstrap.py` reconciles shipped panel/command order with saved user state, generates
  panel menus, records responsive metadata, and resets customization at panel scope.
- The locally maintained Ribbon widget changes support drag reordering and panel-level reset.
- Sketcher uses responsive width tiers so useful commands can move between the ribbon face and
  dropdown rather than becoming inaccessible.

### Preservation requirement

No refactor may reduce the complete command inventory to only the visible buttons or replace
per-panel reset with a destructive global-only reset.

## Adaptive FREQUENT panels

### User benefit

Frequently used commands rise into a small, predictable panel for each modelling context without a
single accidental click constantly rearranging the interface. User-pinned choices remain stable.

### Current support

`layout-manifest.json` defines candidate commands, defaults, capacity, and panel behavior for Part
Design, Part, Sketcher, and Surface. `runtime.py` tracks usage with a 30-day half-life, requires a
promotion threshold, preserves pins, and rewrites only declared adaptive slots or panels. Writes
are coalesced to reduce UI and disk overhead.

### Preservation requirement

Usage tracking must remain local, bounded, explainable, and scoped to declared candidates. Stable
defaults and user pins must survive migration and upgrades.

## Command search

### User benefit

Users can find and invoke commands without knowing where FreeCAD placed them, matching Fusion's
search-oriented workflow and reducing ribbon-navigation cost.

### Current support

The tracked SearchBar runtime is loaded by `InitGui.py`. FMF suppresses its independent first-run
changelog prompt so installation remains a single coherent experience, and exposes its command
through the ribbon/shortcut configuration.

### Preservation requirement

Command search must remain available immediately after activation and must not require a second
manual add-on installation.

## Fusion-familiar keyboard and navigation defaults

### User benefit

Common modelling operations use familiar single-key shortcuts, and viewport navigation/cube
placement is closer to Fusion. Users can move from Fusion without immediately relearning every
interaction.

### Current support

`runtime.py` defines shortcuts for line, rectangles, circle, dimension, pad/extrude, pocket, hole,
trim, offset, projection, construction geometry, and measure. It applies Revit navigation—the
closest current FreeCAD built-in match—and places the navigation cube at the top right. Preferences
allow opting out, and displaced shortcuts are reported by Verify FMF.

### Preservation requirement

The preset remains part of the product. Index hardening may change conflict handling from automatic
displacement to informed first-run acceptance or per-conflict choice, but must provide a one-action
path to the complete Fusion preset and exact restoration of prior bindings.

## Sketch creation and context transitions

### User benefit

Creating a sketch starts from a useful modelling state and preserves FreeCAD's selectable origin
planes. Entering and leaving sketch edit moves between the correct purpose-specific ribbon layouts
without leaving redundant shortcuts, navigation controls, or model-tree state behind.

### Current support

- `FMF_CreateSketch` creates the necessary document/body and delegates the attachment
  step to Part Design so origin planes remain visible and selectable.
- `_SketchEditWorkbenchObserver` in `fmf_bootstrap.py` coordinates the transition into and out of
  the Sketcher context.
- Runtime workbench callbacks refresh the applicable adaptive panel and shared UI state.

### Preservation requirement

Any FMF-owned-workbench design must explicitly solve sketch edit transitions. It must not force the
user through an unrelated generic workspace or lose the Part Design attachment workflow.

## Sketching workflow enhancements

### Unified Coincident

The ribbon exposes FreeCAD's unified Coincident command so the same visible control applies either
point-to-point Coincident or Point-on-Object according to selection. FMF enables the corresponding
Sketcher preference and maps the verified command into the layout.

### Mirror + Constraints

`fmf_sketch_tools.py` builds on native symmetry, restores supported boundary attachments that
native mirroring drops, adds live symmetric relationships for appropriate free geometry, preserves
circle/arc size with equality, rolls back rejected constraints, and reports unsupported cases
instead of silently guessing.

### Midline and midpoint

FMF provides direct commands for creating a construction centerline between suitable selections
and constraining a point to an edge midpoint, reducing multi-command constraint sequences.

### Smart Slot and Smart Offset

FMF provides direct slot construction with geometric relationships and a directional offset
workflow intended to preserve useful continuity.

### Solver Diagnostics

FMF turns solver degrees of freedom and selected geometry state into actionable constraint advice
instead of exposing only raw solver counts.

### Smart Dimension and sketch defaults

FMF exposes the unified Sketcher dimension command prominently and enables unified dimensioning,
diameter/radius behavior, automatic constraints, redundant-constraint avoidance, horizontal/
vertical inference, cursor coordinates, on-view parameters, and internal profile generation.

### Multi-region profile usability

The sketch support code rebuilds internal planar faces when required so divided closed regions stay
selectable for downstream features such as Pad. This compensates for observed FreeCAD behavior in
multi-region and mirrored profiles.

### Preservation requirement

All of these end-user results are baseline features. Safety hardening may make automatic document
repair explicitly activatable or narrow its trigger conditions, but it must not reintroduce the
broken multi-region workflow the code was written to solve. Tests must cover the real regression
before changing the mechanism.

## Faster Part Design dress-up workflow

### User benefit

Chamfer and Fillet behave more like direct modern CAD tools: click geometry, type a dimension, see
the live result, and press Enter without fighting focus or viewport shortcuts.

### Current support

`fmf_dressup_tools.py`:

- enables live spinbox preview;
- routes numpad digits and decimal input to the active dimension field instead of camera views;
- keeps edge/face selection mode ready;
- focuses and selects the dimension text after a 3D pick; and
- commits the typed value and recomputes before accepting the task.

It uses an application event filter and a selection observer, with an explicit uninstall function
for teardown and tests.

### Preservation requirement

The interaction behavior must remain available in the FMF Part Design experience. Refactoring may
tighten event-filter scope to FMF-owned contexts but must retain numpad protection, focus behavior,
live preview, and safe commit.

## Datum Midplane

### User benefit

A user creates a parametric plane centered between two selected planar faces in one operation,
instead of manually configuring attachment modes and reversal flags.

### Current support

`fmf_datum_tools.py` validates selection, finds the active Part Design Body, creates the datum
plane in a FreeCAD transaction, and configures its attachment.

### Preservation requirement

Keep the direct two-face operation, parametric result, validation, and Undo behavior.

## Parameters workflow

### User benefit

Users create, inspect, and edit named model parameters without abandoning the modelling context for
the Spreadsheet workbench.

### Current support

- **Parameter Table** creates or opens the dedicated Parameters spreadsheet.
- `fmf_parameters_dock.py` provides an in-canvas dock for parameter names, values/expressions,
  aliases, and notes.
- The dock tracks its owning document safely and refreshes through a removable document observer.

### Preservation requirement

Keep both the underlying ordinary Spreadsheet data and the faster dock workflow. Documents must
remain usable without FMF installed.

## Repair References and Update Model

### User benefit

Users can diagnose models that silently stopped rebuilding after topology changes. FMF repairs only
references it can identify from surviving geometric evidence and reports uncertain cases rather
than redirecting them to the wrong geometry. It can also force an ordered recompute and distinguish
the first actual failure from untouched downstream features.

### Current support

`fmf_repair_tools.py` audits link/subelement properties. It limits automatic repair to supported
attachment references whose prior placement identifies a unique coplanar face. Other broken edges
and faces are reported. Both repair and update are explicit commands.

### Preservation requirement

Keep the conservative no-guessing contract, explicit invocation, reporting, and transaction/
recompute safety. Do not broaden automatic repair merely to increase the number of fixes.

## Selection-aware export

### User benefit

One prominent Export action selects a sensible format from the selected object, while direct STEP,
STL, 3MF, and DXF actions remain available. Invalid selections are rejected before a misleading
save operation.

### Current support

`fmf_export.py` classifies selected FreeCAD objects, rejects reference-only geometry, chooses the
appropriate registered export filter, and delegates file generation to FreeCAD's native
`Std_Export` command.

### Preservation requirement

Keep selection validation, format-specific commands, and native FreeCAD export as the actual file
writer.

## Studio viewport and Modern Zinc theme

### User benefit

Users can apply a cohesive studio-like canvas, lighting, antialiasing, and dark visual theme, then
restore their prior appearance.

### Current support

`fmf_viewport.py` backs up affected values before applying viewport presets or the bundled QSS,
and exposes commands to apply or restore them.

### Preservation requirement

These remain optional appearance features with exact backup/restoration. They must not become a
prerequisite for modelling features.

## Shared utilities and terminology

### User benefit

Common inspection, measurement, selection, properties, units, and output functions appear in
consistent places and use labels familiar to Fusion users, while still invoking FreeCAD's native
commands where appropriate.

### Current support

The declarative layouts reuse native FreeCAD commands under curated labels, sizes, icons, dropdown
groups, and source-workbench mappings. `command-map.md` records the Fusion-to-FreeCAD decisions.

### Preservation requirement

Retain the semantic grouping and familiar labels while keeping the underlying native command
behavior accessible and identifiable.

## Non-regression gates for an architectural refactor

Before replacing the current startup/layout architecture, capture and pass tests for:

1. all four workbench layouts and every pinned/overflow command;
2. feature-parity matrices against the corresponding stock workbenches, including documented
   alternate paths for intentionally omitted commands;
3. entry into and exit from sketch edit;
4. panel ordering, drag reordering, persistence, responsive tiers, and panel reset;
5. adaptive ranking, decay, pins, and bounded writes;
6. command search and its activation shortcut;
7. shortcut preset application, conflict handling, and exact restoration;
8. navigation, model tree, theme, viewport, and startup-workbench restoration;
9. stock-workbench visibility opt-in, persistence, and exact restoration;
10. every FMF modelling command, including transaction/Undo behavior;
11. multi-region and mirrored sketch profile selection through Pad;
12. Fillet/Chamfer event routing, focus, live preview, and Enter commit;
13. clean install, first activation, upgrade, Reapply, Restore, failed startup, disable, uninstall,
    and reinstall;
14. startup time and workbench-switch latency; and
15. package self-containment on every claimed platform.

The refactor should be staged behind compatibility boundaries so the current implementation remains
available until the replacement passes this matrix in real FreeCAD, not only with test doubles.
