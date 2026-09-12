"""FusionMyFreeCAD additions to the vendored ribbon widgets.

This module is not part of upstream FreeCAD-Ribbon. It exists so the bulk of
FusionMyFreeCAD's widget-level changes live in a file `tools/sync_bundled_addons.py`
never overwrites, leaving only a handful of one-line hooks to be re-applied by
hand in upstream's own modules after a refresh.
"""

from PySide.QtGui import QColor, QPaintEvent, QPainter, QPen
from PySide.QtCore import Qt, QPoint, Signal

from .separator import RibbonVerticalSeparator


class DraggablePanelSeparator(RibbonVerticalSeparator):
    """The divider between two panels, draggable to change how wide a panel is.

    FusionMyFreeCAD local change. Upstream sizes every panel from its contents
    against one global column budget, so a panel the user cares about gets the
    same width as one they never touch. Dragging this divider reports a pixel
    delta; FCBinding turns it into a column count for that panel alone, and the
    commands that no longer fit move into the panel's overflow drawer.

    The drag only reports. Nothing here changes the layout, so a failure to
    interpret the delta cannot leave a panel half-resized.
    """

    dividerReleased = Signal(int)

    def __init__(self, width: int = 6, parent=None) -> None:
        super().__init__(width=width, parent=parent)
        self.setCursor(Qt.CursorShape.SplitHCursor)
        self.setToolTip("Drag to make this panel wider or narrower")
        self._hovered = False
        self._dragging = False
        self._startX = None

    @staticmethod
    def _globalX(event) -> int:
        """Qt6 replaced globalPos() with globalPosition(); support both."""
        position = getattr(event, "globalPosition", None)
        if callable(position):
            return int(position().x())
        return int(event.globalPos().x())

    def enterEvent(self, event) -> None:
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._startX = self._globalX(event)
            self.update()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._dragging and self._startX is not None:
            delta = self._globalX(event) - self._startX
            self._dragging = False
            self._startX = None
            self.update()
            event.accept()
            # Ignore the click-without-drag that just dismisses a menu.
            if abs(delta) >= 4:
                self.dividerReleased.emit(delta)
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


def _console():
    try:
        import FreeCAD

        return FreeCAD.Console
    except Exception:
        return None

def panel_column_budget(panel) -> int:
    """How many columns this panel currently occupies."""
    try:
        columns = int(panel._actionsLayout.columnCount())
    except Exception:
        return 1
    return max(1, columns)

def resize_panel(bar, panel, deltaX: int):
    """Turn a divider drag into a column budget for this panel alone.

    FusionMyFreeCAD local change. The budget is stored on the panel in
    RibbonStructure.json as `maxColumns`, saved through the same path a
    drag-reorder uses, and the panel is rebuilt in place so the commands that
    no longer fit drop into its overflow drawer.
    """
    try:
        workbenchName = bar.tabBar().tabData(bar.tabBar().currentIndex())
        panelName = panel.objectName()
        if not workbenchName or not panelName:
            return

        columns = panel_column_budget(panel)
        # Average width of a column in this panel, so the drag tracks the
        # pointer rather than a guessed constant. Buttons differ in width, so
        # this is deliberately approximate and clamped to something sane.
        columnWidth = max(24, int(max(1, panel.width()) / columns))
        step = int(round(float(deltaX) / columnWidth))
        if step == 0:
            step = 1 if deltaX > 0 else -1
        target = max(1, columns + step)

        bar._ensureDirectDragState()
        toolbars = (
            bar.workBenchDict.setdefault("workbenches", {})
            .setdefault(workbenchName, {})
            .setdefault("toolbars", {})
        )
        toolbar = toolbars.get(panelName)
        if not isinstance(toolbar, dict):
            return
        if toolbar.get("maxColumns") == target:
            return
        toolbar["maxColumns"] = target
        bar._saveDirectDragState()

        replacement = bar.CreatePanel(
            workbenchName,
            panelName,
            addPanel=False,
            Dict=bar.workBenchDict,
            ignoreColumnLimit=False,
            showEnableControl=False,
            enableSeparator=False,
            ActivateButtons=True,
        )
        if replacement is None:
            return
        bar.currentCategory().replacePanel(panel, replacement)
        bar.setPanelProperties(replacement)
        bar.currentCategory()._panels[replacement.objectName()] = replacement
        panel.close()
    except Exception as error:
        # A divider drag must never take the ribbon down with it.
        console = _console()
        if console is not None:
            console.PrintLog("FusionMyFreeCAD could not resize the panel: {}\n".format(error))
