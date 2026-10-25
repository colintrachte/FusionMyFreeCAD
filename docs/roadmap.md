# FMF — Product roadmap

This roadmap protects FMF's multi-workbench product first. Official Addon Index inclusion is an
optional outcome, not permission to remove product-defining benefits. The read-only studies under
`<upstream-reference>` inform decisions but are never modified. The main project
version remains 1.9.0 unless the owner explicitly approves a change.

## Target outcome

Deliver FMF-owned Design, Part, Sketch, and Surface workbenches that are superior everyday
alternatives to their stock equivalents while retaining one-package setup, complete command access,
Fusion-familiar workflows, FMF modelling enhancements, exact recovery, and good performance. Users
use the FMF workbench family while enabled and the corresponding stock family while disabled. The
visibility transition is reversible and never removes the stock implementations.

## Product gates

- `docs/dev-guide/CURRENT-FEATURE-INVENTORY.md` is the preservation baseline.
- Curated Fusion semantics outrank native toolbar order; adaptation stays inside FREQUENT panels.
- Native FreeCAD actions and document state remain authoritative.
- Model changes are explicit, explainable, transactional where supported, and undoable.
- The pre-FMF profile baseline is captured once and never overwritten by FMF state.
- No roadmap task modifies upstream reference files or changes the main project version.

---

## Now — Harden the shipped workbench family

- [ ] **Score 5 🥇 · Class 2 — Maintain the current shipped behavioral baseline**

  **ID:** task_a1020000000000000000000000000002
  **Status:** Continuous validation — static/source-build probes and owner acceptance captured; remaining journeys are ongoing dogfood evidence, not migration blockers
  **Outcome:** Keep repeatable user journeys, profile mutations, reference screenshots, startup time, switching latency, search latency, and recovery results current as field issues are discovered.
  **Work mode:** Forge + Steward
  **Execution size:** Large
  **Uncertainty:** Medium
  **Protected behavior:** One-package install, four layouts, sketch transitions, search, adaptive panels, shortcuts, modelling helpers, and restoration remain available.
  **Acceptance:** Owner-accepted workbench and sketch behavior remains protected; release qualification covers clean/custom profiles, all four contexts, modelling helpers, export, lifecycle, and recovery.
  **Expected evidence:** A checked-in journey specification and machine-readable baseline results repeatable after every migration slice.
  **Implement:** `docs/dev-guide/BASELINE-JOURNEYS.md` · `tests/fixtures/fmf-baseline.json` · `tools/benchmark_fmf.py`
  **Context:** `docs/dev-guide/CURRENT-FEATURE-INVENTORY.md` · `Resources/FMF/layout-v3.json` · `fmf_bootstrap.py` · `Resources/FMF/runtime.py`
  **Route:** claude
  **Context Load:** 1236
  **Chars:** ~176,522 text total (largest: fmf_bootstrap.py ~61,806) — exceeds chatgpt's ~5,000-char inline-paste budget; that file can't go to chatgpt at all
  **Prefer after:** task_a1010000000000000000000000000001

