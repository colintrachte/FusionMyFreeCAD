# Research brief and ADR: Bound FMF's impact on FreeCAD performance

**Status:** Slices 1–2 implemented with automated verification; live Slice 2 transition gate pending
**Date:** 2026-10-24  
**Question:** How should FMF interact with upstream FreeCAD so that FMF cannot silently become the
cause of startup, focus, workbench-switch, idle, or modeling slowdowns?  
**Decision owner:** FMF maintainer  
**Method:** Static boundary audit of FMF and the checked-out upstream FreeCAD source; review of the
existing live profiles and prior FMF study; verification against current FreeCAD and Qt primary
documentation.

## Executive finding

FMF is not yet in a position to promise that a FreeCAD slowdown is not caused by FMF. The recent
focus fixes removed one proven source of severe input latency, but three architectural relationships
still let FMF amplify host work:

1. vendored Ribbon code performs synchronous network I/O while the Ribbon is constructed;
2. Ribbon/SearchBar discovery can activate workbenches to learn their commands, which executes
   host and third-party workbench initialization as a side effect;
3. FMF and its vendors independently react to the same `workbenchActivated` event and repeat global
   scans, style work, ribbon construction, toolbar visibility changes, and deferred tasks.

There are also two systemic risks: a global `QApplication` event filter is on every event-delivery
path, and vendored modules are inserted into the process-wide import namespace. These relationships
are avoidable. The recommended design is a thin, measured integration boundary: no startup network,
no discovery-by-activation, one post-activation coordinator, one generation-based action registry,
target-scoped event filters, and explicit ownership of every observer, signal, preference, and
widget mutation.

This is stronger than “optimize the slow functions.” It makes FMF overhead attributable and gives
CI/live probes a concrete failure condition before a regression ships.

## Observed evidence

### What is already good

- FMF already records named startup spans. One captured source-build session reports feature-command
  registration at 36.87 ms, SearchBar at 20.43 ms, and FreeCAD-Ribbon at 625.37 ms
  (`ai_poop/perf-live-profile-20261023-e/FMF-Diagnostics/events.jsonl`, lines 1-26).
- Workbench callbacks and SearchBar filters now have explicit teardown and idempotence. The repaired
  focus probe measured 0.0121 ms p95 for `ApplicationActivated`, 0.0194 ms p95 for a window-focus
  pair, one SearchBar filter, and zero title-bar replacements
  (`ai_poop/focus-guardrail-results.json`).
- Status writes are coalesced, and deferred work with the same label supersedes older pending work
  (`Resources/FMF/runtime.py:1164-1170`, `Resources/FMF/runtime.py:1218-1231`).
- FMF has an immutable preference baseline and explicit disable/restoration machinery. Those are the
  right foundations for host ownership and recovery.

### P0: synchronous network I/O occurs during Ribbon construction

`FCBinding` checks the latest Ribbon release while constructing the UI
(`bundled-addons/FreeCAD-Ribbon/FCBinding.py:639-655`). The helper calls
`urllib.request.urlopen(url)` with no timeout (`Standard_Functions_Ribbon.py:517-555`). This runs on
the GUI thread and can block startup for DNS, proxy, TLS, server, or captive-portal delays. It also
makes startup timing dependent on an unrelated upstream repository.

**Decision:** remove the version check from FMF's vendored startup path. FMF updates belong to
FreeCAD's Addon Manager/user action. There should be zero network calls in normal startup,
activation, focus, command discovery, and shutdown.

### P0: command discovery mutates host state by activating workbenches

Ribbon deliberately activates `WBtoLoadFirst` workbenches during construction and then restores the
last workbench (`FCBinding.py:1111-1129`). Its cache fallbacks activate a workbench merely to query
toolbars (`CacheFunctions.py:726-745`), and its full refresh loops through workbenches, calls
`Gui.updateGui()`, and activates each one (`CacheFunctions.py:769-805`). SearchBar contains the same
pattern (`bundled-addons/SearchBar/RefreshTools.py:22-58`). Historical live logs show this loading
CAM and BIM among 19 workbenches (`ai_poop/freecad-fmf-2.log:337-362`). The newer environment limit
reduces first-run scope, but the relationship remains unsafe and fallback paths can regress it.

Workbench activation is not a read. It imports code, creates actions and toolbars, changes host UI,
emits signals, and may initialize unrelated add-ons. A failure or slowdown in CAM, BIM, or another
add-on can therefore appear to be an FMF startup failure.

