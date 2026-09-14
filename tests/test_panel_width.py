"""The per-panel column budget behind the draggable panel dividers.

The drag itself is Qt, and the pixel-to-column arithmetic lives in FCBinding
inside the vendored ribbon. What is testable offline -- and what actually has to
survive a FreeCAD restart and an add-on update -- is that the budget round-trips
through FusionMyFreeCAD's own customization file and reaches the generated
ribbon.
"""

from __future__ import annotations

import json


def _toolbar(bootstrap, workbench, panel):
    ribbon, _version = bootstrap._merge_layout()
    return ribbon["workbenches"][workbench]["toolbars"][panel]


def _first_panel(bootstrap):
    spec = bootstrap._load_json(bootstrap.LAYOUT_SPEC)
    workbench = "PartDesignWorkbench"
    return workbench, spec["workbenches"][workbench][0]["name"]


def test_a_panel_has_no_column_budget_until_its_divider_is_dragged(installed):
    """Untouched panels must follow the Ribbon add-on's global preference."""
    workbench, panel = _first_panel(installed)
    assert "maxColumns" not in _toolbar(installed, workbench, panel)


def test_a_dragged_divider_reaches_the_generated_ribbon(installed, env):
    workbench, panel = _first_panel(installed)
    ribbon, _version = installed._merge_layout()
    ribbon["workbenches"][workbench]["toolbars"][panel]["maxColumns"] = 3

    installed.record_customization(ribbon)

    assert _toolbar(installed, workbench, panel)["maxColumns"] == 3


def test_the_budget_survives_a_restart(installed):
    workbench, panel = _first_panel(installed)
    ribbon, _version = installed._merge_layout()
    ribbon["workbenches"][workbench]["toolbars"][panel]["maxColumns"] = 2
    installed.record_customization(ribbon)

    stored = json.loads(open(installed.CUSTOMIZATION_PATH, encoding="utf-8").read())
    saved = stored["workbenches"][workbench]["panels"][panel]
    assert saved["maxColumns"] == 2
    # A second merge reads the file back exactly as a fresh session would.
    assert _toolbar(installed, workbench, panel)["maxColumns"] == 2


def test_a_budget_below_one_column_is_clamped(installed):
    workbench, panel = _first_panel(installed)
    ribbon, _version = installed._merge_layout()
    ribbon["workbenches"][workbench]["toolbars"][panel]["maxColumns"] = 0
    installed.record_customization(ribbon)

    assert _toolbar(installed, workbench, panel)["maxColumns"] == 1


def test_an_unreadable_budget_is_dropped_rather_than_raising(installed):
    """A hand-edited or half-written file must not stop the ribbon from building."""
    workbench, panel = _first_panel(installed)
    customization = installed._read_customization()
    customization.setdefault("workbenches", {}).setdefault(workbench, {}).setdefault(
        "panels", {}
    ).setdefault(panel, {})["maxColumns"] = "wide"
    installed._atomic_json(installed.CUSTOMIZATION_PATH, customization)

    assert "maxColumns" not in _toolbar(installed, workbench, panel)


def test_resetting_one_panel_clears_its_budget(installed):
    workbench, panel = _first_panel(installed)
    ribbon, _version = installed._merge_layout()
    ribbon["workbenches"][workbench]["toolbars"][panel]["maxColumns"] = 5
    installed.record_customization(ribbon)
    assert _toolbar(installed, workbench, panel)["maxColumns"] == 5

    installed.reset_panel_customization(workbench, panel)

    assert "maxColumns" not in _toolbar(installed, workbench, panel)


def test_a_dragged_width_survives_a_restart(installed):
    """The width is what the user dragged, so the width is what persists."""
    workbench, panel = _first_panel(installed)
    ribbon, _version = installed._merge_layout()
    ribbon["workbenches"][workbench]["toolbars"][panel]["minWidth"] = 412
    installed.record_customization(ribbon)

    stored = json.loads(open(installed.CUSTOMIZATION_PATH, encoding="utf-8").read())
    assert stored["workbenches"][workbench]["panels"][panel]["minWidth"] == 412
    assert _toolbar(installed, workbench, panel)["minWidth"] == 412


def test_an_unreadable_width_is_dropped_rather_than_raising(installed):
    workbench, panel = _first_panel(installed)
    customization = installed._read_customization()
    customization.setdefault("workbenches", {}).setdefault(workbench, {}).setdefault(
        "panels", {}
    ).setdefault(panel, {})["minWidth"] = "wide"
    installed._atomic_json(installed.CUSTOMIZATION_PATH, customization)

    assert "minWidth" not in _toolbar(installed, workbench, panel)


def test_resetting_one_panel_clears_its_width(installed):
    workbench, panel = _first_panel(installed)
    ribbon, _version = installed._merge_layout()
    ribbon["workbenches"][workbench]["toolbars"][panel]["minWidth"] = 300
    installed.record_customization(ribbon)
    assert _toolbar(installed, workbench, panel)["minWidth"] == 300

    installed.reset_panel_customization(workbench, panel)

    assert "minWidth" not in _toolbar(installed, workbench, panel)


def test_a_saved_panel_order_from_an_older_layout_is_not_replayed(installed):
    """A release that changes the sections has to be able to reach an install.

    Replaying an order recorded against the previous layout silently overrode
    the new one, and because the result then matched what was already on disk,
    verification passed and nothing was regenerated. Two releases of section
    changes reached nobody that way.
    """
    workbench, _panel = _first_panel(installed)
    spec = installed._load_json(installed.LAYOUT_SPEC)
    shipped = [panel["name"] for panel in spec["workbenches"][workbench]]

    stale = {
        "schemaVersion": 1,
        "layoutVersion": "0.0.1-old",
        "workbenches": {workbench: {"panelOrder": list(reversed(shipped)), "panels": {}}},
    }
    installed._atomic_json(installed.CUSTOMIZATION_PATH, stale)
    ribbon, _version = installed._merge_layout()
    assert ribbon["workbenches"][workbench]["toolbars"]["order"] == shipped

    current = dict(stale, layoutVersion=spec["layoutVersion"])
    installed._atomic_json(installed.CUSTOMIZATION_PATH, current)
    ribbon, _version = installed._merge_layout()
    assert ribbon["workbenches"][workbench]["toolbars"]["order"] == list(reversed(shipped)), (
        "an order recorded against this layout is still the user's to keep"
    )


def test_per_panel_settings_survive_a_layout_version_change(installed):
    """Only the order between sections is taken from the new layout."""
    workbench, panel = _first_panel(installed)
    stale = {
        "schemaVersion": 1,
        "layoutVersion": "0.0.1-old",
        "workbenches": {
            workbench: {"panelOrder": [], "panels": {panel: {"minWidth": 321, "widthModel": 2}}}
        },
    }
    installed._atomic_json(installed.CUSTOMIZATION_PATH, stale)
    assert _toolbar(installed, workbench, panel)["minWidth"] == 321
