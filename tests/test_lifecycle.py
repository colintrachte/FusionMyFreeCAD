"""Existing lifecycle invariants that the activation state machine must preserve."""

import json
from pathlib import Path

import pytest


def test_prepare_is_idempotent_and_preserves_baseline(env, bootstrap):
    env.param("User parameter:BaseApp/Preferences/View").SetString("NavigationStyle", "Original")
    assert bootstrap.prepare() == "installed"
    baseline = Path(bootstrap.BASELINE_PATH).read_bytes()
    assert bootstrap.prepare() == "unchanged"
    assert Path(bootstrap.BASELINE_PATH).read_bytes() == baseline


def test_restore_uses_baseline_after_state_loss(env, bootstrap):
    env.param("User parameter:BaseApp/Preferences/View").SetString("NavigationStyle", "Original")
    bootstrap.prepare()
    Path(bootstrap.STATE_PATH).unlink()
    env.param("User parameter:BaseApp/Preferences/View").SetString("NavigationStyle", "Changed")
    _location, problems = bootstrap.restore()
    assert problems == []
    assert env.param("User parameter:BaseApp/Preferences/View").GetString("NavigationStyle") == (
        "Original"
    )


def test_baseline_has_typed_preference_records(env, bootstrap):
    bootstrap.prepare()
    baseline = json.loads(Path(bootstrap.BASELINE_PATH).read_text(encoding="utf-8"))
    assert baseline["preferences"]
    assert all({"path", "name", "kind", "existed"} <= set(item) for item in baseline["preferences"])


@pytest.mark.parametrize("failure_point", ["merge", "ribbon", "state"])
def test_interrupted_install_recovers_from_write_once_baseline(
    env, bootstrap, monkeypatch, failure_point
):
    """Every durable-install boundary can be retried without replacing the baseline."""
    env.param("User parameter:BaseApp/Preferences/View").SetString("NavigationStyle", "Original")
    original_merge = bootstrap._merge_layout
    original_atomic = bootstrap._atomic_json

    def fail_merge():
        if failure_point == "merge":
            raise RuntimeError("injected layout failure")
        return original_merge()

    def fail_atomic(path, value):
        if failure_point == "ribbon" and path == bootstrap.RIBBON_PATH:
            raise OSError("injected ribbon failure")
        if failure_point == "state" and path == bootstrap.STATE_PATH:
            raise OSError("injected state failure")
        return original_atomic(path, value)

    monkeypatch.setattr(bootstrap, "_merge_layout", fail_merge)
    monkeypatch.setattr(bootstrap, "_atomic_json", fail_atomic)
    with pytest.raises((OSError, RuntimeError), match="injected"):
        bootstrap.prepare()

    baseline_before = Path(bootstrap.BASELINE_PATH).read_bytes()
    assert not Path(bootstrap.STATE_PATH).exists()

    monkeypatch.setattr(bootstrap, "_merge_layout", original_merge)
    monkeypatch.setattr(bootstrap, "_atomic_json", original_atomic)
    assert bootstrap.prepare() == "recovered"
    assert Path(bootstrap.BASELINE_PATH).read_bytes() == baseline_before
    valid, _checks, problems = bootstrap.verify()
    assert valid, problems


def test_restore_preserves_absent_preference(env, bootstrap):
    group = env.param("User parameter:BaseApp/Preferences/View")
    assert "ShowNaviCube" not in group.GetBools()
    bootstrap.prepare()
    group.SetBool("ShowNaviCube", True)
    _location, problems = bootstrap.restore()
    assert problems == []
    assert "ShowNaviCube" not in group.GetBools()
