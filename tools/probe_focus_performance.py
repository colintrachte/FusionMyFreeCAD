"""Measure FMF focus handlers and SearchBar ownership inside a real FreeCAD GUI.

Run this script with FreeCAD/FreeCADCmd and an isolated profile containing FMF.
Set ``FMF_FOCUS_PROBE_OUTPUT`` to the JSON result path.
"""

from __future__ import annotations

import itertools
import json
import os
import statistics
import sys
import time
import traceback
from pathlib import Path

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtWidgets

OUTPUT = Path(os.environ["FMF_FOCUS_PROBE_OUTPUT"])
REPEATED_INSTALLS = 10
FOCUS_CYCLES = 20
P95_LIMIT_MS = 2.0


def measure(repeats, callback):
    samples = []
    for _ in range(repeats):
        started = time.perf_counter_ns()
        callback()
        samples.append((time.perf_counter_ns() - started) / 1_000_000.0)
    samples.sort()
    return {
        "count": repeats,
        "medianMs": round(statistics.median(samples), 4),
        "p95Ms": round(samples[min(len(samples) - 1, int(len(samples) * 0.95))], 4),
        "maxMs": round(max(samples), 4),
        "totalMs": round(sum(samples), 4),
    }


def run():
    result = {"freecadVersion": list(App.Version())}
    try:
        import FCBinding
        from MouseBar import EventInspector_SB

        searchbar = sys.modules["_fmf_vendor_SearchBar"]
        main_window = Gui.getMainWindow()
        ribbon_dock = main_window.findChild(QtWidgets.QDockWidget, "Ribbon")
        inspectors = main_window.findChildren(FCBinding.EventInspector)
        if ribbon_dock is None or not inspectors:
            raise RuntimeError("FMF Ribbon focus services are not installed")
        inspector = inspectors[0]

        application_activate = QtCore.QEvent(QtCore.QEvent.Type.ApplicationActivated)
        result["applicationActivated"] = measure(
            FOCUS_CYCLES,
            lambda: inspector.eventFilter(main_window, application_activate),
        )

        titlebar_ids = []

        def focus_pair():
            inspector.eventFilter(
                main_window,
                QtCore.QEvent(QtCore.QEvent.Type.WindowDeactivate),
            )
            titlebar_ids.append(id(ribbon_dock.titleBarWidget()))
            inspector.eventFilter(
                main_window,
                QtCore.QEvent(QtCore.QEvent.Type.WindowActivate),
            )
            titlebar_ids.append(id(ribbon_dock.titleBarWidget()))

        result["windowFocusPair"] = measure(FOCUS_CYCLES, focus_pair)
        result["titleBarReplacements"] = sum(
            left != right for left, right in itertools.pairwise(titlebar_ids)
        )

        before = len(main_window.findChildren(EventInspector_SB))
        result["searchBarReinstall"] = measure(
            REPEATED_INSTALLS,
            searchbar.SearchBar.addToolSearchBox,
        )
        after = len(main_window.findChildren(EventInspector_SB))
        result["searchBarFiltersBefore"] = before
        result["searchBarFiltersAfter"] = after
        result["searchBarFiltersAdded"] = after - before

        gates = {
            "singleSearchBarFilter": before == 1 and after == 1,
            "idempotentSearchBarInstall": after - before == 0,
            "stableRibbonTitleBar": result["titleBarReplacements"] == 0,
            "applicationActivationP95": (result["applicationActivated"]["p95Ms"] < P95_LIMIT_MS),
            "focusPairP95": result["windowFocusPair"]["p95Ms"] < P95_LIMIT_MS,
        }
        result["gates"] = gates
        result["passed"] = all(gates.values())
    except Exception:
        result["passed"] = False
        result["error"] = traceback.format_exc()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    QtCore.QTimer.singleShot(0, QtWidgets.QApplication.instance().quit)


Gui.showMainWindow()
if "FCBinding" not in sys.modules:
    import fmf_bootstrap

    fmf_bootstrap.start()
    Gui.updateGui()
run()
