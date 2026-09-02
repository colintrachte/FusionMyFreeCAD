"""Apply and report the reversible FusionMyFreeCAD UI at FreeCAD startup."""

import json
import math
import os
import sys
from datetime import UTC, datetime

import FreeCAD as App
import FreeCADGui as Gui

try:
    from PySide import QtCore, QtGui, QtWidgets
except ImportError:  # pragma: no cover - older FreeCAD bindings
    from PySide import QtCore, QtGui

    QtWidgets = QtGui

try:
    import fusion_bootstrap as bootstrap
except ImportError:  # pragma: no cover - executed outside the add-on directory
    _ADDON_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if _ADDON_ROOT not in sys.path:
        sys.path.insert(0, _ADDON_ROOT)
    import fusion_bootstrap as bootstrap


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

START_WORKBENCH_KEYS = {
    ("User parameter:BaseApp/Preferences/General", "AutoloadModule"),
}
NAVIGATION_KEYS = {
    ("User parameter:BaseApp/Preferences/View", "NavigationStyle"),
    ("User parameter:BaseApp/Preferences/View", "ShowNaviCube"),
    ("User parameter:BaseApp/Preferences/NaviCube", "CornerNaviCube"),
}
SHORTCUT_KEYS = {("User parameter:BaseApp/Preferences/Shortcut", command) for command in SHORTCUTS}

# A command must be used more often than this before it displaces a shipped
# default in an adaptive panel. One stray click should not rearrange the ribbon
# for a month, which a baseline below 1.0 allowed.
PROMOTION_BASELINE = 2.5
USAGE_HALF_LIFE_DAYS = 30.0

PREFERENCES = App.ParamGet(bootstrap.PREFERENCE_ROOT)
ADDON_DIR = os.path.dirname(os.path.abspath(__file__))
STATUS_PATH = bootstrap.STATUS_PATH
USAGE_PATH = bootstrap.USAGE_PATH
RIBBON_PATH = bootstrap.RIBBON_PATH

_manifest_cache = None
_usage_cache = None
_usage_write_pending = False
_status_write_pending = False
_problems = []
_displaced_shortcuts = []
_last_workbench = ""
_task_accept_filter = None


def _record_problem(text):
    """Collect a runtime failure so Verify UI can report it instead of hiding it."""
    App.Console.PrintWarning("FusionMyFreeCAD: {}\n".format(text))
    if text not in _problems:
        _problems.append(text)
    schedule_status_write()


def _qaction_type():
    return getattr(QtGui, "QAction", None) or QtWidgets.QAction


def _application_shortcut_context():
    try:
        return QtCore.Qt.ShortcutContext.ApplicationShortcut
    except AttributeError:
        return QtCore.Qt.ApplicationShortcut


def _dock_area():
    area = getattr(QtCore.Qt, "LeftDockWidgetArea", None)
    if area is None:
        area = QtCore.Qt.DockWidgetArea.LeftDockWidgetArea
    return area


def _portable(sequence):
    return QtGui.QKeySequence(sequence).toString()


def _defer(label, function, attempts=10, interval=200):
    """Run `function` as soon as the UI is ready, retrying on a bounded schedule.

    `function` returns True when the work is done and False when the widget it
    needs does not exist yet. Giving up is recorded rather than passed over in
    silence, which is what a fixed startup delay did whenever it guessed wrong.
    """
    remaining = {"attempts": attempts}

    def attempt():
        remaining["attempts"] -= 1
        try:
            if function():
                return
        except Exception as error:
            _record_problem("{} failed: {}".format(label, error))
            return
        if remaining["attempts"] <= 0:
            _record_problem("{} was not available after {} attempts".format(label, attempts))
            return
        QtCore.QTimer.singleShot(interval, attempt)

    QtCore.QTimer.singleShot(0, attempt)


def _run(label, function):
    """Run one best-effort step immediately, recording any failure."""
    try:
        return function()
    except Exception as error:
        _record_problem("{} failed: {}".format(label, error))
        return None