- [ ] **Score 5 🥇 · Class 2 — Qualify native action fidelity and lifecycle guards**

  **ID:** task_a1060000000000000000000000000006
  **Status:** Implementation and automated verification complete; real-FreeCAD disposable-profile smoke check pending
  **Outcome:** Bind FMF ribbon buttons to authoritative native action state without owning invocation, dispose every binding deterministically, restore captured native toolbar visibility before shutdown persistence, and recover immediately when Addon Manager writes `ADDON_DISABLED`.
  **Work mode:** Forge + Steward
  **Execution size:** Medium
  **Uncertainty:** Medium
  **Protected behavior:** Qt's native `setDefaultAction()` remains the invocation path; disabling FMF still switches workbench families without dismantling Ribbon.
  **Acceptance:** Menu, shortcut, ribbon, and native-code state remain synchronized; disabled actions cannot be invoked; fifty rebuilds create no duplicate callbacks; widget/action destruction and FMF disable leave no stale binding; shutdown and Addon Manager disable preserve usable native chrome.
  **Evidence:** Action-registry, renderer-hook, shutdown-visibility, stop-file, and teardown tests pass with the full suite; source-only FreeCAD reference checkout cannot provide the remaining live Qt runtime evidence.
  **Implement:** `fmf_actions.py` · `fmf_bootstrap.py` · `bundled-addons/FreeCAD-Ribbon/FCBinding.py`
  **Context:** `tests/test_actions.py` · `tests/test_startup.py` · `tests/test_package.py` · `docs/dev-guide/ACTIVATION-AND-RESTORATION.md`
  **Read:** `<fmf-study>/ANALYTICAL_FOUNDATIONS_AND_BENCHMARKS.md` · `<fmf-study>/upstream_repos/NeoRibbon/freecad/NeoRibbon/bootstrap.py`
  **Blocked by:** A real FreeCAD 1.1 GUI runtime for the disposable-profile smoke check

- [ ] **Score 5 🥇 · Class 2 — Isolate FMF work from FreeCAD hot paths**

  **ID:** task_a1070000000000000000000000000007
  **Status:** In verification — unbounded startup work and independent transition listeners are removed; the real-FreeCAD 50-transition timing/state gate remains
  **Outcome:** Make FMF overhead attributable by prohibiting startup network and discovery activation, scoping event filters, and routing each host workbench change through one generation-based coordinator.
  **Work mode:** Forge + Steward
  **Execution size:** Large
  **Uncertainty:** Medium
  **Protected behavior:** The Ribbon Sketch/Design second synchronization pass, explicit user workbench changes, search, adaptive panels, shortcuts, and live enable/disable remain intact.
  **Acceptance:** Normal startup performs no network or discovery-driven activation; one FMF-owned host signal connection orders Ribbon, runtime, and SearchBar phases; stale generations do no work; phase failure does not block later phases; fifty transitions preserve correct panels with no rising callback count.
  **Evidence:** Host-isolation, focus, transition ordering/coalescing, teardown, extracted-archive startup, and full automated regression tests pass; phase timing and lifecycle counters are exposed for the live probe.
  **Implement:** `fmf_transitions.py` · `Resources/FMF/runtime.py` · `bundled-addons/FreeCAD-Ribbon/FCBinding.py` · `bundled-addons/SearchBar/InitGui.py`
  **Context:** `research/freecad-integration-performance-plan-2026-10-24.md` · `tools/probe_host_isolation.py` · `tools/probe_focus_performance.py` · `tests/test_transitions.py`
  **Next:** Replace warm-path global action scans with the canonical action registry, after the live transition gate passes.
  **Blocked by:** A real FreeCAD GUI run of the documented 50-transition smoke/latency probe

---

## Next — Product safeguards and release evidence

- [x] **Score 5 🥇 · Class 2 — Register four namespaced FMF workbench shells**

  **ID:** task_b2010000000000000000000000000001
  **Status:** Shipped — deterministic checks and live FreeCAD registration/visibility verification passed
  **Outcome:** Register FMF Design, Part, Sketch, and Surface as distinct, stable workbenches while retaining the stock workbenches as reversible alternatives.
  **Work mode:** Forge + Steward
  **Execution size:** Large
  **Uncertainty:** High
  **Protected behavior:** Stock workbenches remain registered and usable whenever FMF is disabled.
  **Acceptance:** Four stable IDs/classes/icons register without mutating or unregistering stock workbench definitions.
  **Evidence:** Automated registration tests passed; FreeCAD 1.1.1 displayed all four FMF workbenches and switched between FMF and stock families without restart.
  **Implement:** `package.xml` · `InitGui.py` · `fmf_workbenches.py` · `fmf_bootstrap.py`
  **Context:** `docs/dev-guide/workbench-parity.md` · `docs/dev-guide/ACTIVATION-AND-RESTORATION.md`
  **Read:** `<freecad>/src/Gui/FreeCADGuiInit.py` · `<freecad>/src/Gui/Workbench.cpp`
  **Route:** paid-ai
  **Context Load:** 254
  **Chars:** ~28,179 text total (largest: docs/dev-guide/workbench-parity.md ~22,906) — exceeds chatgpt's ~5,000-char inline-paste budget; that file can't go to chatgpt at all
  **Blocked by:** task_a1030000000000000000000000000003 · task_a1040000000000000000000000000004 · task_a1050000000000000000000000000005

