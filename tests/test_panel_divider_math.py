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


def _panel(*widths, columns=None, names=None):
    """A stand-in for a RibbonPanel carrying buttons of the given widths.

    `columns` gives each button's grid column, so a panel can place several
    buttons in one column the way a real stack of small buttons does.
    """
    if columns is None:
        columns = range(len(widths))
    if names is None:
        names = ["button"] * len(widths)
    items = []
    for width, column, name in zip(widths, columns, names, strict=True):
        widget = types.SimpleNamespace(width=lambda w=width: w, objectName=lambda n=name: n)
        items.append((types.SimpleNamespace(widget=lambda w=widget: w), (0, column, 1, 1)))
    layout = types.SimpleNamespace(
        count=lambda: len(items),
        itemAt=lambda i: items[i][0],
        getItemPosition=lambda i: items[i][1],
    )
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


def test_a_nonsense_ceiling_never_moves_a_panel_backwards(math_module):
    """A ceiling of 0 means the command list could not be read.

    Clamping to it would collapse the section to one column on a drag that
    asked for the opposite, so a widen holds its ground instead.
    """
    assert math_module.resolve_target(4, 2, 0) == 4
    assert math_module.resolve_target(4, -2, 0) == 2


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


# ---------------------------------------------------------------------------
# What the drag is measured against
# ---------------------------------------------------------------------------


def test_occupied_columns_counts_columns_not_buttons(math_module):
    """Small buttons stack, so three buttons can be one column wide."""
    panel = _panel(40, 40, 40, columns=[0, 0, 1])
    assert math_module.occupied_column_count(panel) == 2


def test_the_trailing_spacer_is_not_a_column(math_module):
    """It exists to top-align a one-button panel, not to occupy space."""
    panel = _panel(40, 10, columns=[0, 1], names=["button", "ExtraSpacer"])
    assert math_module.occupied_column_count(panel) == 1


def test_an_unlaid_out_panel_reports_nothing(math_module):
    assert math_module.occupied_column_count(_panel()) == 0
    assert math_module.occupied_column_count(types.SimpleNamespace()) == 0


# ---------------------------------------------------------------------------
# Direction safety
# ---------------------------------------------------------------------------


def test_a_widen_never_narrows_and_a_narrow_never_widens(math_module):
    for current in range(1, 10):
        for ceiling in range(1, 10):
            assert math_module.resolve_target(current, 1, ceiling) >= current
            assert math_module.resolve_target(current, -1, ceiling) <= current


def test_widening_a_panel_wider_than_its_contents_does_not_shrink_it(math_module):
    """A section of two commands spread over three columns.

    Clamping to the command count alone turned the widen into a shrink, so the
    divider moved the section the opposite way from the drag.
    """
    assert math_module.resolve_target(3, 1, 2) == 3


# ---------------------------------------------------------------------------
# The whole decision
# ---------------------------------------------------------------------------


def _plan_bar(order, stored=None):
    toolbar = {"order": list(order)}
    if stored is not None:
        toolbar["maxColumns"] = stored
    return _bar({"Fusion Create_newPanel": toolbar})


def _plan(math_module, panel, bar, delta, default=0):
    return math_module.plan_resize(
        bar, panel, "PartDesignWorkbench", "Fusion Create_newPanel", delta, default
    )


def test_a_drag_is_relative_to_what_the_panel_shows(math_module):
    """Not to MAX_COLUMN_PANELS, which is 0 -- "no limit" -- by default.

    Falling back to an invented budget of 6 while the panel was three columns
    wide put every step in a dead zone above the content, so neither direction
    changed anything the user could see.
    """
    bar = _plan_bar(["a"] * 16)
    plan = _plan(math_module, _panel(90, 90, 90), bar, -1)
    assert plan["source"] == "displayed"
    assert (plan["current"], plan["target"]) == (3, 2)