**Decision:** prohibit `Gui.activateWorkbench()` in discovery/cache code. FMF's four curated layouts
must be satisfied from manifests and canonical command IDs. Missing native actions remain unresolved
until FreeCAD naturally loads their owner; they must not trigger a hidden workbench switch. Explicit
user navigation and modeling commands may still activate a workbench when activation is the command's
intended behavior.

### P0: activation handlers run before FreeCAD finishes updating actions

Upstream FreeCAD emits `workbenchActivated(name)` and only then calls `updateActions(true)`
(`Upstream Reference/FreeCAD/src/Gui/MainWindow.cpp:1179-1181`). FreeCAD's action update is itself
timer-backed and ultimately walks command state (`MainWindow.cpp:2017-2053`). FMF's runtime handles
the signal immediately, changes UI mode and adaptive content, and schedules shortcut/navigation/tree
work (`Resources/FMF/runtime.py:1218-1231`). Ribbon separately handles the same signal, restyles the
tab bar, hides toolbars twice, updates tabs, and builds panels (`FCBinding.py:3657-3748`). SearchBar
also subscribes to the signal (`bundled-addons/SearchBar/InitGui.py:87-104`).

This ordering explains why the code needs repeated passes and retry timers: several consumers begin
while the host transition is incomplete. It also means a single user switch fans out into multiple
uncoordinated scans and layouts.

**Decision:** add one FMF transition coordinator. The direct signal handler should only capture the
new generation/name and arm one coalescing single-shot. The settled pass then performs ordered work:
host-state snapshot, ribbon context update, action-registry invalidation, adaptive refresh, and
status scheduling. Preserve the existing Sketcher second-pass correctness contract until a live
state-machine test proves it can be replaced; first consolidate ownership and measure each subspan.

### P1: the action cache still pays for a global generation scan

`_action_inventory()` sorts the complete result of `Gui.listCommands()` and includes the active
workbench in its key. Every workbench change therefore invalidates the cache and then calls
`main_window.findChildren(QAction)` (`Resources/FMF/runtime.py:96-103`). `write_runtime_status()`
also lists all commands (`runtime.py:1130-1157`). Meanwhile Ribbon resolves individual native
commands through `Gui.Command.get(...).getAction()`, which is the narrower boundary already used in
the vendored code (`FCBinding.py:1124-1129`, `CacheFunctions.py:747-767`).

**Decision:** create one canonical action registry consumed by ribbon binding, shortcuts, usage, and
diagnostics. Resolve known IDs directly. Increment its generation only on explicit lifecycle events
or destroyed/replaced actions. Deep `findChildren(QAction)` scans belong only in an explicit Verify
command or a measured cold-build fallback, never every workbench switch.

### P1: an application-wide event filter is used for a task-panel convenience

FMF installs `_TaskAcceptFilter` on `QApplication` (`Resources/FMF/runtime.py:441-481`). It returns
quickly for non-key events, but Qt states that application-level filters run before object-specific
filters and slow delivery of every event; object-specific filters should generally be preferred.[2]

**Decision:** attach the Enter-to-OK filter only to the active task panel/dialog and its relevant
children, then remove it when the task closes. If FreeCAD does not expose a stable task-panel signal,
use one narrowly scoped observer to install/remove it, not an application-wide permanent hook.

### P1: vendored modules share the process-wide Python namespace

`load_vendor()` prepends each vendor directory to `sys.path` and executes its `InitGui.py` under an
FMF-private top-level name, but vendor imports remain generic (`fmf_bootstrap.py:2606-2635`). For
example, `StyleMapping_Ribbon` imports `Standard_Functions_Ribbon` and `Parameters_Ribbon` as global
module names (`StyleMapping_Ribbon.py:40-42`). This can reuse or shadow separately installed copies,
and FMF explicitly reuses modules found through vendor sentinels. The resulting code/version
ownership is ambiguous, making both performance attribution and teardown unreliable.

**Decision:** make FMF's vendored payload an internal namespace or load it behind a narrow adapter
facade. Until that structural migration is approved, record every reused module's `__file__` and
version and fail verification when it is outside FMF's payload. Do not silently combine an external
Ribbon/SearchBar instance with FMF patches.

### P1: UI ownership is distributed across vendor and FMF code

