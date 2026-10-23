# FusionMyFreeCAD study implementation plan

**Date:** 2026-10-23  
**Status:** Phase A automated implementation complete; Phase B implemented and awaiting live FreeCAD verification  
**Scope:** FusionMyFreeCAD only. `Upstream Reference/FusionMyFreeCAD Study` and its bundled repositories remain read-only research inputs.  
**Version rule:** This plan does not authorize changing the main project version.

## Decision

Keep FMF as one curated, declarative workflow layer projected onto native FreeCAD commands and document state. Reimplement only the useful behavior patterns from the study behind FMF-owned contracts. Do not replace FreeCAD-Ribbon with NeoRibbon, replace the Qt Widgets shell with FreeCAD-Nxt, derive the four curated workbenches from toolbar discovery, or ship competing search and personalization engines.

The study's architectural conclusion is sound, but the current roadmap overstates one completed item: FMF has a `NativeActionAdapter`, yet production runtime use currently resolves actions only for shortcut handling. The ribbon renderer has not been shown to subscribe every rendered button to authoritative native enabled/checked state. Closing that integration gap and qualifying lifecycle restoration should precede new user-facing layers.

## Current-state findings

### Keep

- Four FMF-owned workbenches with curated, Fusion-familiar layouts.
- Stable command IDs and JSON layout manifests as the source of workflow semantics.
- Native `QAction` objects as the authority for enabled, checked, and invocation state.
- Native FreeCAD document state, transactions, and Undo.
- Adaptation only in the bounded FREQUENT region; core spatial positions remain stable.
- SearchBar's command, object, and preference coverage until a measured replacement proves parity.
- FMF's write-once pre-FMF baseline and reversible preference management.

### Correct before expanding

- Treat the native-action adapter as **foundation complete, renderer integration pending**, not fully shipped end to end.
- Finish the current personalization/lifecycle verification before adding more observers or Qt event filters.
- Replace roadmap references to nonexistent `freecad/FMF/...` paths with the repository's actual flat-module paths unless a separate package migration is proposed and approved.
- Replace stale “1.8.0 behavioral baseline” wording with a version-neutral “current shipped behavioral baseline” at the next roadmap edit. This is documentation only and must not change the project version.

## Sequenced implementation

### Phase A — Action fidelity and lifecycle safety (Now)

#### A1. Bind ribbon widgets to native actions

Add one FMF-owned binding registry at the ribbon renderer boundary. When a ribbon button is created or rebuilt, bind it to the command's current native action and synchronize:

- enabled state;
- checked state for checkable actions;
- exactly-once invocation through the native action;
- action replacement or destruction;
- disposal when the widget, panel, workbench context, or FMF runtime is torn down.

Use `fmf_actions.py` rather than adding a second resolver. The likely integration seam is the existing `QToolButton.setDefaultAction(...)` construction path in the bundled FreeCAD-Ribbon adapter. Keep the generic vendor code change minimal: expose or call an FMF hook only when FMF is active, with no behavior change for standalone Ribbon use.

**Acceptance gates**

- A checkable command toggled from ribbon, menu, shortcut, or native code displays the same checked state everywhere.
- Disabled native actions cannot be invoked from the ribbon.
- One click causes exactly one native invocation.
- Replacing or destroying a native action does not leave a stale callback.
- Fifty ribbon rebuild/workbench-switch cycles leave no duplicate subscriptions or invocations.
- FMF disable/uninstall disposes all FMF bindings while leaving native actions and unrelated workbenches intact.

**Tests**

- Extend `tests/test_actions.py` for replacement, destruction, duplicate-subscription, and disposal cases.
- Add renderer-boundary tests using the fake FreeCAD/Qt environment.
- Add one real-FreeCAD disposable-profile probe covering menu, shortcut, ribbon, and native-code toggles.

#### A2. Finish restoration qualification

Do not add another restoration mechanism. Extend the existing state service and fixtures to cover only missing cases identified by the study:

- normal enable/disable;
- shutdown while FMF is active;
- Addon Manager disable marker on next startup;
- startup interruption/failure fallback;
- clean and heavily customized profiles;
- repeated enable/disable cycles without an empty ribbon or hidden unrelated workbenches.

**Gate:** every FMF-managed key restores to its captured baseline, unmanaged keys remain byte-for-byte unchanged, and no persisted empty-toolbar/ribbon state is produced.

