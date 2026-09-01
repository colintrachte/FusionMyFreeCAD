"""Installation, upgrade, verification, and restoration behaviour."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_first_install_generates_a_valid_ribbon(env, bootstrap):
    assert bootstrap.prepare() == "installed"
    valid, checks, problems = bootstrap.verify()
    assert valid, (checks, problems)
    assert Path(bootstrap.RIBBON_PATH).is_file()


def test_repeated_startup_is_a_no_op(installed):
    assert installed.prepare() == "unchanged"


def test_version_comes_from_package_xml(bootstrap, repo_root):
    import xml.etree.ElementTree as ET

    root = ET.parse(repo_root / "package.xml").getroot()
    declared = next(child.text.strip() for child in root if child.tag.endswith("version"))
    assert bootstrap.PACKAGE_VERSION == declared


def test_state_records_the_generated_digest(installed):
    state = json.loads(Path(installed.STATE_PATH).read_text("utf-8"))
    assert state["ribbonSha256"] == installed._sha256(installed.RIBBON_PATH)
    assert state["packageVersion"] == installed.PACKAGE_VERSION


# ---------------------------------------------------------------------------
# Baseline protection
# ---------------------------------------------------------------------------


def test_baseline_is_written_once_and_never_overwritten(env, bootstrap):
    env.param("User parameter:BaseApp/Preferences/View").SetString("NavigationStyle", "Original")
    bootstrap.prepare()
    baseline = json.loads(Path(bootstrap.BASELINE_PATH).read_text("utf-8"))
    captured = {(e["path"], e["name"]): e["value"] for e in baseline["preferences"]}
    assert captured[("User parameter:BaseApp/Preferences/View", "NavigationStyle")] == "Original"

    # Simulate FusionMyFreeCAD having applied its own settings.
    env.param("User parameter:BaseApp/Preferences/View").SetString(
        "NavigationStyle", "Gui::RevitNavigationStyle"
    )
    bootstrap._write_baseline("ignored", True)
    again = json.loads(Path(bootstrap.BASELINE_PATH).read_text("utf-8"))
    assert again == baseline


def test_existing_state_is_migrated_to_the_immutable_baseline(env, bootstrap):
    """Upgrading from a pre-baseline release must retain its original restore data."""
    backup_root = Path(bootstrap.BACKUP_ROOT) / "addon-old"
    backup_root.mkdir(parents=True)
    ribbon, _version = bootstrap._merge_layout()
    Path(bootstrap.RIBBON_DIR).mkdir(parents=True)
    bootstrap._atomic_json(bootstrap.RIBBON_PATH, ribbon)
    original_preferences = [
        {
            "path": "User parameter:BaseApp/Preferences/View",
            "name": "NavigationStyle",
            "kind": "String",
            "existed": True,
            "value": "Gui::CADNavigationStyle",
        }
    ]
    bootstrap.write_state(
        {
            "schemaVersion": 1,
            "installedAt": "2026-01-02T03:04:05+00:00",
            "backupRoot": str(backup_root),
            "ribbonHadExisting": True,
            "preferences": original_preferences,
            "packageVersion": bootstrap.PACKAGE_VERSION,
        }
    )

    assert not Path(bootstrap.BASELINE_PATH).exists()
    assert bootstrap.prepare() == "unchanged"
    baseline = json.loads(Path(bootstrap.BASELINE_PATH).read_text("utf-8"))
    assert baseline["backupRoot"] == str(backup_root)
    assert baseline["preferences"] == original_preferences
    assert baseline["migratedFromState"] is True


def test_lost_state_does_not_capture_fusion_settings_as_the_baseline(env, bootstrap):
    """The regression that would silently destroy the user's original profile."""
    env.param("User parameter:BaseApp/Preferences/View").SetString("NavigationStyle", "Original")
    bootstrap.prepare()

    # The state file is lost; FusionMyFreeCAD's own values are now in the profile.
    Path(bootstrap.STATE_PATH).unlink()
    env.param("User parameter:BaseApp/Preferences/View").SetString(
        "NavigationStyle", "Gui::RevitNavigationStyle"
    )

    assert bootstrap.prepare() == "recovered"
    state = json.loads(Path(bootstrap.STATE_PATH).read_text("utf-8"))
    assert state["recoveredFromBaseline"] is True
    bootstrap.restore()
    assert (
        env.param("User parameter:BaseApp/Preferences/View").GetString("NavigationStyle")
        == "Original"
    )


