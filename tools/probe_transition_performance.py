"""Measure native and FMF workbench transitions in a real FreeCAD GUI.

Run this script with an isolated FreeCAD profile and set
``FMF_TRANSITION_PROBE_OUTPUT`` to a JSON path outside the profile. The script
first measures stock workbenches, starts FMF, then measures the four matching
FMF workbenches for thirteen cycles (52 transitions each).
"""

from __future__ import annotations

import json
import os
import statistics
import time
import traceback
from pathlib import Path

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtWidgets

OUTPUT = Path(os.environ["FMF_TRANSITION_PROBE_OUTPUT"])
NATIVE_WORKBENCHES = (
    "PartDesignWorkbench",
    "PartWorkbench",
    "SketcherWorkbench",
    "SurfaceWorkbench",
)
FMF_WORKBENCHES = (
    "FMFDesignWorkbench",
    "FMFPartWorkbench",
    "FMFSketchWorkbench",
    "FMFSurfaceWorkbench",
)
CYCLES = 13


def percentile(values, percent):
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * percent)))
    return ordered[index]


def ribbon_state():
    dock = Gui.getMainWindow().findChild(QtWidgets.QDockWidget, "Ribbon")
    if dock is None or dock.widget() is None:
        return {"present": False}
    ribbon = dock.widget()
    tab_bar = getattr(ribbon, "tabBar", lambda: None)()
    if tab_bar is None:
        return {"present": True, "tab": None, "tabData": None}
    index = tab_bar.currentIndex()
    return {
        "present": True,
        "visible": dock.isVisible(),
        "tab": tab_bar.tabText(index),
        "tabData": tab_bar.tabData(index),
    }


def settle(milliseconds):
    loop = QtCore.QEventLoop()
    QtCore.QTimer.singleShot(milliseconds, loop.quit)
    loop.exec()


class TransitionRun:
    def __init__(self, label, workbenches):
        self.label = label
        self.targets = list(workbenches) * CYCLES
        self.samples = []
        self.failures = []

    def run(self):
        for index, target in enumerate(self.targets):
            started = time.perf_counter()
            try:
                Gui.activateWorkbench(target)
                Gui.updateGui()
                # Let FreeCAD's action update and FMF's zero-delay coordinator
                # settle before measuring the next transition.
                settle(25)
                active = Gui.activeWorkbench().name()
                duration_ms = (time.perf_counter() - started) * 1000
                sample = {
                    "index": index,
                    "target": target,
                    "active": active,
                    "durationMs": round(duration_ms, 3),
                }
                if self.label == "fmf":
                    sample["ribbon"] = ribbon_state()
                self.samples.append(sample)
                if active != target:
                    self.failures.append(
                        "Transition {} requested {} but activated {}".format(index, target, active)
                    )
            except Exception:
                self.failures.append(traceback.format_exc())
        return self.result()

    def result(self):
        durations = [sample["durationMs"] for sample in self.samples]
        return {
            "label": self.label,
            "requested": len(self.targets),
            "completed": len(self.samples),
            "medianMs": round(statistics.median(durations), 3) if durations else 0.0,
            "p95Ms": round(percentile(durations, 0.95), 3),
            "maximumMs": round(max(durations), 3) if durations else 0.0,
            "failures": self.failures,
            "samples": self.samples,
        }


def main():
    result = {"freecadVersion": list(App.Version()), "cycles": CYCLES}
    try:
        Gui.showMainWindow()
        result["native"] = TransitionRun("native", NATIVE_WORKBENCHES).run()

        import fmf_bootstrap
        import fmf_transitions

        fmf_bootstrap.start()
        Gui.updateGui()
        settle(1500)
        fmf_result = TransitionRun("fmf", FMF_WORKBENCHES).run()
        transition_state = fmf_transitions.snapshot()
        native = result["native"]
        delta = fmf_result["p95Ms"] - native["p95Ms"]
        expected_phases = {"ribbon", "runtime", "searchbar"}
        phases = set(transition_state["phases"])
        ribbon_states = [sample.get("ribbon", {}) for sample in fmf_result["samples"]]
        gates = {
            "allNativeTransitionsCompleted": native["completed"] == 4 * CYCLES,
            "allFmfTransitionsCompleted": fmf_result["completed"] == 4 * CYCLES,
            "noTransitionFailures": not native["failures"] and not fmf_result["failures"],
            "coordinatorConnected": transition_state["connected"],
            "expectedPhasesRegistered": expected_phases <= phases,
            "initializerReleased": "ribbon-initialize" not in phases,
            "ribbonPresentAndVisible": all(
                state.get("present") and state.get("visible") for state in ribbon_states
            ),
            "p95IncrementWithin100Ms": delta <= 100.0,
        }
        result.update(
            {
                "fmf": fmf_result,
                "p95IncrementMs": round(delta, 3),
                "transitionCoordinator": transition_state,
                "gates": gates,
                "passed": all(gates.values()),
            }
        )
    except Exception:
        result["passed"] = False
        result["error"] = traceback.format_exc()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")
    QtWidgets.QApplication.instance().quit()


main()