Ribbon directly hides classic toolbars, controls menu visibility, owns a dock, rebuilds panels, and
writes Ribbon JSON. FMF separately snapshots/restores toolbar visibility and manages workbench
families (`fmf_bootstrap.py:137-159`, `fmf_bootstrap.py:1279-1317`). The same transition may call
`hideClassicToolbars()` several times (`FCBinding.py:3619-3655`, `3657-3748`). This is correctable
overlap, not an inherent FreeCAD cost.

**Decision:** one FMF chrome controller owns visibility and restoration. Vendor code should render
into an FMF-provided dock and report desired state; it should not independently decide global menu,
toolbar, workbench-family, or persistence policy. Apply visibility only when the desired snapshot
differs from the current state.

### P2: persistence and observers need ownership budgets

The repository contains 30 direct `App.saveParameter()` call sites across FMF and the two vendors,
and multiple App, Gui, and Selection observers. Most are attached idempotently, but there is no
single registry that proves all are detached, measures callback cost, or prevents a future feature
from adding another hot-path observer. Parameter flushes are appropriate for explicit preference
accept/disable/shutdown boundaries, not routine activation or interactive edits.

**Decision:** route preference mutations through one dirty-state service and flush at explicit
commit/lifecycle boundaries. Register signals, observers, filters, and timers through a lifecycle
registry that can enumerate owners, callback counts, and teardown status. Observer callbacks must
not recompute a document unless the user action represented by that callback explicitly commits a
model change.

## ADR: performance-isolated host integration

### Context

FMF intentionally replaces substantial UI chrome and binds many native commands. Some overhead is
unavoidable, but hidden work on host hot paths makes regressions hard to diagnose. “FreeCAD feels
slow” is not an actionable result unless native and FMF-attributable time can be separated.

### Options considered

| Option | Complexity | Regression confidence | Long-term cost | Assessment |
|---|---:|---:|---:|---|
| Keep patching individual stalls | Low initially | Low | High | Reject; repeats the focus-filter failure pattern |
| Instrument current architecture only | Medium | Medium | High | Useful transition step, but measures avoidable coupling without removing it |
| One measured FMF integration boundary | Medium-high | High | Lowest | **Choose**; centralizes lifecycle, host state, action lookup, and budgets |
| Fork/patch FreeCAD core | Very high | Low | Very high | Reject; upstream APIs are sufficient |

### Decision

Adopt a single measured integration boundary with five rules:

1. **No implicit external work:** no network and no workbench activation for discovery.
2. **One event, one coordinator:** FreeCAD lifecycle events are captured once and coalesced before
   downstream FMF services run.
3. **Narrow lookups and hooks:** known command IDs use direct action lookup; filters attach to the
   narrowest object; deep scans are diagnostic-only.
4. **Explicit ownership:** every signal, observer, timer, event filter, global widget mutation, and
   preference flush has one FMF owner and teardown path.
5. **Measured deltas:** every supported journey compares native and FMF profiles and enforces an
   incremental budget.

### Consequences

- FreeCAD or another add-on can still be slow, but the probe will show whether FMF added material
  wall time, callbacks, layouts, recomputes, I/O, or retained objects.
- Initial work is mostly consolidation and deletion, not new user-facing behavior.
- Vendor upgrades require replaying a small, explicit adapter patch set.
- Some commands owned by unloaded workbenches may appear temporarily unavailable rather than being
  force-loaded. That is preferable to mutating host state during discovery.
- The exact numeric budgets below are initial gates and should be tightened after three clean
  source-build A/B runs on the same machine.

## Performance contract

All timings are FMF-on minus matched FMF-disabled/native measurements, using disposable profiles,
the same source build, document, workbench sequence, and at least 20 warm repetitions. Report median,
p95, maximum, callback counts, filesystem writes, and recompute counts. Do not gate CI on one noisy
wall-clock sample.

| Journey | Initial FMF budget | Structural gate |
|---|---:|---|
| Installed but disabled startup | ≤2% or 10 ms p95, whichever is larger | no vendors, filters, observers, timers, network, or profile writes |
| Enabled warm startup | ≤250 ms p95 incremental | zero network; no unrelated workbench activation |
| Application/window focus | ≤2 ms p95 | zero rebuilds, title-bar replacements, state changes, writes |
| Warm switch among four FMF workbenches | ≤100 ms p95 incremental | one coalesced generation; zero deep action scans after warmup |
| Cold first switch | ≤250 ms p95 incremental | no unrelated workbench activation; each panel built at most once |
| Idle for 60 seconds | ≤1% CPU delta and zero FMF writes | no recurring FMF polling timer; stable object/filter/connection counts |
| Key/mouse input outside FMF widgets | below measurement noise | no application-wide FMF event filter |
| Ordinary property edit/selection | ≤2 ms callback p95 | zero FMF-triggered document recomputes unless explicitly committed |
| 50 switch/focus/task cycles | no upward latency trend >10% | stable QObject, signal, filter, observer, and timer counts |

