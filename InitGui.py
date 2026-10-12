"""One-step, cross-platform FusionMyFreeCAD add-on entry point."""

import os
import time
import traceback

import FreeCAD as App

import fusion_common as diagnostics
from fusion_bootstrap import (
    ADDON_ROOT,
    PACKAGE_VERSION,
    clear_startup_failures,
    defer_ui_mode_sync,
    install_lifecycle_menu,
    is_enabled,
    load_vendor,
    prepare,
    record_startup_failure,
    register_commands,
    register_lifecycle_commands,
    register_owned_workbenches,
    register_preferences_page,
    restore_disabled_native_ui,
    run_runtime,
    validate_enabled_ui,
)


def _step(label, function, *arguments):
    """Run one startup step, reporting failure instead of aborting the add-on.

    An exception raised here would stop FreeCAD from executing the rest of this
    module, which is precisely when the user needs Verify UI and Restore UI most.
    """
    started = time.perf_counter()
    diagnostics.event("info", "startup", label, "started", packageVersion=PACKAGE_VERSION)
    try:
        function(*arguments)
        diagnostics.event(
            "info",
            "startup",
            label,
            "completed",
            durationMs=round((time.perf_counter() - started) * 1000, 2),
            packageVersion=PACKAGE_VERSION,
        )
        return True
    except Exception as error:
        App.Console.PrintError("FusionMyFreeCAD: {} failed: {}\n".format(label, error))
        App.Console.PrintLog(traceback.format_exc())
        record_startup_failure(label, error)
        diagnostics.diagnostic_exception(
            "startup",
            label,
            error,
            durationMs=round((time.perf_counter() - started) * 1000, 2),
            packageVersion=PACKAGE_VERSION,
        )
        diagnostics.set_status("degraded", failedStep=label, error=str(error))
        return False


def _start():
    clear_startup_failures()

    # Recovery must remain available even if diagnostics or feature startup fails.
    register_lifecycle_commands()
    register_preferences_page()
    install_lifecycle_menu()

    diagnostics.start_session(is_enabled(), PACKAGE_VERSION, App.Version())
    try:
        if is_enabled():
            # Feature commands and observers must not modify a disabled FreeCAD session.
            _step("feature command registration", register_commands)
            _step("owned workbench registration", register_owned_workbenches)
            _step("installation", prepare)
            _step("runtime", run_runtime)
            _step(
                "SearchBar",
                load_vendor,
                "SearchBar",
                os.path.join(ADDON_ROOT, "bundled-addons", "SearchBar"),
            )
            _step(
                "FreeCAD Ribbon",
                load_vendor,
                "FreeCAD_Ribbon",
                os.path.join(ADDON_ROOT, "bundled-addons", "FreeCAD-Ribbon"),
            )
            _step("UI mode synchronization", defer_ui_mode_sync)
            _step("enabled UI validation", validate_enabled_ui)
        else:
            _step("native UI restoration", restore_disabled_native_ui)
    except BaseException as error:
        App.Console.PrintError("FusionMyFreeCAD startup failed: {}\n".format(error))
        diagnostics.diagnostic_exception("startup", "top level", error)
        diagnostics.set_status("degraded", failedStep="top level", error=str(error))
    finally:
        diagnostics.flush_diagnostics()


_start()
