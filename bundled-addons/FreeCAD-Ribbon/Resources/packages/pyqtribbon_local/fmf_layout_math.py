"""Pure geometry decisions behind FusionMyFreeCAD's draggable panel dividers.

Not part of upstream FreeCAD-Ribbon. Deliberately free of Qt and FreeCAD
imports: this is the arithmetic that decides how wide a drag leaves a section,
and it has been wrong repeatedly, so it lives where a test can reach it without
standing up a widget toolkit. Everything here is duck-typed against the panel
and ribbon-bar objects rather than importing them.

Everything is in pixels. Earlier versions counted columns, which meant the
number a drag was measured against was the section's *contents* rather than its
*size*: a section three columns of buttons wide reported 3 however much space it
had been given, so a second drag started where the first did and appeared to do
nothing. What the user drags is a distance, so a distance is what is measured,
stored, and restored.
"""

#: Width of one column when a panel has no laid-out button to measure.
#: Roughly a small button plus its spacing.
FALLBACK_COLUMN_WIDTH = 40

#: Narrowest a section may be dragged, in columns.
MIN_COLUMNS = 1

#: Widest a section may be dragged, in columns. Generous, but finite: a stray
#: drag should not be able to push every other section off the ribbon.
MAX_COLUMNS = 24

#: Space a section needs beyond its columns, for margins and the divider.
COLUMN_PADDING = 12


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


def width_for_columns(columns: int, column_width: int, padding: int = COLUMN_PADDING) -> int:
    """The pixel width a section needs to hold `columns` columns of buttons."""
    return max(0, int(columns) * max(1, int(column_width)) + max(0, int(padding)))


def columns_for_width(width_px: int, column_width: int, padding: int = COLUMN_PADDING) -> int:
    """How many columns of commands fit in `width_px`.

    This is what keeps the drawer honest: a section shows what its width can
    hold and the remainder goes to the dropdown, rather than the width and the
    contents being set independently and allowed to disagree.
    """
    column_width = max(1, int(column_width))
    usable = max(0, int(width_px) - max(0, int(padding)))
    return max(MIN_COLUMNS, usable // column_width)


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


def stored_panel_width(bar, workbench_name, panel_name):
    """The width in pixels the user dragged this section to, or None.

    Width is stored directly rather than derived from the column budget. The
    budget says how many columns of commands are shown before the rest go to
    the drawer, which is a different quantity: OUTPUT holds one command but had
    a budget of three, and deriving a width from that claimed 282px for a
    single button. That is why some sections started far wider than the space
    their contents needed.

    A section the user has never dragged returns None and is left to size
    itself exactly as upstream does.
    """
    toolbar = _toolbar_of(bar, workbench_name, panel_name)
    if toolbar is None or toolbar.get("minWidth") is None:
        return None
    try:
        value = int(toolbar["minWidth"])
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def plan_width_resize(current_px, delta_px, column_width) -> dict:
    """Decide the width a drag should leave a section at.

    `status` is ``"resize"`` with a `target`, or ``"at-edge"`` when the drag
    would push past the narrowest or widest a section may be. The preview and
    the commit both call this, so the edge lands where the band showed it.
    """
    column_width = max(1, int(column_width))
    low = width_for_columns(MIN_COLUMNS, column_width)
    high = width_for_columns(MAX_COLUMNS, column_width)
    current = max(0, int(current_px))
    target = max(low, min(current + int(delta_px), high))
    return {
        "status": "at-edge" if target == current else "resize",
        "current": current,
        "target": target,
        "widening": int(delta_px) > 0,
        "columns": columns_for_width(target, column_width),
    }
