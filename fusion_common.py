"""Shared primitives and runtime definitions for FusionMyFreeCAD.

Centralizes runtime module declarations, transaction management, UI notifications,
Sketcher command base classes, and non-fatal error logging to eliminate boilerplate
and prevent single-point correction drift.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any

try:
    import FreeCAD as App
    import FreeCADGui as Gui
except ImportError:
    App = None  # type: ignore[assignment]
    Gui = None  # type: ignore[assignment]

# The canonical tuple of top-level Python runtime files included in the add-on.
# Tools (build_addon_package.py, validate_addon.py) and tests import this tuple directly.
RUNTIME_MODULES: tuple[str, ...] = (
    "Init.py",
    "InitGui.py",
    "fusion_bootstrap.py",
    "fusion_common.py",
    "fusion_datum_tools.py",
    "fusion_dressup_tools.py",
    "fusion_parameters_dock.py",
    "fusion_sketch_tools.py",
    "fusion_viewport.py",
)


@contextmanager
def transaction(document: Any, label: str):
    """Context manager for atomic document transactions with auto-abort on exception."""
    if document is not None and hasattr(document, "openTransaction"):
        document.openTransaction(label)
    try:
        yield
        if document is not None and hasattr(document, "commitTransaction"):
            document.commitTransaction()
    except Exception:
        if document is not None and hasattr(document, "abortTransaction"):
            try:
                document.abortTransaction()
            except Exception:
                pass
        raise


def notify(prefix: str, text: str, error: bool = False) -> None:
    """Show a non-modal result: report view line plus a transient status message."""
    if App is not None and hasattr(App, "Console"):
        printer = App.Console.PrintError if error else App.Console.PrintMessage
        printer(f"FusionMyFreeCAD {prefix}: {text}\n")
    try:
        if Gui is not None and hasattr(Gui, "getMainWindow"):
            window = Gui.getMainWindow()
            status_bar = window.statusBar() if window is not None else None
            if status_bar is not None:
                status_bar.showMessage(f"{prefix}: {text}", 8000)
    except Exception:
        pass


def log_swallowed(context: str, exc: Exception | None = None) -> None:
    """Log an exception that was caught and handled, preventing silent data-mutation failures."""
    msg = f"FusionMyFreeCAD: handled failure in {context}"
    if exc is not None:
        msg += f": {exc}"
    try:
        if App is not None and hasattr(App, "Console") and hasattr(App.Console, "PrintLog"):
            App.Console.PrintLog(msg + "\n")
    except Exception:
        pass


class SketcherCommand:
    """Base class for ribbon commands operating within SketcherWorkbench.

    Provides the canonical, single-point IsActive implementation required for FreeCAD 1.1.
    """

    def IsActive(self) -> bool:
        if App is None or getattr(App, "ActiveDocument", None) is None:
            return False
        try:
            return Gui is not None and Gui.activeWorkbench().name() == "SketcherWorkbench"
        except Exception:
            return False
