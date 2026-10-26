"""State-diff chrome controller for FusionMyFreeCAD.

Eliminates redundant toolbar hiding, menu mutations, and dock visibility sweeps
by comparing desired chrome state against the current applied state during
workbench transitions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def _get_gui() -> Any | None:
    try:
        import FreeCADGui as Gui

        return Gui
    except ImportError:
        return None


def _get_qtwidgets() -> Any | None:
    for mod_name in ("PySide", "PySide6", "PySide2"):
        try:
            mod = __import__(mod_name, fromlist=["QtWidgets"])
            return getattr(mod, "QtWidgets", None)
        except ImportError:
            continue
    return None


@dataclass(frozen=True)
class ChromeState:
    toolbars_hidden: bool = False
    menubar_hidden: bool = False
    ribbon_visible: bool = False
    family_enabled: bool = False


class ChromeController:
    """Manages main window chrome mutations with state diffing."""

    def __init__(self, gui: Any | None = None) -> None:
        self._gui = gui
        self._current_state: ChromeState | None = None

    def _gui_instance(self) -> Any | None:
        return self._gui if self._gui is not None else _get_gui()

    @property
    def current_state(self) -> ChromeState | None:
        return self._current_state

    def reset(self) -> None:
        self._current_state = None

    def apply(
        self,
        desired: ChromeState,
        main_window: Any | None = None,
        *,
        force: bool = False,
    ) -> bool:
        """Apply desired chrome state only if it differs from current state."""
        if not force and self._current_state == desired:
            return False

        gui = self._gui_instance()
        if main_window is None and gui is not None and hasattr(gui, "getMainWindow"):
            main_window = gui.getMainWindow()

        if main_window is None:
            self._current_state = desired
            return False

        # 1. Menubar visibility
        prev = self._current_state
        if force or prev is None or prev.menubar_hidden != desired.menubar_hidden:
            menubar = main_window.menuBar() if hasattr(main_window, "menuBar") else None
            if menubar is not None:
                try:
                    if desired.menubar_hidden:
                        menubar.hide()
                    else:
                        menubar.show()
                except (AttributeError, RuntimeError):
                    pass

        # 2. Ribbon dock and classic toolbars
        qt_widgets = _get_qtwidgets()

        ribbon_dock = (
            main_window.findChild(qt_widgets.QDockWidget, "Ribbon")
            if qt_widgets is not None and hasattr(main_window, "findChild")
            else None
        )
        if ribbon_dock is not None:
            if force or prev is None or prev.ribbon_visible != desired.ribbon_visible:
                try:
                    if desired.ribbon_visible:
                        ribbon_dock.show()
                    else:
                        ribbon_dock.hide()
                except (AttributeError, RuntimeError):
                    pass

            if desired.toolbars_hidden and (
                force or prev is None or not prev.toolbars_hidden
            ):
                ribbon_widget = (
                    ribbon_dock.widget() if hasattr(ribbon_dock, "widget") else None
                )
                if ribbon_widget is not None and hasattr(ribbon_widget, "hideClassicToolbars"):
                    try:
                        ribbon_widget.hideClassicToolbars()
                    except Exception:
                        pass

        # 3. Ribbon workbench family
        if force or prev is None or prev.family_enabled != desired.family_enabled:
            try:
                import fmf_bootstrap

                fmf_bootstrap.set_ribbon_workbench_family(desired.family_enabled)
            except Exception:
                pass

        self._current_state = desired
        return True

    def restore(self, main_window: Any | None = None) -> bool:
        """Restore default native chrome state."""
        native_state = ChromeState(
            toolbars_hidden=False,
            menubar_hidden=False,
            ribbon_visible=False,
            family_enabled=False,
        )
        applied = self.apply(native_state, main_window=main_window, force=True)
        self._current_state = None
        return applied


_default_controller = ChromeController()


def get_chrome_controller() -> ChromeController:
    return _default_controller
