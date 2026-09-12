"""Pure geometry decisions behind FusionMyFreeCAD's draggable panel dividers.

Not part of upstream FreeCAD-Ribbon. Deliberately free of Qt and FreeCAD
imports: this is the arithmetic that decides how far a drag moves a panel edge,
and it has been wrong twice, so it lives where a test can reach it without
standing up a widget toolkit. Everything here is duck-typed against the panel
and ribbon-bar objects rather than importing them.
"""

#: Width of one ribbon column when a panel has no laid-out button to measure.
#: Roughly a small button plus its spacing.
FALLBACK_COLUMN_WIDTH = 40

#: Column budget assumed when the Ribbon add-on's own preference is unreadable.
FALLBACK_COLUMN_BUDGET = 6

#: Ceiling on a panel's width when its command list cannot be read. High enough
#: never to clamp a real panel, low enough to stay a sane number.
FALLBACK_COLUMN_CEILING = 64


def panel_column_width(panel) -> int:
    """Width in pixels of one column of buttons in `panel`.

    Measured from the widest laid-out button, not from the panel's width
    divided by a column count: the grid allocates columns for separators and
    spacers too, so dividing by it produced a figure that corresponded to
    nothing the user could see themselves dragging past.
    """
    try:
        layout = panel._actionsLayout
        widths = []
        for index in range(layout.count()):
            item = layout.itemAt(index)
            widget = item.widget() if item is not None else None
            if widget is not None and widget.width() > 0:
                widths.append(int(widget.width()))
        if widths:
            return max(24, max(widths))
    except Exception:
        pass
    return FALLBACK_COLUMN_WIDTH


def column_delta(panel, pixels: int) -> int:
    """How many whole columns a drag of `pixels` should move a panel edge by.

    The divider previews with this and the rebuild commits the value it
    reports, so the edge lands where the preview said it would.
    """
    width = panel_column_width(panel)
    if width <= 0:
        return 0
    return int(round(float(pixels) / width))


def occupied_column_count(panel) -> int:
    """How many columns of buttons the panel is showing right now, or 0.

    This is the number a drag has to be relative to. Two earlier attempts used
    something else and both produced a divider that appeared to do nothing:
    QGridLayout.columnCount() counts allocated columns, separators and spacers
    included, and the Ribbon add-on's MAX_COLUMN_PANELS preference is 0 by
    default, meaning "no limit" rather than "no columns" -- so on a stock
    profile the drag was added to an invented 6 while the panel was really
    three columns wide, and every step landed in a dead zone above the content.
    """
    try:
        layout = panel._actionsLayout
        columns = set()
        for index in range(layout.count()):
            item = layout.itemAt(index)
            widget = item.widget() if item is not None else None
            if widget is None or widget.width() <= 0:
                continue
            name = ""
            getter = getattr(widget, "objectName", None)
            if callable(getter):
                name = getter() or ""
            # The trailing spacer exists only to keep a one-button panel
            # top-aligned; it is not a column the user can see.
            if name == "ExtraSpacer":
                continue
            row, column, _rowSpan, _columnSpan = layout.getItemPosition(index)
            columns.add(int(column))
        if columns:
            return len(columns)
    except Exception:
        pass
    return 0


def _toolbar_of(bar, workbench_name, panel_name):
    try:
        toolbar = (
            bar.ribbonStructure.get("workbenches", {})
            .get(workbench_name, {})
            .get("toolbars", {})
            .get(panel_name, {})
        )
    except Exception:
        return None
    return toolbar if isinstance(toolbar, dict) else None


def stored_column_budget(bar, workbench_name, panel_name):
    """The budget saved for this panel, or None when it has never been set."""
    toolbar = _toolbar_of(bar, workbench_name, panel_name)
    if toolbar is None or toolbar.get("maxColumns") is None:
        return None
    try:
        return max(1, int(toolbar["maxColumns"]))
    except (TypeError, ValueError):
        return None


def current_column_budget(bar, workbench_name, panel_name, default=None) -> int:
    """The column budget in force for this panel right now.

    This has to be the number CreatePanel reads -- the panel's own maxColumns
    when it has one, the global preference otherwise. Deriving it from the
    laid-out grid instead, as this did at first, counts separator and spacer
    columns, so a drag was added to a base the rebuild never used and often
    produced a target identical to the current one, which looked like the
    divider simply refusing to move.
    """
    toolbar = _toolbar_of(bar, workbench_name, panel_name)
    if toolbar is not None and toolbar.get("maxColumns") is not None:
        try:
            return max(1, int(toolbar["maxColumns"]))
        except (TypeError, ValueError):
            pass
    try:
        resolved = int(default)
    except (TypeError, ValueError):
        resolved = FALLBACK_COLUMN_BUDGET
    return max(1, resolved if resolved > 0 else FALLBACK_COLUMN_BUDGET)


def panel_command_count(bar, workbench_name, panel_name) -> int:
    """How many commands the panel holds, which is the ceiling on its width."""
    toolbar = _toolbar_of(bar, workbench_name, panel_name)
    if toolbar is not None:
        count = len(toolbar.get("order", []))
        if count > 0:
            return count
    return FALLBACK_COLUMN_CEILING


def resolve_target(current: int, delta: int, ceiling: int) -> int:
    """The budget a drag of `delta` columns should land on.

    A drag never moves a panel the way it was not dragged. Clamping to the
    ceiling alone is not enough: a panel can already be wider than its command
    count -- a stale budget, or a section holding two commands across three
    columns -- and then a widen would come back under the current width and
    quietly narrow the section instead.
    """
    ceiling = max(1, ceiling)
    current = max(1, current)
    if delta == 0:
        return current
    target = max(1, current + delta)
    if delta > 0:
        return max(current, min(target, ceiling))
    return min(current, target)


def width_for_columns(columns: int, column_width: int, padding: int = 12) -> int:
    """The pixel width a panel needs to claim `columns` columns of buttons."""
    return max(0, int(columns) * max(1, int(column_width)) + max(0, int(padding)))


def plan_resize(bar, panel, workbench_name, panel_name, delta, default_budget=None) -> dict:
    """Decide what a divider drag should do, without doing any of it.

    Returns a dict with `status` one of:

    - ``"resize"``  -- apply `target` as the panel's new maxColumns
    - ``"at-edge"`` -- the drag cannot move this panel any further that way
    - ``"ignore"``  -- nothing to do

    The whole decision lives here, away from Qt, because every bug in this
    feature so far has been in the decision rather than in the widget.
    """
    if not delta:
        return {"status": "ignore", "reason": "no movement"}

    # What the user can see is what the drag is relative to. A stored budget
    # is only a fallback for the moment before the panel has been laid out.
    current = occupied_column_count(panel)
    source = "displayed"
    if current <= 0:
        current = current_column_budget(bar, workbench_name, panel_name, default_budget)
        source = "stored"

    # Widening is not capped by the command count. A section can be given more
    # room than its commands need -- that is the point of dragging a divider
    # when there is empty ribbon to the right -- and the extra is claimed as
    # minimum width rather than by revealing commands that do not exist.
    ceiling = max(panel_command_count(bar, workbench_name, panel_name), current + max(0, delta))
    target = resolve_target(current, delta, ceiling)
    if target == current:
        return {
            "status": "at-edge",
            "current": current,
            "target": target,
            "widening": delta > 0,
            "source": source,
        }
    return {
        "status": "resize",
        "current": current,
        "target": target,
        "widening": delta > 0,
        "source": source,
    }
