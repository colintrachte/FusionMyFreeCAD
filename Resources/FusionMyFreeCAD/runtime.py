"""Apply and report the reversible FusionMyFreeCAD UI at FreeCAD startup."""

import json
import os
from datetime import datetime, timezone

import FreeCAD as App
import FreeCADGui as Gui

try:
    from PySide import QtCore, QtGui, QtWidgets
except ImportError:
    from PySide import QtCore, QtGui

    QtWidgets = QtGui


SHORTCUTS = {
    "Sketcher_CreateLine": "L",
    "Sketcher_CreateRectangle_Center": "R",
    "Sketcher_CreateRectangle": "Shift+R",
    "Sketcher_CreateCircle": "C",
    "Sketcher_Dimension": "D",
    "PartDesign_Pad": "E",
    "PartDesign_Pocket": "Shift+E",
    "PartDesign_Hole": "H",
    "Sketcher_Trimming": "T",
    "Sketcher_Offset": "O",
    "Sketcher_Projection": "P",
    "Sketcher_ToggleConstruction": "X",
    "Std_Measure": "I",
}

PREFERENCES = App.ParamGet("User parameter:BaseApp/Preferences/Mod/FusionMyFreeCAD")
ADDON_DIR = os.path.dirname(__file__)
STATUS_PATH = os.path.join(App.getUserAppDataDir(), "FusionMyFreeCAD-runtime-status.json")
USAGE_PATH = os.path.join(App.getUserAppDataDir(), "FusionMyFreeCAD-usage.json")
RIBBON_PATH = os.path.join(App.getUserAppDataDir(), "RibbonUI_Data", "RibbonStructure.json")
_manifest_cache = None
_usage_cache = None
_usage_write_pending = False


def _qaction_type():
    return getattr(QtGui, "QAction", None) or QtWidgets.QAction


def _application_shortcut_context():
    try:
        return QtCore.Qt.ShortcutContext.ApplicationShortcut
    except AttributeError:
        return QtCore.Qt.ApplicationShortcut


def _portable(sequence):
    return QtGui.QKeySequence(sequence).toString()


def apply_preferences():
    general = App.ParamGet("User parameter:BaseApp/Preferences/General")
    if PREFERENCES.GetBool("SetStartWorkbench", True):
        general.SetString("AutoloadModule", "PartDesignWorkbench")

    if PREFERENCES.GetBool("SetNavigation", True):
        view = App.ParamGet("User parameter:BaseApp/Preferences/View")
        view.SetString("NavigationStyle", "Gui::RevitNavigationStyle")
        view.SetBool("ShowNaviCube", True)
        nav_cube = App.ParamGet("User parameter:BaseApp/Preferences/NaviCube")
        nav_cube.SetInt("CornerNaviCube", 1)

    # Keep FreeCAD's native Model/Tasks browser. It is more capable than a
    # ribbon imitation and should be present when the application opens.
    App.ParamGet("User parameter:BaseApp/Preferences/DockWindows/ComboView").SetBool("Enabled", True)
    App.ParamGet("User parameter:BaseApp/MainWindow/DockWindows").SetBool("Std_ComboView", True)

    ribbon = App.ParamGet("User parameter:BaseApp/Preferences/Mod/FreeCAD-Ribbon")
    ribbon_dir = os.path.join(App.getUserAppDataDir(), "RibbonUI_Data")
    ribbon.SetString("ConfigDir", ribbon_dir)
    ribbon.SetString("RibbonStructure", os.path.join(ribbon_dir, "RibbonStructure.json"))
    ribbon.SetString("BackupFolder", os.path.join(ribbon_dir, "Backups"))
    ribbon.SetInt("Preferred_view", 3)
    # The bundled Ribbon once persisted the small icon size as its large-icon
    # default. Set all three tiers explicitly so layout "large" and "small"
    # choices remain visually meaningful on existing as well as clean profiles.
    ribbon.SetBool("Link_IconSizes", True)
    ribbon.SetInt("IconSize_Small", 24)
    ribbon.SetInt("IconSize_Medium", 36)
    ribbon.SetInt("IconSize_Large", 72)

    dimensioning = App.ParamGet("User parameter:BaseApp/Preferences/Mod/Sketcher/dimensioning")
    dimensioning.SetBool("SingleDimensioningTool", True)
    dimensioning.SetBool("SeparatedDimensioningTools", False)
    dimensioning.SetBool("DimensioningDiameter", True)
    dimensioning.SetBool("DimensioningRadius", True)

    # The upstream first-run changelog can cover Ribbon's modal cache prompt and
    # leave both windows impossible to operate. FusionMyFreeCAD provides its own
    # release notes, so keep the bundled SearchBar startup non-interactive.
    search = App.ParamGet("User parameter:BaseApp/Preferences/Mod/SearchBar")
    search.SetBool("ShowChangeDialog", False)
    search.SetString("DoNotShowAgain", "1.8")

    if PREFERENCES.GetBool("SetShortcuts", True):
        shortcut_group = App.ParamGet("User parameter:BaseApp/Preferences/Shortcut")
        for command, shortcut in SHORTCUTS.items():
            shortcut_group.SetString(command, shortcut)
    App.saveParameter()


