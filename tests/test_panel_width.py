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
