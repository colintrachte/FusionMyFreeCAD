"""InitGui must degrade gracefully: a broken step cannot cost the user recovery."""

from __future__ import annotations

import json
import types
from pathlib import Path

from fake_freecad import ROOT, FakeObject, FakeTimer, _import_module


def _run_init_gui(env, bootstrap, monkeypatch, stub_vendors=True):
    if stub_vendors:
        monkeypatch.setattr(bootstrap, "load_vendor", lambda *_args: None)
        monkeypatch.setattr(bootstrap, "run_runtime", lambda: None)
    return _import_module("fusion_init_gui_under_test", ROOT / "InitGui.py")


def test_normal_startup_registers_everything(env, bootstrap, monkeypatch):
    _run_init_gui(env, bootstrap, monkeypatch)
    assert set(env.commands) == {
        "FusionMyFreeCAD_CreateSketch",
        "FusionMyFreeCAD_ParameterTable",
        "FusionMyFreeCAD_Verify",
        "FusionMyFreeCAD_Reapply",
        "FusionMyFreeCAD_Restore",
    }
    assert bootstrap.startup_failures() == []


def test_create_sketch_keeps_plane_selection_in_part_design_then_enters_sketcher(env, bootstrap):
    class View:
        def __init__(self):
            self.calls = []

        def viewAxonometric(self):
            self.calls.append("axonometric")

        def fitAll(self):
            self.calls.append("fitAll")

    view = View()
    env.gui.ActiveDocument = types.SimpleNamespace(ActiveView=view)
    bootstrap.register_commands()

    env.commands["FusionMyFreeCAD_CreateSketch"].Activated()
    FakeTimer.pump()

    assert env.active_workbench == "PartDesignWorkbench"
    assert env.gui_events[-2:] == [
        ("workbench", "PartDesignWorkbench"),
        ("command", "PartDesign_NewSketch"),
    ]
    assert view.calls == ["axonometric", "fitAll"]

    observer = env.document_observers[0]
    sketch = FakeObject("Sketcher::SketchObject", "Sketch")
    observer.slotInEdit(types.SimpleNamespace(Object=sketch))
    assert env.active_workbench == "SketcherWorkbench"


def test_a_failing_install_still_leaves_verify_and_restore_available(env, bootstrap, monkeypatch):
    """The regression: an exception in prepare() used to abort the whole module."""

    def broken_prepare():
        raise RuntimeError("simulated bad payload")

    monkeypatch.setattr(bootstrap, "prepare", broken_prepare)
    _run_init_gui(env, bootstrap, monkeypatch)

    assert "FusionMyFreeCAD_Restore" in env.commands
    assert "FusionMyFreeCAD_Verify" in env.commands
    failures = bootstrap.startup_failures()
    assert [entry["step"] for entry in failures] == ["installation"]
    assert "simulated bad payload" in failures[0]["error"]
    assert any("simulated bad payload" in message for message in env.console.errors)


def test_a_failing_runtime_does_not_stop_the_bundled_addons(env, bootstrap, monkeypatch):
    loaded = []
    monkeypatch.setattr(bootstrap, "run_runtime", lambda: (_ for _ in ()).throw(ValueError("qt")))
    monkeypatch.setattr(bootstrap, "load_vendor", lambda name, _dir: loaded.append(name))

    _run_init_gui(env, bootstrap, monkeypatch, stub_vendors=False)
    assert loaded == ["SearchBar", "FreeCAD_Ribbon"]
    assert [entry["step"] for entry in bootstrap.startup_failures()] == ["runtime"]


def test_startup_failures_are_cleared_on_a_clean_launch(env, bootstrap, monkeypatch):
    bootstrap.record_startup_failure("installation", RuntimeError("old news"))
    assert bootstrap.startup_failures()
    _run_init_gui(env, bootstrap, monkeypatch)
    assert bootstrap.startup_failures() == []


def test_failures_from_another_version_are_ignored(env, bootstrap):
    bootstrap.record_startup_failure("installation", RuntimeError("ancient"))
    report = json.loads(Path(bootstrap.STARTUP_PATH).read_text("utf-8"))
    report["failures"][0]["packageVersion"] = "0.0.1"
    Path(bootstrap.STARTUP_PATH).write_text(json.dumps(report), encoding="utf-8")
    assert bootstrap.startup_failures() == []