def ensure_navigation_cube():
    try:
        if Gui.ActiveDocument:
            viewer = Gui.ActiveDocument.ActiveView.getViewer()
            viewer.setEnabledNaviCube(True)
            viewer.setNaviCubeCorner(1)
    except Exception as error:
        App.Console.PrintWarning("FusionMyFreeCAD could not restore the navigation cube: {}\n".format(error))


def ensure_model_tree():
    try:
        main_window = Gui.getMainWindow()
        docks = main_window.findChildren(QtWidgets.QDockWidget)
        names = ("Combo View", "ComboView", "Model", "Tree view")
        dock = next(
            (
                candidate
                for name in names
                for candidate in docks
                if candidate.objectName() == name or candidate.windowTitle() == name
            ),
            None,
        )
        if dock is not None:
            left_area = getattr(QtCore.Qt, "LeftDockWidgetArea", None)
            if left_area is None:
                left_area = QtCore.Qt.DockWidgetArea.LeftDockWidgetArea
            if main_window.dockWidgetArea(dock) != left_area:
                main_window.addDockWidget(left_area, dock)
            dock.show()
            dock.raise_()
            if dock.width() < 260:
                dock.resize(300, dock.height())

            # Combo View contains Model and Tasks tabs. Select Model so a
            # newly created document/body is immediately visible.
            tabs = dock.findChild(QtWidgets.QTabWidget)
            if tabs is not None:
                for index in range(tabs.count()):
                    if tabs.tabText(index).replace("&", "").strip().lower() == "model":
                        tabs.setCurrentIndex(index)
                        break

            # Selection View is useful on demand but should not replace the
            # primary design browser at startup.
            for candidate in docks:
                title = candidate.windowTitle().replace("&", "").strip().lower()
                if candidate is not dock and title == "selection view":
                    candidate.hide()
    except Exception as error:
        App.Console.PrintWarning("FusionMyFreeCAD could not restore the model tree: {}\n".format(error))


def ensure_starter_design():
    """Open into an editable Part Design document instead of an empty shell."""
    try:
        if not PREFERENCES.GetBool("CreateStarterDesign", True):
            return
        if App.ActiveDocument is None:
            document = App.newDocument()
            body = document.addObject("PartDesign::Body", "Body")
            body.Label = "Part"
            document.recompute()
        Gui.activateWorkbench("PartDesignWorkbench")
    except Exception as error:
        App.Console.PrintWarning("FusionMyFreeCAD could not create the starter design: {}\n".format(error))


def load_manifest():
    global _manifest_cache
    if _manifest_cache is None:
        with open(os.path.join(ADDON_DIR, "layout-manifest.json"), "r", encoding="utf-8") as stream:
            _manifest_cache = json.load(stream)
    return _manifest_cache


def load_usage():
    global _usage_cache
    if _usage_cache is not None:
        return _usage_cache
    try:
        with open(USAGE_PATH, "r", encoding="utf-8") as stream:
            loaded = json.load(stream)
        if loaded.get("schemaVersion") != 1:
            raise ValueError("unsupported usage data")
        _usage_cache = loaded
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        _usage_cache = {"schemaVersion": 1, "workbenches": {}}
    return _usage_cache


def _utc_now():
    return datetime.now(timezone.utc)


def _parse_time(value):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError):
        return _utc_now()


def _decayed_score(entry, now):
    age_days = max(0.0, (now - _parse_time(entry.get("lastUsed"))).total_seconds() / 86400.0)
    return float(entry.get("score", 0.0)) * (0.5 ** (age_days / 30.0))