A gate failure blocks a release unless the owner records a reviewed exception with the trace and a
bounded reason. “FreeCAD was slow” is not an exception: the comparison must identify native versus
FMF-attributable time.

## Approved implementation sequence

The repository's planning rule requires explicit approval before these multi-file changes begin.
Approval of this document should authorize **Slice 1 only**; later slices remain separately gated.

### Slice 1 — eliminate unbounded work (implemented)

1. Patch the vendored Ribbon adapter and sync script to disable its startup update check under FMF.
2. Add structural tests forbidding `urlopen`, `requests`, or equivalent network entry points from
   normal FMF startup/activation paths.
3. Disable all discovery/cache fallbacks that call `Gui.activateWorkbench()` under FMF. Keep only
   explicit user-intent workbench changes.
4. Add a live activation recorder that fails if the startup allowlist is exceeded.
5. Move Enter-to-OK filtering from `QApplication` to the active task surface, with teardown tests.

**Exit gate:** zero startup network calls, zero discovery-induced unrelated workbench activations,
zero application-wide FMF event filters, full existing pytest/package/privacy checks, and a source-
build smoke run through startup, the four FMF workbenches, Sketch edit enter/exit, and shutdown.

### Slice 2 — consolidate workbench transitions (implemented; live gate pending)

1. Introduce one transition coordinator with a monotonic generation and one restartable single-shot.
2. Adapt runtime, Ribbon, and SearchBar to register bounded phase callbacks instead of independently
   subscribing to `workbenchActivated`.
3. Instrument capture, settle delay, chrome diff, ribbon update, action invalidation, adaptive
   refresh, and status scheduling separately.
4. Preserve and test the existing double synchronization needed for Sketcher exit; remove repetition
   only after the live state-machine test proves equivalent layout and command state.

**Exit gate:** one upstream signal connection owned by FMF, no stale-generation work, correct Sketch
and Design panels after 50 transitions, and the switch budgets above.

### Slice 3 — replace global scans with one action registry

1. Move native-action resolution, shortcut reconciliation, usage wiring, and ribbon binding behind
   the existing `fmf_actions.py` boundary.
2. Resolve manifest IDs directly with `Gui.Command.get(id).getAction()` and track destruction.
3. Permit one measured cold fallback scan only for non-command/text actions; cache it by explicit
   generation.
4. Make runtime status consume registry counters rather than call `Gui.listCommands()` again.

**Exit gate:** no warm-switch `findChildren(QAction)` or sorted `listCommands()` call, exactly-once
invocation/subscriptions, and stable registry size over 50 rebuilds.

### Slice 4 — centralize chrome, lifecycle, and persistence ownership

1. Add a lifecycle registry for signals, observers, filters, and timers with an inspectable snapshot.
2. Put menu, toolbar, ribbon-dock, and workbench-family visibility behind one diff-based chrome
   controller.
3. Put parameter writes behind a dirty-state service and batch `saveParameter()` at explicit
   preference/disable/shutdown boundaries.
4. Namespace vendored imports or introduce an FMF-owned adapter package; reject ambiguous external
   module reuse during Verify.

**Exit gate:** disable returns lifecycle counts to zero, unmanaged host state is unchanged, idle does
no FMF writes, and vendor module provenance is deterministic.

### Slice 5 — continuous A/B attribution

1. Extend the existing source-build probe to run matched FMF-disabled and FMF-enabled journeys.
2. Collect ETW/process CPU where available plus FMF spans, Qt object counts, workbench activations,
   action scans, recomputes, parameter flushes, and file writes.
3. Store machine/build metadata and a versioned baseline fixture; compare distributions, not one run.
4. Run the short structural/performance suite in CI and the full source-build A/B suite before a
   release or vendor refresh.

**Exit gate:** every regression report can answer which FMF phase, if any, added the delay; all
budgets pass on the reference source build.

