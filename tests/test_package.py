"""Package integrity: metadata, layout coherence, vendor patches, and the archive."""

from __future__ import annotations

import ast
import hashlib
import json
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest
from fake_freecad import ROOT, _import_module

NAMESPACE = {"p": "https://wiki.freecad.org/Package_Metadata"}
RESOURCES = ROOT / "Resources" / "FusionMyFreeCAD"
BUNDLED = ROOT / "bundled-addons"


@pytest.fixture(scope="module")
def package():
    return ET.parse(ROOT / "package.xml").getroot()


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


def test_package_metadata(package):
    assert package.findtext("p:name", namespaces=NAMESPACE) == "FusionMyFreeCAD"
    assert package.findtext("p:license", namespaces=NAMESPACE) == "GPL-3.0-or-later"
    assert package.findtext("p:freecadmin", namespaces=NAMESPACE) == "1.1.0"


def test_one_version_everywhere(package, layout, manifest):
    """package.xml is the single source of truth; nothing may drift from it."""
    version = package.findtext("p:version", namespaces=NAMESPACE)
    assert layout["layoutVersion"] == version
    assert manifest["layoutVersion"] == version


def test_required_files_are_present():
    required = [
        ROOT / "Init.py",
        ROOT / "InitGui.py",
        ROOT / "fusion_bootstrap.py",
        ROOT / "LICENSE",
        ROOT / "THIRD_PARTY_NOTICES.md",
        RESOURCES / "RibbonStructure.json",
        RESOURCES / "layout-v3.json",
        RESOURCES / "layout-manifest.json",
        RESOURCES / "runtime.py",
        BUNDLED / "FreeCAD-Ribbon" / "InitGui.py",
        BUNDLED / "FreeCAD-Ribbon" / "LICENSE",
        BUNDLED / "SearchBar" / "InitGui.py",
        BUNDLED / "SearchBar" / "LICENSE",
    ]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    assert missing == []


def test_every_python_file_compiles():
    skipped = {"vendor", "__pycache__", ".git"}
    for path in ROOT.rglob("*.py"):
        if skipped.intersection(path.parts):
            continue
        compile(path.read_text(encoding="utf-8-sig"), str(path), "exec")


def test_no_nested_git_repositories_in_the_payload():
    assert list(BUNDLED.rglob(".git")) == []


# ---------------------------------------------------------------------------
# Layout and manifest coherence
# ---------------------------------------------------------------------------


def test_manifest_panel_order_matches_the_layout(layout, manifest):
    expected = {
        workbench: [panel["name"] for panel in panels]
        for workbench, panels in layout["workbenches"].items()
    }
    assert manifest["workbenchPanelOrder"] == expected


def test_adaptive_pins_target_panels_that_exist(layout, manifest):
    for workbench, config in manifest["adaptivePins"].items():
        groups = config["panels"].items() if "panels" in config else [(config["panel"], config)]
        panels = {panel["name"]: panel for panel in layout["workbenches"][workbench]}
        for panel_name, _group in groups:
            assert panel_name in panels, "{}/{} is not in the layout".format(workbench, panel_name)


def test_adaptive_defaults_come_from_the_candidate_pool(manifest):
    for workbench, config in manifest["adaptivePins"].items():
        groups = config["panels"].items() if "panels" in config else [(config["panel"], config)]
        for panel_name, group in groups:
            missing = set(group.get("defaults", [])) - set(group["commands"])
            assert missing == set(), "{}/{}: {}".format(workbench, panel_name, missing)


def test_a_whole_panel_pin_ships_its_defaults_as_the_starting_layout(layout, manifest):
    """A `panel` pin replaces the whole panel, so the layout must start at its defaults."""
    for workbench, config in manifest["adaptivePins"].items():
        if "panels" in config:
            continue
        panels = {panel["name"]: panel for panel in layout["workbenches"][workbench]}
        shipped = [entry[0] for entry in panels[config["panel"]]["commands"]]
        assert shipped == config["defaults"], "{}/{}".format(workbench, config["panel"])


def test_a_slot_swap_pin_only_names_commands_already_in_the_panel(layout, manifest):
    """A `panels` pin permutes existing slots, so every candidate must be present."""
    for workbench, config in manifest["adaptivePins"].items():
        if "panels" not in config:
            continue
        panels = {panel["name"]: panel for panel in layout["workbenches"][workbench]}
        for panel_name, group in config["panels"].items():
            declared = {entry[0] for entry in panels[panel_name]["commands"]}
            missing = set(group["commands"]) - declared
            assert missing == set(), "{}/{}: {}".format(workbench, panel_name, missing)


def test_adaptive_capacity_fits_the_panel(manifest):
    for _workbench, config in manifest["adaptivePins"].items():
        groups = config["panels"].values() if "panels" in config else [config]
        for group in groups:
            assert int(group.get("capacity", 4)) <= len(group["commands"])
            assert len(group.get("defaults", [])) <= int(group.get("capacity", 4))


