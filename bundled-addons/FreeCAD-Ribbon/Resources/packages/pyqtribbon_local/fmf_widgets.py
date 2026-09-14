"""FusionMyFreeCAD additions to the vendored ribbon widgets.

This module is not part of upstream FreeCAD-Ribbon. It exists so the bulk of
FusionMyFreeCAD's widget-level changes live in a file `tools/sync_bundled_addons.py`
never overwrites, leaving only a handful of one-line hooks to be re-applied by
hand in upstream's own modules after a refresh.
"""

from PySide.QtGui import QColor, QPaintEvent, QPainter, QPen
from PySide.QtCore import Qt, QPoint, Signal
from PySide.QtWidgets import QRubberBand

from .fmf_layout_math import (
    MAX_COLUMNS,
    WIDTH_MODEL,
    choose_column_budget,
    panel_column_width,
    plan_width_resize,
    stored_panel_width,
)
from .separator import RibbonVerticalSeparator


def _console():
    try:
        import FreeCAD

        return FreeCAD.Console
    except Exception:
        return None


def _enum(owner, scoped, flat):
    """Qt6 scopes its enums; Qt5 hangs them off the class. Accept either."""
    container = getattr(owner, scoped, None)
    if container is not None:
        value = getattr(container, flat, None)
        if value is not None:
            return value
    return getattr(owner, flat, None)


def popup_menu_at(menu, widget) -> bool:
    """Open `menu` under the left edge of `widget`.

    QToolButton.showMenu() anchors to the button, which sits at the right end of
    a panel's title bar, so a menu opened from the title appeared off to one
    side of the section it belongs to. Anchoring to the panel itself lines the
    two up. popup() rather than exec()/exec_() because only popup() is spelled
    the same way in Qt5 and Qt6, and Qt clamps it to the screen for us.
    """
    if menu is None or widget is None:
        return False
    menu.popup(widget.mapToGlobal(widget.rect().bottomLeft()))
    return True


class DraggablePanelSeparator(RibbonVerticalSeparator):
    """The divider between two panels, draggable to change how wide a panel is.

    FusionMyFreeCAD local change. Upstream sizes every section from its contents
    against one global column budget, so a section the user works in constantly
    gets the same space as one they never touch.

    The drag works in pixels against the section's real width, previews with a
    rubber band sitting exactly where the edge will land, and reports that
    width. Nothing here changes the layout itself, so a failure to apply the
    width cannot leave a section half-resized.
    """

    #: Emitted on release with the pixel width the section should end up at.
    dividerReleased = Signal(int)

    def __init__(self, width: int = 6, parent=None) -> None:
        super().__init__(width=width, parent=parent)
        cursor = _enum(Qt, "CursorShape", "SplitHCursor")
        if cursor is not None:
            self.setCursor(cursor)
        self.setToolTip("Drag to make the panel on the left wider or narrower")
        self._hovered = False
        self._dragging = False
        self._startX = None
        self._startWidth = None
        self._band = None

    # -- geometry ---------------------------------------------------------

    def _panel(self):
        """The panel this divider belongs to, or None if it is not in one yet."""
        parent = self.parentWidget()
        # A RibbonPanel owns its separator directly; guard anyway so a reparent
        # upstream cannot turn a drag into an exception.
        return parent if parent is not None and hasattr(parent, "_actionsLayout") else None

    @staticmethod
    def _globalX(event) -> int:
        """Qt6 replaced globalPos() with globalPosition(); support both."""
        position = getattr(event, "globalPosition", None)
        if callable(position):
            return int(position().x())
        return int(event.globalPos().x())

    def _plan(self, rawDelta: int):
        """Where this drag would leave the section, as a width plan or None."""
        panel = self._panel()
        if panel is None or self._startWidth is None:
            return None
        return plan_width_resize(self._startWidth, rawDelta, panel_column_width(panel))

    # -- live preview -----------------------------------------------------

    def _showPreview(self) -> None:
        if self._band is not None:
            return
        shape = _enum(QRubberBand, "Shape", "Line")
        try:
            self._band = QRubberBand(shape, self.window()) if shape else None
        except Exception:
            self._band = None
        self._movePreview(0)
        if self._band is not None:
            self._band.show()

    def _movePreview(self, offsetPixels: int) -> None:
        if self._band is None:
            return
        try:
            origin = self.mapTo(self.window(), self.rect().topLeft())
            self._band.setGeometry(
                origin.x() + offsetPixels, origin.y(), max(3, self.width()), self.height()
            )
        except Exception:
            pass

    def _hidePreview(self) -> None:
        if self._band is None:
            return
        try:
            self._band.hide()
            self._band.deleteLater()
        except Exception:
            pass
        self._band = None

    # -- events -----------------------------------------------------------

    def enterEvent(self, event) -> None:
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == _enum(Qt, "MouseButton", "LeftButton"):
            self._dragging = True
            self._startX = self._globalX(event)
            panel = self._panel()
            # The width at the moment of the press is what the drag is relative
            # to, so releasing leaves the edge exactly where the band is.
            self._startWidth = panel.width() if panel is not None else None
            self._showPreview()
            self.update()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._dragging and self._startX is not None:
            plan = self._plan(self._globalX(event) - self._startX)
            if plan is not None:
                self._movePreview(plan["target"] - plan["current"])
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._dragging and self._startX is not None:
            plan = self._plan(self._globalX(event) - self._startX)
            self._dragging = False
            self._startX = None
            self._startWidth = None
            self._hidePreview()
            self.update()
            event.accept()
            # A press that did not move is a click, not a resize.
            if plan is not None and plan["status"] == "resize":
                self.dividerReleased.emit(plan["target"])
            return
        super().mouseReleaseEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:
        if not (self._hovered or self._dragging):
            super().paintEvent(event)
            return
        painter = QPainter(self)
        pen = QPen()
        pen.setColor(QColor("#007acc"))
        pen.setWidth(2)
        painter.setPen(pen)
        x1 = self.rect().center().x()
        painter.drawLine(
            QPoint(x1, self.rect().top() + self._topMargins),
            QPoint(x1, self.rect().bottom() - self._bottomMargins),
        )


