"""Runtime behaviour: preferences, shortcuts, deferral, and adaptive panels."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

from fake_freecad import FakeAction, FakeDialogButtonBox, FakeDock, FakeTabWidget, FakeTimer

SHORTCUT_GROUP = "User parameter:BaseApp/Preferences/Shortcut"
VIEW_GROUP = "User parameter:BaseApp/Preferences/View"
RIBBON_GROUP = "User parameter:BaseApp/Preferences/Mod/FreeCAD-Ribbon"
SKETCHER_GROUP = "User parameter:BaseApp/Preferences/Mod/Sketcher"


# ---------------------------------------------------------------------------
# Preferences are applied once, not at every launch
# ---------------------------------------------------------------------------


def test_defaults_are_applied_on_first_run(env, runtime):
    assert runtime.apply_preferences() is True
    assert env.param(VIEW_GROUP).GetString("NavigationStyle") == "Gui::RevitNavigationStyle"
    assert env.param(SHORTCUT_GROUP).GetString("PartDesign_Pad") == "E"
    assert env.param(SKETCHER_GROUP).GetBool("MakeInternals") is True
    assert env.param(SKETCHER_GROUP).GetBool("ShowCursorCoords") is True
    assert (
        env.param("User parameter:BaseApp/Preferences/Mod/Sketcher/General").GetBool(
            "AutoConstraints"
        )
        is True
    )
    assert (
        env.param("User parameter:BaseApp/Preferences/Mod/Sketcher/Tools").GetInt(
            "OnViewParameterVisibility"
        )
        == 1
    )
    assert env.param(runtime.bootstrap.PREFERENCE_ROOT).GetString("AppliedVersion") == (
        runtime.bootstrap.PACKAGE_VERSION
    )


def test_user_changes_survive_the_next_launch(env, runtime):
    """The regression: managed preferences used to be rewritten at every start."""
    runtime.apply_preferences()
    env.param(VIEW_GROUP).SetString("NavigationStyle", "Gui::BlenderNavigationStyle")
    env.param(RIBBON_GROUP).SetInt("IconSize_Large", 48)

    assert runtime.apply_preferences() is False
    assert env.param(VIEW_GROUP).GetString("NavigationStyle") == "Gui::BlenderNavigationStyle"
    assert env.param(RIBBON_GROUP).GetInt("IconSize_Large") == 48


def test_a_new_version_reapplies_defaults(env, runtime, monkeypatch):
    runtime.apply_preferences()
    env.param(VIEW_GROUP).SetString("NavigationStyle", "Gui::BlenderNavigationStyle")
    monkeypatch.setattr(runtime.bootstrap, "PACKAGE_VERSION", "9.9.9")

    assert runtime.apply_preferences() is True
    assert env.param(VIEW_GROUP).GetString("NavigationStyle") == "Gui::RevitNavigationStyle"


def test_force_reapplies_defaults(env, runtime):
    runtime.apply_preferences()
    env.param(VIEW_GROUP).SetString("NavigationStyle", "Gui::BlenderNavigationStyle")
    assert runtime.apply_preferences(force=True) is True
    assert env.param(VIEW_GROUP).GetString("NavigationStyle") == "Gui::RevitNavigationStyle"


def test_ribbon_paths_are_reasserted_every_launch(env, runtime):
    """Structural paths are not user preferences and must always be correct."""
    runtime.apply_preferences()
    env.param(RIBBON_GROUP).SetString("ConfigDir", "/somewhere/stale")
    runtime.apply_preferences()
    assert env.param(RIBBON_GROUP).GetString("ConfigDir").endswith("RibbonUI_Data")


def test_opt_outs_are_respected(env, runtime):
    env.param(runtime.bootstrap.PREFERENCE_ROOT).SetBool("SetShortcuts", False)
    env.param(runtime.bootstrap.PREFERENCE_ROOT).SetBool("SetNavigation", False)
    runtime.apply_preferences()
    assert "PartDesign_Pad" not in env.param(SHORTCUT_GROUP).GetStrings()
    assert "NavigationStyle" not in env.param(VIEW_GROUP).GetStrings()


def test_reapply_restores_baseline_values_for_newly_disabled_groups(env, bootstrap, runtime):
    env.param(VIEW_GROUP).SetString("NavigationStyle", "Gui::CADNavigationStyle")
    env.param(SHORTCUT_GROUP).SetString("PartDesign_Pad", "Ctrl+P")
    bootstrap.prepare()
    runtime.apply_preferences()
    assert env.param(VIEW_GROUP).GetString("NavigationStyle") == "Gui::RevitNavigationStyle"
    assert env.param(SHORTCUT_GROUP).GetString("PartDesign_Pad") == "E"

    preferences = env.param(runtime.bootstrap.PREFERENCE_ROOT)
    preferences.SetBool("SetNavigation", False)
    preferences.SetBool("SetShortcuts", False)
    runtime.apply_preferences(force=True)

    assert env.param(VIEW_GROUP).GetString("NavigationStyle") == "Gui::CADNavigationStyle"
    assert env.param(SHORTCUT_GROUP).GetString("PartDesign_Pad") == "Ctrl+P"


def test_reapply_command_round_trip(env, bootstrap, runtime, monkeypatch):
    bootstrap.prepare()
    runtime.apply_preferences()
    env.param(VIEW_GROUP).SetString("NavigationStyle", "Gui::BlenderNavigationStyle")
    monkeypatch.setitem(__import__("sys").modules, "_fmf_my_freecad_runtime", runtime)

    message = bootstrap.reapply()
    assert "reapplied" in message
    assert env.param(VIEW_GROUP).GetString("NavigationStyle") == "Gui::RevitNavigationStyle"


# ---------------------------------------------------------------------------
# Starter design
# ---------------------------------------------------------------------------


def test_starter_design_is_off_by_default(env, runtime):
    runtime.ensure_starter_design()
    assert env.app.ActiveDocument is None


def test_starter_design_can_be_enabled(env, runtime):
    env.param(runtime.bootstrap.PREFERENCE_ROOT).SetBool("CreateStarterDesign", True)
    runtime.ensure_starter_design()
    assert env.app.ActiveDocument is not None
    assert env.app.ActiveDocument.Objects[0].TypeId == "PartDesign::Body"


# ---------------------------------------------------------------------------
# Shortcuts
# ---------------------------------------------------------------------------


def _actions(env, *pairs):
    env.main_window.actions = [FakeAction(name, shortcut) for name, shortcut in pairs]
    return {action.objectName(): action for action in env.main_window.actions}


def test_shortcuts_are_assigned_to_the_fmf_commands(env, runtime):
    actions = _actions(env, ("PartDesign_Pad", ""), ("Sketcher_CreateLine", ""))
    runtime.reconcile_actions(env.main_window)
    assert actions["PartDesign_Pad"].shortcut().toString() == "E"
    assert actions["Sketcher_CreateLine"].shortcut().toString() == "L"


def test_a_displaced_shortcut_is_recorded_and_reported(env, runtime):
    """Taking a binding from another action used to happen silently."""
    actions = _actions(env, ("PartDesign_Pad", ""), ("Std_SomethingElse", "E"))
    runtime.reconcile_actions(env.main_window)

    assert actions["Std_SomethingElse"].shortcut().toString() == ""
    assert actions["PartDesign_Pad"].shortcut().toString() == "E"
    assert runtime._displaced_shortcuts == [
        {"sequence": "E", "from": "Std_SomethingElse", "to": "PartDesign_Pad"}
    ]
    # Per-shortcut detail goes to the log; the Report view gets one summary line.
    assert any("moved the E shortcut" in line for line in env.console.log)
    assert any("reassigned 1 keyboard shortcut" in message for message in env.console.messages)


def test_displaced_shortcuts_reach_the_status_file(env, bootstrap, runtime):
    bootstrap.prepare()
    _actions(env, ("PartDesign_Pad", ""), ("Std_SomethingElse", "E"))
    runtime.reconcile_actions(env.main_window)
    runtime.write_runtime_status("PartDesignWorkbench")

    status = json.loads(Path(bootstrap.STATUS_PATH).read_text("utf-8"))
    assert status["displacedShortcuts"][0]["from"] == "Std_SomethingElse"
    assert status["services"]["displacedShortcutCount"] == 1
    _valid, _checks, problems = bootstrap.verify()
    assert any("taken from Std_SomethingElse" in problem for problem in problems)


def test_shortcuts_are_skipped_when_opted_out(env, runtime):
    env.param(runtime.bootstrap.PREFERENCE_ROOT).SetBool("SetShortcuts", False)
    actions = _actions(env, ("PartDesign_Pad", ""), ("Std_SomethingElse", "E"))
    runtime.reconcile_actions(env.main_window)
    assert actions["PartDesign_Pad"].shortcut().toString() == ""
    assert actions["Std_SomethingElse"].shortcut().toString() == "E"


def test_usage_tracking_connects_once_per_action(env, runtime):
    actions = _actions(env, ("PartDesign_Revolution", ""))
    runtime.reconcile_actions(env.main_window)
    runtime.reconcile_actions(env.main_window)
    assert len(actions["PartDesign_Revolution"].triggered.handlers) == 1


# ---------------------------------------------------------------------------
# Deferral instead of fixed startup delays
# ---------------------------------------------------------------------------


def test_deferred_work_retries_until_the_widget_exists(env, runtime):
    attempts = {"count": 0}

    def not_ready_yet():
        attempts["count"] += 1
        return attempts["count"] >= 3

    runtime._defer("late widget", not_ready_yet, attempts=5, interval=0)
    FakeTimer.pump()
    assert attempts["count"] == 3
    assert runtime._problems == []


def test_deferred_work_reports_giving_up(env, runtime):
    runtime._defer("missing widget", lambda: False, attempts=3, interval=0)
    FakeTimer.pump()
    assert any("missing widget" in problem for problem in runtime._problems)


def test_deferred_work_reports_an_exception(env, runtime):
    def explode():
        raise ValueError("no such dock")

    runtime._defer("broken step", explode, attempts=3, interval=0)
    FakeTimer.pump()
    assert any("no such dock" in problem for problem in runtime._problems)


def test_newer_deferred_work_supersedes_an_older_retry_chain(env, runtime):
    calls = []

    runtime._defer("action scan", lambda: calls.append("old") or True, interval=0)
    runtime._defer("action scan", lambda: calls.append("new") or True, interval=0)
    FakeTimer.pump()

    assert calls == ["new"]


def test_model_tree_is_docked_left_and_shows_the_model_tab(env, runtime):
    dock = FakeDock(object_name="Combo View", window_title="Combo View")
    dock.tabs = FakeTabWidget(["&Tasks", "&Model"])
    selection = FakeDock(window_title="Selection view")
    selection.visible = True
    env.main_window.docks = [dock, selection]

    assert runtime.ensure_model_tree() is True
    assert env.main_window.dockWidgetArea(dock) == "left"
    assert dock.visible and dock.raised
    assert dock.width() >= 260
    assert dock.tabs.current == 1
    assert selection.visible is False


def test_model_tree_asks_to_be_retried_when_absent(env, runtime):
    assert runtime.ensure_model_tree() is False


def test_enter_accepts_the_active_task_dialog(env, runtime):
    class EnterEvent:
        accepted = False

        def type(self):
            return "key-press"

        def key(self):
            return "return"

        def accept(self):
            self.accepted = True

    box = FakeDialogButtonBox()
    env.main_window.button_boxes = [box]
    env.task_dialog_active = True
    event = EnterEvent()

    assert runtime._TaskAcceptFilter().eventFilter(None, event) is True
    assert event.accepted is True
    assert box.buttons()[0].clicks == 1
    assert box.buttons()[1].clicks == 0


def test_enter_does_nothing_without_an_active_task(env, runtime):
    box = FakeDialogButtonBox()
    env.main_window.button_boxes = [box]
    env.task_dialog_active = False

    assert runtime.accept_active_task() is False
    assert box.buttons()[0].clicks == 0


def test_task_accept_filter_is_installed_once(env, runtime):
    assert runtime.install_task_accept_filter() is True
    assert runtime.install_task_accept_filter() is True
    application = env.qtwidgets.QApplication.instance()
    assert application.filters == [runtime._task_accept_filter]


def test_runtime_problems_reach_verify(env, bootstrap, runtime):
    bootstrap.prepare()
    runtime._defer("missing widget", lambda: False, attempts=1, interval=0)
    FakeTimer.pump()
    runtime.write_runtime_status("PartDesignWorkbench")

    valid, checks, problems = bootstrap.verify()
    assert not valid
    assert checks["runtimeClean"] is False
    assert any("missing widget" in problem for problem in problems)


def test_status_writes_are_coalesced(env, bootstrap, runtime):
    bootstrap.prepare()
    for _ in range(5):
        runtime.schedule_status_write()
    assert len(FakeTimer.queue) == 1


# ---------------------------------------------------------------------------
# Adaptive panels
# ---------------------------------------------------------------------------


PART_DESIGN_FREQUENT = "FMF Frequent_newPanel"


def _frequent(runtime, workbench=PART_DESIGN_FREQUENT):
    """What the FREQUENT section of PartDesign would hold right now.

    A workbench can have several adaptive sections, so the selection is keyed
    by panel; asking a dict whether a command is "in" it would answer about
    panel names and quietly pass whatever the ranking did.
    """
    return runtime.adaptive_selection("PartDesignWorkbench")[workbench]


def test_a_single_click_does_not_displace_a_default(env, runtime):
    """One stray use used to reorder the panel for a month."""
    runtime.load_usage()["workbenches"]["PartDesignWorkbench"] = {
        "PartDesign_Draft": {"score": 1.0, "lastUsed": runtime._utc_now().isoformat()}
    }
    assert "PartDesign_Draft" not in _frequent(runtime)


def test_sustained_use_does_displace_a_default(env, runtime):
    runtime.load_usage()["workbenches"]["PartDesignWorkbench"] = {
        "PartDesign_Draft": {"score": 3.0, "lastUsed": runtime._utc_now().isoformat()}
    }
    assert _frequent(runtime)[0] == "PartDesign_Draft"


def test_usage_decays_so_an_old_habit_yields_to_the_default(env, runtime):
    stale = runtime._utc_now() - timedelta(days=365)
    runtime.load_usage()["workbenches"]["PartDesignWorkbench"] = {
        "PartDesign_Draft": {"score": 3.0, "lastUsed": stale.isoformat()}
    }
    assert "PartDesign_Draft" not in _frequent(runtime)


def test_recorded_usage_is_persisted(env, bootstrap, runtime):
    bootstrap.prepare()
    env.active_workbench = "PartDesignWorkbench"
    runtime.record_usage("PartDesign_Draft")
    FakeTimer.pump()

    usage = json.loads(Path(bootstrap.USAGE_PATH).read_text("utf-8"))
    assert usage["workbenches"]["PartDesignWorkbench"]["PartDesign_Draft"]["score"] == 1.0


def test_owned_mode_migrates_native_usage_history(env, bootstrap, runtime):
    env.param(bootstrap.PREFERENCE_ROOT).SetBool("UseOwnedWorkbenches", True)
    Path(runtime.USAGE_PATH).parent.mkdir(parents=True, exist_ok=True)
    Path(runtime.USAGE_PATH).write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "workbenches": {
                    "PartDesignWorkbench": {
                        "PartDesign_Pad": {
                            "score": 4.0,
                            "lastUsed": "2026-01-01T00:00:00+00:00",
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    usage = runtime.load_usage()

    assert "PartDesignWorkbench" not in usage["workbenches"]
    assert usage["workbenches"]["FMFDesignWorkbench"]["PartDesign_Pad"]["score"] == 4.0


def test_owned_mode_migrates_development_usage_and_pin_names(env, bootstrap, runtime):
    env.param(bootstrap.PREFERENCE_ROOT).SetBool("UseOwnedWorkbenches", True)
    Path(runtime.USAGE_PATH).parent.mkdir(parents=True, exist_ok=True)
    Path(runtime.USAGE_PATH).write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "workbenches": {
                    "FusionDesignWorkbench": {
                        "FusionMyFreeCAD_AddMidline": {
                            "score": 2.0,
                            "lastUsed": "2026-01-01T00:00:00+00:00",
                        }
                    }
                },
                "pins": {
                    "FusionDesignWorkbench": {
                        "Fusion Frequent_newPanel": {
                            "kept": ["PartDesign_Pad", "FusionMyFreeCAD_AddMidline"]
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    usage = runtime.load_usage()

    assert "FusionDesignWorkbench" not in usage["workbenches"]
    assert "FMFDesignWorkbench" in usage["workbenches"]
    assert "FMF_AddMidline" in usage["workbenches"]["FMFDesignWorkbench"]
    assert usage["pins"]["FMFDesignWorkbench"]["FMF Frequent_newPanel"]["kept"] == [
        "PartDesign_Pad",
        "FMF_AddMidline",
    ]


def test_adaptive_command_reverse_index_is_built_once(env, runtime, monkeypatch):
    real_groups = runtime.adaptive_groups
    calls = {"count": 0}

    def counted_groups(workbench):
        calls["count"] += 1
        return real_groups(workbench)

    monkeypatch.setattr(runtime, "adaptive_groups", counted_groups)
    first = runtime.adaptive_workbenches_by_command()
    second = runtime.adaptive_workbenches_by_command()

    assert first is second
    assert "PartDesignWorkbench" in first["PartDesign_Draft"]
    assert calls["count"] == len(runtime.load_manifest()["adaptivePins"])


def test_refresh_rewrites_the_frequent_panel_and_records_the_new_digest(env, bootstrap, runtime):
    bootstrap.prepare()
    before = json.loads(Path(bootstrap.STATE_PATH).read_text("utf-8"))["ribbonSha256"]
    runtime.load_usage()["workbenches"]["PartDesignWorkbench"] = {
        "PartDesign_Draft": {"score": 9.0, "lastUsed": runtime._utc_now().isoformat()}
    }

    assert runtime.refresh_adaptive_panel("PartDesignWorkbench") is True
    ribbon = json.loads(Path(bootstrap.RIBBON_PATH).read_text("utf-8"))
    panel = ribbon["workbenches"]["PartDesignWorkbench"]["toolbars"]["FMF Frequent_newPanel"]
    assert panel["order"][0] == "PartDesign_Draft"

    after = json.loads(Path(bootstrap.STATE_PATH).read_text("utf-8"))["ribbonSha256"]
    assert after != before
    # The rewrite is ours, so it must not later look like an external edit.
    assert after == bootstrap._sha256(bootstrap.RIBBON_PATH)


def test_refresh_is_idempotent(env, bootstrap, runtime):
    bootstrap.prepare()
    runtime.refresh_adaptive_panel("PartDesignWorkbench")
    assert runtime.refresh_adaptive_panel("PartDesignWorkbench") is False


def test_sketcher_slot_swap_keeps_non_candidates_in_place(env, bootstrap, runtime):
    bootstrap.prepare()
    path = Path(bootstrap.RIBBON_PATH)
    before = json.loads(path.read_text("utf-8"))
    toolbar = before["workbenches"]["SketcherWorkbench"]["toolbars"]["FMF Sketch Create_newPanel"]
    fixed = [
        c
        for c in toolbar["order"]
        if c not in {"Sketcher_CreatePolyline", "Sketcher_CreateBSpline"}
    ]

    runtime.load_usage()["workbenches"]["SketcherWorkbench"] = {
        "Sketcher_CreateBSpline": {"score": 9.0, "lastUsed": runtime._utc_now().isoformat()}
    }
    assert runtime.refresh_adaptive_panel("SketcherWorkbench") is True

    after = json.loads(path.read_text("utf-8"))
    toolbar = after["workbenches"]["SketcherWorkbench"]["toolbars"]["FMF Sketch Create_newPanel"]
    assert [c for c in toolbar["order"] if c in fixed] == fixed
    assert toolbar["commands"]["Sketcher_CreateBSpline"]["size"] == "large"
    assert toolbar["commands"]["Sketcher_CreatePolyline"]["size"] == "small"


# ---------------------------------------------------------------------------
# Putting something in FREQUENT by hand
# ---------------------------------------------------------------------------


FREQUENT = "FMF Frequent_newPanel"


def _frequent_panel(bootstrap, workbench="PartDesignWorkbench", panel=FREQUENT):
    ribbon = json.loads(Path(bootstrap.RIBBON_PATH).read_text("utf-8"))
    return ribbon["workbenches"][workbench]["toolbars"][panel]


def _drag_into_frequent(bootstrap, command, source="PartDesignWorkbench", **entry):
    """Stand in for dropping a button into FREQUENT, as the ribbon records it."""
    path = Path(bootstrap.RIBBON_PATH)
    ribbon = json.loads(path.read_text("utf-8"))
    toolbar = ribbon["workbenches"]["PartDesignWorkbench"]["toolbars"][FREQUENT]
    toolbar["order"] = [*toolbar["order"], command]
    toolbar["commands"][command] = dict(
        {"size": "small", "text": command, "icon": command, "IsExtra": True}, **entry
    )
    ribbon["newPanels"]["PartDesignWorkbench"][FREQUENT].append([command, source])
    path.write_text(json.dumps(ribbon), encoding="utf-8")


def test_the_shipped_contents_are_not_mistaken_for_the_users_choices(env, bootstrap, runtime):
    """Otherwise every default would pin itself and nothing could ever change."""
    bootstrap.prepare()
    runtime.refresh_adaptive_panel("PartDesignWorkbench")
    assert runtime.pinned_commands("PartDesignWorkbench", FREQUENT) == []


def test_a_command_dragged_into_frequent_stays_there(env, bootstrap, runtime):
    """The section rewrites itself, so without this a drop lasts one switch."""
    bootstrap.prepare()
    runtime.refresh_adaptive_panel("PartDesignWorkbench")
    _drag_into_frequent(bootstrap, "PartDesign_Pocket")

    runtime.refresh_adaptive_panel("PartDesignWorkbench")
    assert "PartDesign_Pocket" in _frequent_panel(bootstrap)["order"]

    # And again, because the earlier bug only showed on the second pass.
    runtime.refresh_adaptive_panel("PartDesignWorkbench")
    assert "PartDesign_Pocket" in _frequent_panel(bootstrap)["order"]


def test_a_dragged_command_outranks_a_measured_habit(env, bootstrap, runtime):
    bootstrap.prepare()
    runtime.refresh_adaptive_panel("PartDesignWorkbench")
    _drag_into_frequent(bootstrap, "PartDesign_Pocket")
    runtime.load_usage()["workbenches"]["PartDesignWorkbench"] = {
        "PartDesign_Draft": {"score": 50.0, "lastUsed": runtime._utc_now().isoformat()}
    }

    runtime.refresh_adaptive_panel("PartDesignWorkbench")
    assert _frequent_panel(bootstrap)["order"][0] == "PartDesign_Pocket"


def test_a_command_taken_out_of_frequent_does_not_come_back(env, bootstrap, runtime):
    bootstrap.prepare()
    runtime.refresh_adaptive_panel("PartDesignWorkbench")
    _drag_into_frequent(bootstrap, "PartDesign_Pocket")
    runtime.refresh_adaptive_panel("PartDesignWorkbench")

    path = Path(bootstrap.RIBBON_PATH)
    ribbon = json.loads(path.read_text("utf-8"))
    toolbar = ribbon["workbenches"]["PartDesignWorkbench"]["toolbars"][FREQUENT]
    toolbar["order"] = [c for c in toolbar["order"] if c != "PartDesign_Pocket"]
    path.write_text(json.dumps(ribbon), encoding="utf-8")

    runtime.refresh_adaptive_panel("PartDesignWorkbench")
    assert "PartDesign_Pocket" not in _frequent_panel(bootstrap)["order"]
    assert runtime.pinned_commands("PartDesignWorkbench", FREQUENT) == []


def test_a_dragged_command_keeps_the_label_and_icon_it_arrived_with(env, bootstrap, runtime):
    """A command from outside the pool has no candidate entry to draw from."""
    bootstrap.prepare()
    runtime.refresh_adaptive_panel("PartDesignWorkbench")
    _drag_into_frequent(
        bootstrap,
        "Spreadsheet_CreateSheet",
        source="SpreadsheetWorkbench",
        text="Spreadsheet",
        icon="Spreadsheet",
    )

    runtime.refresh_adaptive_panel("PartDesignWorkbench")
    toolbar = _frequent_panel(bootstrap)
    assert toolbar["commands"]["Spreadsheet_CreateSheet"]["text"] == "Spreadsheet"
    assert toolbar["commands"]["Spreadsheet_CreateSheet"]["icon"] == "Spreadsheet"


def test_a_frequent_section_keeps_its_shape_whatever_is_promoted(env, bootstrap, runtime):
    """Two large slots then small ones, so buttons stay where the hand left them."""
    bootstrap.prepare()
    runtime.load_usage()["workbenches"]["PartDesignWorkbench"] = {
        "PartDesign_Draft": {"score": 9.0, "lastUsed": runtime._utc_now().isoformat()}
    }
    runtime.refresh_adaptive_panel("PartDesignWorkbench")

    toolbar = _frequent_panel(bootstrap)
    sizes = [toolbar["commands"][command]["size"] for command in toolbar["order"]]
    assert sizes == ["large", "large", "small", "small"]


def test_sketcher_has_a_frequent_section_alongside_its_slot_swaps(env, bootstrap, runtime):
    """A workbench may carry both kinds of adaptive section."""
    bootstrap.prepare()
    now = runtime._utc_now()
    runtime.load_usage()["workbenches"]["SketcherWorkbench"] = {
        "Sketcher_CreateBSpline": {
            "score": 9.0,
            "lastUsed": (now - timedelta(seconds=1)).isoformat(),
        },
        "Sketcher_ConstrainTangent": {"score": 9.0, "lastUsed": now.isoformat()},
    }
    assert runtime.refresh_adaptive_panel("SketcherWorkbench") is True

    create = _frequent_panel(bootstrap, "SketcherWorkbench", "FMF Sketch Create_newPanel")
    assert create["commands"]["Sketcher_CreateBSpline"]["size"] == "large"
    frequent = _frequent_panel(bootstrap, "SketcherWorkbench", "FMF Sketch Frequent_newPanel")
    assert frequent["order"][0] == "Sketcher_ConstrainTangent"


def test_a_ribbon_missing_source_data_is_reported_not_crashed(env, bootstrap, runtime):
    bootstrap.prepare()
    path = Path(bootstrap.RIBBON_PATH)
    ribbon = json.loads(path.read_text("utf-8"))
    ribbon["newPanels"]["SketcherWorkbench"]["FMF Sketch Create_newPanel"] = []
    path.write_text(json.dumps(ribbon), encoding="utf-8")

    runtime.load_usage()["workbenches"]["SketcherWorkbench"] = {
        "Sketcher_CreateBSpline": {"score": 9.0, "lastUsed": runtime._utc_now().isoformat()}
    }
    runtime.refresh_adaptive_panel("SketcherWorkbench")
    assert any("missing source data" in problem for problem in runtime._problems)


def test_corrupt_usage_data_falls_back_to_defaults(env, bootstrap, runtime):
    Path(bootstrap.USAGE_PATH).write_text("not json", encoding="utf-8")
    assert runtime.load_usage() == {"schemaVersion": 1, "workbenches": {}}


def test_wrong_shaped_usage_data_falls_back_to_defaults(env, bootstrap, runtime):
    Path(bootstrap.USAGE_PATH).write_text("[]", encoding="utf-8")
    assert runtime.load_usage() == {"schemaVersion": 1, "workbenches": {}}


def test_malformed_usage_entries_do_not_break_adaptive_selection(env, runtime):
    runtime.load_usage()["workbenches"]["PartDesignWorkbench"] = {
        "PartDesign_Draft": {"score": "not-a-number", "lastUsed": "2026-01-01T00:00:00"},
        "PartDesign_Boolean": "not-an-entry",
    }
    selection = _frequent(runtime)
    assert "PartDesign_Draft" not in selection
    assert "PartDesign_Boolean" not in selection


# ---------------------------------------------------------------------------
# Session wiring
# ---------------------------------------------------------------------------


def test_install_wires_the_session_without_fixed_delays(env, bootstrap, runtime):
    bootstrap.prepare()
    dock = FakeDock(object_name="Combo View")
    env.main_window.docks = [dock]
    env.main_window.actions = [FakeAction("PartDesign_Pad")]

    runtime.install()
    FakeTimer.pump()

    assert dock.visible
    assert env.main_window.actions[0].shortcut().toString() == "E"
    assert Path(bootstrap.STATUS_PATH).is_file()
    assert runtime._problems == []


def test_install_waits_for_a_slow_main_window(env, bootstrap, runtime):
    """On a slow start the docks do not exist yet; the default retry must cover it.

    This is what the old fixed 500ms delay guessed at, and silently lost when it
    guessed wrong.
    """
    bootstrap.prepare()
    dock = FakeDock(object_name="Combo View")
    calls = {"count": 0}
    real_find = env.main_window.findChildren

    def findChildren(kind):
        calls["count"] += 1
        # The Combo View only appears once FreeCAD has finished building the UI.
        if kind is FakeDock and calls["count"] < 6:
            return []
        return real_find(kind)

    env.main_window.docks = [dock]
    env.main_window.findChildren = findChildren

    runtime.install()
    FakeTimer.pump()

    assert dock.visible, "the model tree was never docked"
    assert runtime._problems == []


def test_workbench_activation_refreshes_state(env, bootstrap, runtime):
    bootstrap.prepare()
    env.main_window.docks = [FakeDock(object_name="Combo View")]
    runtime.install()
    FakeTimer.pump()

    env.main_window.workbenchActivated.emit("SketcherWorkbench")
    FakeTimer.pump()
    status = json.loads(Path(bootstrap.STATUS_PATH).read_text("utf-8"))
    assert status["activeWorkbench"] == "SketcherWorkbench"


def test_install_connects_the_signal_only_once(env, bootstrap, runtime):
    bootstrap.prepare()
    runtime.install()
    runtime.install()
    FakeTimer.pump()
    assert len(env.main_window.workbenchActivated.handlers) == 1


def test_disabled_runtime_ignores_late_workbench_and_usage_callbacks(
    env, bootstrap, runtime, monkeypatch
):
    runtime.install()
    env.param(bootstrap.PREFERENCE_ROOT).SetBool("Enabled", False)
    refreshes = []
    monkeypatch.setattr(runtime, "refresh_adaptive_panel", refreshes.append)

    runtime.after_workbench_activation("PartDesignWorkbench")
    runtime.record_usage("PartDesign_Draft")

    assert refreshes == []
    assert runtime.load_usage()["workbenches"] == {}


def test_runtime_uninstall_disconnects_live_services(env, runtime):
    runtime.install()
    FakeTimer.pump()
    assert env.main_window._fmf_my_freecad_connected is True
    assert runtime._task_accept_filter is not None
    installed = runtime.runtime_service_state()
    assert installed["workbenchSignalConnected"] is True
    assert installed["taskAcceptFilterInstalled"] is True

    runtime.uninstall()

    assert env.main_window._fmf_my_freecad_connected is False
    assert env.main_window.workbenchActivated.handlers == []
    assert runtime._task_accept_filter is None
    removed = runtime.runtime_service_state()
    assert removed["workbenchSignalConnected"] is False
    assert removed["taskAcceptFilterInstalled"] is False
    assert removed["pendingDeferredTasks"] == []


def test_runtime_uninstall_reports_a_signal_cleanup_failure(env, runtime, monkeypatch):
    runtime.install()
    FakeTimer.pump()

    def fail_disconnect(_handler):
        raise RuntimeError("simulated disconnect failure")

    monkeypatch.setattr(env.main_window.workbenchActivated, "disconnect", fail_disconnect)
    runtime.uninstall()

    assert any("workbench activation signal" in problem for problem in runtime._problems)
    assert any("simulated disconnect failure" in line for line in env.console.warnings)


def test_every_action_is_asked_for_its_shortcut_once(env, runtime):
    """This runs twice per sketch, on the thread that draws the window.

    Entering a sketch edit activates Sketcher and leaving activates PartDesign
    again, so a sweep that asked every action for its shortcut once per
    shortcut FMF sets walked a tree of thousands of actions
    thirteen times over, each way. The count is the whole point of the test.
    """
    reads = {"count": 0}

    class Counting(FakeAction):
        def shortcut(self):
            reads["count"] += 1
            return super().shortcut()

    env.main_window.actions = [Counting("Action{}".format(index), "") for index in range(40)]
    env.main_window.actions.append(Counting("PartDesign_Pad", ""))

    runtime.reconcile_actions(env.main_window)
    assert reads["count"] <= len(env.main_window.actions), reads["count"]
