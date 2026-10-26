"""Coalesce FreeCAD workbench changes behind one FMF-owned signal connection."""

from __future__ import annotations

import time

import FreeCAD as App
import FreeCADGui as Gui

_callbacks = {}
_main_window = None
_connected = False
_generation = 0
_settled_generation = 0
_active_name = ""
_phase_metrics = {}


def _record(operation, outcome, **details):
    """Keep transition diagnostics useful without making dispatch depend on logging."""
    try:
        import fmf_common as diagnostics

        diagnostics.event("info", "transition", operation, outcome, **details)
    except Exception as error:
        App.Console.PrintLog("FMF: transition diagnostic event failed: {}\n".format(error))


def _normalize_workbench_name(name):
    if not name:
        return ""
    try:
        import fmf_bootstrap

        return fmf_bootstrap.fmf_workbench_for(name)
    except Exception:
        return name


def _current_workbench_name():
    try:
        return _normalize_workbench_name(Gui.activeWorkbench().name())
    except Exception:
        return ""


def _schedule_settled_pass(name):
    """Capture one generation and let FreeCAD finish its native action update first."""
    global _generation, _active_name
    from PySide import QtCore

    _generation += 1
    generation = _generation
    _active_name = _normalize_workbench_name(name) or _current_workbench_name()

    def settle():
        if generation != _generation:
            return
        _dispatch(generation, _active_name)

    QtCore.QTimer.singleShot(0, settle)


def _dispatch(generation, name):
    global _settled_generation
    if generation != _generation or generation <= _settled_generation:
        return False
    _settled_generation = generation
    started = time.perf_counter()
    phases = tuple(sorted(_callbacks.items(), key=lambda item: (item[1][0], item[0])))
    for phase_name, (_order, callback) in phases:
        phase_started = time.perf_counter()
        try:
            callback(name)
            outcome = "completed"
        except Exception as error:
            outcome = "failed"
            App.Console.PrintWarning(
                "FMF transition phase {} failed: {}\n".format(phase_name, error)
            )
            _record(
                phase_name,
                outcome,
                generation=generation,
                workbench=name,
                error=str(error),
            )
        duration_ms = round((time.perf_counter() - phase_started) * 1000, 3)
        metric = _phase_metrics.setdefault(
            phase_name, {"count": 0, "failures": 0, "lastDurationMs": 0.0}
        )
        metric["count"] += 1
        metric["failures"] += int(outcome == "failed")
        metric["lastDurationMs"] = duration_ms
    _phase_metrics["settled-pass"] = {
        "count": _phase_metrics.get("settled-pass", {}).get("count", 0) + 1,
        "failures": 0,
        "lastDurationMs": round((time.perf_counter() - started) * 1000, 3),
        "phaseCount": len(phases),
    }
    return True


def install(main_window=None):
    """Own the sole FMF connection to FreeCAD's workbench-activation signal."""
    global _main_window, _connected
    candidate = main_window if main_window is not None else Gui.getMainWindow()
    if candidate is None:
        return False
    if _connected and _main_window is candidate:
        return True
    if _connected:
        uninstall(clear_callbacks=False)
    candidate.workbenchActivated.connect(_schedule_settled_pass)
    _main_window = candidate
    _connected = True
    return True


def uninstall(clear_callbacks=True):
    """Detach the upstream signal; optionally retain phases for a live reinstall."""
    global _main_window, _connected, _generation
    _generation += 1
    if _connected and _main_window is not None:
        try:
            _main_window.workbenchActivated.disconnect(_schedule_settled_pass)
        except (RuntimeError, TypeError, AttributeError) as error:
            App.Console.PrintWarning("FMF transition coordinator detach failed: {}\n".format(error))
    _main_window = None
    _connected = False
    if clear_callbacks:
        _callbacks.clear()


def register_phase(name, callback, order=100):
    """Register or replace one named, ordered transition phase."""
    if not name or not callable(callback):
        raise ValueError("Transition phases require a stable name and callable.")
    _callbacks[name] = (int(order), callback)
    install()
    return callback


def unregister_phase(name, callback=None):
    """Remove a phase without disturbing other transition consumers."""
    registered = _callbacks.get(name)
    if registered is None:
        return False
    if callback is not None and registered[1] != callback:
        return False
    del _callbacks[name]
    if not _callbacks:
        uninstall(clear_callbacks=False)
    return True


def request_current_transition():
    """Schedule reconciliation for the current workbench without emitting a host signal."""
    install()
    _schedule_settled_pass(_current_workbench_name())


def snapshot():
    """Return inspectable coordinator ownership and phase timing state."""
    return {
        "connected": _connected,
        "generation": _generation,
        "settledGeneration": _settled_generation,
        "activeWorkbench": _active_name,
        "phases": [
            name
            for name, _entry in sorted(_callbacks.items(), key=lambda item: (item[1][0], item[0]))
        ],
        "phaseMetrics": {name: dict(metric) for name, metric in _phase_metrics.items()},
    }
