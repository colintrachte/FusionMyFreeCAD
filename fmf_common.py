"""Shared primitives and runtime definitions for FMF.

Centralizes runtime module declarations, transaction management, UI notifications,
Sketcher command base classes, and non-fatal error logging to eliminate boilerplate
and prevent single-point correction drift.
"""

from __future__ import annotations

import json
import os
import traceback
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
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
    "fmf_actions.py",
    "fmf_bootstrap.py",
    "fmf_catalog.py",
    "fmf_common.py",
    "fmf_datum_tools.py",
    "fmf_dressup_tools.py",
    "fmf_export.py",
    "fmf_parameters_dock.py",
    "fmf_repair_tools.py",
    "fmf_sketch_tools.py",
    "fmf_viewport.py",
    "fmf_workbenches.py",
)


# Diagnostics live in this existing runtime module so package composition cannot
# drift when diagnostics are added or changed. Every operation is deliberately
# failure-safe: inability to write a log must never affect FreeCAD startup.
USER_ROOT = App.getUserAppDataDir() if App is not None else os.getcwd()
DIAGNOSTICS_DIR = os.path.join(USER_ROOT, "FMF-Diagnostics")
LOG_PATH = os.path.join(DIAGNOSTICS_DIR, "events.jsonl")
STATUS_PATH = os.path.join(DIAGNOSTICS_DIR, "session-status.json")
MAX_LOG_BYTES = 512 * 1024
MAX_ARCHIVES = 3
SESSION_ID = uuid.uuid4().hex
_BUFFERING = False
_BUFFERED_RECORDS: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []


def _diagnostic_time() -> str:
    return datetime.now(UTC).astimezone().isoformat()


def _rotate_diagnostics() -> None:
    if not os.path.isfile(LOG_PATH) or os.path.getsize(LOG_PATH) < MAX_LOG_BYTES:
        return
    oldest = f"{LOG_PATH}.{MAX_ARCHIVES}"
    if os.path.exists(oldest):
        os.remove(oldest)
    for index in range(MAX_ARCHIVES - 1, 0, -1):
        source = f"{LOG_PATH}.{index}"
        if os.path.exists(source):
            os.replace(source, f"{LOG_PATH}.{index + 1}")
    os.replace(LOG_PATH, LOG_PATH + ".1")


def _write_event(level: str, subsystem: str, operation: str, outcome: str, **details: Any) -> None:
    try:
        os.makedirs(DIAGNOSTICS_DIR, exist_ok=True)
        _rotate_diagnostics()
        record = {
            "at": _diagnostic_time(),
            "sessionId": SESSION_ID,
            "level": level,
            "subsystem": subsystem,
            "operation": operation,
            "outcome": outcome,
            "packageVersion": details.pop("packageVersion", None),
            "details": details,
        }
        with open(LOG_PATH, "a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, default=str, separators=(",", ":")) + "\n")
    except Exception:
        pass


def event(level: str, subsystem: str, operation: str, outcome: str, **details: Any) -> None:
    """Record one event without affecting product behavior on failure."""
    if _BUFFERING:
        _BUFFERED_RECORDS.append(("event", (level, subsystem, operation, outcome), details))
        return
    _write_event(level, subsystem, operation, outcome, **details)


def diagnostic_exception(
    subsystem: str, operation: str, error: BaseException, **details: Any
) -> None:
    trace = "".join(traceback.format_exception(type(error), error, error.__traceback__))
    details.update(error=str(error), traceback=trace)
    event("error", subsystem, operation, "failed", **details)


def _write_status(state: str, **details: Any) -> None:
    try:
        os.makedirs(DIAGNOSTICS_DIR, exist_ok=True)
        payload = {
            "state": state,
            "sessionId": SESSION_ID,
            "updatedAt": _diagnostic_time(),
            "details": details,
        }
        temporary = STATUS_PATH + ".tmp"
        with open(temporary, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, default=str)
        os.replace(temporary, STATUS_PATH)
    except Exception:
        pass


def set_status(state: str, **details: Any) -> None:
    if _BUFFERING:
        _BUFFERED_RECORDS.append(("status", (state,), details))
        return
    _write_status(state, **details)


def start_session(enabled: bool, package_version: str, freecad_version: Any) -> None:
    global _BUFFERING
    _BUFFERING = True
    _BUFFERED_RECORDS.clear()
    set_status("starting", enabled=enabled, packageVersion=package_version)
    event(
        "info",
        "startup",
        "session",
        "started",
        enabled=enabled,
        packageVersion=package_version,
        freeCADVersion=list(freecad_version),
    )


def flush_diagnostics() -> None:
    """Flush startup records after UI initialization leaves the critical path."""
    global _BUFFERING
    records = tuple(_BUFFERED_RECORDS)
    _BUFFERED_RECORDS.clear()
    _BUFFERING = False
    for kind, arguments, details in records:
        if kind == "event":
            _write_event(*arguments, **details)
        else:
            _write_status(*arguments, **details)


def diagnostic_summary() -> str:
    status: dict[str, Any] = {}
    try:
        with open(STATUS_PATH, encoding="utf-8") as stream:
            status = json.load(stream)
    except Exception:
        pass
    return "\n".join(
        (
            "FMF diagnostics",
            f"State: {status.get('state', 'unknown')}",
            f"Session: {status.get('sessionId', SESSION_ID)}",
            f"Updated: {status.get('updatedAt', 'unknown')}",
            f"Folder: {DIAGNOSTICS_DIR}",
        )
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
        printer(f"FMF {prefix}: {text}\n")
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
    msg = f"FMF: handled failure in {context}"
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
            return Gui is not None and Gui.activeWorkbench().name() in {
                "SketcherWorkbench",
                "FMFSketchWorkbench",
            }
        except Exception:
            return False
