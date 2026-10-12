"""Package integrity: metadata, layout coherence, vendor patches, and the archive."""

from __future__ import annotations

import ast
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest
from fake_freecad import ROOT, _import_module

sys.path.insert(0, str(ROOT / "tools"))
from validate_layout_contracts import (
    COMMAND_CONTRACTS,
)
from validate_layout_contracts import (
    validate as validate_layout_contracts,
)

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


def test_behavior_sensitive_layout_commands_match_contracts():
    assert {"coincident", "mirror", "create-sketch", "pad", "pocket"} <= set(COMMAND_CONTRACTS)
    validate_layout_contracts(ROOT)


def test_required_files_are_present():
    required = [
        ROOT / "Init.py",
        ROOT / "InitGui.py",
        ROOT / "fusion_actions.py",
        ROOT / "fusion_bootstrap.py",
        ROOT / "fusion_workbenches.py",
        ROOT / "fusion_sketch_tools.py",
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


def test_current_fmf_owned_names_do_not_use_fusion_prefix(layout):
    assert set(layout["workbenches"]) == {
        "FMFDesignWorkbench",
        "FMFPartWorkbench",
        "FMFSketchWorkbench",
        "FMFSurfaceWorkbench",
    }
    panel_names = [panel["name"] for panels in layout["workbenches"].values() for panel in panels]
    assert all(not name.startswith("Fusion ") for name in panel_names)


def test_dev_installer_rejects_saved_scratch_profile():
    source = (ROOT / "tools" / "install-dev.ps1").read_text(encoding="utf-8-sig")
    assert "Test-IsScratchModDir" in source
    assert "Ignoring saved isolated test profile" in source


def test_runtime_local_imports_are_declared_for_packaging():
    """A source-checkout import must not hide a module omitted from release ZIPs."""
    import ast

    from fusion_common import RUNTIME_MODULES

    declared = {Path(name).stem for name in RUNTIME_MODULES}
    runtime_tree = ast.parse((RESOURCES / "runtime.py").read_text(encoding="utf-8"))
    imported = {
        alias.name.split(".", 1)[0]
        for node in ast.walk(runtime_tree)
        if isinstance(node, ast.Import)
        for alias in node.names
        if alias.name.startswith("fusion_")
    }
    imported.update(
        node.module.split(".", 1)[0]
        for node in ast.walk(runtime_tree)
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("fusion_")
    )
    assert imported <= declared, "Undeclared packaged runtime imports: {}".format(
        sorted(imported - declared)
    )


def test_every_python_file_compiles():
    skipped = {"vendor", "__pycache__", ".git"}
    for path in ROOT.rglob("*.py"):
        if skipped.intersection(path.parts):
            continue
        compile(path.read_text(encoding="utf-8-sig"), str(path), "exec")


def test_no_nested_git_repositories_in_the_payload():
    assert list(BUNDLED.rglob(".git")) == []


def test_bundled_ribbon_keeps_non_fmf_workbenches_visible():
    source = (BUNDLED / "FreeCAD-Ribbon" / "FCBinding.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    method = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "onWbActivated"
    )
    method_source = ast.get_source_segment(source, method)
    assert "_setFmfChromeVisible(True)" in method_source
    assert "_setFmfChromeVisible(False)" not in method_source


def test_bundled_ribbon_customization_rejects_a_missing_replacement_panel():
    source = (BUNDLED / "FreeCAD-Ribbon" / "FCBinding.py").read_text(encoding="utf-8")
    assert "if newPanel is None:" in source
    assert "leaving the existing panel unchanged" in source


# ---------------------------------------------------------------------------
# Layout and manifest coherence
# ---------------------------------------------------------------------------


def test_manifest_panel_order_matches_the_layout(layout, manifest):
    expected = {
        workbench: [panel["name"] for panel in panels]
        for workbench, panels in layout["workbenches"].items()
    }
    assert manifest["workbenchPanelOrder"] == expected


def _adaptive_groups(config):
    """(panel name, group, whether it owns the whole section) for one workbench."""
    return [
        (name, group, bool(group.get("whole", False))) for name, group in config["panels"].items()
    ]


def test_adaptive_pins_target_panels_that_exist(layout, manifest):
    for workbench, config in manifest["adaptivePins"].items():
        panels = {panel["name"]: panel for panel in layout["workbenches"][workbench]}
        for panel_name, _group, _whole in _adaptive_groups(config):
            assert panel_name in panels, "{}/{} is not in the layout".format(workbench, panel_name)


def test_adaptive_defaults_come_from_the_candidate_pool(manifest):
    for workbench, config in manifest["adaptivePins"].items():
        for panel_name, group, _whole in _adaptive_groups(config):
            missing = set(group.get("defaults", [])) - set(group["commands"])
            assert missing == set(), "{}/{}: {}".format(workbench, panel_name, missing)


def test_a_whole_panel_pin_ships_its_defaults_as_the_starting_layout(layout, manifest):
    """A whole-panel pin replaces the section, so the layout must start at its defaults."""
    for workbench, config in manifest["adaptivePins"].items():
        panels = {panel["name"]: panel for panel in layout["workbenches"][workbench]}
        for panel_name, group, whole in _adaptive_groups(config):
            if not whole:
                continue
            shipped = [entry[0] for entry in panels[panel_name]["commands"]]
            assert shipped == group["defaults"], "{}/{}".format(workbench, panel_name)


def test_a_frequent_section_ships_the_shape_the_runtime_rewrites_it_to(layout, manifest):
    """Two large slots then small ones.

    The runtime fixes the shape so the section does not rearrange itself as
    habits change; if the shipped layout disagreed, every FREQUENT section
    would be rewritten once on first use for no visible reason.
    """
    for workbench, config in manifest["adaptivePins"].items():
        panels = {panel["name"]: panel for panel in layout["workbenches"][workbench]}
        for panel_name, _group, whole in _adaptive_groups(config):
            if not whole:
                continue
            sizes = [entry[2] for entry in panels[panel_name]["commands"]]
            expected = ["large" if index < 2 else "small" for index in range(len(sizes))]
            assert sizes == expected, "{}/{}".format(workbench, panel_name)


def test_a_slot_swap_pin_only_names_commands_already_in_the_panel(layout, manifest):
    """A slot-swap pin permutes existing slots, so every candidate must be present."""
    for workbench, config in manifest["adaptivePins"].items():
        panels = {panel["name"]: panel for panel in layout["workbenches"][workbench]}
        for panel_name, group, whole in _adaptive_groups(config):
            if whole:
                continue
            declared = {entry[0] for entry in panels[panel_name]["commands"]}
            missing = set(group["commands"]) - declared
            assert missing == set(), "{}/{}: {}".format(workbench, panel_name, missing)


def test_every_command_a_workbench_offers_can_reach_its_frequent_section(layout, manifest):
    """The candidate pool is the whole ribbon, not a hand-picked shortlist.

    A section that promotes what gets used can only promote what it is allowed
    to consider. The pool used to be a dozen commands per workbench, so almost
    everything a user actually clicked was invisible to the ranking and the
    section never changed -- which reads, from outside, as a feature that does
    not work. `tools/generate_frequent_pools.py` regenerates these.
    """
    for workbench, config in manifest["adaptivePins"].items():
        offered = {
            entry[0]
            for panel in layout["workbenches"][workbench]
            for entry in list(panel.get("commands", [])) + list(panel.get("overflow", []))
            if not entry[0].endswith("_ddb")
        }
        for panel_name, group, whole in _adaptive_groups(config):
            if not whole:
                continue
            missing = offered - set(group["commands"])
            assert missing == set(), "{}/{}: {}".format(workbench, panel_name, sorted(missing))


def test_every_workbench_has_a_frequent_section(layout):
    """Somewhere to collect what you reach for, whichever workbench you are in."""
    for workbench, panels in layout["workbenches"].items():
        titles = [panel["title"] for panel in panels]
        assert "FREQUENT" in titles, workbench


def test_adaptive_capacity_fits_the_panel(manifest):
    for _workbench, config in manifest["adaptivePins"].items():
        for _panel_name, group, _whole in _adaptive_groups(config):
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


def test_responsive_commands_are_real_overflow_commands(layout):
    """Width-aware commands must remain available in the panel menu when compact."""
    for workbench, panels in layout["workbenches"].items():
        for panel in panels:
            overflow = {entry[0] for entry in panel.get("overflow", [])}
            responsive = panel.get("responsive", {})
            assert set(responsive) <= overflow, "{}/{}".format(workbench, panel["name"])
            assert all(isinstance(width, int) and width >= 1024 for width in responsive.values())

    sketcher = layout["workbenches"]["FMFSketchWorkbench"]
    assert sum(len(panel.get("responsive", {})) for panel in sketcher) >= 25


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


def test_validate_sketch_is_visible_after_finishing_a_sketch(layout):
    """Profile repair must not be hidden when Part Design regains control after sketch editing."""
    panels = {panel["name"]: panel for panel in layout["workbenches"]["FMFDesignWorkbench"]}
    visible = {entry[0] for entry in panels["FMF Sketch Entry_newPanel"]["commands"]}
    assert "Sketcher_ValidateSketch" in visible


def test_create_sketch_stays_visible_in_the_sketcher_workbench(layout):
    """Finishing a sketch must not strand the user without Create Sketch."""
    panels = {panel["name"]: panel for panel in layout["workbenches"]["FMFSketchWorkbench"]}
    visible = {entry[0] for entry in panels["FMF Sketch Create_newPanel"]["commands"]}
    assert "FusionMyFreeCAD_CreateSketch" in visible


def test_symmetric_constraint_is_a_top_level_movable_command(layout):
    panels = {panel["name"]: panel for panel in layout["workbenches"]["FMFSketchWorkbench"]}
    constraints = panels["FMF Sketch Constraints_newPanel"]
    visible = {entry[0] for entry in constraints["commands"]}
    assert "Sketcher_ConstrainSymmetric" in visible
    assert "Fusion_MoreConstraints_ddb" not in visible
    assert "Fusion_MoreConstraints_ddb" not in layout["dropdownButtons"]


def test_mirror_with_constraints_sits_beside_the_native_mirror(layout, manifest):
    """The constraint-copying mirror is a small button in front of native Mirror,
    which keeps its 1.3.1 size so the panel wrap geometry is barely disturbed."""
    modify = {panel["name"]: panel for panel in layout["workbenches"]["FMFSketchWorkbench"]}[
        "FMF Sketch Modify_newPanel"
    ]
    commands = modify["commands"]
    order = [entry[0] for entry in commands]
    assert "FusionMyFreeCAD_MirrorWithConstraints" in order
    by_name = {entry[0]: entry for entry in commands}
    assert by_name["FusionMyFreeCAD_MirrorWithConstraints"][2] == "small"
    assert by_name["FusionMyFreeCAD_MirrorWithConstraints"][3] == "Mirror + Constraints"
    assert by_name["Sketcher_Symmetry"][2] == "large"
    assert (
        order.index("Sketcher_Symmetry") - order.index("FusionMyFreeCAD_MirrorWithConstraints") == 1
    )
    assert "FusionMyFreeCAD_MirrorWithConstraints" in manifest["primaryCommands"]
    assert "FusionMyFreeCAD_AddMidline" in order
    assert by_name["FusionMyFreeCAD_AddMidline"][2] == "small"
    assert by_name["FusionMyFreeCAD_AddMidline"][3] == "Midline"
    assert (
        order.index("FusionMyFreeCAD_MirrorWithConstraints")
        - order.index("FusionMyFreeCAD_AddMidline")
        == 1
    )
    assert "FusionMyFreeCAD_AddMidline" in manifest["primaryCommands"]

    constraints_panel = {
        panel["name"]: panel for panel in layout["workbenches"]["FMFSketchWorkbench"]
    }["FMF Sketch Constraints_newPanel"]
    const_commands = constraints_panel["commands"]
    const_order = [entry[0] for entry in const_commands]
    const_by_name = {entry[0]: entry for entry in const_commands}
    assert "FusionMyFreeCAD_ConstrainMidpoint" in const_order
    assert const_by_name["FusionMyFreeCAD_ConstrainMidpoint"][2] == "small"
    assert const_by_name["FusionMyFreeCAD_ConstrainMidpoint"][3] == "Midpoint"
    assert "Sketcher_ConstrainCoincidentUnified" in const_order
    assert "Sketcher_ConstrainCoincident" not in const_order
    assert (
        const_order.index("FusionMyFreeCAD_ConstrainMidpoint")
        - const_order.index("Sketcher_ConstrainCoincidentUnified")
        == 1
    )
    assert "FusionMyFreeCAD_ConstrainMidpoint" in manifest["primaryCommands"]

    frequent_panel = {
        panel["name"]: panel for panel in layout["workbenches"]["FMFSketchWorkbench"]
    }["FMF Sketch Frequent_newPanel"]
    frequent_order = [entry[0] for entry in frequent_panel["commands"]]
    assert "Sketcher_ConstrainCoincidentUnified" in frequent_order
    assert "Sketcher_ConstrainCoincident" not in frequent_order

    frequent_manifest = manifest["adaptivePins"]["FMFSketchWorkbench"]["panels"][
        "FMF Sketch Frequent_newPanel"
    ]
    assert "Sketcher_ConstrainCoincidentUnified" in frequent_manifest["defaults"]
    assert "Sketcher_ConstrainCoincidentUnified" in frequent_manifest["commands"]
    assert "Sketcher_ConstrainCoincident" not in frequent_manifest["commands"]


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


def test_ribbon_surfaces_overflow_commands_at_declared_width_tiers():
    source = (BUNDLED / "FreeCAD-Ribbon" / "FCBinding.py").read_text("utf-8")
    assert "def _responsiveWidthTier" in source
    assert "def _rebuildResponsivePanels" in source
    assert "def resizeEvent" in source
    assert 'responsiveCommands = panelDefinition.get("responsive", {})' in source
    assert "mw.width() >= int(minimumResponsiveWidth)" in source
    assert "panelMenuOrder" in source
    assert 'Dict.get("authoritativeWorkbenches", [])' in source


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


def test_the_panel_title_opens_the_overflow_drawer():
    """The clickable section header is a local change; a refresh must not drop it.

    tools/sync_bundled_addons.py replaces the whole vendored tree and re-applies
    this from PANEL_TITLE_DRAWER_PATCH. Asserting the result here means a sync
    against an upstream that moved the anchors fails the suite rather than
    quietly shipping a ribbon whose titles do nothing.
    """
    panel = (
        BUNDLED / "FreeCAD-Ribbon" / "Resources" / "packages" / "pyqtribbon_local" / "panel.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(panel)
    classes = {node.name: node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}

    title = classes["RibbonPanelTitle"]
    title_members = {node.name for node in title.body if isinstance(node, ast.FunctionDef)}
    assert {"mousePressEvent", "enterEvent"} <= title_members
    assert any(
        isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") == "drawerAvailable"
        for node in title.body
    ), "RibbonPanelTitle must report whether the drawer can open"

    panel_class = classes["RibbonPanel"]
    panel_members = {node.name for node in panel_class.body if isinstance(node, ast.FunctionDef)}
    assert {"isDrawerAvailable", "openDrawer"} <= panel_members


def _sync_tool():
    sys.path.insert(0, str(ROOT / "tools"))
    try:
        import sync_bundled_addons

        return sync_bundled_addons
    finally:
        sys.path.pop(0)


def test_every_local_ui_patch_is_present_in_the_bundled_tree():
    """Re-applying a patch must be a no-op, so a sync cannot double-apply it.

    This is also what catches a hand-edit to the vendored tree that the sync tool
    does not know how to reproduce: the next refresh would silently drop it.
    """
    sync = _sync_tool()
    for parts, patches in sync.LOCAL_PATCHES:
        text = BUNDLED.joinpath(*parts).read_text(encoding="utf-8")
        lines = text.splitlines(keepends=True)
        for patch in patches:
            # Ask the tool itself whether the patch reads as applied, rather than
            # testing for the replacement here. A substring test compares the
            # wrong things: where upstream repeats a handler the shorter
            # replacement is a substring of the longer one, a patch that only
            # deletes leaves a replacement that is part of its own anchor, and a
            # later patch may edit inside an earlier one's replacement.
            anchor, replacement = patch[0], patch[1]
            expected = patch[2] if len(patch) > 2 else 1
            proof = patch[3] if len(patch) > 3 else None
            assert sync.patch_is_applied(text, lines, anchor, replacement, expected, proof), (
                "{} is missing a local patch: {}".format(parts[-1], anchor.strip().splitlines()[0])
            )


def test_the_files_fusionmyfreecad_owns_are_bundled():
    """A refresh wipes the tree; these have to be carried across it."""
    sync = _sync_tool()
    assert sync.FMF_OWNED_FILES
    for parts in sync.FMF_OWNED_FILES:
        assert BUNDLED.joinpath(*parts).is_file(), parts


def test_no_local_hook_probes_a_ribbon_panel_with_getattr():
    """RibbonPanel.__getattr__ turns any attribute miss into AssertionError.

    It exists to synthesise addSmall*/addMedium*/addLarge* and asserts on every
    other name, so `getattr(panel, "x", default)` does not fall back -- getattr's
    default only swallows AttributeError. Reading __dict__ is the safe probe.
    Every FusionMyFreeCAD hook that asks a panel whether an attribute exists must
    use it; one that did not took the whole ribbon down on workbench activation.
    """
    offenders = []
    for parts, patches in _sync_tool().LOCAL_PATCHES:
        # `self` is only a RibbonPanel inside panel.py; in FCBinding.py it is the
        # ribbon bar and in CustomWidgets.py a tool button, neither of which traps
        # attribute lookup. A variable actually named `panel` is a RibbonPanel
        # wherever it appears.
        probes = (
            r"getattr\(\s*(self|panel)\s*," if parts[-1] == "panel.py" else r"getattr\(\s*panel\s*,"
        )
        for patch in patches:
            replacement = patch[1]
            for line in replacement.splitlines():
                stripped = line.strip()
                if not stripped.startswith("#") and re.search(probes, stripped):
                    offenders.append("{}: {}".format(parts[-1], stripped))
    assert offenders == [], (
        "Probe a RibbonPanel with __dict__.get() instead; getattr raises here: {}".format(offenders)
    )


def test_the_ribbon_panel_getattr_trap_still_behaves_as_assumed():
    """Pin the upstream behaviour the rule above exists for.

    If upstream ever makes __getattr__ raise AttributeError properly, this fails
    and the __dict__ probes can be simplified back to getattr.
    """
    panel = (
        BUNDLED / "FreeCAD-Ribbon" / "Resources" / "packages" / "pyqtribbon_local" / "panel.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(panel)
    panel_class = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and node.name == "RibbonPanel"
    )
    getattr_def = next(
        node
        for node in panel_class.body
        if isinstance(node, ast.FunctionDef) and node.name == "__getattr__"
    )
    assert any(isinstance(node, ast.Assert) for node in ast.walk(getattr_def)), (
        "RibbonPanel.__getattr__ no longer asserts; the __dict__ probes can be relaxed"
    )
    assert not any(
        isinstance(node, ast.Raise)
        and isinstance(node.exc, ast.Call)
        and getattr(node.exc.func, "id", "") == "AttributeError"
        for node in ast.walk(getattr_def)
    )


def test_the_draggable_divider_reaches_the_panel():
    """The widget is FusionMyFreeCAD's, but the wiring lives in upstream's panel."""
    panel = (
        BUNDLED / "FreeCAD-Ribbon" / "Resources" / "packages" / "pyqtribbon_local" / "panel.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(panel)
    panel_class = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and node.name == "RibbonPanel"
    )
    assert any(
        isinstance(node, ast.Assign)
        and any(getattr(t, "id", "") == "panelResizeRequested" for t in node.targets)
        for node in panel_class.body
    ), "RibbonPanel must expose panelResizeRequested"
    assert "DraggablePanelSeparator(width=3)" in panel


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
            "FusionMyFreeCAD/fusion_actions.py",
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
        assert {entry.create_system for entry in archive.infolist()} == {3}
        text_entries = [
            entry
            for entry in archive.infolist()
            if Path(entry.filename).suffix.lower() not in builder.BINARY_SUFFIXES
        ]
        assert not any(b"\r" in archive.read(entry) for entry in text_entries)
        # The archive must contain exactly one top-level directory.
        assert {name.split("/")[0] for name in names} == {"FusionMyFreeCAD"}


def test_fresh_extracted_archive_startup(tmp_path, env, monkeypatch):
    """Test startup from an extracted archive with the git checkout excluded from sys.path."""
    builder = _import_module("build_addon_package", ROOT / "tools" / "build_addon_package.py")
    builder.main()
    version = builder.package_version()
    archive_path = ROOT / "dist" / f"FusionMyFreeCAD-{version}.zip"

    extract_dir = tmp_path / "extracted"
    with zipfile.ZipFile(archive_path) as archive:
        archive.extractall(extract_dir)

    addon_root = extract_dir / "FusionMyFreeCAD"
    from fusion_common import RUNTIME_MODULES

    for mod_name in RUNTIME_MODULES:
        assert (addon_root / mod_name).is_file(), f"Missing from zip: {mod_name}"

    # Remove ROOT from sys.path and prepend extracted addon_root
    clean_sys_path = [p for p in sys.path if Path(p).resolve() != ROOT.resolve()]
    clean_sys_path.insert(0, str(addon_root))
    monkeypatch.setattr(sys, "path", clean_sys_path)

    # Pop cached modules
    for name in [
        k
        for k in list(sys.modules.keys())
        if k.startswith("fusion_")
        or k in ("_fusion_my_freecad_runtime", "fusion_init_gui_extracted")
    ]:
        sys.modules.pop(name, None)

    env.install()
    # Stub vendor loads to test add-on bootstrap & registration cleanly
    extracted_bootstrap = _import_module("fusion_bootstrap", addon_root / "fusion_bootstrap.py")
    monkeypatch.setattr(extracted_bootstrap, "load_vendor", lambda *_args: None)
    monkeypatch.setattr(extracted_bootstrap, "run_runtime", lambda: None)

    init_gui = _import_module("fusion_init_gui_extracted", addon_root / "InitGui.py")
    assert init_gui is not None
    assert "FusionMyFreeCAD_CreateSketch" in env.commands
    assert "FusionMyFreeCAD_ParameterDock" in env.commands
    assert "FusionMyFreeCAD_DatumMidplane" in env.commands
    assert "FusionMyFreeCAD_StudioViewport" in env.commands


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


def test_every_layout_icon_was_verified_by_freecad_or_its_source(layout, manifest):
    """Guard icon names using a recorded runtime probe or exact source files.

    `Gui.getIcon()` returns a placeholder rather than failing for an unknown name,
    so a wrong name renders a grey question mark instead of raising. The verified
    list comes from `tools/probe_freecad_icons.py` run against a real install.
    FusionMyFreeCAD's own composite icons are declared in `authoredIcons`.
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
    verified = set(runtime["verified"]) | set(source["icons"]) | set(manifest["authoredIcons"])
    unverified = sorted(used - verified)
    assert unverified == [], (
        "These icon names were never verified against FreeCAD, resolved from its "
        "official source checkout, or declared in authoredIcons: {}".format(unverified)
    )


def test_authored_icons_are_vendored_and_not_claimed_as_freecad_source(manifest):
    """Each authored icon must ship as a file and must not masquerade as FreeCAD's."""
    directory = BUNDLED / "FreeCAD-Ribbon" / "Resources" / "FreeCAD Icons"
    source = json.loads((RESOURCES / "source-icons.json").read_text("utf-8"))
    for name in manifest["authoredIcons"]:
        assert (directory / (name + ".svg")).is_file(), name
        assert name not in source["icons"], name


def test_the_source_icon_list_has_no_stale_entries(layout, manifest):
    """A name dropped from the layout should not linger in the source manifest."""
    verified = json.loads((RESOURCES / "source-icons.json").read_text("utf-8"))
    used = {
        entry[4]
        for panels in layout["workbenches"].values()
        for panel in panels
        for entry in panel["commands"] + panel.get("overflow", [])
    }
    assert set(verified["icons"]) == used - set(manifest["authoredIcons"])
    directory = BUNDLED / "FreeCAD-Ribbon" / "Resources" / "FreeCAD Icons"
    for name, evidence in verified["icons"].items():
        content = (directory / (name + ".svg")).read_bytes()
        canonical = content.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        actual = hashlib.sha256(canonical).hexdigest()
        assert actual == evidence["sha256"], name


def test_the_probe_records_which_freecad_it_checked():
    verified = json.loads((RESOURCES / "verified-icons.json").read_text("utf-8"))
    assert verified["freeCADVersion"].startswith("1.1"), verified["freeCADVersion"]


def test_the_ribbon_global_tools_panel_is_not_carried_into_the_layout(bootstrap):
    """UTILITIES replaces it, and a global panel belongs to no workbench.

    FreeCAD-Ribbon adds a "Tools" panel of Std_ commands to every workbench
    from newPanels/Global. Because it is not part of any workbench's toolbars,
    a divider drag on it had nothing to write to and reported "no toolbar named
    that in the ribbon structure".
    """
    ribbon, _version = bootstrap._merge_layout()
    assert "Tools_newPanel" not in ribbon.get("newPanels", {}).get("Global", {})


def test_the_ribbon_tools_panel_preference_is_managed(bootstrap):
    """Otherwise the add-on recreates the panel on the next start."""
    managed = {(group, key) for group, key, _kind in bootstrap.PREFERENCE_KEYS}
    assert ("User parameter:BaseApp/Preferences/Mod/FreeCAD-Ribbon", "UseToolsPanel") in managed


def test_every_workbench_carries_a_utilities_section(layout):
    """The commands the global Tools panel held now live in the layout."""
    for workbench, panels in layout["workbenches"].items():
        utilities = [panel for panel in panels if panel["title"] == "UTILITIES"]
        assert len(utilities) == 1, workbench
        commands = {entry[0] for entry in utilities[0]["commands"] + utilities[0]["overflow"]}
        assert "Std_UnitsCalculator" in commands
        assert "Std_Measure" not in commands, "already in INSPECT; do not duplicate"


def test_export_ends_the_tab_wherever_it_appears(layout):
    """Export is the right-hand bookend, as Create Sketch is the left-hand one.

    A ribbon tab is read from its edges, so the command that finishes a part
    belongs at the end of it rather than buried before the utilities.
    """
    for workbench, panels in layout["workbenches"].items():
        output = [panel for panel in panels if panel["title"] == "EXPORT"]
        if not output:
            continue
        assert panels[-1] is output[0], workbench
        first = output[0]["commands"][0]
        assert first[0] == "FusionMyFreeCAD_Export"
        assert first[2] == "large", "the export button has to read as prominent"


def test_every_export_format_is_told_apart_by_its_own_icon(layout):
    """One shared icon four times over tells the user nothing.

    The format buttons sit side by side once the section is widened, so each
    needs its own mark and its own caption to be picked out at a glance.
    """
    for workbench, panels in layout["workbenches"].items():
        export = [panel for panel in panels if panel["title"] == "EXPORT"]
        if not export:
            continue
        entries = export[0]["commands"] + export[0]["overflow"]
        icons = [entry[4] for entry in entries]
        captions = [entry[3] for entry in entries]
        assert len(set(icons)) == len(icons), "{}: duplicate icon".format(workbench)
        assert len(set(captions)) == len(captions), "{}: duplicate caption".format(workbench)
        for entry in entries[1:]:
            assert entry[3] in {"STEP", "STL", "3MF", "DXF"}, entry


def test_create_sketch_still_opens_the_part_design_tab(layout):
    """README promises it; the export bookend must not have displaced it."""
    first = layout["workbenches"]["FMFDesignWorkbench"][0]
    assert first["commands"][0][0] == "FusionMyFreeCAD_CreateSketch"
    assert first["commands"][0][2] == "large"