def test_layout_command_entries_are_well_formed(layout):
    for workbench, panels in layout["workbenches"].items():
        names = [panel["name"] for panel in panels]
        assert len(names) == len(set(names)), "duplicate panel in {}".format(workbench)
        for panel in panels:
            assert panel["title"] and panel["name"].endswith("_newPanel")
            entries = panel["commands"] + panel.get("overflow", [])
            commands = [entry[0] for entry in entries]
            assert len(commands) == len(set(commands)), "duplicate command in " + panel["name"]
            for entry in entries:
                assert len(entry) == 5, entry
                _command, _source, size, text, _icon = entry
                assert size in {"small", "medium", "large"}, entry
                assert text.strip(), entry


def test_first_party_commands_in_the_layout_are_registered(layout, env, bootstrap):
    """Every FusionMyFreeCAD_* button in the ribbon must have a command behind it."""
    bootstrap.register_commands()
    declared = {
        entry[0]
        for panels in layout["workbenches"].values()
        for panel in panels
        for entry in panel["commands"] + panel.get("overflow", [])
        if entry[0].startswith("FusionMyFreeCAD_")
    }
    assert declared <= set(env.commands), declared - set(env.commands)


def _layout_commands(layout):
    """Real FreeCAD command ids in the layout, excluding generated dropdown ids."""
    return {
        entry[0]
        for panels in layout["workbenches"].values()
        for panel in panels
        for entry in panel["commands"] + panel.get("overflow", [])
        if not entry[0].endswith("_ddb")
    }


def test_primary_commands_cover_the_layout(layout, manifest):
    """write_runtime_status reports on primaryCommands, so it must list them all."""
    missing = _layout_commands(layout) - set(manifest["primaryCommands"])
    assert missing == set(), "manifest primaryCommands is missing {}".format(sorted(missing))


def test_every_dropdown_button_is_placed_in_a_panel(layout):
    placed = {
        entry[0]
        for panels in layout["workbenches"].values()
        for panel in panels
        for entry in panel["commands"]
        if entry[0].endswith("_ddb")
    }
    assert set(layout["dropdownButtons"]) == placed


def test_dropdown_members_are_tracked_commands(layout, manifest):
    known = set(manifest["primaryCommands"])
    for name, entries in layout["dropdownButtons"].items():
        assert entries, "{} is empty".format(name)
        for command, _source in entries:
            assert command in known, "{} in {} is not in primaryCommands".format(command, name)


def test_every_panel_has_a_complete_menu_inventory(layout):
    """Every authoritative panel gets a dropdown, even when nothing is initially hidden."""
    for workbench, panels in layout["workbenches"].items():
        for panel in panels:
            assert "overflow" in panel, "{}/{} has no menu inventory".format(
                workbench, panel["name"]
            )


# ---------------------------------------------------------------------------
# Vendor patches that must survive an upstream refresh
# ---------------------------------------------------------------------------


def test_ribbon_startup_cache_check_shows_no_modal_dialog():
    """A modal here can sit behind SearchBar's changelog and deadlock startup."""
    source = (BUNDLED / "FreeCAD-Ribbon" / "CacheFunctions.py").read_text("utf-8")
    tree = ast.parse(source)
    check = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "CheckDataFileVersion"
    )
    assert not any(
        isinstance(node, ast.Attribute) and node.attr == "Mbox" for node in ast.walk(check)
    )


def test_ribbon_dialogs_keep_a_close_button():
    source = (BUNDLED / "FreeCAD-Ribbon" / "CacheFunctions.py").read_text("utf-8")
    assert "WindowCloseButtonHint, True" in source


def test_ribbon_honours_the_authoritative_workbench_list():
    source = (BUNDLED / "FreeCAD-Ribbon" / "FCBinding.py").read_text("utf-8")
    assert 'workbenchName in Dict.get("authoritativeWorkbenches", [])' in source
    assert "ListToolbars: list = []" in source


def test_ribbon_buttons_use_direct_drag_with_the_platform_threshold():
    widgets = (BUNDLED / "FreeCAD-Ribbon" / "CustomWidgets.py").read_text("utf-8")
    binding = (BUNDLED / "FreeCAD-Ribbon" / "FCBinding.py").read_text("utf-8")
    assert "QApplication.startDragDistance()" in widgets
    assert "def _ensureDirectDragState" in binding
    assert "def _saveDirectDragState" in binding
    assert "fusion_bootstrap.record_customization" in binding


def test_every_fmf_panel_menu_offers_only_a_panel_scoped_reset():
    binding = (BUNDLED / "FreeCAD-Ribbon" / "FCBinding.py").read_text("utf-8")
    assert 'translate("FreeCAD Ribbon", "Reset this panel")' in binding
    assert "fusion_bootstrap.reset_panel_customization" in binding
    assert "FusionMyFreeCAD_ResetRibbon" not in binding


def test_searchbar_startup_is_non_interactive():
    """The upstream changelog dialog can sit under Ribbon's prompt and deadlock startup."""
    source = (BUNDLED / "SearchBar" / "InitGui.py").read_text("utf-8")
    dialog_calls = [
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and "ChangeDialog" in ast.dump(node.func)
    ]
    assert dialog_calls == [], "the SearchBar changelog dialog must stay suppressed"
    assert 'SetBoolSetting("ShowChangeDialog", False)' in source