- [x] **Score 5 🥇 · Class 2 — Project all curated layouts into owned workbenches**

  **ID:** task_b2020000000000000000000000000002
  **Status:** Shipped — automated parity/migration checks passed and the owner accepted all four workbenches for continued daily use
  **Outcome:** Preserve every pinned, overflow, dropdown, responsive, adaptive, personalization, label, icon, and size behavior inside the corresponding FMF-owned workbench.
  **Work mode:** Steward
  **Execution size:** Large
  **Uncertainty:** High
  **Protected behavior:** No current layout capability disappears; adaptation remains confined to FREQUENT.
  **Acceptance:** Parity checks are complete and baseline journeys are equivalent or better in all four workbenches.
  **Evidence:** Layout contracts and migration tests pass; subsequent discrepancies are handled as field regressions without reopening the owned-workbench architecture.
  **Implement:** `fmf_bootstrap.py` · `Resources/FMF/runtime.py` · `Resources/FMF/layout-v3.json` · `Resources/FMF/layout-manifest.json`
  **Context:** `fmf_workbenches.py` · `fmf_actions.py` · `tests/fixtures/fmf-baseline.json`
  **Route:** claude
  **Context Load:** 1430
  **Chars:** ~204,352 text total (largest: fmf_bootstrap.py ~61,806) — exceeds chatgpt's ~5,000-char inline-paste budget; that file can't go to chatgpt at all
  **Blocked by:** task_b2010000000000000000000000000001

- [x] **Score 5 🥇 · Class 2 — Preserve sketch-edit context transitions**

  **ID:** task_b2030000000000000000000000000003
  **Status:** Shipped — automated transition tests passed and the owner accepted sketch creation/editing in normal use
  **Outcome:** Enter and leave sketch editing through FMF Design and Sketch without losing origin-plane selection, body context, tree state, shortcuts, or return context.
  **Work mode:** Forge + Steward
  **Execution size:** Large
  **Uncertainty:** High
  **Protected behavior:** Create Sketch delegates attachment to Part Design and changes ribbon context only after the sketch opens.
  **Acceptance:** New/existing, attached/unattached, cancel, finish, close, failure, and repeated edit paths have no duplicate observers or shortcuts.
  **Evidence:** Observer tests and owner dogfood acceptance; future transition defects remain release-blocking regressions when reported.
  **Implement:** `fmf_bootstrap.py` · `Resources/FMF/runtime.py` · `fmf_workbenches.py`
  **Context:** `tests/test_startup.py` · `tests/test_runtime.py` · `docs/dev-guide/BASELINE-JOURNEYS.md`
  **Route:** claude
  **Context Load:** 868
  **Chars:** ~144,658 text total (largest: fmf_bootstrap.py ~61,806) — exceeds chatgpt's ~5,000-char inline-paste budget; that file can't go to chatgpt at all
  **Blocked by:** task_b2020000000000000000000000000002