# ---------------------------------------------------------------------------
# Preferences
# ---------------------------------------------------------------------------


def _apply_structural():
    """Point the bundled Ribbon at this profile's generated layout.

    These are not user-facing preferences; they are paths the bundled add-on needs
    in order to find its own data, so they are re-asserted at every launch.
    """
    ribbon = App.ParamGet("User parameter:BaseApp/Preferences/Mod/FreeCAD-Ribbon")
    ribbon_dir = os.path.join(App.getUserAppDataDir(), "RibbonUI_Data")
    ribbon.SetString("ConfigDir", ribbon_dir)
    ribbon.SetString("RibbonStructure", os.path.join(ribbon_dir, "RibbonStructure.json"))
    ribbon.SetString("BackupFolder", os.path.join(ribbon_dir, "Backups"))


def _apply_defaults():
    """Write FusionMyFreeCAD's opinionated defaults over the user's profile."""
    if PREFERENCES.GetBool("SetStartWorkbench", True):
        App.ParamGet("User parameter:BaseApp/Preferences/General").SetString(
            "AutoloadModule", "PartDesignWorkbench"
        )

    if PREFERENCES.GetBool("SetNavigation", True):
        view = App.ParamGet("User parameter:BaseApp/Preferences/View")
        view.SetString("NavigationStyle", "Gui::RevitNavigationStyle")
        view.SetBool("ShowNaviCube", True)
        App.ParamGet("User parameter:BaseApp/Preferences/NaviCube").SetInt("CornerNaviCube", 1)

    # Keep FreeCAD's native Model/Tasks browser. It is more capable than a ribbon
    # imitation and should be present when the application opens.
    App.ParamGet("User parameter:BaseApp/Preferences/DockWindows/ComboView").SetBool(
        "Enabled", True
    )
    App.ParamGet("User parameter:BaseApp/MainWindow/DockWindows").SetBool("Std_ComboView", True)

    ribbon = App.ParamGet("User parameter:BaseApp/Preferences/Mod/FreeCAD-Ribbon")
    ribbon.SetInt("Preferred_view", 3)
    # The bundled Ribbon once persisted the small icon size as its large-icon
    # default. Set all three tiers explicitly so layout "large" and "small" choices
    # remain visually meaningful on existing as well as clean profiles.
    ribbon.SetBool("Link_IconSizes", True)
    ribbon.SetInt("IconSize_Small", 24)
    ribbon.SetInt("IconSize_Medium", 36)
    ribbon.SetInt("IconSize_Large", 72)

    dimensioning = App.ParamGet("User parameter:BaseApp/Preferences/Mod/Sketcher/dimensioning")
    dimensioning.SetBool("SingleDimensioningTool", True)
    dimensioning.SetBool("SeparatedDimensioningTools", False)
    dimensioning.SetBool("DimensioningDiameter", True)
    dimensioning.SetBool("DimensioningRadius", True)

    # Generate selectable planar regions from closed sketch boundaries. This is
    # FreeCAD's native profile-face pipeline: crossing and boundary-to-boundary
    # lines subdivide a profile, while dangling open geometry is ignored.
    App.ParamGet("User parameter:BaseApp/Preferences/Mod/Sketcher").SetBool("MakeInternals", True)

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


def _restore_opted_out_defaults():
    """Undo previously applied values for preference groups the user disabled."""
    keys = set()
    if not PREFERENCES.GetBool("SetStartWorkbench", True):
        keys.update(START_WORKBENCH_KEYS)
    if not PREFERENCES.GetBool("SetNavigation", True):
        keys.update(NAVIGATION_KEYS)
    if not PREFERENCES.GetBool("SetShortcuts", True):
        keys.update(SHORTCUT_KEYS)
    if not keys:
        return
    for problem in bootstrap.restore_preference_keys(keys):
        _record_problem("preference opt-out could not be restored: {}".format(problem))


