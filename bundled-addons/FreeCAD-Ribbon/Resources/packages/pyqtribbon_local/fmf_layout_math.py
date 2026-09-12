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
    """The budget a drag of `delta` columns should land on."""
    return max(1, min(current + delta, max(1, ceiling)))
