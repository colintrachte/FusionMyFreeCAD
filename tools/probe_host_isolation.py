"""Verify FMF activation does not perform hidden host work in a real FreeCAD GUI.

Run with an isolated profile in which FMF is installed but disabled, and set
``FMF_HOST_ISOLATION_OUTPUT`` to the JSON result path. The probe blocks network
access, enables FMF, records workbench transitions, and checks event-filter scope.
"""

from __future__ import annotations

import json
import os
import traceback
import urllib.request
from pathlib import Path

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtWidgets

OUTPUT = Path(os.environ["FMF_HOST_ISOLATION_OUTPUT"])


def run():
    result = {"freecadVersion": list(App.Version())}
    activations = []
    activation_traces = []
    network_attempts = []
    main_window = Gui.getMainWindow()
    original_urlopen = urllib.request.urlopen

    def reject_network(url, *args, **kwargs):
        network_attempts.append(str(url))
        raise RuntimeError("FMF host-isolation probe blocked a network request")

    def record_activation(name):
        activations.append(str(name))
        activation_traces.append(
            {"workbench": str(name), "stack": traceback.format_stack(limit=16)}
        )

    main_window.workbenchActivated.connect(record_activation)
    urllib.request.urlopen = reject_network
    try:
        import fmf_bootstrap

        starting_workbench = fmf_bootstrap.active_workbench_name()
        fmf_bootstrap.enable()
        Gui.updateGui()

        runtime = __import__("_fmf_my_freecad_runtime")
        application = QtWidgets.QApplication.instance()
        app_filters = getattr(application, "filters", None)
        if app_filters is None:
            app_filters = application.findChildren(runtime._TaskAcceptFilter)

        unexpected = [
            name
            for name in activations
            if name not in fmf_bootstrap.OWNED_TO_NATIVE_WORKBENCH and name != starting_workbench
        ]
        gates = {
            "noStartupNetwork": network_attempts == [],
            "noDiscoveryWorkbenchActivation": unexpected == [],
            "noApplicationTaskFilter": runtime._task_accept_filter not in app_filters,
        }
        result.update(
            {
                "startingWorkbench": starting_workbench,
                "activations": activations,
                "activationTraces": activation_traces,
                "unexpectedActivations": unexpected,
                "networkAttempts": network_attempts,
                "taskAcceptTargets": len(runtime._task_accept_targets),
                "gates": gates,
                "passed": all(gates.values()),
            }
        )
    except Exception:
        result["passed"] = False
        result["error"] = traceback.format_exc()
    finally:
        urllib.request.urlopen = original_urlopen
        try:
            main_window.workbenchActivated.disconnect(record_activation)
        except (RuntimeError, TypeError):
            pass

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    QtCore.QTimer.singleShot(0, QtWidgets.QApplication.instance().quit)


Gui.showMainWindow()
run()