def apply_preferences(force=False):
    """Apply managed defaults once per installed version.

    Re-applying them at every launch silently discarded any change the user made
    in FreeCAD's own preferences dialog. Reapply FusionMyFreeCAD (or `force`) is
    the supported way to return to the shipped defaults.
    """
    _apply_structural()
    already = PREFERENCES.GetString("AppliedVersion", "")
    if already == bootstrap.PACKAGE_VERSION and not force:
        App.saveParameter()
        return False
    _apply_defaults()
    _restore_opted_out_defaults()
    PREFERENCES.SetString("AppliedVersion", bootstrap.PACKAGE_VERSION)
    App.saveParameter()
    return True


# ---------------------------------------------------------------------------
# Window furniture
# ---------------------------------------------------------------------------


def ensure_navigation_cube():
    if not PREFERENCES.GetBool("SetNavigation", True):
        return True
    if not Gui.ActiveDocument:
        # Nothing to configure yet; the preference covers views created later.
        return True
    viewer = Gui.ActiveDocument.ActiveView.getViewer()
    viewer.setEnabledNaviCube(True)
    viewer.setNaviCubeCorner(1)
    return True


def ensure_model_tree():
    """Dock the Model tree on the left and select its Model tab.

    Returns False while the dock does not exist yet so the caller can retry.
    """
    main_window = Gui.getMainWindow()
    if main_window is None:
        return False
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
    if dock is None:
        return False

    left_area = _dock_area()
    if main_window.dockWidgetArea(dock) != left_area:
        main_window.addDockWidget(left_area, dock)
    dock.show()
    dock.raise_()
    if dock.width() < 260:
        dock.resize(300, dock.height())

    # Combo View contains Model and Tasks tabs. Select Model so a newly created
    # document or body is immediately visible.
    tabs = dock.findChild(QtWidgets.QTabWidget)
    if tabs is not None:
        for index in range(tabs.count()):
            if tabs.tabText(index).replace("&", "").strip().lower() == "model":
                tabs.setCurrentIndex(index)
                break

    # Selection View is useful on demand but should not replace the primary design
    # browser at startup.
    for candidate in docks:
        title = candidate.windowTitle().replace("&", "").strip().lower()
        if candidate is not dock and title == "selection view":
            candidate.hide()
    return True


def ensure_starter_design():
    """Optionally open into an editable Part Design document.

    Off by default: creating an unsaved document at every launch produces a
    document the user did not ask for and a save prompt when they quit.
    """
    if not PREFERENCES.GetBool("CreateStarterDesign", False):
        return True
    if App.ActiveDocument is None:
        document = App.newDocument()
        body = document.addObject("PartDesign::Body", "Body")
        body.Label = "Part"
        document.recompute()
    Gui.activateWorkbench("PartDesignWorkbench")
    return True


def _qt_enum(owner, group, name, default=None):
    """Read an enum from either the Qt5 or Qt6 spelling."""
    value = getattr(owner, name, None)
    if value is not None:
        return value
    nested = getattr(owner, group, None)
    return getattr(nested, name, default) if nested is not None else default


def accept_active_task():
    """Click the active task dialog's real affirmative button."""
    control = getattr(Gui, "Control", None)
    if control is None or not control.activeDialog():
        return False
    main_window = Gui.getMainWindow()
    if main_window is None:
        return False

    button_box_type = getattr(QtWidgets, "QDialogButtonBox", None)
    if button_box_type is None:
        return False
    accept_roles = {
        _qt_enum(button_box_type, "ButtonRole", "AcceptRole"),
        _qt_enum(button_box_type, "ButtonRole", "YesRole"),
    }
    accept_roles.discard(None)
    for box in reversed(main_window.findChildren(button_box_type)):
        if hasattr(box, "isVisible") and not box.isVisible():
            continue
        for button in box.buttons():
            if box.buttonRole(button) not in accept_roles:
                continue
            if hasattr(button, "isEnabled") and not button.isEnabled():
                continue
            button.click()
            return True
    return False