def flush_usage():
    global _usage_write_pending
    _usage_write_pending = False
    if _usage_cache is None:
        return
    _usage_cache["updatedAt"] = _utc_now().isoformat()
    temporary = USAGE_PATH + ".tmp"
    try:
        with open(temporary, "w", encoding="utf-8") as stream:
            json.dump(_usage_cache, stream, indent=2)
        os.replace(temporary, USAGE_PATH)
    except OSError as error:
        App.Console.PrintWarning("FusionMyFreeCAD could not save command usage: {}\n".format(error))


def schedule_usage_write():
    global _usage_write_pending
    if _usage_write_pending:
        return
    _usage_write_pending = True
    QtCore.QTimer.singleShot(1000, flush_usage)


def record_usage(command):
    adaptive = load_manifest().get("adaptivePins", {})
    candidates = [
        name
        for name in adaptive
        if any(command in group.get("commands", {}) for _panel, group in adaptive_groups(name))
    ]
    if not candidates:
        return
    try:
        active = Gui.activeWorkbench().name()
    except Exception:
        active = ""
    workbench = active if active in candidates else candidates[0] if len(candidates) == 1 else ""
    if not workbench:
        return
    now = _utc_now()
    usage = load_usage().setdefault("workbenches", {}).setdefault(workbench, {})
    previous = usage.get(command, {})
    usage[command] = {
        "score": _decayed_score(previous, now) + 1.0,
        "lastUsed": now.isoformat(),
    }
    schedule_usage_write()


def adaptive_groups(workbench):
    config = load_manifest().get("adaptivePins", {}).get(workbench)
    if not config:
        return []
    if "panels" in config:
        return list(config["panels"].items())
    panel = config.get("panel")
    return [(panel, config)] if panel else []


def _adaptive_group_selection(workbench, config):
    now = _utc_now()
    usage = load_usage().get("workbenches", {}).get(workbench, {})
    defaults = config.get("defaults", [])
    default_rank = {command: index for index, command in enumerate(defaults)}

    def rank(command):
        measured = _decayed_score(usage.get(command, {}), now)
        baseline = 0.75 if command in default_rank else 0.0
        return (max(measured, baseline), -default_rank.get(command, len(defaults)))

    commands = list(config.get("commands", {}))
    commands.sort(key=rank, reverse=True)
    return commands[: int(config.get("capacity", 4))]


def adaptive_selection(workbench):
    config = load_manifest().get("adaptivePins", {}).get(workbench)
    groups = adaptive_groups(workbench)
    if not config or not groups:
        return []
    selected = {
        panel: _adaptive_group_selection(workbench, group) for panel, group in groups
    }
    return selected if "panels" in config else selected[groups[0][0]]


def refresh_adaptive_panel(workbench):
    config = load_manifest().get("adaptivePins", {}).get(workbench)
    selected = adaptive_selection(workbench)
    if not config or not selected or not os.path.isfile(RIBBON_PATH):
        return
    try:
        with open(RIBBON_PATH, "r", encoding="utf-8") as stream:
            ribbon = json.load(stream)
        if "panels" in config:
            changed = False
            for panel_name, group in adaptive_groups(workbench):
                promoted = selected.get(panel_name, [])
                toolbar = ribbon["workbenches"][workbench]["toolbars"][panel_name]
                current_order = list(toolbar["order"])
                candidate_set = set(group.get("commands", {}))
                candidate_positions = [
                    index for index, command in enumerate(current_order) if command in candidate_set
                ]
                reordered = promoted + [
                    command
                    for command in current_order
                    if command in candidate_set and command not in promoted
                ]
                new_order = list(current_order)
                for index, command in zip(candidate_positions, reordered):
                    new_order[index] = command
                if new_order != current_order:
                    toolbar["order"] = new_order
                    sources = {
                        command: source
                        for command, source in ribbon["newPanels"][workbench][panel_name]
                    }
                    ribbon["newPanels"][workbench][panel_name] = [
                        [command, sources[command]] for command in new_order
                    ]
                    changed = True
                for command in candidate_set.intersection(toolbar["commands"]):
                    wanted_size = "large" if command in promoted else "small"
                    if toolbar["commands"][command].get("size") != wanted_size:
                        toolbar["commands"][command]["size"] = wanted_size
                        changed = True
            if not changed:
                return
        else:
            panel_name = config["panel"]
            toolbar = ribbon["workbenches"][workbench]["toolbars"][panel_name]
            metadata = config["commands"]
            if toolbar.get("order") == selected:
                return
            toolbar["order"] = selected
            toolbar["commands"] = {
                command: {
                    "size": metadata[command][1],
                    "text": metadata[command][2],
                    "icon": metadata[command][3],
                    "IsExtra": True,
                }
                for command in selected
            }
            ribbon["newPanels"][workbench][panel_name] = [
                [command, metadata[command][0]] for command in selected
            ]
        temporary = RIBBON_PATH + ".tmp"
        with open(temporary, "w", encoding="utf-8") as stream:
            json.dump(ribbon, stream, indent=2)
        os.replace(temporary, RIBBON_PATH)
        App.Console.PrintMessage(
            "FusionMyFreeCAD updated FREQUENT for {}; it appears on the next ribbon reload.\n".format(workbench)
        )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        App.Console.PrintWarning("FusionMyFreeCAD adaptive pins were not updated: {}\n".format(error))