def test_an_old_freecad_is_refused_with_a_clear_message(tmp_path, monkeypatch):
    from fake_freecad import Environment

    environment = Environment(tmp_path / "FreeCAD", version=("1", "0", "0")).install()
    bootstrap = environment.load_bootstrap()
    try:
        bootstrap.prepare()
    except RuntimeError as error:
        assert "1.1 or newer" in str(error)
    else:  # pragma: no cover
        raise AssertionError("an unsupported FreeCAD version should be refused")


def test_vendor_payload_is_not_loaded_twice(env, bootstrap, monkeypatch):
    executed = []
    monkeypatch.setattr(bootstrap, "_execute_module", lambda name, path: executed.append(name))
    directory = ROOT / "bundled-addons" / "SearchBar"
    bootstrap.load_vendor("SearchBar", str(directory))
    bootstrap.load_vendor("SearchBar", str(directory))
    assert len(executed) == 1


def test_a_failed_runtime_load_can_be_retried(env, bootstrap, monkeypatch):
    attempts = {"count": 0}

    def execute(_name, _path):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("not ready")

    monkeypatch.setattr(bootstrap, "_execute_module", execute)
    try:
        bootstrap.run_runtime()
    except RuntimeError:
        pass
    bootstrap.run_runtime()
    assert attempts["count"] == 2


def test_failed_module_execution_does_not_leave_a_partial_module(env, bootstrap, tmp_path):
    import sys

    path = tmp_path / "broken.py"
    path.write_text("marker = True\nraise RuntimeError('broken')\n", encoding="utf-8")
    try:
        bootstrap._execute_module("fusion_broken_test_module", str(path))
    except RuntimeError:
        pass
    assert "fusion_broken_test_module" not in sys.modules


def test_an_active_standalone_addon_is_reused(env, bootstrap, monkeypatch):
    import sys
    import types

    monkeypatch.setitem(sys.modules, "FCBinding", types.ModuleType("FCBinding"))
    executed = []
    monkeypatch.setattr(bootstrap, "_execute_module", lambda name, path: executed.append(name))

    bootstrap.load_vendor("FreeCAD_Ribbon", str(ROOT / "bundled-addons" / "FreeCAD-Ribbon"))
    assert executed == []
    assert any("already active" in message for message in env.console.messages)


def test_the_preferences_page_is_registered(env, bootstrap, monkeypatch):
    """The opt-outs must be reachable from FreeCAD's own preferences dialog."""
    _run_init_gui(env, bootstrap, monkeypatch)
    assert len(env.preference_pages) == 1
    path, group = env.preference_pages[0]
    assert group == "FusionMyFreeCAD"
    assert Path(path).is_file()


def test_the_preferences_page_covers_every_switch_the_runtime_reads(bootstrap):
    """A new opt-out must not ship without a control the user can actually find.

    The expected set is read out of runtime.py rather than restated here, so adding
    `PREFERENCES.GetBool("Something", ...)` fails until the page gains a control.
    """
    import ast
    import xml.etree.ElementTree as ET

    runtime_source = Path(bootstrap.RUNTIME).read_text(encoding="utf-8")
    read_by_runtime = {
        node.args[0].value
        for node in ast.walk(ast.parse(runtime_source))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"GetBool", "GetString"}
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "PREFERENCES"
        and node.args
        and isinstance(node.args[0], ast.Constant)
    }
    # AppliedVersion is internal bookkeeping, not a user-facing switch.
    read_by_runtime.discard("AppliedVersion")

    tree = ET.parse(bootstrap.PREFERENCES_UI)
    entries = {
        element.find("cstring").text
        for element in tree.iter("property")
        if element.get("name") == "prefEntry"
    }
    assert entries == read_by_runtime
    paths = {
        element.find("cstring").text
        for element in tree.iter("property")
        if element.get("name") == "prefPath"
    }
    assert paths == {"Mod/FusionMyFreeCAD"}, "every control must write to the add-on's group"
