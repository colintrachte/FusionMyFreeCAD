"""FMF-owned workbench identities backed by FreeCAD's native command providers."""

from __future__ import annotations

import importlib
import os

import FreeCAD as App
import FreeCADGui as Gui

FMF_TO_NATIVE = {
    "FusionDesignWorkbench": "PartDesignWorkbench",
    "FusionPartWorkbench": "PartWorkbench",
    "FusionSketchWorkbench": "SketcherWorkbench",
    "FusionSurfaceWorkbench": "SurfaceWorkbench",
}
NATIVE_TO_FMF = {native: owned for owned, native in FMF_TO_NATIVE.items()}

_registered = False


class _FusionWorkbench(Gui.Workbench):
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


class FusionDesignWorkbench(_FusionWorkbench):
    WorkbenchId = "FusionDesignWorkbench"
    NativeWorkbench = "PartDesignWorkbench"
    MenuText = "Fusion Design"
    ToolTip = "Fusion-familiar solid design workbench"
    Icon = os.path.join(
        App.getResourceDir(), "Mod", "PartDesign", "Resources", "icons", "PartDesignWorkbench.svg"
    )

    def Initialize(self):
        importlib.import_module("PartDesign")
        importlib.import_module("PartDesignGui")


class FusionPartWorkbench(_FusionWorkbench):
    WorkbenchId = "FusionPartWorkbench"
    NativeWorkbench = "PartWorkbench"
    MenuText = "Fusion Part"
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


class FusionSketchWorkbench(_FusionWorkbench):
    WorkbenchId = "FusionSketchWorkbench"
    NativeWorkbench = "SketcherWorkbench"
    MenuText = "Fusion Sketch"
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


class FusionSurfaceWorkbench(_FusionWorkbench):
    WorkbenchId = "FusionSurfaceWorkbench"
    NativeWorkbench = "SurfaceWorkbench"
    MenuText = "Fusion Surface"
    ToolTip = "Fusion-familiar surface design workbench"
    Icon = os.path.join(
        App.getResourceDir(), "Mod", "Surface", "Resources", "icons", "Surface_Workbench.svg"
    )

    def Initialize(self):
        importlib.import_module("Surface")
        importlib.import_module("SurfaceGui")


WORKBENCH_CLASSES = (
    FusionDesignWorkbench,
    FusionPartWorkbench,
    FusionSketchWorkbench,
    FusionSurfaceWorkbench,
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
