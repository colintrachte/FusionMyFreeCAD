"""FMF-owned workbench identities backed by FreeCAD's native command providers."""

from __future__ import annotations

import importlib
import os

import FreeCAD as App
import FreeCADGui as Gui

FMF_TO_NATIVE = {
    "FMFDesignWorkbench": "PartDesignWorkbench",
    "FMFPartWorkbench": "PartWorkbench",
    "FMFSketchWorkbench": "SketcherWorkbench",
    "FMFSurfaceWorkbench": "SurfaceWorkbench",
}
NATIVE_TO_FMF = {native: owned for owned, native in FMF_TO_NATIVE.items()}

_registered = False


class _FMFWorkbench(Gui.Workbench):
    """Common identity and activation hooks for an FMF-owned workbench."""

    WorkbenchId = ""
    NativeWorkbench = ""
    NativeClassName = "Gui::PythonWorkbench"

    def GetClassName(self):
        return self.NativeClassName

    def Activated(self):
        import fusion_bootstrap

        fusion_bootstrap.activate_owned_workbench(self.WorkbenchId)

    def Deactivated(self):
        import fusion_bootstrap

        fusion_bootstrap.defer_ui_mode_sync()


class FMFDesignWorkbench(_FMFWorkbench):
    WorkbenchId = "FMFDesignWorkbench"
    NativeWorkbench = "PartDesignWorkbench"
    NativeClassName = "PartDesignGui::Workbench"
    MenuText = "FMF Design"
    ToolTip = "Fusion-familiar solid design workbench"
    Icon = os.path.join(
        App.getResourceDir(), "Mod", "PartDesign", "Resources", "icons", "PartDesignWorkbench.svg"
    )

    def Initialize(self):
        importlib.import_module("PartDesign")
        importlib.import_module("PartDesignGui")


class FMFPartWorkbench(_FMFWorkbench):
    WorkbenchId = "FMFPartWorkbench"
    NativeWorkbench = "PartWorkbench"
    NativeClassName = "PartGui::Workbench"
    MenuText = "FMF Part"
    ToolTip = "Fusion-familiar direct shape workbench"
    Icon = os.path.join(
        App.getResourceDir(), "Mod", "Part", "Resources", "icons", "PartWorkbench.svg"
    )

    def Initialize(self):
        part_gui = importlib.import_module("PartGui")

        try:
            importlib.import_module("BasicShapes.CommandShapes")
            importlib.import_module("CompoundTools._CommandCompoundFilter")
            importlib.import_module("CompoundTools._CommandExplodeCompound")
        except ImportError as error:
            App.Console.PrintWarning(
                "FusionMyFreeCAD: optional Part commands unavailable: {}\n".format(error)
            )
        try:
            bop = __import__("BOPTools")
            bop.importAll()
            bop.addCommands()
            part_gui.BOPTools = bop
        except Exception as error:
            App.Console.PrintWarning(
                "FusionMyFreeCAD: optional BOP commands unavailable: {}\n".format(error)
            )


class FMFSketchWorkbench(_FMFWorkbench):
    WorkbenchId = "FMFSketchWorkbench"
    NativeWorkbench = "SketcherWorkbench"
    NativeClassName = "SketcherGui::Workbench"
    MenuText = "FMF Sketch"
    ToolTip = "Fusion-familiar sketching workbench"
    Icon = os.path.join(
        App.getResourceDir(), "Mod", "Sketcher", "Resources", "icons", "SketcherWorkbench.svg"
    )

    def Initialize(self):
        importlib.import_module("Sketcher")
        importlib.import_module("SketcherGui")

        try:
            importlib.import_module("Profiles")
        except ImportError as error:
            App.Console.PrintWarning(
                "FusionMyFreeCAD: optional Sketcher profiles unavailable: {}\n".format(error)
            )


class FMFSurfaceWorkbench(_FMFWorkbench):
    WorkbenchId = "FMFSurfaceWorkbench"
    NativeWorkbench = "SurfaceWorkbench"
    NativeClassName = "SurfaceGui::Workbench"
    MenuText = "FMF Surface"
    ToolTip = "Fusion-familiar surface design workbench"
    Icon = os.path.join(
        App.getResourceDir(), "Mod", "Surface", "Resources", "icons", "Surface_Workbench.svg"
    )

    def Initialize(self):
        importlib.import_module("Surface")
        importlib.import_module("SurfaceGui")


WORKBENCH_CLASSES = (
    FMFDesignWorkbench,
    FMFPartWorkbench,
    FMFSketchWorkbench,
    FMFSurfaceWorkbench,
)


def register() -> None:
    """Register every FMF workbench once without replacing native identities."""
    global _registered
    if _registered:
        return
    existing = set(Gui.listWorkbenches()) if hasattr(Gui, "listWorkbenches") else set()
    for workbench_class in WORKBENCH_CLASSES:
        if workbench_class.WorkbenchId not in existing:
            Gui.addWorkbench(workbench_class())
    _registered = True
