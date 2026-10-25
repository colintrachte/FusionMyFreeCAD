# Research brief: FMF focus and responsiveness latency

**Status:** Independent research pass for later comparison  
**Date:** 2026-10-24  
**Question:** Is FreeCAD materially slower with FMF installed, especially when it regains window
focus, and which FMF paths best explain the delay?  
**Method:** Inspected the current bundled Ribbon, SearchBar, FMF runtime, recent history, isolated
source-build startup diagnostics, the prior FMF study, and primary Qt and FreeCAD sources.

## Executive finding

The reported slowdown is real and the source-build probes identify two FMF-specific causes.
The strongest culprit is the bundled Ribbon event filter, which reacts to every application
activation by calling `setWindowState(WindowMaximized)`. Qt documents that `setWindowState()` hides
the widget, requires it to be shown again, and emits `WindowStateChange` when state changes [1]. In
the same focus path, Ribbon replaces the dock title-bar widget on both `WindowActivate` and
`WindowDeactivate`. These are structural UI mutations on a latency-sensitive event and do not
belong in routine focus handling.

A second confirmed defect compounds general responsiveness over time: SearchBar's
`addToolSearchBox()` is connected to every `workbenchActivated` signal and installs fresh event
filters on the main window, central widget, viewport, and viewport children each time. It has no
installed-once guard and retains each filter through its main-window parent. The filters inspect
every key press and several mouse-release events. After repeated workbench switches, one physical
input event can therefore traverse many redundant Python filters. In the built FreeCAD checkout,
the probe found 94 live SearchBar filters after startup. Processing one irrelevant key press through
all 94 took a median 27.24 ms, versus 0.30 ms through one filter—about 91 times as much Python work.

The earlier action-reconciliation and ribbon-reconstruction hypotheses remain valid for workbench
switch latency, but neither explains a delay specifically triggered by switching focus as directly
as the Ribbon event filter does.

## Key findings

### 1. Focus regain performs an unconditional top-level window-state mutation

`bundled-addons/FreeCAD-Ribbon/FCBinding.py:7825-7840` handles
`QEvent.ApplicationActivated`. It always calls:

```python
mw.setWindowState(Qt.WindowState.WindowMaximized)
```

It then walks Ribbon widgets and resets the restore-button icon. There is no check that the window
is not already maximized and no evidence that focus activation requires a window-state write.

Qt says `QWidget.setWindowState()` applies immediately to visible windows, hides the widget, and
causes a `WindowStateChange` event when state changes [1]. Qt also marks
`QEvent.ApplicationActivated` deprecated in favor of `ApplicationStateChange` [2]. This makes the
call both semantically unnecessary and capable of causing top-level layout, dock, and viewport
work exactly when the user returns to FreeCAD.

### 2. Both sides of every focus transition replace the Ribbon title bar

`bundled-addons/FreeCAD-Ribbon/FCBinding.py:7809-7818` handles both `WindowActivate` and
`WindowDeactivate`. For a docked Ribbon it allocates a new `QWidget` and passes it to
`QDockWidget.setTitleBarWidget()` each time.

Qt describes a default-constructed title-bar widget as the technique for visually removing the
dock title bar, but nothing requires recreating it on focus changes [3]. The dock is already given
such a widget during construction at `FCBinding.py:7932`. The focus handler therefore repeats an
existing invariant by replacing a live dock child twice per away-and-back cycle.

The real-FreeCAD probe invoked this exact away/back handler 30 times. Median handler time was
17.43 ms per pair, p95 was 18.81 ms, and the first 20-cycle probe observed 39 distinct title-bar
replacements. This excludes Windows compositor, dock relayout, viewport repaint, and queued-event
cost, so it is a lower bound rather than an end-user latency estimate.

### 3. SearchBar event filters accumulate on every workbench activation

`bundled-addons/SearchBar/InitGui.py:83-84` calls `addToolSearchBox()` once and connects it to
`workbenchActivated`. Lines 63-67 construct and install a separate `EventInspector_SB` on four or
more objects each time. There is no retained filter registry, installed marker, disconnect path, or
uninstall path.

`bundled-addons/SearchBar/MouseBar.py:106-197` shows that every installed filter executes Python on
key presses, mouse releases, graphics-scene mouse releases, and Escape. Key handling performs
widget searches, parent walking, parameter reads, shortcut parsing, and Ribbon inspection. This is
not necessarily the multi-second focus delay by itself because the filter ignores ordinary focus
events, but it is a confirmed progressive input-latency and lifetime-ownership defect. The
source-build probe began with 94 retained filters; ten direct `addToolSearchBox()` calls added 40
more. The ten calls took 37.17 ms total, but their lasting per-input cost is more important than
their installation cost.