def test_corrupt_state_file_is_quarantined_not_fatal(env, bootstrap):
    bootstrap.prepare()
    Path(bootstrap.STATE_PATH).write_text("{ this is not json", encoding="utf-8")
    assert bootstrap.prepare() in {"installed", "recovered", "updated"}
    quarantined = list(Path(bootstrap.USER_ROOT).glob("*addon-state.json.corrupt-*"))
    assert quarantined, "the unreadable state file should have been moved aside"


def test_state_without_a_backup_root_is_survivable(env, bootstrap):
    bootstrap.prepare()
    state = json.loads(Path(bootstrap.STATE_PATH).read_text("utf-8"))
    del state["backupRoot"]
    Path(bootstrap.STATE_PATH).write_text(json.dumps(state), encoding="utf-8")
    assert bootstrap.prepare() == "recovered"


# ---------------------------------------------------------------------------
# Upgrade
# ---------------------------------------------------------------------------


def test_upgrade_backs_up_the_previous_ribbon(env, bootstrap, monkeypatch):
    bootstrap.prepare()
    monkeypatch.setattr(bootstrap, "PACKAGE_VERSION", "9.9.9")
    assert bootstrap.prepare() == "updated"
    state = json.loads(Path(bootstrap.STATE_PATH).read_text("utf-8"))
    assert state["packageVersion"] == "9.9.9"
    assert state["updates"], "the previous ribbon should be kept"
    assert Path(state["updates"][0]).is_file()


def test_upgrade_flags_a_ribbon_edited_outside_the_addon(env, bootstrap, monkeypatch):
    bootstrap.prepare()
    ribbon = json.loads(Path(bootstrap.RIBBON_PATH).read_text("utf-8"))
    ribbon["userAddedSomething"] = True
    Path(bootstrap.RIBBON_PATH).write_text(json.dumps(ribbon), encoding="utf-8")

    monkeypatch.setattr(bootstrap, "PACKAGE_VERSION", "9.9.9")
    bootstrap.prepare()
    state = json.loads(Path(bootstrap.STATE_PATH).read_text("utf-8"))
    assert "externalRibbonEdit" in state
    kept = json.loads(Path(state["externalRibbonEdit"]).read_text("utf-8"))
    assert kept["userAddedSomething"] is True


def test_update_ribbon_hash_keeps_adaptive_rewrites_from_looking_external(installed):
    path = Path(installed.RIBBON_PATH)
    ribbon = json.loads(path.read_text("utf-8"))
    ribbon["adaptiveRewrite"] = True
    path.write_text(json.dumps(ribbon), encoding="utf-8")
    assert installed.update_ribbon_hash() is True
    state = json.loads(Path(installed.STATE_PATH).read_text("utf-8"))
    assert state["ribbonSha256"] == installed._sha256(installed.RIBBON_PATH)


def test_direct_drag_order_survives_restart(installed):
    path = Path(installed.RIBBON_PATH)
    ribbon = json.loads(path.read_text("utf-8"))
    toolbar = ribbon["workbenches"]["PartDesignWorkbench"]["toolbars"]["Fusion Create_newPanel"]
    dragged_order = list(toolbar["order"])
    dragged_order[0], dragged_order[1] = dragged_order[1], dragged_order[0]
    toolbar["order"] = dragged_order
    toolbar["panelMenu"] = list(dragged_order)
    path.write_text(json.dumps(ribbon), encoding="utf-8")

    installed.record_customization(ribbon)

    assert installed.prepare() == "unchanged"
    restarted = json.loads(path.read_text("utf-8"))
    actual = restarted["workbenches"]["PartDesignWorkbench"]["toolbars"]["Fusion Create_newPanel"]
    assert actual["order"] == dragged_order
    assert actual["panelMenu"] == dragged_order
    valid, checks, problems = installed.verify()
    assert valid, (checks, problems)


