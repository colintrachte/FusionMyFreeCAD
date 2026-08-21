"""Cross-platform installation, verification, restoration, and vendor loading."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import sys
from datetime import datetime, timezone

import FreeCAD as App
import FreeCADGui as Gui


PACKAGE_VERSION = "3.1.0"
ADDON_ROOT = os.path.dirname(__file__)
RESOURCE_ROOT = os.path.join(ADDON_ROOT, "Resources", "FusionMyFreeCAD")
BASE_LAYOUT = os.path.join(RESOURCE_ROOT, "RibbonStructure.json")
LAYOUT_SPEC = os.path.join(RESOURCE_ROOT, "layout-v3.json")
RUNTIME = os.path.join(RESOURCE_ROOT, "runtime.py")
USER_ROOT = App.getUserAppDataDir()
RIBBON_DIR = os.path.join(USER_ROOT, "RibbonUI_Data")
RIBBON_PATH = os.path.join(RIBBON_DIR, "RibbonStructure.json")
STATE_PATH = os.path.join(USER_ROOT, "FusionMyFreeCAD-addon-state.json")


PREFERENCE_KEYS = (
    ("User parameter:BaseApp/Preferences/General", "AutoloadModule", "String"),
    ("User parameter:BaseApp/Preferences/View", "NavigationStyle", "String"),
    ("User parameter:BaseApp/Preferences/View", "ShowNaviCube", "Bool"),
    ("User parameter:BaseApp/Preferences/NaviCube", "CornerNaviCube", "Int"),
    ("User parameter:BaseApp/Preferences/DockWindows/ComboView", "Enabled", "Bool"),
    ("User parameter:BaseApp/MainWindow/DockWindows", "Std_ComboView", "Bool"),
    ("User parameter:BaseApp/Preferences/Mod/FreeCAD-Ribbon", "ConfigDir", "String"),
    ("User parameter:BaseApp/Preferences/Mod/FreeCAD-Ribbon", "RibbonStructure", "String"),
    ("User parameter:BaseApp/Preferences/Mod/FreeCAD-Ribbon", "BackupFolder", "String"),
    ("User parameter:BaseApp/Preferences/Mod/FreeCAD-Ribbon", "Preferred_view", "Int"),
    ("User parameter:BaseApp/Preferences/Mod/FreeCAD-Ribbon", "Link_IconSizes", "Bool"),
    ("User parameter:BaseApp/Preferences/Mod/FreeCAD-Ribbon", "IconSize_Small", "Int"),
    ("User parameter:BaseApp/Preferences/Mod/FreeCAD-Ribbon", "IconSize_Medium", "Int"),
    ("User parameter:BaseApp/Preferences/Mod/FreeCAD-Ribbon", "IconSize_Large", "Int"),
    ("User parameter:BaseApp/Preferences/Mod/Sketcher/dimensioning", "SingleDimensioningTool", "Bool"),
    ("User parameter:BaseApp/Preferences/Mod/Sketcher/dimensioning", "SeparatedDimensioningTools", "Bool"),
    ("User parameter:BaseApp/Preferences/Mod/Sketcher/dimensioning", "DimensioningDiameter", "Bool"),
    ("User parameter:BaseApp/Preferences/Mod/Sketcher/dimensioning", "DimensioningRadius", "Bool"),
    ("User parameter:BaseApp/Preferences/Mod/SearchBar", "ShowChangeDialog", "Bool"),
    ("User parameter:BaseApp/Preferences/Mod/SearchBar", "DoNotShowAgain", "String"),
    ("User parameter:BaseApp/Preferences/Shortcut", "Sketcher_CreateLine", "String"),
    ("User parameter:BaseApp/Preferences/Shortcut", "Sketcher_CreateRectangle_Center", "String"),
    ("User parameter:BaseApp/Preferences/Shortcut", "Sketcher_CreateRectangle", "String"),
    ("User parameter:BaseApp/Preferences/Shortcut", "Sketcher_CreateCircle", "String"),
    ("User parameter:BaseApp/Preferences/Shortcut", "Sketcher_Dimension", "String"),
    ("User parameter:BaseApp/Preferences/Shortcut", "PartDesign_Pad", "String"),
    ("User parameter:BaseApp/Preferences/Shortcut", "PartDesign_Pocket", "String"),
    ("User parameter:BaseApp/Preferences/Shortcut", "PartDesign_Hole", "String"),
    ("User parameter:BaseApp/Preferences/Shortcut", "Sketcher_Trimming", "String"),
    ("User parameter:BaseApp/Preferences/Shortcut", "Sketcher_Offset", "String"),
    ("User parameter:BaseApp/Preferences/Shortcut", "Sketcher_Projection", "String"),
    ("User parameter:BaseApp/Preferences/Shortcut", "Sketcher_ToggleConstruction", "String"),
    ("User parameter:BaseApp/Preferences/Shortcut", "Std_Measure", "String"),
)


def _now():
    return datetime.now(timezone.utc).astimezone().isoformat()


def _timestamp():
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _atomic_json(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2)
    os.replace(temporary, path)


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path):
    with open(path, "r", encoding="utf-8") as stream:
        return json.load(stream)


def _capture_preferences():
    captured = []
    for path, name, kind in PREFERENCE_KEYS:
        group = App.ParamGet(path)
        names = getattr(group, "Get{}s".format(kind))()
        captured.append(
            {
                "path": path,
                "name": name,
                "kind": kind,
                "existed": name in names,
                "value": getattr(group, "Get{}".format(kind))(name),
            }
        )
    return captured


def _restore_preferences(entries):
    for entry in entries:
        group = App.ParamGet(entry["path"])
        method = "Set{}" if entry["existed"] else "Rem{}"
        function = getattr(group, method.format(entry["kind"]))
        if entry["existed"]:
            function(entry["name"], entry["value"])
        else:
            function(entry["name"])
    App.saveParameter()


def _merge_layout():
    ribbon = _load_json(BASE_LAYOUT)
    spec = _load_json(LAYOUT_SPEC)
    ribbon.setdefault("dropdownButtons", {}).update(spec["dropdownButtons"])
    all_new_panels = ribbon.setdefault("newPanels", {})
    all_workbenches = ribbon.setdefault("workbenches", {})
    ribbon["authoritativeWorkbenches"] = list(spec["workbenches"])
    for workbench, panels in spec["workbenches"].items():
        toolbars = {}
        order = []
        new_panels = {}
        for panel in panels:
            name = panel["name"]
            commands = {}
            command_order = []
            new_panel_commands = []
            for command, source, size, text, icon in panel["commands"]:
                command_order.append(command)
                new_panel_commands.append([command, source])
                commands[command] = {
                    "size": size,
                    "text": text,
                    "icon": icon,
                    "IsExtra": True,
                }
            order.append(name)
            new_panels[name] = new_panel_commands
            toolbars[name] = {
                "title": panel["title"],
                "Enabled": True,
                "order": command_order,
                "commands": commands,
            }
        # FreeCAD-Ribbon stores panel order alongside the toolbar entries.
        # A top-level workbench "order" is ignored and causes the add-on to
        # rediscover and prepend every native FreeCAD toolbar.
        toolbars["order"] = order
        all_new_panels[workbench] = new_panels
        all_workbenches[workbench] = {"toolbars": toolbars}
    return ribbon, spec["layoutVersion"]


def _verify_layout(path):
    try:
        ribbon = _load_json(path)
        workbenches = ribbon["workbenches"]
        part = workbenches["PartDesignWorkbench"]
        sketch = workbenches["SketcherWorkbench"]
        surface = workbenches["SurfaceWorkbench"]
        part_tools = workbenches["PartWorkbench"]
        checks = {
            "createSketch": "FusionMyFreeCAD_CreateSketch"
            in part["toolbars"]["Fusion Sketch Entry_newPanel"]["commands"],
            "centeredRectangle": "Sketcher_CreateRectangle_Center"
            in sketch["toolbars"]["Fusion Sketch Create_newPanel"]["commands"],
            "smartDimension": sketch["toolbars"]["Fusion Sketch Constraints_newPanel"]
            ["commands"]["Sketcher_Dimension"]["text"]
            == "Smart Dimension",
            "surfaceMode": "Surface_Filling"
            in surface["toolbars"]["Fusion Surface Create_newPanel"]["commands"],
            "parameterTable": "FusionMyFreeCAD_ParameterTable"
            in part["toolbars"]["Fusion Parameters_newPanel"]["commands"],
            "linkedGeometry": "PartDesign_SubShapeBinder"
            in part["toolbars"]["Fusion Construct_newPanel"]["commands"],
            "partFragments": "Part_BooleanFragments"
            in part_tools["toolbars"]["Fusion Part Boolean_newPanel"]["commands"],
            "partRepair": "Part_RefineShape"
            in part_tools["toolbars"]["Fusion Part Repair_newPanel"]["commands"],
            "sketchCreateFirst": sketch["toolbars"]["order"][0] == "Fusion Sketch Create_newPanel",
            "finishSketchLast": sketch["toolbars"]["order"][-1] == "Fusion Finish_newPanel",
            "ribbonViewsRemoved": not any(
                "view" in name.lower()
                for name in part["toolbars"]["order"] + sketch["toolbars"]["order"]
            ),
            "nativePanelsExcluded": not any(
                name in sketch["toolbars"]["order"]
                for name in ("Views", "Structure", "Sketcher", "Edit Mode", "Geometries", "Tools")
            ),
            "invalidSketchPanelsExcluded": not any(
                name in sketch["toolbars"]["order"]
                for name in ("Fusion Sketch Entry_newPanel", "Fusion Sketch Frequent_newPanel")
            ),
            "authoritativeWorkbenches": all(
                name in ribbon.get("authoritativeWorkbenches", [])
                for name in ("PartDesignWorkbench", "PartWorkbench", "SketcherWorkbench", "SurfaceWorkbench")
            ),
        }
        return all(checks.values()), checks
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        return False, {"error": str(error)}


def prepare():
    version = tuple(int(part) for part in App.Version()[:2])
    if version < (1, 1):
        raise RuntimeError("FusionMyFreeCAD requires FreeCAD 1.1 or newer.")
    for required in (BASE_LAYOUT, LAYOUT_SPEC, RUNTIME):
        if not os.path.isfile(required):
            raise RuntimeError("FusionMyFreeCAD package is incomplete: {}".format(required))

    state = _load_json(STATE_PATH) if os.path.isfile(STATE_PATH) else None
    if state and state.get("packageVersion") == PACKAGE_VERSION:
        valid, _checks = _verify_layout(RIBBON_PATH)
        if valid:
            return

    os.makedirs(RIBBON_DIR, exist_ok=True)
    if state is None:
        backup_root = os.path.join(USER_ROOT, "FusionMyFreeCAD-Backups", "addon-" + _timestamp())
        os.makedirs(backup_root, exist_ok=True)
        prior = os.path.join(backup_root, "RibbonStructure.json")
        had_ribbon = os.path.isfile(RIBBON_PATH)
        if had_ribbon:
            shutil.copy2(RIBBON_PATH, prior)
        state = {
            "schemaVersion": 1,
            "installedAt": _now(),
            "backupRoot": backup_root,
            "ribbonHadExisting": had_ribbon,
            "preferences": _capture_preferences(),
            "updates": [],
        }
    elif os.path.isfile(RIBBON_PATH):
        update_path = os.path.join(state["backupRoot"], "updates", _timestamp() + "-RibbonStructure.json")
        os.makedirs(os.path.dirname(update_path), exist_ok=True)
        shutil.copy2(RIBBON_PATH, update_path)
        state.setdefault("updates", []).append(update_path)

    ribbon, layout_version = _merge_layout()
    _atomic_json(RIBBON_PATH, ribbon)
    valid, checks = _verify_layout(RIBBON_PATH)
    if not valid:
        raise RuntimeError("FusionMyFreeCAD generated an invalid ribbon: {}".format(checks))
    state.update(
        {
            "packageVersion": PACKAGE_VERSION,
            "layoutVersion": layout_version,
            "updatedAt": _now(),
            "ribbonSha256": _sha256(RIBBON_PATH),
        }
    )
    _atomic_json(STATE_PATH, state)


def verify():
    valid, checks = _verify_layout(RIBBON_PATH)
    state = _load_json(STATE_PATH) if os.path.isfile(STATE_PATH) else {}
    checks["stateVersion"] = state.get("packageVersion") == PACKAGE_VERSION
    checks["bundledRibbon"] = os.path.isfile(
        os.path.join(ADDON_ROOT, "bundled-addons", "FreeCAD-Ribbon", "InitGui.py")
    )
    checks["bundledSearch"] = os.path.isfile(
        os.path.join(ADDON_ROOT, "bundled-addons", "SearchBar", "InitGui.py")
    )
    return valid and all(checks.values()), checks


def restore():
    if not os.path.isfile(STATE_PATH):
        raise RuntimeError("FusionMyFreeCAD restoration state is missing.")
    state = _load_json(STATE_PATH)
    removed = os.path.join(state["backupRoot"], "removed-" + _timestamp())
    os.makedirs(removed, exist_ok=True)
    if os.path.isfile(RIBBON_PATH):
        shutil.move(RIBBON_PATH, os.path.join(removed, "RibbonStructure.json"))
    prior = os.path.join(state["backupRoot"], "RibbonStructure.json")
    if state.get("ribbonHadExisting") and os.path.isfile(prior):
        shutil.copy2(prior, RIBBON_PATH)
    _restore_preferences(state.get("preferences", []))
    shutil.move(STATE_PATH, os.path.join(removed, "FusionMyFreeCAD-addon-state.json"))
    main_window = Gui.getMainWindow()
    main_window.menuBar().show()
    try:
        from PySide import QtWidgets

        for toolbar in main_window.findChildren(QtWidgets.QToolBar):
            toolbar.show()
    except Exception:
        pass
    return removed


def _message(title, text, error=False):
    from PySide import QtWidgets

    icon = QtWidgets.QMessageBox.Critical if error else QtWidgets.QMessageBox.Information
    QtWidgets.QMessageBox(icon, title, text, parent=Gui.getMainWindow()).exec()


class VerifyCommand:
    def GetResources(self):
        return {"MenuText": "Verify FusionMyFreeCAD", "ToolTip": "Check the installed UI package"}

    def Activated(self):
        valid, checks = verify()
        lines = ["{}: {}".format(name, "OK" if result else "FAILED") for name, result in checks.items()]
        _message("FusionMyFreeCAD verification", "\n".join(lines), not valid)


class RestoreCommand:
    def GetResources(self):
        return {"MenuText": "Restore Previous UI", "ToolTip": "Restore the UI from before FusionMyFreeCAD"}

    def Activated(self):
        from PySide import QtWidgets

        answer = QtWidgets.QMessageBox.question(
            Gui.getMainWindow(),
            "Restore Previous UI",
            "Restore the UI settings from before FusionMyFreeCAD was installed?",
        )
        if answer != QtWidgets.QMessageBox.Yes:
            return
        try:
            location = restore()
            _message(
                "FusionMyFreeCAD restored",
                "Previous UI restored. Remove FusionMyFreeCAD in Addon Manager, then restart FreeCAD.\n\n"
                "The removed configuration remains recoverable at:\n{}".format(location),
            )
        except Exception as error:
            _message("FusionMyFreeCAD restoration failed", str(error), True)


class CreateSketchCommand:
    def GetResources(self):
        return {
            "Pixmap": "Sketcher_NewSketch",
            "MenuText": "Create Sketch",
            "ToolTip": "Create a document if needed, then start a Part Design sketch",
        }

    def IsActive(self):
        # FreeCAD's PartDesign_NewSketch is disabled until a document exists.
        # This wrapper remains available so the first click can create one.
        return True

    def Activated(self):
        if App.ActiveDocument is None:
            App.newDocument()
        document = App.ActiveDocument
        if not any(obj.isDerivedFrom("PartDesign::Body") for obj in document.Objects):
            document.addObject("PartDesign::Body", "Body")
            document.recompute()
        Gui.activateWorkbench("PartDesignWorkbench")
        Gui.runCommand("PartDesign_NewSketch")
        Gui.activateWorkbench("SketcherWorkbench")


class ParameterTableCommand:
    def GetResources(self):
        return {
            "Pixmap": "Spreadsheet",
            "MenuText": "Parameter Table",
            "ToolTip": "Create or open a spreadsheet for model parameters, calculations, and reports",
        }

    def IsActive(self):
        return True

    def Activated(self):
        if App.ActiveDocument is None:
            App.newDocument()
        Gui.activateWorkbench("SpreadsheetWorkbench")
        document = App.ActiveDocument
        sheet = next(
            (
                obj
                for obj in document.Objects
                if obj.isDerivedFrom("Spreadsheet::Sheet") and obj.Label == "Parameters"
            ),
            None,
        )
        if sheet is None:
            sheet = document.addObject("Spreadsheet::Sheet", "Parameters")
            sheet.Label = "Parameters"
            sheet.set("A1", "Parameter")
            sheet.set("B1", "Value / Expression")
            sheet.set("C1", "Notes")
            sheet.setStyle("A1:C1", "bold", "add")
            sheet.setColumnWidth("A", 180)
            sheet.setColumnWidth("B", 180)
            sheet.setColumnWidth("C", 260)
            document.recompute()
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(sheet)
        Gui.activeDocument().setEdit(sheet.Name)


def register_commands():
    Gui.addCommand("FusionMyFreeCAD_CreateSketch", CreateSketchCommand())
    Gui.addCommand("FusionMyFreeCAD_ParameterTable", ParameterTableCommand())
    Gui.addCommand("FusionMyFreeCAD_Verify", VerifyCommand())
    Gui.addCommand("FusionMyFreeCAD_Restore", RestoreCommand())


def _execute_module(module_name, path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError("Could not load {}".format(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def run_runtime():
    if getattr(App, "_fusion_my_freecad_runtime_loaded", False):
        return
    App._fusion_my_freecad_runtime_loaded = True
    _execute_module("_fusion_my_freecad_runtime", RUNTIME)


def load_vendor(name, directory):
    marker = "_fusion_my_freecad_vendor_{}_loaded".format(name)
    if getattr(App, marker, False):
        return
    # Reuse an already active standalone installation instead of creating duplicate
    # Ribbon docks or SearchBar toolbars. Clean installations use the bundled copy.
    if name == "FreeCAD_Ribbon" and "FCBinding" in sys.modules:
        setattr(App, marker, True)
        App.Console.PrintMessage("FusionMyFreeCAD is using the already active FreeCAD Ribbon.\n")
        return
    if name == "SearchBar" and "Parameters_SearchBar" in sys.modules:
        setattr(App, marker, True)
        App.Console.PrintMessage("FusionMyFreeCAD is using the already active SearchBar.\n")
        return
    init_gui = os.path.join(directory, "InitGui.py")
    if not os.path.isfile(init_gui):
        raise RuntimeError("FusionMyFreeCAD vendor payload is incomplete: {}".format(init_gui))
    if directory not in sys.path:
        sys.path.insert(0, directory)
    setattr(App, marker, True)
    _execute_module("_fusion_vendor_{}".format(name), init_gui)
