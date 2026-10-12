"""InitGui must degrade gracefully: a broken step cannot cost the user recovery."""

from __future__ import annotations

import json
import types
from pathlib import Path

from fake_freecad import (
    ROOT,
    FakeLineSegment,
    FakeObject,
    FakeSketch,
    FakeTimer,
    _import_module,
)


def _run_init_gui(env, bootstrap, monkeypatch, stub_vendors=True):
    monkeypatch.setattr(bootstrap, "validate_enabled_ui", lambda: None)
    if stub_vendors:
        monkeypatch.setattr(bootstrap, "load_vendor", lambda *_args: None)
        monkeypatch.setattr(bootstrap, "run_runtime", lambda: None)
    return _import_module("fusion_init_gui_under_test", ROOT / "InitGui.py")


def test_normal_startup_registers_everything(env, bootstrap, monkeypatch):
    _run_init_gui(env, bootstrap, monkeypatch)
    assert set(env.commands) == {
        "FusionMyFreeCAD_AddMidline",
        "FusionMyFreeCAD_ConstrainMidpoint",
        "FusionMyFreeCAD_CopyDiagnostics",
        "FusionMyFreeCAD_CreateSketch",
        "FusionMyFreeCAD_CreateSlot",
        "FusionMyFreeCAD_DatumMidplane",
        "FusionMyFreeCAD_Export",
        "FusionMyFreeCAD_Export3MF",
        "FusionMyFreeCAD_ExportDXF",
        "FusionMyFreeCAD_ExportSTEP",
        "FusionMyFreeCAD_ExportSTL",
        "FusionMyFreeCAD_Enable",
        "FusionMyFreeCAD_MirrorWithConstraints",
        "FusionMyFreeCAD_ModernZincTheme",
        "FusionMyFreeCAD_OpenDiagnostics",
        "FusionMyFreeCAD_ParameterDock",
        "FusionMyFreeCAD_ParameterTable",
        "FusionMyFreeCAD_Reapply",
        "FusionMyFreeCAD_RepairReferences",
        "FusionMyFreeCAD_Restore",
        "FusionMyFreeCAD_RestoreViewport",
        "FusionMyFreeCAD_SmartOffset",
        "FusionMyFreeCAD_SolverDiagnostics",
        "FusionMyFreeCAD_StudioViewport",
        "FusionMyFreeCAD_UpdateModel",
        "FusionMyFreeCAD_Verify",
    }
    assert bootstrap.startup_failures() == []
    assert len(env.selection_observers) == 2  # _PadSelectionObserver, _DressUpSelectionObserver


def test_command_registration_is_idempotent(env, bootstrap, monkeypatch):
    registrations = []
    original_add_command = env.gui.addCommand

    def record_registration(name, command):
        registrations.append(name)
        original_add_command(name, command)

    monkeypatch.setattr(env.gui, "addCommand", record_registration)

    bootstrap.register_lifecycle_commands()
    bootstrap.register_commands()
    bootstrap.register_lifecycle_commands()
    bootstrap.register_commands()

    assert len(registrations) == len(set(registrations))
    assert registrations.count("FusionMyFreeCAD_Verify") == 1
    assert registrations.count("FusionMyFreeCAD_StudioViewport") == 1


def test_owned_workbenches_register_without_replacing_native_workbenches(env, bootstrap):
    native_ids = {
        "PartDesignWorkbench",
        "PartWorkbench",
        "SketcherWorkbench",
        "SurfaceWorkbench",
    }
    env.workbenches.update({name: object() for name in native_ids})
    env.param(bootstrap.PREFERENCE_ROOT).SetBool("UseOwnedWorkbenches", True)

    assert bootstrap.register_owned_workbenches() is True
    import fusion_workbenches

    assert native_ids <= set(env.workbenches)
    assert set(fusion_workbenches.FMF_TO_NATIVE) <= set(env.workbenches)
    assert fusion_workbenches.NATIVE_TO_FMF == {
        native: owned for owned, native in fusion_workbenches.FMF_TO_NATIVE.items()
    }
    assert env.workbenches["FMFDesignWorkbench"].GetClassName() == "PartDesignGui::Workbench"
    assert env.workbenches["FMFPartWorkbench"].GetClassName() == "PartGui::Workbench"
    assert env.workbenches["FMFSketchWorkbench"].GetClassName() == "SketcherGui::Workbench"
    assert env.workbenches["FMFSurfaceWorkbench"].GetClassName() == "SurfaceGui::Workbench"