### 4. FMF has measurable cold-start overhead, but it is smaller than the reported pause

The isolated source-build run on FreeCAD 26.3.0 recorded:

- FMF feature command registration: 28.51 ms
- FMF installation: 21.10 ms
- FMF runtime installation: 11.44 ms
- SearchBar import: 17.07 ms
- Ribbon import: 518.40 ms

These spans total roughly 597 ms of instrumented FMF startup work. They do not include all Qt
painting, deferred Ribbon construction, or first-run command-cache work, so they are a lower bound.
They prove nonzero overhead, but not several seconds of focus latency.

FreeCAD itself also runs a 150 ms repeating action-update timer in `MainWindow.cpp` [4]. FMF's
additional Qt widgets and actions enlarge the population that FreeCAD periodically updates, so some
steady-state overhead is plausible even after FMF's own polling timer was removed. This is an
inference, not yet a measured attribution.

### 5. Workbench switching still has distinct costs

The current FMF runtime caches action discovery, but its generation key includes the active
workbench and the sorted result of `Gui.listCommands()`. A workbench change therefore still sorts
commands and usually rebuilds the Qt action inventory. Ribbon also intentionally performs a second
synchronization pass during tab-driven transitions to prevent Sketch/Design panel corruption.
Those paths should be profiled separately from focus changes rather than optimized together.

## Contradictions and uncertainty

- The exact Python handlers were measured inside the built FreeCAD 26.3.0 checkout. True Windows
  away/back trials were not automated because desktop-control permission was denied. Consequently,
  the measurements exclude OS compositor and actual viewport repaint latency.
- The source-build GUI process loaded FMF successfully in a disposable profile and recorded the
  startup spans above. It did not provide a reliable command-line GUI harness for repeated focus
  trials.
- Qt only guarantees a `WindowStateChange` event when the state changes. Calling the setter with
  the same maximized state may be cheaper on some Qt/Windows combinations. It remains unnecessary,
  and the title-bar replacement still occurs on every focus transition.
- Geometry recomputation can dominate modeling pauses, but it is unrelated to an otherwise idle
  focus-regain delay unless a document observer or queued recompute is active.

## Suggested decision and next experiment

Treat the focus delay as a real FMF defect, not user perception. The smallest controlled experiment
is an A/B package containing only these changes:

1. Remove the `ApplicationActivated` call to `setWindowState()`.
2. Reuse the Ribbon dock's existing title-bar widget; do no title-bar work on focus events.
3. Install one retained SearchBar event filter per watched object and make teardown explicit.
4. Add counters and `perf_counter_ns()` spans around focus handling, Ribbon workbench activation,
   action reconciliation, and SearchBar installation.
5. Compare at least 20 focus cycles and 20 workbench cycles in matched disposable native and FMF
   profiles. Report median and p95 separately.

Do not remove Ribbon's second tab/workbench synchronization pass during this experiment; the
repository's regression evidence shows it prevents merged Sketch and Design panels.

## Implemented A/B result

The approved minimal correction was then applied and the original source-build probe was rerun
unchanged against a fresh disposable profile:

| Measurement | Before | After |
| --- | ---: | ---: |
| SearchBar filter objects after startup | 94 | 1 |
| Filters added by ten reinstall calls | 40 | 0 |
| `ApplicationActivated` median | 1.4120 ms | 0.0035 ms |
| Focus away/back median | 17.1863 ms | 0.0095 ms |
| Focus away/back p95 | 20.1557 ms | 0.0389 ms |
| Title-bar replacements across twenty cycles | 39 | 0 |

The measured focus-handler path is roughly 1,800 times faster by median. This ratio applies only
to the isolated Python/Qt handler, not total perceived Windows focus latency. The post-fix probe
also showed that first-run Ribbon caching loaded only the active Assembly workbench plus FMF's four
curated native workbenches; it did not enumerate CAM or every installed workbench.

## Sources

1. Qt, `QWidget::setWindowState`: https://doc.qt.io/qt-6/qwidget.html#setWindowState
2. Qt, `QEvent` event types: https://doc.qt.io/qt-6/qevent.html#Type-enum
3. Qt, `QDockWidget::setTitleBarWidget`: https://doc.qt.io/qt-6/qdockwidget.html#setTitleBarWidget
4. FreeCAD, `src/Gui/MainWindow.cpp`: https://github.com/FreeCAD/FreeCAD/blob/main/src/Gui/MainWindow.cpp