def _report(text, quiet=False):
    """Say what a divider drag did, in the Report view.

    Every failure in this feature so far has been silent -- swallowed into a
    log nobody reads -- and each one cost a round trip to diagnose. A resize is
    a deliberate user action, so it is allowed to say what it did.
    """
    console = _console()
    if console is None:
        return
    message = "FusionMyFreeCAD divider: {}\n".format(text)
    if quiet:
        console.PrintMessage(message)
    else:
        console.PrintWarning(message)


#: Qt's "no constraint" maximum.
_UNBOUNDED_WIDTH = 16777215


def apply_panel_width(bar, panel) -> None:
    """Hold a section at the width the user dragged it to.

    Only a stored width does this. Deriving one from the column budget instead
    claimed 282px for OUTPUT's single button, because a budget of three columns
    and one command are different quantities -- which is why some sections
    started far wider than their contents needed.

    A section the user has never dragged is left entirely alone, so the default
    ribbon sizes itself exactly as upstream does.
    """
    try:
        workbenchName = bar.tabBar().tabData(bar.tabBar().currentIndex())
        panelName = panel.objectName()
        if not workbenchName or not panelName:
            return
        width = stored_panel_width(bar, workbenchName, panelName)
        if width is None:
            panel.setMinimumWidth(0)
            panel.setMaximumWidth(_UNBOUNDED_WIDTH)
            return
        # Pinned both ways: a minimum alone lets a section grow past where it
        # was dragged, so narrowing one would not appear to take.
        panel.setMinimumWidth(width)
        panel.setMaximumWidth(width)
    except Exception as error:
        _report("could not size the panel: {}: {}".format(type(error).__name__, error))


def _build_panel(bar, workbenchName, panelName):
    """One rebuild of a section from the current ribbon structure."""
    panel = bar.CreatePanel(
        workbenchName,
        panelName,
        addPanel=False,
        Dict=bar.workBenchDict,
        ignoreColumnLimit=False,
        showEnableControl=False,
        enableSeparator=False,
        # Not an arranging operation: leaving every button force-enabled
        # would make unavailable commands look usable.
        ActivateButtons=False,
    )
    if panel is not None:
        try:
            # Built unparented, so it would not inherit the ribbon's stylesheet
            # and would measure against the wrong font and padding. Adopting it
            # into the category first costs nothing -- it stays hidden until
            # replacePanel puts it in the layout -- and makes the width it
            # reports the width it will have.
            panel.setParent(bar.currentCategory())
        except Exception:
            pass
    return panel