def test_resetting_one_panel_preserves_other_panel_customization(installed):
    path = Path(installed.RIBBON_PATH)
    ribbon = json.loads(path.read_text("utf-8"))
    toolbars = ribbon["workbenches"]["PartDesignWorkbench"]["toolbars"]
    reset_name = "Fusion Create_newPanel"
    keep_name = "Fusion Modify_newPanel"
    reset_order = list(reversed(toolbars[reset_name]["order"]))
    keep_order = list(reversed(toolbars[keep_name]["order"]))
    toolbars[reset_name]["order"] = reset_order
    toolbars[reset_name]["panelMenu"] = list(reset_order)
    toolbars[keep_name]["order"] = keep_order
    toolbars[keep_name]["panelMenu"] = list(keep_order)
    path.write_text(json.dumps(ribbon), encoding="utf-8")
    installed.record_customization(ribbon)

    installed.reset_panel_customization("PartDesignWorkbench", reset_name)

    actual = json.loads(path.read_text("utf-8"))
    defaults, _version = installed._merge_layout(apply_customization=False)
    actual_toolbars = actual["workbenches"]["PartDesignWorkbench"]["toolbars"]
    default_toolbars = defaults["workbenches"]["PartDesignWorkbench"]["toolbars"]
    assert actual_toolbars[reset_name]["order"] == default_toolbars[reset_name]["order"]
    assert actual_toolbars[keep_name]["order"] == keep_order
    saved = json.loads(Path(installed.CUSTOMIZATION_PATH).read_text("utf-8"))
    saved_panels = saved["workbenches"]["PartDesignWorkbench"]["panels"]
    assert reset_name not in saved_panels
    assert keep_name in saved_panels


# ---------------------------------------------------------------------------
# Restoration
# ---------------------------------------------------------------------------


def test_restore_returns_the_profile_to_its_original_state(env, bootstrap):
    view = env.param("User parameter:BaseApp/Preferences/View")
    sketcher = env.param("User parameter:BaseApp/Preferences/Mod/Sketcher")
    view.SetString("NavigationStyle", "PreviousStyle")
    sketcher.SetBool("MakeInternals", False)
    Path(bootstrap.RIBBON_DIR).mkdir(parents=True, exist_ok=True)
    Path(bootstrap.RIBBON_PATH).write_text('{"previous": true}', encoding="utf-8")

    bootstrap.prepare()
    view.SetString("NavigationStyle", "Gui::RevitNavigationStyle")
    sketcher.SetBool("MakeInternals", True)

    removed, problems = bootstrap.restore()
    assert problems == []
    assert json.loads(Path(bootstrap.RIBBON_PATH).read_text("utf-8")) == {"previous": True}
    assert view.GetString("NavigationStyle") == "PreviousStyle"
    assert sketcher.GetBool("MakeInternals") is False
    assert (Path(removed) / "FusionMyFreeCAD-addon-state.json").is_file()


def test_restore_removes_keys_that_did_not_previously_exist(env, bootstrap):
    shortcuts = env.param("User parameter:BaseApp/Preferences/Shortcut")
    assert "PartDesign_Pad" not in shortcuts.GetStrings()
    bootstrap.prepare()
    shortcuts.SetString("PartDesign_Pad", "E")

    bootstrap.restore()
    assert "PartDesign_Pad" not in shortcuts.GetStrings()