def test_bundled_addons_declare_no_third_party_python_dependencies():
    """The dependency-stripping patches are the reason for bundling at all."""
    for name in ("FreeCAD-Ribbon", "SearchBar"):
        package = ET.parse(BUNDLED / name / "package.xml").getroot()
        required = [
            element.text
            for element in package.iter()
            if element.tag.endswith("depend")
            and element.get("type") == "python"
            and element.get("optional") != "true"
        ]
        assert required == [], "{} still declares {}".format(name, required)


def test_no_stripped_dependency_is_still_imported():
    stripped = ("lxml", "numpy", "matplotlib")
    offenders = []
    for path in BUNDLED.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), str(path))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                if name.split(".")[0] in stripped:
                    offenders.append("{}: {}".format(path.relative_to(ROOT), name))
    assert offenders == []


# ---------------------------------------------------------------------------
# Archive
# ---------------------------------------------------------------------------


def test_build_addon_package_produces_a_loadable_archive(package):
    version = package.findtext("p:version", namespaces=NAMESPACE)
    builder = _import_module("build_addon_package", ROOT / "tools" / "build_addon_package.py")
    builder.main()
    archive_path = ROOT / "dist" / "FusionMyFreeCAD-{}.zip".format(version)
    assert archive_path.is_file()
    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        for required in (
            "FusionMyFreeCAD/InitGui.py",
            "FusionMyFreeCAD/package.xml",
            "FusionMyFreeCAD/fusion_bootstrap.py",
            "FusionMyFreeCAD/Resources/FusionMyFreeCAD/runtime.py",
            "FusionMyFreeCAD/bundled-addons/FreeCAD-Ribbon/InitGui.py",
            "FusionMyFreeCAD/bundled-addons/SearchBar/InitGui.py",
            # The install guide points removers at this macro inside the archive.
            "FusionMyFreeCAD/tools/RestoreFusionMyFreeCAD.FCMacro",
        ):
            assert required in names, required
        assert not any(name.endswith(".pyc") for name in names)
        assert not any("__pycache__" in name for name in names)
        # The archive must contain exactly one top-level directory.
        assert {name.split("/")[0] for name in names} == {"FusionMyFreeCAD"}


def test_archive_stays_small_enough_to_ship(package):
    version = package.findtext("p:version", namespaces=NAMESPACE)
    archive_path = ROOT / "dist" / "FusionMyFreeCAD-{}.zip".format(version)
    if not archive_path.is_file():
        pytest.skip("archive not built")
    assert archive_path.stat().st_size < 8 * 1024 * 1024


def test_only_layout_icons_are_vendored(layout):
    """Ribbon needs local startup icons, but the full FreeCAD set is unnecessary."""
    directory = BUNDLED / "FreeCAD-Ribbon" / "Resources" / "FreeCAD Icons"
    bundled = {path.stem for path in directory.iterdir() if path.is_file()}
    used = {
        Path(entry[4]).stem
        for panels in layout["workbenches"].values()
        for panel in panels
        for entry in panel["commands"] + panel.get("overflow", [])
    }
    assert bundled == used


def test_every_layout_icon_was_verified_by_freecad_or_its_source(layout):
    """Guard icon names using a recorded runtime probe or exact source files.

    `Gui.getIcon()` returns a placeholder rather than failing for an unknown name,
    so a wrong name renders a grey question mark instead of raising. The verified
    list comes from `tools/probe_freecad_icons.py` run against a real install.
    """
    runtime = json.loads((RESOURCES / "verified-icons.json").read_text("utf-8"))
    source = json.loads((RESOURCES / "source-icons.json").read_text("utf-8"))
    assert runtime["missing"] == [], runtime["missing"]
    used = {
        entry[4]
        for panels in layout["workbenches"].values()
        for panel in panels
        for entry in panel["commands"] + panel.get("overflow", [])
    }
    verified = set(runtime["verified"]) | set(source["icons"])
    unverified = sorted(used - verified)
    assert unverified == [], (
        "These icon names were never verified against FreeCAD or resolved from "
        "its official source checkout: {}".format(unverified)
    )


def test_the_source_icon_list_has_no_stale_entries(layout):
    """A name dropped from the layout should not linger in the source manifest."""
    verified = json.loads((RESOURCES / "source-icons.json").read_text("utf-8"))
    used = {
        entry[4]
        for panels in layout["workbenches"].values()
        for panel in panels
        for entry in panel["commands"] + panel.get("overflow", [])
    }
    assert set(verified["icons"]) == used
    directory = BUNDLED / "FreeCAD-Ribbon" / "Resources" / "FreeCAD Icons"
    for name, evidence in verified["icons"].items():
        actual = hashlib.sha256((directory / (name + ".svg")).read_bytes()).hexdigest()
        assert actual == evidence["sha256"], name


def test_the_probe_records_which_freecad_it_checked():
    verified = json.loads((RESOURCES / "verified-icons.json").read_text("utf-8"))
    assert verified["freeCADVersion"].startswith("1.1"), verified["freeCADVersion"]