- [ ] **Score 5 🥇 · Class 2 — Implement atomic first-run activation**

  **ID:** task_b2040000000000000000000000000004
  **Status:** Deferred — conditional on pursuing an Addon Index opt-in flow; current install-and-go activation remains the product default
  **Outcome:** Present a branded **Activate FMF** page that atomically applies the complete experience; decline changes nothing and activation remains available later.
  **Work mode:** Forge + Steward
  **Execution size:** Medium
  **Uncertainty:** Medium
  **Protected behavior:** One package and one activation action produce the coherent experience.
  **Acceptance:** Activation completes or rolls back; interruption recovers; no version change occurs.
  **Expected evidence:** Transition tests, failure injection, and first-run walkthrough.
  **Implement:** `fmf_activation.py` · `Resources/FMF/activation.ui` · `fmf_bootstrap.py`
  **Context:** `docs/dev-guide/ACTIVATION-AND-RESTORATION.md` · `README.md`
  **Route:** kimi
  **Context Load:** 376
  **Chars:** ~75,174 text total (largest: fmf_bootstrap.py ~61,806) — exceeds chatgpt's ~5,000-char inline-paste budget; that file can't go to chatgpt at all
  **Prefer after:** task_c3050000000000000000000000000005

- [x] **Score 5 🥇 · Class 2 — Add reversible stock-workbench visibility controls**

  **ID:** task_b2050000000000000000000000000005
  **Status:** Shipped — reversible state tests and live no-restart selector switching passed
  **Outcome:** Enabling FMF hides the corresponding stock workbenches; disabling FMF unhides them and hides the FMF family.
  **Work mode:** Steward
  **Execution size:** Medium
  **Uncertainty:** Medium
  **Protected behavior:** The Ribbon remains active, unrelated workbench tabs are untouched, and stock workbenches are never removed or rewritten.
  **Acceptance:** Repeated enable/disable cycles expose exactly one of the four corresponding workbench families, preserve unrelated visibility choices, avoid unregistering workbenches, and never autoload a hidden FMF workbench.
  **Evidence:** Automated lifecycle/state tests passed; live FreeCAD 1.1.1 verification confirmed immediate switching without restart and successful right-click customization while FMF was disabled.
  **Implement:** `fmf_bootstrap.py` · `fmf_workbenches.py` · `bundled-addons/FreeCAD-Ribbon/FCBinding.py` · `Resources/FMF/preferences.ui`
  **Context:** `docs/dev-guide/ACTIVATION-AND-RESTORATION.md` · `tests/test_install.py` · `tests/test_runtime.py`
  **Route:** kimi
  **Context Load:** 323
  **Chars:** ~80,629 text total (largest: fmf_bootstrap.py ~61,806) — exceeds chatgpt's ~5,000-char inline-paste budget; that file can't go to chatgpt at all

- [ ] **Score 5 🥇 · Class 2 — Make shortcut activation conflict-safe**

  **ID:** task_b2060000000000000000000000000006
  **Status:** In verification — conflict planning, cancel/accept, exact restoration, menu access, and diagnostics are automated; live FreeCAD keyboard verification remains
  **Outcome:** Retain one-action application of the full Fusion preset while previewing occupied bindings, supporting explicit resolution, and restoring prior bindings exactly.
  **Work mode:** Forge + Steward
  **Execution size:** Medium
  **Uncertainty:** Medium
  **Protected behavior:** The complete preset and Verify UI reporting remain available.
  **Acceptance:** Cancel changes nothing; accept applies chosen resolutions; Restore returns exact prior bindings.
  **Evidence:** The shared catalog now produces a non-mutating plan; occupied keys are not changed until **FMF > Review FMF Shortcuts** is accepted; cancel is a no-op; the exact prior action bindings are persisted and restored. The debug pass added late-loaded-command snapshots, unnamed-action restoration, live disable restoration, and disable/re-enable service reinstallation coverage. Automated conflict-matrix and lifecycle tests pass. Real-FreeCAD keyboard verification remains.
  **Implement:** `fmf_catalog.py` · `Resources/FMF/runtime.py` · `Resources/FMF/preferences.ui` · `fmf_bootstrap.py`
  **Context:** `command-map.md` · `docs/dev-guide/COMMAND-CATALOG.md` · `tests/test_catalog.py` · `tests/test_runtime.py`
  **Read:** `<fmf-study>/upstream_repos/ToolSeek/freecad/ToolSeek/prefs.py`
  **Route:** paid-ai
  **Context Load:** 1100
  **Chars:** ~157,169 text total (largest: fmf_bootstrap.py ~61,806) — exceeds chatgpt's ~5,000-char inline-paste budget; that file can't go to chatgpt at all
  **Prefer after:** task_a1040000000000000000000000000004

