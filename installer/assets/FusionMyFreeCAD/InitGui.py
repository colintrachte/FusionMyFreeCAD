"""Load FusionMyFreeCAD through a normal Python module namespace."""

import importlib.util
import os
import sys

import FreeCAD as App


addon_dir = os.path.join(App.getUserAppDataDir(), "Mod", "FusionMyFreeCAD")
runtime_path = os.path.join(addon_dir, "FusionRuntime.py")
module_name = "FusionMyFreeCAD_InstalledRuntime"
spec = importlib.util.spec_from_file_location(module_name, runtime_path)
if spec is None or spec.loader is None:
    raise ImportError("Could not load FusionMyFreeCAD runtime: {}".format(runtime_path))
module = importlib.util.module_from_spec(spec)
sys.modules[module_name] = module
spec.loader.exec_module(module)