class _TaskAcceptFilter(QtCore.QObject):
    """Give FreeCAD task dialogs Fusion-style Enter-to-OK behaviour."""

    def eventFilter(self, watched, event):
        key_press = _qt_enum(QtCore.QEvent, "Type", "KeyPress")
        enter_keys = {
            _qt_enum(QtCore.Qt, "Key", "Key_Return"),
            _qt_enum(QtCore.Qt, "Key", "Key_Enter"),
        }
        enter_keys.discard(None)
        if event.type() != key_press or event.key() not in enter_keys:
            return False

        # A newline is intentional in multiline editors; do not turn it into OK.
        multiline_types = tuple(
            widget_type
            for widget_type in (
                getattr(QtWidgets, "QTextEdit", None),
                getattr(QtWidgets, "QPlainTextEdit", None),
            )
            if widget_type is not None
        )
        focus = QtWidgets.QApplication.focusWidget()
        if multiline_types and isinstance(focus, multiline_types):
            return False
        if not accept_active_task():
            return False
        if hasattr(event, "accept"):
            event.accept()
        return True


def install_task_accept_filter():
    global _task_accept_filter
    application = QtWidgets.QApplication.instance()
    if application is None:
        return False
    if _task_accept_filter is None:
        _task_accept_filter = _TaskAcceptFilter(application)
        application.installEventFilter(_task_accept_filter)
    return True


# ---------------------------------------------------------------------------
# Adaptive panels
# ---------------------------------------------------------------------------


def load_manifest():
    global _manifest_cache
    if _manifest_cache is None:
        with open(os.path.join(ADDON_DIR, "layout-manifest.json"), encoding="utf-8") as stream:
            _manifest_cache = json.load(stream)
    return _manifest_cache


def load_usage():
    global _usage_cache
    if _usage_cache is not None:
        return _usage_cache
    try:
        with open(USAGE_PATH, encoding="utf-8") as stream:
            loaded = json.load(stream)
        if (
            not isinstance(loaded, dict)
            or loaded.get("schemaVersion") != 1
            or not isinstance(loaded.get("workbenches"), dict)
        ):
            raise ValueError("unsupported usage data")
        _usage_cache = loaded
    except (OSError, ValueError, TypeError):
        _usage_cache = {"schemaVersion": 1, "workbenches": {}}
    return _usage_cache


def _utc_now():
    return datetime.now(UTC)