- [ ] **Score 4 🥇 · Class 2 — Consolidate personalization and scope runtime observers**

  **ID:** task_b2070000000000000000000000000007
  **Status:** In verification — service-state diagnostics, teardown evidence, leak checks, static benchmark, and coordinated workbench transitions are complete; live startup/switch timing remains
  **Outcome:** Give stable-ID personalization one owner and activate expensive scans, filters, observers, and adaptive rewrites only in their owning FMF contexts.
  **Work mode:** Forge + Steward
  **Execution size:** Large
  **Uncertainty:** High
  **Protected behavior:** Decayed ranking, pins, order, reset, dress-up input, multi-region profiles, dock refresh, and recovery remain intact.
  **Acceptance:** State migrates without loss; installation/teardown is idempotent; no duplicate callbacks remain; startup/switching meet baseline.
  **Expected evidence:** Migration/lifecycle tests, callback counts, persistence tests, and timings.
  **Implement:** `fmf_personalization.py` · `Resources/FMF/runtime.py` · `fmf_bootstrap.py` · `fmf_dressup_tools.py` · `fmf_parameters_dock.py`
  **Context:** `Resources/FMF/layout-manifest.json` · `tests/test_runtime.py` · `tests/test_install.py`
  **Route:** claude
  **Context Load:** 1870
  **Chars:** ~233,693 text total (largest: fmf_bootstrap.py ~61,806) — exceeds chatgpt's ~5,000-char inline-paste budget; that file can't go to chatgpt at all

---

## Later — Prove superiority and choose distribution

- [ ] **Score 4 🥇 · Class 2 — Unify the command catalog and benchmark search**

  **ID:** task_c3010000000000000000000000000001
  **Status:** In verification — catalog contract, 32-query corpus, deterministic bakeoff, SearchBar alias integration, and provider decision are complete; live Qt latency/lifetime verification remains
  **Outcome:** Define one catalog for commands, Fusion aliases, shortcuts, availability, objects, preferences, and help; compare SearchBar and ToolSeek on 30 queries and retain one provider.
  **Work mode:** Forge
  **Execution size:** Large
  **Uncertainty:** High
  **Acceptance:** Results cover recall, top-three relevance, explanations, cold/warm latency, stability, coverage, and packaging impact.
  **Evidence:** The checked-in corpus reports the FMF ranker at 1.000 top-three success and 0 misses versus the substring baseline at 0.875 and 2 misses on the current machine. SearchBar remains the sole UI provider and consumes catalog aliases; toolbar command IDs now survive cache serialization, and a one-time schema refresh replaces stale pre-catalog caches. No ToolSeek runtime or dependency is shipped.
  **Implement:** `fmf_catalog.py` · `Resources/FMF/command-catalog.json` · `bundled-addons/SearchBar/SearchBox.py` · `docs/dev-guide/COMMAND-CATALOG.md` · `tests/fixtures/search-corpus.json` · `tools/benchmark_search.py`
  **Context:** `bundled-addons/SearchBar/` · `command-map.md`
  **Read:** `<fmf-study>/upstream_repos/ToolSeek/freecad/ToolSeek/` · `<fmf-study>/THE_IDEAL_ARCHITECTURE.md`
  **Route:** paid-ai
  **Context Load:** 46
  **Chars:** ~6,549 text total (largest: command-map.md ~6,549) — exceeds chatgpt's ~5,000-char inline-paste budget; that file can't go to chatgpt at all
  **Prefer after:** task_b2020000000000000000000000000002

