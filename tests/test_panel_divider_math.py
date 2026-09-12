"""The arithmetic behind the draggable panel dividers.

This is the logic that decides how far a drag moves a panel edge. It has been
wrong twice -- once measuring a column from the grid's allocated column count,
once adding the drag to a base the rebuild never read -- and both times the
symptom was a divider that "sometimes just does not move". It lives in a
Qt-free module precisely so these cases can be pinned down without standing up
a widget toolkit.
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
# Turning a drag into columns
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("pixels", "expected"),
    [(0, 0), (10, 0), (44, 0), (70, 1), (90, 1), (135, 2), (-70, -1), (-135, -2)],
)
def test_a_drag_snaps_to_whole_columns(math_module, pixels, expected):
    """A 90px column: under half a column must not move the edge."""
    assert math_module.column_delta(_panel(90), pixels) == expected


def test_a_drag_shorter_than_half_a_column_is_a_click(math_module):
    """Otherwise every stray press on the divider would rebuild the panel.

    The rubber band shows this while the drag is live, so a drag that is not
    going to move anything looks like one rather than failing silently.
    """
    assert math_module.column_delta(_panel(90), 20) == 0
    assert math_module.column_delta(_panel(90), 44) == 0
    assert math_module.column_delta(_panel(90), 70) == 1


# ---------------------------------------------------------------------------
# The budget a drag is added to
# ---------------------------------------------------------------------------


def test_a_panel_with_a_saved_budget_uses_it(math_module):
    bar = _bar({"Fusion Create_newPanel": {"maxColumns": 3}})
    assert (
        math_module.current_column_budget(bar, "PartDesignWorkbench", "Fusion Create_newPanel", 6)
        == 3
    )


def test_a_panel_without_one_uses_the_global_preference(math_module):
    """This is the number CreatePanel reads, so a drag must be added to it.

    Deriving the base from the laid-out grid instead counted separator and
    spacer columns, producing a target the rebuild had never used and very
    often one identical to the current width -- the divider refusing to move.
    """
    bar = _bar({"Fusion Create_newPanel": {"order": ["a", "b"]}})
    assert (
        math_module.current_column_budget(bar, "PartDesignWorkbench", "Fusion Create_newPanel", 6)
        == 6
    )


def test_an_unreadable_saved_budget_falls_back(math_module):
    bar = _bar({"Fusion Create_newPanel": {"maxColumns": "wide"}})
    assert (
        math_module.current_column_budget(bar, "PartDesignWorkbench", "Fusion Create_newPanel", 5)
        == 5
    )


def test_an_unreadable_preference_falls_back_to_a_sane_default(math_module):
    bar = _bar({"Fusion Create_newPanel": {}})
    got = math_module.current_column_budget(
        bar, "PartDesignWorkbench", "Fusion Create_newPanel", None
    )
    assert got == math_module.FALLBACK_COLUMN_BUDGET


def test_a_nonsensical_preference_falls_back(math_module):
    """MAX_COLUMN_PANELS of 0 means "no limit" upstream, not "no columns"."""
    bar = _bar({"Fusion Create_newPanel": {}})
    got = math_module.current_column_budget(bar, "PartDesignWorkbench", "Fusion Create_newPanel", 0)
    assert got == math_module.FALLBACK_COLUMN_BUDGET


def test_an_unknown_panel_falls_back_rather_than_raising(math_module):
    assert math_module.current_column_budget(_bar({}), "PartDesignWorkbench", "Nope", 6) == 6
    assert math_module.current_column_budget(types.SimpleNamespace(), "X", "Y", 6) == 6


# ---------------------------------------------------------------------------
# Where a drag lands
# ---------------------------------------------------------------------------


def test_the_ceiling_is_how_many_commands_the_panel_holds(math_module):
    bar = _bar({"Fusion Create_newPanel": {"order": ["a", "b", "c"]}})
    assert (
        math_module.panel_command_count(bar, "PartDesignWorkbench", "Fusion Create_newPanel") == 3
    )


def test_an_unreadable_panel_gets_a_high_ceiling(math_module):
    """Better to allow a too-wide panel than to clamp a real one to nothing."""
    assert (
        math_module.panel_command_count(_bar({}), "PartDesignWorkbench", "Nope")
        == math_module.FALLBACK_COLUMN_CEILING
    )


@pytest.mark.parametrize(
    ("current", "delta", "ceiling", "expected"),
    [
        (6, 1, 10, 7),
        (6, -1, 10, 5),
        (6, 5, 8, 8),  # clamped to the commands the panel actually holds
        (2, -5, 10, 1),  # never narrower than one column
        (1, -1, 10, 1),
        (6, 0, 10, 6),
    ],
)
def test_a_drag_lands_inside_the_panel_range(math_module, current, delta, ceiling, expected):
    assert math_module.resolve_target(current, delta, ceiling) == expected


def test_a_zero_ceiling_still_leaves_one_column(math_module):
    assert math_module.resolve_target(4, 2, 0) == 1


def test_the_preview_and_the_commit_agree(math_module):
    """The divider previews with column_delta and the rebuild commits it.

    If these two ever diverge the edge lands somewhere other than where the
    rubber band said it would, which is the whole complaint this replaced.
    """
    panel = _panel(90)
    for pixels in (-200, -95, -40, 0, 40, 95, 200):
        columns = math_module.column_delta(panel, pixels)
        preview_pixels = columns * math_module.panel_column_width(panel)
        assert math_module.column_delta(panel, preview_pixels) == columns
