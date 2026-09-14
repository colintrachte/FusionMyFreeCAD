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

#: How a stored width was arrived at. A width recorded under an older model was
#: measured against something this one no longer means -- columns rather than
#: pixels, the widest button rather than the median column, or a button's
#: laid-out width rather than the width it asks for -- so it is retired rather
#: than honoured, and the section returns to sizing itself.
#: Bump this whenever the measurement changes.
WIDTH_MODEL = 3


def natural_width(widget) -> int:
    """What a button wants to be, not what the layout handed it.

    The item widgets in a panel have an Expanding size policy, so once a
    section is pinned wider than its contents every one of them grows to
    swallow a share of the slack. Measuring `width()` therefore fed the empty
    space back in as the size of a column: each extra pixel of emptiness
    demanded more emptiness before the next command could come out of the
    drawer, which is exactly how a section ended up having to be dragged far
    past its icons. `sizeHint()` describes the contents and nothing else.
    """
    hint = getattr(widget, "sizeHint", None)
    if callable(hint):
        try:
            wanted = int(hint().width())
        except Exception:
            wanted = 0
        if wanted > 0:
            return wanted
    try:
        return int(widget.width())
    except Exception:
        return 0


def panel_column_widths(panel) -> list:
    """The width of each laid-out column of buttons in `panel`.

    Grouped by grid column, because a column is a stack: three small buttons
    sit in one, a large button fills one on its own. Measuring individual
    buttons instead conflates the two.
    """
    try:
        layout = panel._actionsLayout
        by_column = {}
        for index in range(layout.count()):
            item = layout.itemAt(index)
            widget = item.widget() if item is not None else None
            if widget is None:
                continue
            wanted = natural_width(widget)
            if wanted <= 0:
                continue
            name = ""
            getter = getattr(widget, "objectName", None)
            if callable(getter):
                name = getter() or ""
            # The trailing spacer only top-aligns a one-button panel.
            if name == "ExtraSpacer":
                continue
            _row, column, _rowSpan, _columnSpan = layout.getItemPosition(index)
            column = int(column)
            by_column[column] = max(by_column.get(column, 0), wanted)
        return [width for _column, width in sorted(by_column.items())]
    except Exception:
        return []


def panel_column_width(panel) -> int:
    """The width in pixels of a representative column of buttons in `panel`.

    The median column, not the widest. A section mixing one large button with
    stacks of small ones has columns of very different widths, and taking the
    widest made every column look like the largest: the space a width could
    hold was underestimated, commands were pushed to the drawer that would
    have fitted, and the section was left visibly wider than the icons in it.
    """
    widths = panel_column_widths(panel)
    if not widths:
        return FALLBACK_COLUMN_WIDTH
    widths = sorted(widths)
    middle = len(widths) // 2
    if len(widths) % 2:
        median = widths[middle]
    else:
        median = (widths[middle - 1] + widths[middle]) // 2
    return max(24, int(median))


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
    if toolbar.get("widthModel") != WIDTH_MODEL:
        # Recorded by a build that measured differently. Honouring it pinned
        # sections to widths that no longer correspond to their contents -- the
        # export button arrived squeezed into 131px because of one.
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


def choose_column_budget(available_px, max_budget, measure) -> int:
    """The largest column budget whose panel fits in `available_px` pixels.

    `measure(budget)` returns the width a panel built with that budget asks
    for, or None if it could not be built. Asking the toolkit instead of doing
    arithmetic is the whole point of this function: a budget counts three small
    buttons as one column and does not count a half-filled stack at all, so
    multiplying a representative column width by a budget cannot say what a
    section will actually occupy. Under that arithmetic one more notional
    column could cost far more room than the icon it would reveal, which is how
    a section came to sit full of empty space with its last commands still in
    the drawer.

    The width a panel asks for only grows as the budget does, so a binary
    search settles this in about four builds.
    """
    ceiling = max(MIN_COLUMNS, min(int(max_budget), MAX_COLUMNS))
    available = int(available_px)
    best = MIN_COLUMNS
    low, high = MIN_COLUMNS, ceiling
    while low <= high:
        middle = (low + high) // 2
        width = measure(middle)
        if width is None:
            # Nothing was built, so nothing is known about wider budgets
            # either. Keep the best that did fit rather than guessing.
            break
        if int(width) <= available:
            best = middle
            low = middle + 1
        else:
            high = middle - 1
    return best