def test_owned_workbench_registration_stays_off_outside_the_pilot(env, bootstrap):
    assert bootstrap.owned_workbenches_enabled() is False
    assert bootstrap.register_owned_workbenches() is False
    assert env.workbenches == {}


def test_owned_workbench_visibility_preserves_unrelated_user_choices(env, bootstrap):
    env.param(bootstrap.PREFERENCE_ROOT).SetBool("UseOwnedWorkbenches", True)
    workbenches = env.param(bootstrap.WORKBENCH_PREFERENCE_ROOT)
    workbenches.SetString("Disabled", "DraftWorkbench,SurfaceWorkbench")

    bootstrap.set_owned_workbench_visibility(True)
    disabled = workbenches.GetString("Disabled").split(",")
    assert "DraftWorkbench" in disabled
    assert "SurfaceWorkbench" in disabled
    assert not set(bootstrap.OWNED_TO_NATIVE_WORKBENCH) & set(disabled)

    bootstrap.set_owned_workbench_visibility(False)
    disabled = set(workbenches.GetString("Disabled").split(","))
    assert "DraftWorkbench" in disabled
    assert "SurfaceWorkbench" in disabled
    assert set(bootstrap.OWNED_TO_NATIVE_WORKBENCH) <= disabled


def test_hiding_stock_workbenches_is_reversed_without_unhiding_user_choices(env, bootstrap):
    env.param(bootstrap.PREFERENCE_ROOT).SetBool("UseOwnedWorkbenches", True)
    env.param(bootstrap.PREFERENCE_ROOT).SetBool("HideNativeWorkbenches", True)
    workbenches = env.param(bootstrap.WORKBENCH_PREFERENCE_ROOT)
    workbenches.SetString("Disabled", "PartWorkbench,DraftWorkbench")

    bootstrap.set_owned_workbench_visibility(True)
    bootstrap.set_owned_workbench_visibility(True)
    bootstrap.set_owned_workbench_visibility(False)

    disabled = set(workbenches.GetString("Disabled").split(","))
    assert "PartWorkbench" in disabled
    assert "DraftWorkbench" in disabled
    assert "PartDesignWorkbench" not in disabled
    assert set(bootstrap.OWNED_TO_NATIVE_WORKBENCH) <= disabled


def test_owned_mode_disable_switches_to_native_without_removing_layout(env, bootstrap, monkeypatch):
    env.param(bootstrap.PREFERENCE_ROOT).SetBool("UseOwnedWorkbenches", True)
    view = env.param("User parameter:BaseApp/Preferences/View")
    view.SetString("NavigationStyle", "Gui::CADNavigationStyle")
    env.active_workbench = "FMFDesignWorkbench"
    bootstrap.prepare()
    view.SetString("NavigationStyle", "Gui::RevitNavigationStyle")
    env.param(bootstrap.PREFERENCE_ROOT).SetString("AppliedVersion", bootstrap.PACKAGE_VERSION)
    ribbon_before = Path(bootstrap.RIBBON_PATH).read_bytes()
    monkeypatch.setattr(bootstrap, "_restore_native_ui_now", lambda: None)
    monkeypatch.setattr(bootstrap, "install_lifecycle_menu", lambda: None)

    message, problems = bootstrap.disable()

    assert problems == []
    assert "disabled" in message
    assert bootstrap.is_enabled() is False
    assert env.active_workbench == "PartDesignWorkbench"
    assert view.GetString("NavigationStyle") == "Gui::CADNavigationStyle"
    assert env.param(bootstrap.PREFERENCE_ROOT).GetString("AppliedVersion", "") == ""
    assert Path(bootstrap.RIBBON_PATH).read_bytes() == ribbon_before


