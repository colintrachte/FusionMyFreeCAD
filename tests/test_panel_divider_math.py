"""The arithmetic behind the draggable panel dividers.

This decides how wide a drag leaves a ribbon section. It has been wrong four
times, and every symptom looked the same from outside: a divider that sometimes
or never appeared to do anything. It lives in a Qt-free module so the cases can
be pinned down without standing up a widget toolkit.

The mistake underneath most of those attempts was measuring in columns. A
section's column count describes its *contents*, not its *size*, so it did not
change when the section was given more room -- a second drag then started from
exactly where the first did. Everything here is in pixels.
"""

from __future__ import annotations

import importlib.util
import sys
import types

import pytest
from fake_freecad import ROOT

MODULE = (
    ROOT
    / "bundled-addons"
    / "FreeCAD-Ribbon"
    / "Resources"
    / "packages"
    / "pyqtribbon_local"
    / "fmf_layout_math.py"
)


@pytest.fixture(scope="module")
def math_module():
    spec = importlib.util.spec_from_file_location("fmf_layout_math", MODULE)
    module = importlib.util.module_from_spec(spec)
    sys.modules["fmf_layout_math"] = module
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop("fmf_layout_math", None)


def _panel(*widths):
    """A stand-in for a RibbonPanel carrying buttons of the given widths."""
    items = [
        types.SimpleNamespace(widget=lambda w=w: types.SimpleNamespace(width=lambda: w))
        for w in widths
    ]
    layout = types.SimpleNamespace(count=lambda: len(items), itemAt=lambda i: items[i])
    return types.SimpleNamespace(_actionsLayout=layout)


def _bar(toolbars):
    return types.SimpleNamespace(
        ribbonStructure={"workbenches": {"PartDesignWorkbench": {"toolbars": toolbars}}}
    )


# ---------------------------------------------------------------------------
# Measuring a column
# ---------------------------------------------------------------------------


def test_a_column_is_as_wide_as_the_widest_button(math_module):
    assert math_module.panel_column_width(_panel(32, 90, 40)) == 90


def test_a_panel_with_no_laid_out_buttons_falls_back(math_module):
    assert math_module.panel_column_width(_panel()) == math_module.FALLBACK_COLUMN_WIDTH


def test_zero_width_buttons_are_ignored(math_module):
    """Buttons report width 0 before the first layout pass."""
    assert math_module.panel_column_width(_panel(0, 0)) == math_module.FALLBACK_COLUMN_WIDTH


def test_a_panel_without_a_layout_falls_back(math_module):
    assert (
        math_module.panel_column_width(types.SimpleNamespace()) == math_module.FALLBACK_COLUMN_WIDTH
    )


# ---------------------------------------------------------------------------
# Width and columns convert both ways
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("columns", "width", "expected"),
    [(1, 90, 102), (3, 40, 132), (0, 90, 12)],
)
def test_the_width_for_a_column_count(math_module, columns, width, expected):
    assert math_module.width_for_columns(columns, width) == expected


def test_a_nonsense_column_width_still_yields_a_usable_number(math_module):
    assert math_module.width_for_columns(2, 0) > 0
    # A negative column count claims nothing rather than a negative width.
    assert math_module.width_for_columns(-1, 40) == 0


@pytest.mark.parametrize(
    ("width", "column_width", "expected"),
    [(102, 90, 1), (192, 90, 2), (100, 90, 1), (12, 90, 1), (0, 90, 1), (492, 90, 5)],
)
def test_the_columns_that_fit_in_a_width(math_module, width, column_width, expected):
    assert math_module.columns_for_width(width, column_width) == expected


def test_a_section_always_keeps_at_least_one_column(math_module):
    """Otherwise a narrow drag would leave a section with nothing in it."""
    assert math_module.columns_for_width(1, 200) == math_module.MIN_COLUMNS


def test_width_and_columns_round_trip(math_module):
    """What a width claims is what fits in it.

    The drawer is filled from columns_for_width while the space is claimed from
    width_for_columns. If they disagreed, a section would either clip its own
    buttons or leave a gap where commands had been pushed to the dropdown.
    """
    for columns in range(1, 12):
        for column_width in (24, 40, 62, 90):
            width = math_module.width_for_columns(columns, column_width)
            assert math_module.columns_for_width(width, column_width) == columns


# ---------------------------------------------------------------------------
# What a drag is measured against
# ---------------------------------------------------------------------------