def test_restore_clears_the_applied_version_marker(env, bootstrap):
    bootstrap.prepare()
    env.param(bootstrap.PREFERENCE_ROOT).SetString("AppliedVersion", bootstrap.PACKAGE_VERSION)
    bootstrap.restore()
    assert "AppliedVersion" not in env.param(bootstrap.PREFERENCE_ROOT).GetStrings()


def test_restore_moves_machine_local_runtime_files_aside(env, bootstrap):
    bootstrap.prepare()
    for path in (bootstrap.STATUS_PATH, bootstrap.USAGE_PATH):
        Path(path).write_text("{}", encoding="utf-8")
    removed, _problems = bootstrap.restore()
    for path in (bootstrap.STATE_PATH, bootstrap.STATUS_PATH, bootstrap.USAGE_PATH):
        assert not Path(path).exists()
        assert (Path(removed) / Path(path).name).is_file()


def test_restore_without_any_state_reports_clearly(env, bootstrap):
    with pytest.raises(RuntimeError, match="no restoration data"):
        bootstrap.restore()


def test_restore_survives_an_unrestorable_preference(env, bootstrap):
    bootstrap.prepare()
    baseline = json.loads(Path(bootstrap.BASELINE_PATH).read_text("utf-8"))
    baseline["preferences"].insert(
        0, {"path": "bad", "name": "x", "kind": "Nonsense", "existed": True, "value": 1}
    )
    Path(bootstrap.BASELINE_PATH).write_text(json.dumps(baseline), encoding="utf-8")

    _removed, problems = bootstrap.restore()
    assert len(problems) == 1 and "bad/x" in problems[0]
    # The remaining entries were still restored despite the bad one.
    assert not Path(bootstrap.STATE_PATH).exists()
    view = env.param("User parameter:BaseApp/Preferences/View")
    assert "NavigationStyle" not in view.GetStrings()


# ---------------------------------------------------------------------------
# Verification reporting
# ---------------------------------------------------------------------------


def test_verify_reports_a_missing_restore_point(env, bootstrap):
    bootstrap.prepare()
    Path(bootstrap.BASELINE_PATH).unlink()
    valid, checks, problems = bootstrap.verify()
    assert not valid
    assert checks["restorePointPresent"] is False
    assert any("restore baseline" in problem for problem in problems)


def test_verify_surfaces_startup_failures(installed):
    installed.record_startup_failure("runtime", RuntimeError("boom"))
    valid, checks, problems = installed.verify()
    assert not valid
    assert checks["startupClean"] is False
    assert any("boom" in problem for problem in problems)
    installed.clear_startup_failures()
    assert installed.verify()[0]


def test_verify_surfaces_displaced_shortcuts(installed):
    Path(installed.STATUS_PATH).write_text(
        json.dumps(
            {
                "problems": [],
                "displacedShortcuts": [
                    {"sequence": "E", "from": "Std_Edit", "to": "PartDesign_Pad"}
                ],
            }
        ),
        encoding="utf-8",
    )
    _valid, _checks, problems = installed.verify()
    assert any("taken from Std_Edit" in problem for problem in problems)


def test_verify_detects_a_tampered_panel_title(installed):
    path = Path(installed.RIBBON_PATH)
    ribbon = json.loads(path.read_text("utf-8"))
    ribbon["workbenches"]["PartDesignWorkbench"]["toolbars"]["Fusion Create_newPanel"]["title"] = (
        "X"
    )
    path.write_text(json.dumps(ribbon), encoding="utf-8")

    valid, checks, problems = installed.verify()
    assert not valid
    assert checks["commandLabels"] is False
    assert any("Fusion Create_newPanel" in problem for problem in problems)


def test_verify_detects_a_dropped_panel(installed):
    path = Path(installed.RIBBON_PATH)
    ribbon = json.loads(path.read_text("utf-8"))
    toolbars = ribbon["workbenches"]["SketcherWorkbench"]["toolbars"]
    toolbars["order"].remove("Fusion Finish_newPanel")
    path.write_text(json.dumps(ribbon), encoding="utf-8")

    valid, checks, _problems = installed.verify()
    assert not valid
    assert checks["panelOrder"] is False