Phase B must not start until A1's automated checks pass and A2 has at least one successful real-FreeCAD disposable-profile run.

### Phase B — One catalog and measurable discovery (Next)

#### B1. Define the catalog contract before changing the search UI

Create one metadata contract keyed by canonical command/object/preference/help IDs. Command entries should support:

- canonical FreeCAD name and command ID;
- Fusion alias terms used for discovery only;
- workbench and current availability;
- active and conflicting shortcuts;
- object, preference, and help targets where applicable;
- a concise reason when a result cannot currently run.

Aliases never become invocation identities. Search, shortcut preview, contextual guidance, and future diagnostics consume this catalog; none owns a private duplicate.

#### B2. Run a SearchBar/ToolSeek bakeoff

Build a versioned corpus of at least 30 queries covering exact names, Fusion terms, abbreviations, misspellings, other-workbench commands, unavailable commands, document objects, preferences, and help intents. Measure reciprocal rank, top-three success, false positives, explanation quality, conflict visibility, cold/warm latency, crash/lifetime behavior, and packaging cost.

Retain one provider. ToolSeek's ranking ideas may be reimplemented cleanly, but a command-only provider fails unless object and preference discovery remain available. Do not vendor a second palette merely for comparison.

**Gate:** the selected provider meets or exceeds current capability coverage and improves the agreed ranking/latency measures without new startup or shutdown failures.

#### B3. Make shortcut activation conflict-safe

Use the same catalog/action inventory to preview conflicts before applying FMF's shortcut preset. Cancel must be a no-op; acceptance applies explicit resolutions; restore returns the exact prior bindings. This should consume catalog metadata rather than create a separate shortcut scanner.

### Phase C — Progressive personalization

Consolidate pins, FREQUENT ranking, hidden curated panels, user order, and related deltas behind one service keyed by stable IDs. Preserve opinionated defaults and keep unknown IDs during upgrades rather than deleting them.

Add discoverable controls in this order:

1. pin/unpin in existing overflow surfaces;
2. hide/show for curated panels with immediate preview;
3. reorder curated panels with Reset restoring the manifest default.

Do not permit automatic reordering outside FREQUENT. Do not create another usage store. Compact three-row packing is a separate experiment, not a prerequisite: prototype it in one Sketch panel only after personalization is stable, and remove it unless it demonstrates benefit with no clipping or inaccessible commands across the width/DPI/theme/locale matrix.

**Gate:** state survives restart, migrates without loss, resets exactly, ignores temporarily unknown IDs safely, and leaves no duplicate observers after repeated context switches.

### Phase D — Understand and recover

#### D1. Read-only selection provenance

Start with a side-effect-free selection-context service. For a selected face, edge, vertex, or tree feature, return an explicit result of `exact`, `ambiguous`, or `unavailable`, plus the owning feature/body when supportable. Cover direct, linked, consumed-sketch, transformed/patterned, external-geometry, deleted, and recomputed cases.

Expose one small breadcrumb/highlight path using existing Qt Widgets and native tree/selection APIs. Do not claim that UI provenance makes topological naming stable.

#### D2. One actionable diagnostic

Implement one bounded case: an open sketch wire that blocks a solid-producing operation. Keep four outputs separate: observed condition, likely cause, proposed action, and expected postcondition. Detection must never mutate the document. Applying the proposal requires confirmation, one named transaction, visible postcondition, and one Undo restoring the prior model.

#### D3. Fixed contextual actions

Only after D1 predicates are proven, prototype at most five fixed-position actions for planar-face and sketch selections. The same semantic state must yield the same order; usage data may not rotate or reorder these actions. Always retain the complete ribbon/search route.

**Gate:** negative fixtures do not misfire, ambiguous provenance is surfaced rather than guessed, and the measured journey improves without increasing modeling errors.

### Phase E — Semantic visuals and accessibility

Define semantic roles for selection, preselection, focus, construction, reference, disabled, warning, error, and overlay content. Map roles to theme values rather than hard-coding widget-specific colors. Require keyboard focus visibility, accessible names, and non-color cues for critical states.

Test light/dark themes at 100%, 125%, 150%, 175%, and 200% scaling and representative widths of 1024, 1280, 1450, 1750, and 2560 pixels. OpenTheme is a source of validation ideas, not FMF branding or a required runtime dependency.