def _parse_time(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        # Earlier builds and hand-edited files may contain an ISO timestamp
        # without an offset.  Treat it as UTC rather than mixing naïve and aware
        # datetimes during score decay.
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
    except (AttributeError, TypeError, ValueError):
        return _utc_now()


def _decayed_score(entry, now):
    if not isinstance(entry, dict):
        return 0.0
    age_days = max(0.0, (now - _parse_time(entry.get("lastUsed"))).total_seconds() / 86400.0)
    try:
        score = float(entry.get("score", 0.0))
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(score) or score < 0.0:
        return 0.0
    return score * (0.5 ** (age_days / USAGE_HALF_LIFE_DAYS))


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
        _record_problem("command usage could not be saved: {}".format(error))


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
        baseline = PROMOTION_BASELINE if command in default_rank else 0.0
        return (max(measured, baseline), -default_rank.get(command, len(defaults)))

    commands = list(config.get("commands", {}))
    commands.sort(key=rank, reverse=True)
    return commands[: int(config.get("capacity", 4))]


def adaptive_selection(workbench):
    config = load_manifest().get("adaptivePins", {}).get(workbench)
    groups = adaptive_groups(workbench)
    if not config or not groups:
        return []
    selected = {panel: _adaptive_group_selection(workbench, group) for panel, group in groups}
    return selected if "panels" in config else selected[groups[0][0]]


def _rewrite_panels(ribbon, workbench, config, selected):
    """Permute adaptive candidates inside the slots they already occupy."""
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
        if len(reordered) != len(candidate_positions):
            # Silently truncating here would drop a promoted command from the
            # panel; report the mismatch and leave this panel untouched instead.
            _record_problem(
                "adaptive panel {}/{} has {} candidates for {} slots".format(
                    workbench, panel_name, len(reordered), len(candidate_positions)
                )
            )
            continue
        new_order = list(current_order)
        for index, command in zip(candidate_positions, reordered, strict=True):
            new_order[index] = command
        if new_order != current_order:
            sources = dict(ribbon["newPanels"][workbench][panel_name])
            missing = [command for command in new_order if command not in sources]
            if missing:
                _record_problem(
                    "adaptive panel {}/{} is missing source data for {}".format(
                        workbench, panel_name, missing
                    )
                )
                continue
            toolbar["order"] = new_order
            if "panelMenu" in toolbar:
                toolbar["panelMenu"] = list(new_order)
            ribbon["newPanels"][workbench][panel_name] = [
                [command, sources[command]] for command in new_order
            ]
            changed = True
        for command in candidate_set.intersection(toolbar["commands"]):
            wanted_size = "large" if command in promoted else "small"
            if toolbar["commands"][command].get("size") != wanted_size:
                toolbar["commands"][command]["size"] = wanted_size
                changed = True
    return changed


def _rewrite_single_panel(ribbon, workbench, config, selected):
    panel_name = config["panel"]
    toolbar = ribbon["workbenches"][workbench]["toolbars"][panel_name]
    metadata = config["commands"]
    if toolbar.get("order") == selected:
        return False
    toolbar["order"] = list(selected)
    toolbar["panelMenu"] = list(selected)
    toolbar["overflow"] = []
    toolbar["pinCount"] = len(selected)
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
    return True


def refresh_adaptive_panel(workbench):
    config = load_manifest().get("adaptivePins", {}).get(workbench)
    selected = adaptive_selection(workbench)
    if not config or not selected or not os.path.isfile(RIBBON_PATH):
        return False
    try:
        with open(RIBBON_PATH, encoding="utf-8") as stream:
            ribbon = json.load(stream)
        if "panels" in config:
            changed = _rewrite_panels(ribbon, workbench, config, selected)
        else:
            changed = _rewrite_single_panel(ribbon, workbench, config, selected)
        if not changed:
            return False
        temporary = RIBBON_PATH + ".tmp"
        with open(temporary, "w", encoding="utf-8") as stream:
            json.dump(ribbon, stream, indent=2)
        os.replace(temporary, RIBBON_PATH)
        # Keep the recorded digest current so a future mismatch means a genuine
        # edit from outside the add-on rather than our own adaptive rewrite.
        bootstrap.update_ribbon_hash()
        # Housekeeping, not something the user acts on -- keep it in the log only.
        App.Console.PrintLog(
            "FusionMyFreeCAD updated FREQUENT for {}; it appears on the next "
            "ribbon reload.\n".format(workbench)
        )
        return True
    except (OSError, KeyError, TypeError, ValueError) as error:
        _record_problem("adaptive pins were not updated: {}".format(error))
        return False


# ---------------------------------------------------------------------------
# Shortcuts
# ---------------------------------------------------------------------------


def reconcile_actions(main_window=None):
    """Connect usage tracking and enforce the Fusion shortcut set.

    Any shortcut taken from another action is recorded so Verify UI can tell the
    user exactly what changed instead of leaving them to discover it.
    """
    main_window = main_window if main_window is not None else Gui.getMainWindow()
    if main_window is None:
        return False
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

    if not PREFERENCES.GetBool("SetShortcuts", True):
        return True

    context = _application_shortcut_context()
    newly_displaced = []
    for command, shortcut in SHORTCUTS.items():
        target = by_name.get(command)
        if target is None:
            continue
        wanted = _portable(shortcut)
        for action in actions:
            if action is target or _portable(action.shortcut().toString()) != wanted:
                continue
            action.setShortcut(QtGui.QKeySequence())
            entry = {
                "sequence": wanted,
                "from": action.objectName() or action.text() or "(unnamed action)",
                "to": command,
            }
            if entry not in _displaced_shortcuts:
                _displaced_shortcuts.append(entry)
                newly_displaced.append(entry)
                # Per-shortcut detail stays in the log; Verify UI lists them too.
                App.Console.PrintLog(
                    "FusionMyFreeCAD moved the {} shortcut from {} to {}.\n".format(
                        entry["sequence"], entry["from"], entry["to"]
                    )
                )
        target.setShortcut(QtGui.QKeySequence(shortcut))
        target.setShortcutContext(context)
    if newly_displaced:
        App.Console.PrintMessage(
            "FusionMyFreeCAD reassigned {} keyboard shortcut{} from other commands "
            "(run Verify FusionMyFreeCAD to see which).\n".format(
                len(newly_displaced), "" if len(newly_displaced) == 1 else "s"
            )
        )
    return True


# ---------------------------------------------------------------------------
# Status reporting
# ---------------------------------------------------------------------------


def write_runtime_status(active_workbench=None):
    global _status_write_pending
    _status_write_pending = False
    active_workbench = _last_workbench if active_workbench is None else active_workbench
    try:
        manifest = load_manifest()
        available = set(Gui.listCommands())
        expected = manifest.get("primaryCommands", [])
        status = {
            "status": "loaded",
            "checkedAt": datetime.now().astimezone().isoformat(),
            "packageVersion": bootstrap.PACKAGE_VERSION,
            "layoutVersion": manifest.get("layoutVersion"),
            "freeCADVersion": ".".join(str(part) for part in App.Version()[:3]),
            "activeWorkbench": active_workbench,
            "ribbonStructure": RIBBON_PATH,
            "adaptivePins": {
                name: adaptive_selection(name) for name in manifest.get("adaptivePins", {})
            },
            "availablePrimaryCommands": [command for command in expected if command in available],
            "commandsNotLoadedYet": [command for command in expected if command not in available],
            "displacedShortcuts": list(_displaced_shortcuts),
            "problems": list(_problems),
        }
        with open(STATUS_PATH + ".tmp", "w", encoding="utf-8") as stream:
            json.dump(status, stream, indent=2)
        os.replace(STATUS_PATH + ".tmp", STATUS_PATH)
        return True
    except Exception as error:
        App.Console.PrintWarning("FusionMyFreeCAD status check failed: {}\n".format(error))
        return False


def schedule_status_write(delay=750):
    """Coalesce status writes so a burst of workbench switches writes once."""
    global _status_write_pending
    if _status_write_pending:
        return
    _status_write_pending = True
    QtCore.QTimer.singleShot(delay, write_runtime_status)


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------


def after_workbench_activation(name):
    global _last_workbench
    _last_workbench = name
    _run("adaptive pins", lambda: refresh_adaptive_panel(name))
    _run("shortcut reconciliation", reconcile_actions)
    _defer("navigation cube", ensure_navigation_cube)
    _defer("model tree", ensure_model_tree)
    schedule_status_write()


def install():
    """Wire the runtime into the running FreeCAD session."""
    _run("preferences", apply_preferences)
    main_window = Gui.getMainWindow()
    if main_window is not None and not getattr(main_window, "_fusion_my_freecad_connected", False):
        main_window._fusion_my_freecad_connected = True
        main_window.workbenchActivated.connect(after_workbench_activation)
    _defer("starter design", ensure_starter_design)
    _defer("model tree", ensure_model_tree)
    _defer("navigation cube", ensure_navigation_cube)
    _defer("shortcut reconciliation", reconcile_actions)
    _defer("Enter-to-OK task handling", install_task_accept_filter)
    schedule_status_write(1500)
    App.Console.PrintMessage(
        "FusionMyFreeCAD {}: adaptive ribbon, smart dimensions, navigation cube, "
        "and shortcuts configured.\n".format(bootstrap.PACKAGE_VERSION)
    )


# Tests import this module for its logic and drive `install()` themselves.
if not os.environ.get("FUSION_MY_FREECAD_NO_AUTOSTART"):
    install()
