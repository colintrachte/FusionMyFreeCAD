"""Batched preference persistence service.

Buffers parameter mutations and flushes via App.saveParameter() only at
explicit user or lifecycle commit boundaries, eliminating saveParameter()
churn during active modeling, viewport navigation, and workbench switching.
"""

from __future__ import annotations

from typing import Any

_parameters_dirty: bool = False


def _get_app() -> Any | None:
    try:
        import FreeCAD as App

        return App
    except ImportError:
        return None


def mark_parameters_dirty() -> None:
    """Flag that FreeCAD parameter values have changed and need persisting."""
    global _parameters_dirty
    _parameters_dirty = True


def is_parameters_dirty() -> bool:
    """Return whether unflushed parameter changes exist."""
    return _parameters_dirty


def flush_parameters(*, force: bool = False) -> bool:
    """Save parameters to disk if dirty or forced, resetting the dirty flag."""
    global _parameters_dirty
    if not _parameters_dirty and not force:
        return False

    _parameters_dirty = False
    app = _get_app()
    if app is not None:
        save_fn = getattr(app, "saveParameter", None)
        if callable(save_fn):
            try:
                save_fn()
                return True
            except Exception:
                return False
    return False


def reset() -> None:
    """Reset the dirty flag without saving."""
    global _parameters_dirty
    _parameters_dirty = False