def test_disabled_startup_registers_only_lifecycle_commands(env, bootstrap, monkeypatch):
    env.param(bootstrap.PREFERENCE_ROOT).SetBool("Enabled", False)
    calls = []
    monkeypatch.setattr(bootstrap, "prepare", lambda: calls.append("prepare"))
    monkeypatch.setattr(bootstrap, "run_runtime", lambda: calls.append("runtime"))
    monkeypatch.setattr(bootstrap, "load_vendor", lambda *args: calls.append(args[0]))

    _run_init_gui(env, bootstrap, monkeypatch, stub_vendors=False)

    assert set(env.commands) == {
        "FusionMyFreeCAD_Enable",
        "FusionMyFreeCAD_CopyDiagnostics",
        "FusionMyFreeCAD_OpenDiagnostics",
        "FusionMyFreeCAD_Reapply",
        "FusionMyFreeCAD_Restore",
        "FusionMyFreeCAD_Verify",
    }
    assert calls == []
    assert env.selection_observers == []
    assert env.document_observers == []


def test_enabled_ui_validation_keeps_a_visible_ribbon_enabled(env, bootstrap):
    env.active_workbench = "FMFDesignWorkbench"
    ribbon = env.pyside.QtWidgets.QDockWidget(object_name="Ribbon")
    ribbon.show()
    env.main_window.docks.append(ribbon)

    bootstrap.validate_enabled_ui()
    FakeTimer.pump()

    assert bootstrap.is_enabled() is True
    assert bootstrap.startup_failures() == []


def test_enabled_ui_validation_accepts_native_chrome_with_hidden_ribbon(
    env, bootstrap, monkeypatch
):
    class Visible:
        def isVisible(self):
            return True

    ribbon = env.pyside.QtWidgets.QDockWidget(object_name="Ribbon")
    ribbon.hide()
    env.main_window.docks.append(ribbon)
    menu = env.main_window.menuBar()
    monkeypatch.setattr(menu, "isVisible", lambda: True, raising=False)
    monkeypatch.setattr(env.main_window, "menuBar", lambda: menu)
    monkeypatch.setattr(env.main_window, "centralWidget", lambda: Visible(), raising=False)

    bootstrap.validate_enabled_ui()
    FakeTimer.pump()

    assert bootstrap.is_enabled() is True
    assert bootstrap.startup_failures() == []


def test_production_default_registers_owned_workbenches_on_startup(env, bootstrap, monkeypatch):
    env.param(bootstrap.PREFERENCE_ROOT).RemBool("UseOwnedWorkbenches")
    _run_init_gui(env, bootstrap, monkeypatch)

    assert set(bootstrap.OWNED_TO_NATIVE_WORKBENCH) <= set(env.workbenches)
    ribbon = json.loads(Path(bootstrap.RIBBON_PATH).read_text(encoding="utf-8"))
    assert set(ribbon["authoritativeWorkbenches"]) == set(bootstrap.OWNED_TO_NATIVE_WORKBENCH)


def test_enabled_ui_validation_rolls_back_an_invisible_ribbon(env, bootstrap, monkeypatch):
    recovery_calls = []
    monkeypatch.setattr(
        bootstrap, "_restore_native_ui_now", lambda: recovery_calls.append("native-ui")
    )
    monkeypatch.setattr(bootstrap, "install_lifecycle_menu", lambda: recovery_calls.append("menu"))

    bootstrap.validate_enabled_ui()
    FakeTimer.pump()

    assert bootstrap.is_enabled() is False
    assert recovery_calls == ["native-ui", "menu"]
    assert bootstrap.startup_failures()[0]["step"] == "enabled UI validation"