- [ ] **Score 4 🥇 · Class 2 — Add provenance and actionable diagnostic foundations**

  **ID:** task_c3020000000000000000000000000002
  **Status:** Defined
  **Outcome:** Provide selected geometry to owning feature/body breadcrumbs and one diagnostic journey with explicit evidence, preview, one transaction, visible result, and one-step Undo.
  **Work mode:** Forge + Steward
  **Execution size:** Large
  **Uncertainty:** High
  **Protected behavior:** Repair References remains conservative; ambiguity is reported, never guessed.
  **Acceptance:** Provenance distinguishes exact/ambiguous/unavailable and direct/linked/patterned cases; diagnostic detection works without applying a fix.
  **Expected evidence:** Geometry fixtures, ambiguity cases, transaction tests, and a measured journey.
  **Implement:** `fmf_selection_context.py` · `fmf_provenance.py` · `fmf_diagnostics.py`
  **Context:** `fmf_repair_tools.py` · `fmf_sketch_tools.py` · `fmf_common.py`
  **Read:** `<fmf-study>/upstream_repos/FreeCAD-Nxt/freecad/nxt/tree/` · `<fmf-study>/THE_IDEAL_ARCHITECTURE.md`
  **Route:** paid-ai
  **Context Load:** 1067
  **Chars:** ~133,436 text total (largest: fmf_sketch_tools.py ~103,017) — exceeds chatgpt's ~5,000-char inline-paste budget; that file can't go to chatgpt at all
  **Prefer after:** task_b2070000000000000000000000000007

- [ ] **Score 3 🥈 · Class 2 — Prototype fixed selection-context actions**

  **ID:** task_c3030000000000000000000000000003
  **Status:** Deferred — provenance foundation required
  **Outcome:** Test at most five fixed-position actions for planar-face and sketch selections using explicit predicates and a complete list/search fallback.
  **Work mode:** Forge
  **Execution size:** Medium
  **Uncertainty:** High
  **Acceptance:** Positions never rotate; negative fixtures do not misfire; measured command time improves without more errors.
  **Expected evidence:** Predicate tests and comparative journey results.
  **Implement:** `fmf_context_actions.py`
  **Context:** `docs/dev-guide/CURRENT-FEATURE-INVENTORY.md` · `fmf_selection_context.py` · `docs/dev-guide/BASELINE-JOURNEYS.md`
  **Read:** `<fmf-study>/upstream_repos/PieMenu/piemenu/`
  **Route:** paid-ai
  **Context Load:** 114
  **Chars:** ~22,799 text total (largest: docs/dev-guide/CURRENT-FEATURE-INVENTORY.md ~19,159) — exceeds chatgpt's ~5,000-char inline-paste budget; that file can't go to chatgpt at all
  **Blocked by:** task_c3020000000000000000000000000002

- [ ] **Score 4 🥇 · Class 2 — Define semantic visual and accessibility gates**

  **ID:** task_c3040000000000000000000000000004
  **Status:** Defined
  **Outcome:** Define semantic normal/hover/focus/selected/disabled/warning/error/construction/reference roles with contrast and non-color checks.
  **Work mode:** Forge + Steward
  **Execution size:** Medium
  **Uncertainty:** Medium
  **Protected behavior:** Modern Zinc and Studio View remain optional and exactly restorable.
  **Acceptance:** Light/dark themes preserve focus and state distinctions at 100–200% scaling.
  **Expected evidence:** Automated contrast report and human screenshot matrix.
  **Implement:** `Resources/Themes/modern_zinc.qss` · `tools/check_theme_contrast.py` · `docs/dev-guide/VISUAL-SEMANTICS.md`
  **Context:** `fmf_viewport.py` · `tests/test_aesthetic_spatial.py`
  **Read:** `<fmf-study>/upstream_repos/OpenTheme/scss/`
  **Route:** paid-ai
  **Context Load:** 145
  **Chars:** ~24,168 text total (largest: fmf_viewport.py ~13,990) — exceeds chatgpt's ~5,000-char inline-paste budget; that file can't go to chatgpt at all
  **Prefer after:** task_b2020000000000000000000000000002

