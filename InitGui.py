"""FreeCAD GUI entry point for FMF."""

# FreeCAD executes InitGui.py inside a loader function. Keep this file to an
# immediate module call so imports and startup functions live in a normal Python
# module namespace rather than the loader's temporary local namespace.
import fmf_bootstrap

fmf_bootstrap.start()
