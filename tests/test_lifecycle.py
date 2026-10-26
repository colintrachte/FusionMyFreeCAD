"""Tests for fmf_lifecycle registry."""

from __future__ import annotations

import types

import pytest

import fmf_lifecycle as lifecycle


@pytest.fixture(autouse=True)
def clean_lifecycle():
    lifecycle.teardown_all()
    yield
    lifecycle.teardown_all()


def test_observer_registration_and_teardown():
    detached = []
    target = types.SimpleNamespace(removeObserver=lambda obs: detached.append(("target", obs)))
    obs = object()

    lifecycle.register_observer("selection", "pad", target, obs)
    snap = lifecycle.snapshot()
    assert snap["observer_count"] == 1
    assert "selection:pad" in snap["observers"]
    assert snap["total_hooks"] == 1

    success = lifecycle.unregister_observer("selection", "pad")
    assert success is True
    assert detached == [("target", obs)]
    assert lifecycle.snapshot()["observer_count"] == 0


def test_observer_custom_detach_function():
    detached = []
    lifecycle.register_observer(
        "app", "doc", None, None, detach_fn=lambda: detached.append("custom")
    )
    assert lifecycle.snapshot()["observer_count"] == 1

    success = lifecycle.unregister_observer("app", "doc")
    assert success is True
    assert detached == ["custom"]
    assert lifecycle.snapshot()["observer_count"] == 0


def test_filter_registration_and_teardown():
    removed = []
    widget = types.SimpleNamespace(removeEventFilter=lambda flt: removed.append(flt))
    flt = object()

    lifecycle.register_filter("task_shield", widget, flt)
    snap = lifecycle.snapshot()
    assert snap["filter_count"] == 1
    assert "task_shield" in snap["filters"]

    assert lifecycle.unregister_filter("task_shield") is True
    assert removed == [flt]
    assert lifecycle.snapshot()["filter_count"] == 0


def test_timer_registration_and_teardown():
    stopped = []
    timer = types.SimpleNamespace(stop=lambda: stopped.append(True))

    lifecycle.register_timer("status_delay", timer)
    assert lifecycle.snapshot()["timer_count"] == 1

    assert lifecycle.unregister_timer("status_delay") is True
    assert stopped == [True]
    assert lifecycle.snapshot()["timer_count"] == 0


def test_teardown_all_cleans_everything():
    obs_detached = []
    target = types.SimpleNamespace(removeObserver=lambda obs: obs_detached.append(obs))
    flt_removed = []
    widget = types.SimpleNamespace(removeEventFilter=lambda flt: flt_removed.append(flt))
    timer_stopped = []
    timer = types.SimpleNamespace(stop=lambda: timer_stopped.append(True))

    lifecycle.register_observer("cat1", "obs1", target, "my_obs")
    lifecycle.register_filter("flt1", widget, "my_flt")
    lifecycle.register_timer("tmr1", timer)

    snap = lifecycle.snapshot()
    assert snap["total_hooks"] == 3

    count = lifecycle.teardown_all()
    assert count == 3

    final_snap = lifecycle.snapshot()
    assert final_snap["total_hooks"] == 0
    assert final_snap["observer_count"] == 0
    assert final_snap["filter_count"] == 0
    assert final_snap["timer_count"] == 0

    assert obs_detached == ["my_obs"]
    assert flt_removed == ["my_flt"]
    assert timer_stopped == [True]
