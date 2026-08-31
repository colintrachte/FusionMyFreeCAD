"""One-step, cross-platform FusionMyFreeCAD add-on entry point."""

import os
import traceback

import FreeCAD as App

from fusion_bootstrap import (
    ADDON_ROOT,
    clear_startup_failures,
    load_vendor,
    prepare,
    record_startup_failure,
    register_commands,
    register_preferences_page,
    run_runtime,
)


def _step(label, function, *arguments):
    """Run one startup step, reporting failure instead of aborting the add-on.

    An exception raised here would stop FreeCAD from executing the rest of this
    module, which is precisely when the user needs Verify UI and Restore UI most.
    """
    try:
        function(*arguments)
        return True
    except Exception as error:
        App.Console.PrintError("FusionMyFreeCAD: {} failed: {}\n".format(label, error))
        App.Console.PrintLog(traceback.format_exc())
        record_startup_failure(label, error)
        return False


clear_startup_failures()

# Recovery commands are registered first so Verify UI, Reapply, and Restore UI stay
# reachable even when installation or the runtime fails.
_step("command registration", register_commands)
_step("preferences page", register_preferences_page)
_step("installation", prepare)
_step("runtime", run_runtime)
_step(
    "SearchBar", load_vendor, "SearchBar", os.path.join(ADDON_ROOT, "bundled-addons", "SearchBar")
)
_step(
    "FreeCAD Ribbon",
    load_vendor,
    "FreeCAD_Ribbon",
    os.path.join(ADDON_ROOT, "bundled-addons", "FreeCAD-Ribbon"),
)