- [ ] **Score 5 🥇 · Class 2 — Run cross-platform beta and restoration qualification**

  **ID:** task_c3050000000000000000000000000005
  **Status:** Defined — owned-workbench migration is owner-accepted; performance isolation gates and cross-platform participant coverage remain
  **Outcome:** Qualify owned workbenches with real users and FreeCAD installations before retiring the legacy path.
  **Work mode:** Steward
  **Execution size:** Large
  **Uncertainty:** High
  **Protected behavior:** The current shipped path remains until all gates pass.
  **Acceptance:** Test novice Fusion migrants, experienced FreeCAD users, clean/custom profiles, claimed platforms, and the full install-to-reinstall lifecycle; no critical/high corruption or core regression remains.
  **Expected evidence:** Beta matrix, issue disposition, journey comparisons, restoration diffs, and readiness checklist.
  **Implement:** `docs/dev-guide/BETA-QUALIFICATION.md`
  **Context:** `docs/dev-guide/CURRENT-FEATURE-INVENTORY.md` · `docs/dev-guide/BASELINE-JOURNEYS.md` · `docs/dev-guide/workbench-parity.md` · `docs/dev-guide/ACTIVATION-AND-RESTORATION.md`
  **Route:** kimi
  **Context Load:** 243
  **Chars:** ~48,588 text total (largest: docs/dev-guide/workbench-parity.md ~22,906) — exceeds chatgpt's ~5,000-char inline-paste budget; that file can't go to chatgpt at all
  **Blocked by:** task_b2020000000000000000000000000002 · task_b2030000000000000000000000000003 · task_b2040000000000000000000000000004 · task_b2050000000000000000000000000005 · task_b2070000000000000000000000000007

- [ ] **Score 3 🥈 · Class 1 — Decide distribution from evidence**

  **ID:** task_c3060000000000000000000000000006
  **Status:** Blocked — qualification required
  **Outcome:** Choose full Index submission, a separate Index-compatible variant, or continued GitHub/portable/reference distribution without weakening the primary product.
  **Work mode:** Steward
  **Execution size:** Small
  **Uncertainty:** Medium
  **Protected behavior:** No feature or project version changes merely to favor submission.
  **Acceptance:** Decision covers owned workbenches, optional hiding, dependencies, startup behavior, metadata, maturity, and maintenance obligations.
  **Expected evidence:** A dated decision record linked to qualification and then-current official documentation.
  **Implement:** `docs/dev-guide/DISTRIBUTION-DECISION.md`
  **Context:** `research/freecad-addon-index-readiness-2026-10-09.md` · `docs/dev-guide/BETA-QUALIFICATION.md`
  **Route:** gemini
  **Context Load:** 56
  **Chars:** ~18,823 text total (largest: research/freecad-addon-index-readiness-2026-10-09.md ~18,823) — exceeds chatgpt's ~5,000-char inline-paste budget; that file can't go to chatgpt at all
  **Blocked by:** task_c3050000000000000000000000000005

## Rejected directions

- One generic FMF workbench; unregistering workbenches or disabling the whole Ribbon as a visibility
  mechanism; generic toolbar discovery as the core taxonomy; wholesale merges of
  NeoRibbon, ToolSeek, PieMenu, FreeCAD-Nxt, or OpenTheme; a second usage database; adaptive
  movement outside FREQUENT; production telemetry; speculative QtQuick shell replacement; Git
  history rewriting; or an unapproved main-version change.

## Capacity and verification

Now is committed; Next is a vertical-slice architecture program; Later is evidence-driven. During
Next, reserve roughly 60% for owned-workbench migration, 30% for restoration/testing/technical
health, and 10% for urgent regressions. Verify with `python -m pytest tests -q`,
`python tools/validate_layout_contracts.py`, `python tools/validate_release_metadata.py 1.9.0`,
`ruff check .`, `ruff format --check .`, and PMT route/check commands.