def test_verification_is_derived_from_the_layout_not_hardcoded(env, bootstrap, monkeypatch):
    """Renaming a panel in the spec must move the check with it."""
    bootstrap.prepare()
    # Rename a panel in the spec only. A hardcoded checklist would keep passing;
    # a derived one must now report the panel it no longer finds.
    spec = json.loads(Path(bootstrap.LAYOUT_SPEC).read_text("utf-8"))
    spec["workbenches"]["PartDesignWorkbench"][0]["name"] = "Fusion Renamed_newPanel"
    valid, _checks, problems = bootstrap._verify_layout(bootstrap.RIBBON_PATH, spec)
    assert not valid
    assert any("Fusion Renamed_newPanel" in problem for problem in problems)


def test_adaptive_permutation_still_verifies(installed):
    """The runtime reorders FREQUENT panels; verification must tolerate that."""
    path = Path(installed.RIBBON_PATH)
    ribbon = json.loads(path.read_text("utf-8"))
    toolbar = ribbon["workbenches"]["PartDesignWorkbench"]["toolbars"]["Fusion Frequent_newPanel"]
    toolbar["order"] = list(reversed(toolbar["order"]))
    panel = ribbon["newPanels"]["PartDesignWorkbench"]["Fusion Frequent_newPanel"]
    ribbon["newPanels"]["PartDesignWorkbench"]["Fusion Frequent_newPanel"] = list(reversed(panel))
    for entry in toolbar["commands"].values():
        entry["size"] = "small"
    path.write_text(json.dumps(ribbon), encoding="utf-8")

    valid, checks, problems = installed.verify()
    assert valid, (checks, problems)


# ---------------------------------------------------------------------------
# Standalone recovery macro
# ---------------------------------------------------------------------------


def test_the_recovery_macro_restores_without_the_addon_installed(env, bootstrap, tmp_path):
    """Users remove the add-on before clicking Restore UI; the macro is the way back."""
    view = env.param("User parameter:BaseApp/Preferences/View")
    view.SetString("NavigationStyle", "PreviousStyle")
    bootstrap.prepare()
    view.SetString("NavigationStyle", "Gui::RevitNavigationStyle")
    env.param(bootstrap.PREFERENCE_ROOT).SetString("AppliedVersion", bootstrap.PACKAGE_VERSION)

    # Simulate Addon Manager having deleted Mod/FusionMyFreeCAD entirely.
    import sys

    from fake_freecad import ROOT, _import_module

    sys.modules.pop("fusion_bootstrap", None)
    macro = ROOT / "tools" / "RestoreFusionMyFreeCAD.FCMacro"
    module_path = tmp_path / "restore_macro.py"
    module_path.write_text(macro.read_text(encoding="utf-8"), encoding="utf-8")
    _import_module("restore_macro_under_test", module_path)

    assert view.GetString("NavigationStyle") == "PreviousStyle"
    assert "AppliedVersion" not in env.param(bootstrap.PREFERENCE_ROOT).GetStrings()
    assert not Path(bootstrap.STATE_PATH).exists()
    assert any("FusionMyFreeCAD restored" in message for message in env.console.messages)


def test_the_recovery_macro_says_so_when_there_is_nothing_to_restore(env, bootstrap, tmp_path):
    import sys

    from fake_freecad import ROOT, _import_module

    sys.modules.pop("fusion_bootstrap", None)
    macro = ROOT / "tools" / "RestoreFusionMyFreeCAD.FCMacro"
    module_path = tmp_path / "restore_macro_empty.py"
    module_path.write_text(macro.read_text(encoding="utf-8"), encoding="utf-8")
    _import_module("restore_macro_empty_under_test", module_path)

    assert any("Nothing to restore" in message for message in env.console.errors)
