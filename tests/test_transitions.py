"""Workbench-transition ownership and coalescing contracts."""

from __future__ import annotations

import importlib

from fake_freecad import FakeTimer


def _coordinator():
    module = importlib.import_module("fmf_transitions")
    module.uninstall()
    return module


def test_coordinator_owns_one_host_signal_and_orders_phases(env):
    transitions = _coordinator()
    calls = []

    transitions.register_phase("last", lambda name: calls.append(("last", name)), order=30)
    transitions.register_phase("first", lambda name: calls.append(("first", name)), order=10)
    initial_generation = transitions.snapshot()["generation"]

    assert len(env.main_window.workbenchActivated.handlers) == 1
    env.main_window.workbenchActivated.emit("FMFSketchWorkbench")
    FakeTimer.pump()

    assert calls == [
        ("first", "FMFSketchWorkbench"),
        ("last", "FMFSketchWorkbench"),
    ]
    assert transitions.snapshot()["settledGeneration"] == initial_generation + 1


def test_new_generation_supersedes_pending_transition(env):
    transitions = _coordinator()
    calls = []
    transitions.register_phase("runtime", calls.append, order=30)
    initial_generation = transitions.snapshot()["generation"]

    env.main_window.workbenchActivated.emit("FMFPartWorkbench")
    env.main_window.workbenchActivated.emit("FMFSketchWorkbench")
    FakeTimer.pump()

    assert calls == ["FMFSketchWorkbench"]
    state = transitions.snapshot()
    assert state["generation"] == initial_generation + 2
    assert state["settledGeneration"] == initial_generation + 2


def test_replacing_phase_does_not_duplicate_callback(env):
    transitions = _coordinator()
    calls = []
    transitions.register_phase("runtime", lambda name: calls.append(("old", name)))
    transitions.register_phase("runtime", lambda name: calls.append(("new", name)))

    env.main_window.workbenchActivated.emit("FMFDesignWorkbench")
    FakeTimer.pump()

    assert calls == [("new", "FMFDesignWorkbench")]
    assert len(env.main_window.workbenchActivated.handlers) == 1


def test_last_phase_removal_detaches_host_signal(env):
    transitions = _coordinator()

    def callback(_name):
        return None

    transitions.register_phase("runtime", callback)

    assert transitions.unregister_phase("runtime", callback) is True
    assert env.main_window.workbenchActivated.handlers == []
    assert transitions.snapshot()["connected"] is False


def test_failed_phase_does_not_block_later_phases(env):
    transitions = _coordinator()
    calls = []

    def fail(_name):
        raise RuntimeError("simulated transition failure")

    transitions.register_phase("broken", fail, order=10)
    transitions.register_phase("healthy", calls.append, order=20)
    env.main_window.workbenchActivated.emit("FMFSurfaceWorkbench")
    FakeTimer.pump()

    assert calls == ["FMFSurfaceWorkbench"]
    assert transitions.snapshot()["phaseMetrics"]["broken"]["failures"] == 1
    assert any("simulated transition failure" in line for line in env.console.warnings)


def test_successful_transition_keeps_metrics_in_memory(env, monkeypatch):
    transitions = _coordinator()
    recorded = []
    monkeypatch.setattr(transitions, "_record", lambda *args, **kwargs: recorded.append(args))
    transitions.register_phase("runtime", lambda _name: None)

    env.main_window.workbenchActivated.emit("FMFDesignWorkbench")
    FakeTimer.pump()

    assert recorded == []
    metrics = transitions.snapshot()["phaseMetrics"]
    assert metrics["runtime"]["count"] == 1
    assert metrics["settled-pass"]["count"] == 1