**Gate:** no clipped/inaccessible command, critical states remain distinguishable without color alone, overlays stay inside available screen geometry, and prior theme preferences restore exactly.

### Phase F — Unsupported-workbench fallback (Later, demand-driven)

Only if user evidence shows demand, offer an explicitly enabled and visibly “uncurated” fallback generated from native toolbar items for unsupported workbenches. It must have zero effect on FMF Design, Part, Sketch, and Surface and must fall back cleanly to native UI. It is not a fifth generic FMF product model.

## Explicitly rejected for this cycle

- Replacing FreeCAD-Ribbon with NeoRibbon or shipping both engines.
- A full QtQuick/QML shell or FreeCAD core fork.
- Deriving FMF's four curated workbenches from incidental toolbar order.
- Two active search palettes, ranking stores, or personalization stores.
- Automatic model repair or repairs without preview and one-step Undo.
- Usage-driven movement of core ribbon or contextual-action positions.
- Production telemetry or synchronized usage profiles.
- New runtime dependencies when FreeCAD/PySide and the standard library suffice.
- Main project version changes without explicit owner approval.

## Verification and release gates

Every phase must preserve the current shipped journeys and add deterministic evidence before being marked shipped:

1. Unit/contract tests for pure logic and lifecycle ownership.
2. Fake-FreeCAD integration tests for action, preference, and observer behavior.
3. Real-FreeCAD disposable-profile probes for Qt lifetime, visual state, and restoration.
4. `ruff check .`, `ruff format --check .`, and the complete project pytest suite.
5. Privacy/provenance scans and package validation.
6. A changed-file diff review proving that Upstream Reference was not modified.

Cross-platform visual behavior, latency, long-session Qt lifetime, predicate precision, and journey improvements remain unverified until their experiments run. Static inspection is not proof of those outcomes.

## Roadmap changes to make after approval

- Insert A1 ahead of search and personalization expansion.
- Reword the shipped adapter item as “adapter foundation complete; ribbon integration pending.”
- Make restoration qualification a gate for all new Qt observer/filter work.
- Keep the existing search, provenance, context-action, visual, and beta tasks, but sequence them as B through E above.
- Correct stale baseline wording and nonexistent implementation paths without changing the project version.
- Keep the compact-group and unsupported-workbench work as experiments with removal gates, not promised features.

## Evidence reviewed

Local study:

- `Upstream Reference/FusionMyFreeCAD Study/THE_IDEAL_ARCHITECTURE.md`
- `Upstream Reference/FusionMyFreeCAD Study/ANALYTICAL_FOUNDATIONS_AND_BENCHMARKS.md`
- `Upstream Reference/FusionMyFreeCAD Study/ASSET_SUITE_IMPLEMENTATION_PLAN.md`
- `Upstream Reference/FusionMyFreeCAD Study/research/BROAD_FREECAD_UX_PRIOR_ART_2026-10-09.md`
- `Upstream Reference/FusionMyFreeCAD Study/research/NEORIBBON_TECHNICAL_REVIEW.md`
- Local source snapshots and licensing/provenance matrix in that study

Current external primary sources checked:

- [NeoRibbon](https://github.com/robdevtech/NeoRibbon) — useful action-state, compact-layout, pin, and restoration behavior; not an FMF taxonomy replacement.
- [ToolSeek](https://github.com/robdevtech/ToolSeek) — useful ranking and shortcut-conflict behavior; command-only scope requires a parity bakeoff.
- [FreeCAD-Nxt](https://github.com/obelisk79/FreeCAD-Nxt) — useful provenance/diagnostic hypotheses; explicitly experimental and not a basis for replacing FMF's shell.
- [OpenTheme](https://github.com/obelisk79/OpenTheme) — useful semantic role and contrast-validation ideas.
- [FreeCAD interface customization](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Interface_Customization.md) — native commands, toolbars, and shortcuts remain the platform authority.
- [FreeCAD PieMenu workbench](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/PieMenu_Workbench.md) — supports a small optional contextual experiment, not a ribbon replacement.
- [FreeCAD tree view](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Tree_view.md) and [selection view](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Selection_view.md) — native primitives to reuse for provenance and model comprehension.

## Approval boundary

Approval of this plan should authorize **Phase A only** as the first implementation slice. Later phases retain their own gates and should not begin merely because Phase A is approved.
