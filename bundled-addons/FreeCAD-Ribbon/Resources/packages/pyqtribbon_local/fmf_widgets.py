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
    column_delta,
    current_column_budget,
    panel_column_width,
    panel_command_count,
    resolve_target,
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

    FusionMyFreeCAD local change. Upstream sizes every panel from its contents
    against one global column budget, so a panel the user works in constantly
    gets the same width as one they never touch.

    The drag previews with a rubber band that snaps to whole columns, and
    reports a column delta rather than a pixel one, so what is committed is
    exactly what the preview showed. Nothing here changes the layout itself, so
    a failure to apply the delta cannot leave a panel half-resized.
    """

    #: Emitted on release with the number of columns to grow (+) or shrink (-).
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
        self._previewColumns = 0
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

    def _snappedOffset(self, rawDelta: int) -> tuple:
        """Return (columns, pixels) for a raw drag, snapped to whole columns."""
        panel = self._panel()
        if panel is None:
            return 0, 0
        columns = column_delta(panel, rawDelta)
        return columns, columns * panel_column_width(panel)

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
            self._previewColumns = 0
            self._showPreview()
            self.update()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._dragging and self._startX is not None:
            columns, pixels = self._snappedOffset(self._globalX(event) - self._startX)
            if columns != self._previewColumns:
                self._previewColumns = columns
            self._movePreview(pixels)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._dragging and self._startX is not None:
            columns, _pixels = self._snappedOffset(self._globalX(event) - self._startX)
            self._dragging = False
            self._startX = None
            self._previewColumns = 0
            self._hidePreview()
            self.update()
            event.accept()
            # A drag too short to cross a column boundary is a click, not a
            # resize. Emitting 0 would rebuild the panel for no visible change.
            if columns != 0:
                self.dividerReleased.emit(columns)
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


def _global_column_budget():
    """The Ribbon add-on's own MAX_COLUMN_PANELS preference, or None."""
    try:
        import Parameters_Ribbon

        return int(Parameters_Ribbon.Parameters.MAX_COLUMN_PANELS)
    except Exception:
        return None


def resize_panel(bar, panel, columnDelta: int):
    """Apply a divider drag as a column budget for this panel alone.

    The budget is stored on the panel in RibbonStructure.json as `maxColumns`,
    saved through the same path a drag-reorder uses, and the panel is rebuilt in
    place so the commands that no longer fit drop into its overflow drawer.
    """
    try:
        if not columnDelta:
            return
        workbenchName = bar.tabBar().tabData(bar.tabBar().currentIndex())
        panelName = panel.objectName()
        if not workbenchName or not panelName:
            return

        current = current_column_budget(bar, workbenchName, panelName, _global_column_budget())
        ceiling = panel_command_count(bar, workbenchName, panelName)
        target = resolve_target(current, columnDelta, ceiling)
        if target == current:
            # Already at the end of its range. Say so rather than looking broken.
            console = _console()
            if console is not None:
                edge = "widest" if columnDelta > 0 else "narrowest"
                console.PrintMessage(
                    "FusionMyFreeCAD: {} is already at its {} ({} column(s)).\n".format(
                        panel.title() if hasattr(panel, "title") else panelName, edge, target
                    )
                )
            return

        bar._ensureDirectDragState()
        toolbars = (
            bar.workBenchDict.setdefault("workbenches", {})
            .setdefault(workbenchName, {})
            .setdefault("toolbars", {})
        )
        toolbar = toolbars.get(panelName)
        if not isinstance(toolbar, dict):
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
