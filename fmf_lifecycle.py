"""Centralized lifecycle registry for signals, observers, filters, and timers.

Provides one authoritative registry to inspect attached hooks and verify
complete, zero-leak teardown across FreeCAD lifecycle boundaries.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

_observers: dict[tuple[str, str], tuple[Any, Any, Callable[[], None] | None]] = {}
_filters: dict[str, tuple[Any, Any]] = {}
_timers: dict[str, Any] = {}


def register_observer(
    category: str,
    name: str,
    target: Any,
    observer: Any,
    detach_fn: Callable[[], None] | None = None,
) -> None:
    """Register an observer on an App, Gui, or Selection target."""
    key = (category, name)
    if key in _observers:
        unregister_observer(category, name)
    _observers[key] = (target, observer, detach_fn)


def unregister_observer(category: str, name: str) -> bool:
    """Detach and remove an observer from the registry."""
    key = (category, name)
    entry = _observers.pop(key, None)
    if entry is None:
        return False
    target, observer, detach_fn = entry
    if detach_fn is not None:
        try:
            detach_fn()
            return True
        except Exception:
            return False

    if target is None or observer is None:
        return True

    # Standard FreeCAD detachment patterns
    for method_name in ("removeObserver", "removeDocumentObserver", "Detach", "detach"):
        method = getattr(target, method_name, None)
        if callable(method):
            try:
                method(observer)
                return True
            except (AttributeError, RuntimeError, TypeError, ValueError):
                pass
    return False


def register_filter(name: str, target: Any, filter_obj: Any) -> None:
    """Register an event filter installed on a QObject / QWidget target."""
    if name in _filters:
        unregister_filter(name)
    _filters[name] = (target, filter_obj)


def unregister_filter(name: str) -> bool:
    """Remove and detach an event filter."""
    entry = _filters.pop(name, None)
    if entry is None:
        return False
    target, filter_obj = entry
    if target is not None and filter_obj is not None:
        remove_fn = getattr(target, "removeEventFilter", None)
        if callable(remove_fn):
            try:
                remove_fn(filter_obj)
                return True
            except (AttributeError, RuntimeError, TypeError, ValueError):
                pass
    return False


def register_timer(name: str, timer_obj: Any) -> None:
    """Register a QTimer."""
    if name in _timers:
        unregister_timer(name)
    _timers[name] = timer_obj


def unregister_timer(name: str) -> bool:
    """Stop and unregister a QTimer."""
    timer_obj = _timers.pop(name, None)
    if timer_obj is None:
        return False
    stop_fn = getattr(timer_obj, "stop", None)
    if callable(stop_fn):
        try:
            stop_fn()
            return True
        except Exception:
            pass
    return False


def snapshot() -> dict[str, Any]:
    """Inspect active lifecycle counts and registrations."""
    return {
        "observers": {
            f"{cat}:{name}": bool(target)
            for (cat, name), (target, _, _) in _observers.items()
        },
        "observer_count": len(_observers),
        "filters": list(_filters.keys()),
        "filter_count": len(_filters),
        "timers": list(_timers.keys()),
        "timer_count": len(_timers),
        "total_hooks": len(_observers) + len(_filters) + len(_timers),
    }


def teardown_all() -> int:
    """Detach every registered observer, filter, and timer, returning hook count to zero."""
    detached = 0
    # Observers
    for category, name in tuple(_observers.keys()):
        if unregister_observer(category, name):
            detached += 1
    _observers.clear()

    # Filters
    for name in tuple(_filters.keys()):
        if unregister_filter(name):
            detached += 1
    _filters.clear()

    # Timers
    for name in tuple(_timers.keys()):
        if unregister_timer(name):
            detached += 1
    _timers.clear()

    return detached