def test_diagnostics_rotate_and_preserve_structured_events(env, bootstrap, monkeypatch, tmp_path):
    import fusion_common as diagnostics

    log_path = tmp_path / "events.jsonl"
    monkeypatch.setattr(diagnostics, "DIAGNOSTICS_DIR", str(tmp_path))
    monkeypatch.setattr(diagnostics, "LOG_PATH", str(log_path))
    monkeypatch.setattr(diagnostics, "MAX_LOG_BYTES", 1)

    diagnostics.event("info", "startup", "first", "completed")
    diagnostics.event("warning", "ui", "second", "degraded", reason="test")

    assert (tmp_path / "events.jsonl.1").is_file()
    current = json.loads(log_path.read_text(encoding="utf-8"))
    assert current["subsystem"] == "ui"
    assert current["details"] == {"reason": "test"}


def test_diagnostics_write_failure_never_breaks_startup(env, bootstrap, monkeypatch):
    import fusion_common as diagnostics

    def fail(*_args, **_kwargs):
        raise PermissionError("read-only profile")

    monkeypatch.setattr(diagnostics.os, "makedirs", fail)
    diagnostics.event("error", "startup", "write", "failed")
    diagnostics.set_status("degraded", reason="test")


def test_startup_diagnostics_do_not_write_until_flushed(env, bootstrap, monkeypatch, tmp_path):
    import fusion_common as diagnostics

    log_path = tmp_path / "events.jsonl"
    status_path = tmp_path / "session-status.json"
    monkeypatch.setattr(diagnostics, "DIAGNOSTICS_DIR", str(tmp_path))
    monkeypatch.setattr(diagnostics, "LOG_PATH", str(log_path))
    monkeypatch.setattr(diagnostics, "STATUS_PATH", str(status_path))

    diagnostics.start_session(True, "1.8.0", ("1", "1", "1"))
    diagnostics.event("info", "startup", "installation", "completed")

    assert not log_path.exists()
    assert not status_path.exists()
    diagnostics.flush_diagnostics()
    assert log_path.is_file()
    assert json.loads(status_path.read_text(encoding="utf-8"))["state"] == "starting"


def test_create_sketch_keeps_plane_selection_in_part_design_then_enters_sketcher(env, bootstrap):
    class View:
        def __init__(self):
            self.calls = []

        def viewAxonometric(self):
            self.calls.append("axonometric")

        def setCameraCenter(self, center, height):
            self.calls.append(("centerCamera", center, height))

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
    # Origin planes are framed centered on origin (0, 0, 0) at default 100mm scale, not fitAll.
    assert view.calls == ["axonometric", ("centerCamera", (0.0, 0.0, 0.0), 100.0)]

    observer = env.document_observers[0]
    sketch = FakeObject("Sketcher::SketchObject", "Sketch")
    observer.slotInEdit(types.SimpleNamespace(Object=sketch))
    # The switch is deferred out of the slotInEdit callback so it cannot re-enter
    # a half-built edit state; it lands on the next event-loop turn.
    assert env.active_workbench == "PartDesignWorkbench"
    FakeTimer.pump()
    assert env.active_workbench == "SketcherWorkbench"
    # New empty sketch is centered on sketch plane origin at 100mm initial range
    assert view.calls == [
        "axonometric",
        ("centerCamera", (0.0, 0.0, 0.0), 100.0),
        ("centerCamera", (0.0, 0.0, 0.0), 100.0),
    ]


def test_owned_sketch_edit_returns_to_the_fmf_workbench(env, bootstrap):
    env.param(bootstrap.PREFERENCE_ROOT).SetBool("UseOwnedWorkbenches", True)
    env.active_workbench = "FMFDesignWorkbench"
    bootstrap.register_commands()
    observer = env.document_observers[0]
    sketch = FakeSketch()
    view_provider = types.SimpleNamespace(Object=sketch)

    observer.slotInEdit(view_provider)
    FakeTimer.pump()
    assert env.active_workbench == "FMFSketchWorkbench"

    observer.slotResetEdit(view_provider)
    FakeTimer.pump()
    assert env.active_workbench == "FMFDesignWorkbench"