def write_runtime_status(active_workbench=""):
    try:
        manifest_path = os.path.join(ADDON_DIR, "layout-manifest.json")
        with open(manifest_path, "r", encoding="utf-8") as stream:
            manifest = json.load(stream)
        available = set(Gui.listCommands())
        expected = manifest.get("primaryCommands", [])
        status = {
            "status": "loaded",
            "checkedAt": datetime.now().astimezone().isoformat(),
            "layoutVersion": manifest.get("layoutVersion"),
            "freeCADVersion": ".".join(str(part) for part in App.Version()[:3]),
            "activeWorkbench": active_workbench,
            "ribbonStructure": RIBBON_PATH,
            "adaptivePins": {
                name: adaptive_selection(name) for name in manifest.get("adaptivePins", {})
            },
            "availablePrimaryCommands": [command for command in expected if command in available],
            "commandsNotLoadedYet": [command for command in expected if command not in available],
        }
        with open(STATUS_PATH, "w", encoding="utf-8") as stream:
            json.dump(status, stream, indent=2)
    except Exception as error:
        App.Console.PrintWarning("FusionMyFreeCAD status check failed: {}\n".format(error))


def reconcile_actions():
    main_window = Gui.getMainWindow()
    actions = main_window.findChildren(_qaction_type())
    by_name = {action.objectName(): action for action in actions if action.objectName()}
    adaptive_commands = {
        command
        for workbench in load_manifest().get("adaptivePins", {})
        for _panel, config in adaptive_groups(workbench)
        for command in config.get("commands", {})
    }
    for command in adaptive_commands:
        action = by_name.get(command)
        if action is None or action.property("fusionUsageConnected"):
            continue
        action.setProperty("fusionUsageConnected", True)
        action.triggered.connect(lambda checked=False, name=command: record_usage(name))

    if PREFERENCES.GetBool("SetShortcuts", True):
        context = _application_shortcut_context()
        for command, shortcut in SHORTCUTS.items():
            target = by_name.get(command)
            if target is None:
                continue
            wanted = _portable(shortcut)
            for action in actions:
                if action is not target and _portable(action.shortcut().toString()) == wanted:
                    action.setShortcut(QtGui.QKeySequence())
            target.setShortcut(QtGui.QKeySequence(shortcut))
            target.setShortcutContext(context)


apply_preferences()

main_window = Gui.getMainWindow()
def after_workbench_activation(name):
    QtCore.QTimer.singleShot(100, lambda: refresh_adaptive_panel(name))
    QtCore.QTimer.singleShot(250, reconcile_actions)
    QtCore.QTimer.singleShot(400, ensure_navigation_cube)
    QtCore.QTimer.singleShot(500, ensure_model_tree)
    QtCore.QTimer.singleShot(750, lambda: write_runtime_status(name))


if not getattr(main_window, "_fusion_my_freecad_connected", False):
    main_window._fusion_my_freecad_connected = True
    main_window.workbenchActivated.connect(after_workbench_activation)

QtCore.QTimer.singleShot(1500, reconcile_actions)
QtCore.QTimer.singleShot(900, ensure_starter_design)
QtCore.QTimer.singleShot(1750, ensure_navigation_cube)
QtCore.QTimer.singleShot(1800, ensure_model_tree)
QtCore.QTimer.singleShot(2000, write_runtime_status)
App.Console.PrintMessage("FusionMyFreeCAD 3: adaptive ribbon, smart dimensions, navigation cube, and shortcuts configured.\n")
