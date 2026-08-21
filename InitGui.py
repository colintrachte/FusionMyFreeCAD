"""One-step, cross-platform FusionMyFreeCAD add-on entry point."""

import os

from fusion_bootstrap import ADDON_ROOT, load_vendor, prepare, register_commands, run_runtime

prepare()
register_commands()
run_runtime()
load_vendor("SearchBar", os.path.join(ADDON_ROOT, "vendor", "SearchBar"))
load_vendor("FreeCAD_Ribbon", os.path.join(ADDON_ROOT, "vendor", "FreeCAD-Ribbon"))