def test_create_sketch_with_preselection_skips_origin_plane_framing(env, bootstrap):
    class View:
        def __init__(self):
            self.calls = []

        def viewAxonometric(self):
            self.calls.append("axonometric")

        def setCameraCenter(self, center, height):
            self.calls.append(("centerCamera", center, height))

    view = View()
    env.gui.ActiveDocument = types.SimpleNamespace(ActiveView=view)
    bootstrap.register_commands()

    # Pre-select an existing face/feature
    env.selection_ex = [
        types.SimpleNamespace(
            Object=FakeObject("PartDesign::Feature", "Pad"),
            ObjectName="Pad",
            SubElementNames=["Face1"],
        )
    ]

    env.commands["FusionMyFreeCAD_CreateSketch"].Activated()
    FakeTimer.pump()

    assert env.active_workbench == "PartDesignWorkbench"
    # Origin planes framing is skipped because the user had an active selection
    assert view.calls == []


def test_existing_sketch_with_geometry_preserves_camera_framing(env, bootstrap):
    class View:
        def __init__(self):
            self.calls = []

        def viewAxonometric(self):
            self.calls.append("axonometric")

        def setCameraCenter(self, center, height):
            self.calls.append(("centerCamera", center, height))

    view = View()
    env.gui.ActiveDocument = types.SimpleNamespace(ActiveView=view)
    bootstrap.register_commands()

    observer = env.document_observers[0]
    env.load_sketch_tools()  # ensure sketch tools are available
    sketch_obj = FakeSketch("ExistingSketch")
    sketch_obj.addGeometry(FakeLineSegment((0, 0), (50, 50)))

    observer.slotInEdit(types.SimpleNamespace(Object=sketch_obj))
    FakeTimer.pump()

    assert env.active_workbench == "SketcherWorkbench"
    # Geometry exists, so camera zoom/framing is not overridden
    assert view.calls == []


def test_center_camera_node_orthographic(env, bootstrap):
    class FakeField:
        def __init__(self, val):
            self.val = val

        def getValue(self):
            return self.val

        def setValue(self, val):
            self.val = val

    class FakeCamNode:
        def __init__(self):
            self.orientation = FakeField(FakeField((0.0, 0.0, 0.0, 1.0)))
            self.position = FakeField([0.0, 0.0, 0.0])
            self.focalDistance = FakeField(100.0)
            self.height = FakeField(50.0)

    cam = FakeCamNode()
    view = types.SimpleNamespace(getCameraNode=lambda: cam)

    bootstrap._center_camera(view, center=(10.0, 20.0, 0.0), height=100.0)

    assert cam.height.val == 100.0
    assert cam.focalDistance.val == 100.0
    # Looking down -Z, eye placed at target + (0, 0, 1) * 100
    assert cam.position.val == [10.0, 20.0, 100.0]


def test_center_camera_node_perspective(env, bootstrap):
    import math

    class FakeField:
        def __init__(self, val):
            self.val = val

        def getValue(self):
            return self.val

        def setValue(self, val):
            self.val = val

    class FakeCamNode:
        def __init__(self):
            self.orientation = FakeField(FakeField((0.0, 0.0, 0.0, 1.0)))
            self.position = FakeField([0.0, 0.0, 0.0])
            self.focalDistance = FakeField(50.0)
            self.heightAngle = FakeField(math.pi / 4.0)  # 45 degrees

    cam = FakeCamNode()
    view = types.SimpleNamespace(getCameraNode=lambda: cam)

    bootstrap._center_camera(view, center=(0.0, 0.0, 0.0), height=100.0)

    expected_dist = (100.0 / 2.0) / math.tan((math.pi / 4.0) / 2.0)
    assert math.isclose(cam.focalDistance.val, expected_dist, rel_tol=1e-5)
    assert math.isclose(cam.position.val[2], expected_dist, rel_tol=1e-5)


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
    # These activation controls are consumed by bootstrap before runtime.py is loaded.
    assert entries == read_by_runtime | {"Enabled", "HideNativeWorkbenches"}
    paths = {
        element.find("cstring").text
        for element in tree.iter("property")
        if element.get("name") == "prefPath"
    }
    assert paths == {"Mod/FusionMyFreeCAD"}, "every control must write to the add-on's group"