def test_a_stale_saved_budget_does_not_override_what_is_on_screen(math_module):
    bar = _plan_bar(["a"] * 16, stored=7)
    plan = _plan(math_module, _panel(90, 90, 90), bar, 1)
    assert (plan["current"], plan["target"]) == (3, 4)


def test_an_unlaid_out_panel_falls_back_to_the_saved_budget(math_module):
    bar = _plan_bar(["a"] * 16, stored=5)
    plan = _plan(math_module, _panel(), bar, 1)
    assert plan["source"] == "stored"
    assert (plan["current"], plan["target"]) == (5, 6)


def test_a_one_column_panel_reports_that_it_cannot_narrow(math_module):
    bar = _plan_bar(["a", "b", "c"])
    plan = _plan(math_module, _panel(90), bar, -1)
    assert plan["status"] == "at-edge"
    assert plan["widening"] is False


def test_a_drag_of_no_columns_is_ignored(math_module):
    assert _plan(math_module, _panel(90, 90), _plan_bar(["a"] * 5), 0)["status"] == "ignore"


def test_every_real_panel_can_be_dragged_both_ways(math_module):
    """The regression itself: six of eight panels could not move at all.

    Each holds more commands than the three columns a laid-out panel typically
    shows, so both directions have somewhere to go.
    """
    for count in (4, 5, 6, 7, 8, 16):
        bar = _plan_bar(["a"] * count)
        panel = _panel(90, 90, 90)
        assert _plan(math_module, panel, bar, -1)["status"] == "resize"
        assert _plan(math_module, panel, bar, 1)["status"] == "resize"


# ---------------------------------------------------------------------------
# Claiming space that is actually free
# ---------------------------------------------------------------------------


def test_widening_is_not_capped_by_the_command_count(math_module):
    """A section can be given more room than its commands need.

    maxColumns alone only decides how many columns are shown before the rest go
    to the drawer, so capping a widen at the command count meant a section that
    already showed everything could never grow -- even with empty ribbon to the
    right of it. Six of the eight PartDesign sections were stuck that way.
    """
    bar = _plan_bar(["a", "b"])
    plan = _plan(math_module, _panel(90, 90), bar, 1)
    assert plan["status"] == "resize"
    assert (plan["current"], plan["target"]) == (2, 3)


def test_widening_still_stops_growing_without_a_drag(math_module):
    bar = _plan_bar(["a", "b"])
    assert _plan(math_module, _panel(90, 90), bar, 0)["status"] == "ignore"


def test_narrowing_is_still_bounded_at_one_column(math_module):
    bar = _plan_bar(["a", "b", "c"])
    plan = _plan(math_module, _panel(90), bar, -1)
    assert plan["status"] == "at-edge"


@pytest.mark.parametrize(
    ("columns", "width", "expected"),
    [(1, 90, 102), (3, 40, 132), (0, 90, 12)],
)
def test_the_claimed_width_covers_the_columns_asked_for(math_module, columns, width, expected):
    assert math_module.width_for_columns(columns, width) == expected


def test_a_nonsense_column_width_still_yields_a_usable_number(math_module):
    assert math_module.width_for_columns(2, 0) > 0
    # A negative column count claims nothing rather than a negative width.
    assert math_module.width_for_columns(-1, 40) == 0


def test_a_saved_budget_is_readable_on_its_own(math_module):
    """apply_panel_width needs to tell "never set" from "set to something"."""
    assert (
        math_module.stored_column_budget(
            _plan_bar(["a"]), "PartDesignWorkbench", "Fusion Create_newPanel"
        )
        is None
    )
    bar = _plan_bar(["a"], stored=4)
    assert (
        math_module.stored_column_budget(bar, "PartDesignWorkbench", "Fusion Create_newPanel") == 4
    )


def test_an_unreadable_saved_budget_reads_as_unset(math_module):
    bar = _plan_bar(["a"], stored="wide")
    assert (
        math_module.stored_column_budget(bar, "PartDesignWorkbench", "Fusion Create_newPanel")
        is None
    )