## Best-practices checklist for future changes

- Does this code run at FreeCAD startup even if the user never opens an FMF workbench? If yes, keep
  it to registration only. FreeCAD's current add-on guidance explicitly recommends minimal module-
  level work because GUI initialization runs on every launch.[1]
- Does discovery activate a workbench, recompute a document, call `updateGui()`, touch the network,
  flush parameters, or write a file? If yes, it is mutation, not discovery.
- Is a filter installed on `QApplication` or the main window for a local widget concern? Scope it to
  the target object; Qt warns that global filters slow every event.[2]
- Can repeated install/activate/rebuild calls add another connection, filter, observer, timer, or
  widget? Require an idempotence test and an explicit detach path.
- Does a cache key contain a value that changes on every common transition? Measure whether it is a
  cache in the real journey, not only in a unit test.
- Does a timer merely postpone expensive GUI-thread work? It still counts against the originating
  journey; timers coalesce work but do not make it free. Qt also warns against keeping the event loop
  busy with zero timers.[3]
- Is FMF duplicating a host registry or authoritative state? Prefer native command/action/document
  state and store only FMF policy/deltas.
- Does a model-changing helper use one named transaction and one intended recompute? Observer and
  presentation code must stay read-only.
- Are vendor modifications represented in the sync tool and guarded by structural tests? A direct
  bundled edit alone is not durable.
- Does the change add a hot-path span/counter and update the relevant A/B journey? If not, a future
  slowdown will again be unattributable.

## Contradictions, limits, and open questions

- The 625 ms Ribbon startup sample proves Ribbon is the largest instrumented FMF startup component
  in that run, but it does not isolate network, import, style, or widget construction time. Slice 1
  must add nested spans before claiming the network check explains most of it.
- The recent focus measurements used a source build newer than a stable FreeCAD release. They are
  excellent regression evidence for the patched handlers, not a cross-platform guarantee.
- FreeCAD's `workbenchActivated` ordering is confirmed by the checked-out source snapshot. FMF targets
  FreeCAD 1.1+, so the coordinator needs a compatibility probe rather than assuming every future
  version preserves the exact order.
- Some native command actions do not exist until their workbench is initialized. The curated manifest
  should identify which are required, then either register them through a documented module import or
  show them unavailable. Hidden workbench activation is rejected.
- Exact numeric budgets need calibration on three clean A/B runs. The structural gates—no network,
  no discovery activation, no global event filter, stable lifecycle counts—are immediately enforceable.
- On 2026-10-25 the new matched transition probe initialized the checked source build and FMF under
  `FreeCADCmd`, but the GUI harness exited before producing its result file. This is not a passing
  transition measurement. Run the same probe in a normal visible source-build GUI before closing
  the Slice 2 gate; keep the deterministic coordinator tests as structural evidence only.

## Recommendation

Approve Slice 1 first. It removes unbounded dependencies before investing in deeper optimization and
creates clean evidence for Slice 2. Do not begin new personalization, search, provenance, or visual
features until Slices 1-3 pass, because each new observer or renderer consumer would otherwise deepen
the same coupling this plan is intended to remove.

No second independent research pass is needed: the local source, captured traces, checked-out
upstream implementation, and primary framework documentation agree on the first decisions. Live A/B
measurement is the appropriate next evidence, not another opinion pass.

## Sources

1. FreeCAD Addon Academy, “Workbench registration” (module-level startup and lazy `Initialize()`
   guidance): https://github.com/FreeCAD/Addon-Academy/blob/main/Source/Guides/Code/Workbench/index.md
2. Qt, “The Event System” (application-wide event-filter cost and target-scoped preference):
   https://doc.qt.io/qt-6/eventsandfilters.html
3. Qt, `QTimer` (single-shot behavior and warning about keeping the event loop busy):
   https://doc.qt.io/qt-6/qtimer.html
4. FreeCAD, `Gui::DocumentObserverPython` (paired observer add/remove API):
   https://freecad.github.io/SourceDoc/dd/dd9/classGui_1_1DocumentObserverPython.html
5. FreeCAD documentation, “Workbench creation” (workbench lifecycle and one-time preference-page
   registration): https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Workbench_creation.md
6. FreeCAD source, `MainWindow.cpp` (local authoritative source for activation/action-update order):
   `<upstream-reference>/FreeCAD/src/Gui/MainWindow.cpp:1179-1181`