def test_a_drag_moves_the_edge_by_the_distance_dragged(math_module):
    """Pixels, not columns.

    Measuring in columns read the section's contents rather than its size, so a
    section three columns of buttons wide reported 3 however much room it had.
    A second drag then started where the first did and looked like a no-op.
    """
    plan = math_module.plan_width_resize(300, 120, 90)
    assert plan["status"] == "resize"
    assert (plan["current"], plan["target"]) == (300, 420)


def test_dragging_back_returns_to_where_it_started(math_module):
    out = math_module.plan_width_resize(300, 120, 90)
    back = math_module.plan_width_resize(out["target"], -120, 90)
    assert back["target"] == 300


def test_a_drag_that_does_not_move_is_at_edge(math_module):
    assert math_module.plan_width_resize(300, 0, 90)["status"] == "at-edge"


def test_a_section_cannot_be_dragged_narrower_than_one_column(math_module):
    plan = math_module.plan_width_resize(120, -500, 90)
    assert plan["target"] == math_module.width_for_columns(math_module.MIN_COLUMNS, 90)
    assert plan["status"] == "resize"


def test_a_section_already_at_the_floor_reports_at_edge(math_module):
    floor = math_module.width_for_columns(math_module.MIN_COLUMNS, 90)
    plan = math_module.plan_width_resize(floor, -200, 90)
    assert plan["status"] == "at-edge"
    assert plan["widening"] is False


def test_a_section_cannot_be_dragged_off_the_ribbon(math_module):
    """A stray drag must not push every other section out of view."""
    plan = math_module.plan_width_resize(300, 100000, 90)
    assert plan["target"] == math_module.width_for_columns(math_module.MAX_COLUMNS, 90)


def test_a_section_already_at_the_ceiling_reports_at_edge(math_module):
    ceiling = math_module.width_for_columns(math_module.MAX_COLUMNS, 90)
    plan = math_module.plan_width_resize(ceiling, 500, 90)
    assert plan["status"] == "at-edge"
    assert plan["widening"] is True


def test_the_plan_carries_the_columns_that_will_fit(math_module):
    """The drawer budget is derived from the width, never set apart from it."""
    plan = math_module.plan_width_resize(102, 180, 90)
    assert plan["target"] == 282
    assert plan["columns"] == math_module.columns_for_width(282, 90)


def test_the_preview_and_the_commit_agree(math_module):
    """Both call plan_width_resize, so the edge lands where the band showed it.

    Their disagreeing is the complaint this whole approach replaced.
    """
    for delta in (-400, -120, -30, 0, 30, 120, 400):
        plan = math_module.plan_width_resize(300, delta, 90)
        again = math_module.plan_width_resize(300, plan["target"] - plan["current"], 90)
        assert again["target"] == plan["target"]


# ---------------------------------------------------------------------------
# Remembering a width
# ---------------------------------------------------------------------------


def _width_bar(stored=None):
    toolbar = {"order": ["a", "b"]}
    if stored is not None:
        toolbar["minWidth"] = stored
    return _bar({"Fusion Create_newPanel": toolbar})


def test_a_section_never_dragged_has_no_stored_width(math_module):
    """It must then size itself exactly as upstream does."""
    got = math_module.stored_panel_width(
        _width_bar(), "PartDesignWorkbench", "Fusion Create_newPanel"
    )
    assert got is None


def test_a_dragged_section_remembers_its_width(math_module):
    got = math_module.stored_panel_width(
        _width_bar(412), "PartDesignWorkbench", "Fusion Create_newPanel"
    )
    assert got == 412


def test_a_width_is_not_derived_from_the_column_budget(math_module):
    """OUTPUT held one command with a budget of three.

    Turning that budget into a width claimed 282px for a single button, which
    is why some sections started far wider than their contents needed.
    """
    bar = _bar({"Fusion Output_newPanel": {"order": ["a"], "maxColumns": 3}})
    got = math_module.stored_panel_width(bar, "PartDesignWorkbench", "Fusion Output_newPanel")
    assert got is None


@pytest.mark.parametrize("stored", ["wide", 0, -5])
def test_an_unusable_stored_width_reads_as_unset(math_module, stored):
    bar = _bar({"Fusion Create_newPanel": {"order": ["a"], "minWidth": stored}})
    got = math_module.stored_panel_width(bar, "PartDesignWorkbench", "Fusion Create_newPanel")
    assert got is None


def test_an_unknown_section_reads_as_unset_rather_than_raising(math_module):
    assert math_module.stored_panel_width(_bar({}), "PartDesignWorkbench", "Nope") is None
    assert math_module.stored_panel_width(types.SimpleNamespace(), "X", "Y") is None