def _fit_to_width(bar, workbenchName, panelName, toolbar, targetWidth: int):
    """Build the fullest version of a section that fits in `targetWidth`.

    Returns (panel, budget). The budget is found by building candidates and
    asking each what width it wants, rather than by multiplying a column width
    by a count: a budget of N does not mean N columns of buttons on screen --
    three small commands share a column, a half-filled stack occupies one
    without being counted, and a large button's column is nothing like a small
    one's. Every earlier attempt to compute this arithmetically left the
    section demanding far more room than its icons needed.
    """
    built = {}

    def measure(budget):
        toolbar["maxColumns"] = int(budget)
        candidate = _build_panel(bar, workbenchName, panelName)
        built[int(budget)] = candidate
        if candidate is None:
            return None
        return candidate.sizeHint().width()

    ceiling = len(toolbar.get("order", [])) or MAX_COLUMNS
    budget = choose_column_budget(targetWidth, ceiling, measure)
    chosen = built.get(budget)
    if chosen is None:
        toolbar["maxColumns"] = budget
        chosen = _build_panel(bar, workbenchName, panelName)
    for candidate in built.values():
        if candidate is not None and candidate is not chosen:
            candidate.close()
            candidate.deleteLater()
    toolbar["maxColumns"] = budget
    return chosen, budget


def resize_panel(bar, panel, targetWidth: int):
    """Refit this section to the width the user dragged it to.

    The drag sets a ceiling, not a target. Inside it the fullest set of
    commands that fits is shown, and the section is then held at the width
    *that* set needs. Dragging past the point where everything already fits
    therefore does nothing rather than opening a dead zone on the right, which
    is the whole complaint about the previous behaviour: a section could be
    left demanding a great deal of empty space with commands still in its
    drawer.
    """
    try:
        if not targetWidth or targetWidth <= 0:
            return
        workbenchName = bar.tabBar().tabData(bar.tabBar().currentIndex())
        panelName = panel.objectName()
        if not workbenchName or not panelName:
            return
        label = panel.title() if hasattr(panel, "title") else panelName
        was = panel.width()

        bar._ensureDirectDragState()
        toolbars = (
            bar.workBenchDict.setdefault("workbenches", {})
            .setdefault(workbenchName, {})
            .setdefault("toolbars", {})
        )
        toolbar = toolbars.get(panelName)
        if not isinstance(toolbar, dict):
            _report("{}: no toolbar named that in the ribbon structure.".format(label))
            return
        toolbar["minWidth"] = int(targetWidth)
        toolbar["widthModel"] = WIDTH_MODEL

        replacement, columns = _fit_to_width(
            bar, workbenchName, panelName, toolbar, int(targetWidth)
        )
        if replacement is None:
            _report("{}: the rebuild produced no panel.".format(label))
            return
        # What the chosen set of commands actually occupies, which is at most
        # the dragged width and usually a little less. Storing the drag instead
        # is what let a section keep space it had no use for.
        finalWidth = max(1, int(replacement.sizeHint().width()))
        toolbar["minWidth"] = finalWidth
        bar._saveDirectDragState()
        bar.currentCategory().replacePanel(panel, replacement)
        bar.setPanelProperties(replacement)
        apply_panel_width(bar, replacement)
        bar.currentCategory()._panels[replacement.objectName()] = replacement
        panel.close()
        _report(
            "{}: {}px -> {}px within a {}px drag ({} column(s)).".format(
                label, was, finalWidth, targetWidth, columns
            ),
            quiet=True,
        )
    except Exception as error:
        # A divider drag must never take the ribbon down with it, but it must
        # not fail silently either: silent failure is what made three attempts
        # at this feature undiagnosable from outside FreeCAD.
        _report("failed: {}: {}".format(type(error).__name__, error))
