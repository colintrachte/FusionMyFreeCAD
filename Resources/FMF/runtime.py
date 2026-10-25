"""Apply and report the reversible FMF UI at FreeCAD startup."""

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
    import fmf_bootstrap as bootstrap
    from fmf_catalog import plan_shortcuts
except ImportError:  # pragma: no cover - executed outside the add-on directory
    _ADDON_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if _ADDON_ROOT not in sys.path:
        sys.path.insert(0, _ADDON_ROOT)
    import fmf_bootstrap as bootstrap
    from fmf_catalog import plan_shortcuts


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
_adaptive_command_workbenches_cache = None
_usage_cache = None
_usage_write_pending = False
_status_write_pending = False
_problems = []
_displaced_shortcuts = []
_pending_shortcut_conflicts = []
_last_workbench = ""
_task_accept_filter = None
_task_accept_targets = []
_deferred_tokens = {}
_usage_action_connections = 0
_adaptive_refresh_fingerprints = {}


def _record_problem(text):
    """Collect a runtime failure so Verify UI can report it instead of hiding it."""
    App.Console.PrintWarning("FMF: {}\n".format(text))
    if text not in _problems:
        _problems.append(text)
    schedule_status_write()


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
    token = _deferred_tokens.get(label, 0) + 1
    _deferred_tokens[label] = token
    remaining = {"attempts": attempts}

    def attempt():
        # Workbench changes can arrive in a burst (notably when entering or
        # leaving a sketch).  Only the newest request for a named UI task is
        # useful; allowing every older retry chain to continue repeats the
        # same main-window scans while FreeCAD is trying to redraw.
        if _deferred_tokens.get(label) != token:
            return
        remaining["attempts"] -= 1
        try:
            if function():
                _deferred_tokens.pop(label, None)
                return
        except Exception as error:
            _deferred_tokens.pop(label, None)
            _record_problem("{} failed: {}".format(label, error))
            return
        if remaining["attempts"] <= 0:
            _deferred_tokens.pop(label, None)
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
    """Keep the native UI anchors and bundled Ribbon paths valid.

    These are not user-facing preferences; they are paths the bundled add-on needs
    in order to find its own data, so they are re-asserted at every launch.
    """
    # FreeCAD anchors notification popups to a tray button in its status bar.
    # Leaving notifications enabled while that bar is hidden gives the anchor
    # stale geometry and can place popups over the middle of the model view.
    App.ParamGet("User parameter:BaseApp/Preferences/MainWindow").SetBool("StatusBar", True)
    Gui.getMainWindow().statusBar().show()

    ribbon = App.ParamGet("User parameter:BaseApp/Preferences/Mod/FreeCAD-Ribbon")
    ribbon_dir = os.path.join(App.getUserAppDataDir(), "RibbonUI_Data")
    ribbon.SetString("ConfigDir", ribbon_dir)
    ribbon.SetString("RibbonStructure", os.path.join(ribbon_dir, "RibbonStructure.json"))
    ribbon.SetString("BackupFolder", os.path.join(ribbon_dir, "Backups"))
    _refresh_search_catalog_cache()


def _refresh_search_catalog_cache():
    """Regenerate cached SearchBar records when FMF's catalog contract changes."""
    search = App.ParamGet("User parameter:BaseApp/Preferences/Mod/SearchBar")
    schema = 1
    if search.GetInt("FMFCatalogSchema", 0) == schema:
        return
    cache_path = os.path.join(App.getUserAppDataDir(), "Cache_SearchBarMod")
    try:
        os.remove(cache_path)
    except FileNotFoundError:
        pass
    except OSError as error:
        _record_problem("SearchBar catalog cache could not be refreshed: {}".format(error))
        return
    search.SetInt("FMFCatalogSchema", schema)


def _apply_defaults():
    """Write FMF's opinionated defaults over the user's profile."""
    if PREFERENCES.GetBool("SetStartWorkbench", True):
        App.ParamGet("User parameter:BaseApp/Preferences/General").SetString(
            "AutoloadModule", bootstrap.fmf_workbench_for("PartDesignWorkbench")
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
    # The Ribbon add-on injects its own global "Tools" panel of Std_ commands
    # into every workbench. FMF carries the same commands in its
    # UTILITIES section, which belongs to the layout and so can be ordered,
    # resized and reset; leaving both on gave every tab a duplicate panel that
    # sat outside the layout and could not be resized.
    ribbon.SetBool("UseToolsPanel", False)
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
    sketcher = App.ParamGet("User parameter:BaseApp/Preferences/Mod/Sketcher")
    sketcher.SetBool("MakeInternals", True)
    sketcher.SetBool("ShowCursorCoords", True)

    # Enable Fusion-style live in-canvas auto-constraints and On-View Parameters (OVP)
    sketcher_gen = App.ParamGet("User parameter:BaseApp/Preferences/Mod/Sketcher/General")
    sketcher_gen.SetBool("AutoConstraints", True)
    sketcher_gen.SetBool("AvoidRedundantAutoconstraints", True)
    sketcher_gen.SetBool("NotifyConstraintSubstitutions", True)

    sketcher_const = App.ParamGet("User parameter:BaseApp/Preferences/Mod/Sketcher/Constraints")
    sketcher_const.SetBool("UnifiedCoincident", True)
    sketcher_const.SetBool("AutoHorVer", True)

    sketcher_tools = App.ParamGet("User parameter:BaseApp/Preferences/Mod/Sketcher/Tools")
    sketcher_tools.SetInt("OnViewParameterVisibility", 1)

    # The upstream first-run changelog can cover Ribbon's modal cache prompt and
    # leave both windows impossible to operate. FMF provides its own
    # release notes, so keep the bundled SearchBar startup non-interactive.
    search = App.ParamGet("User parameter:BaseApp/Preferences/Mod/SearchBar")
    search.SetBool("ShowChangeDialog", False)
    search.SetString("DoNotShowAgain", "1.8")

    # Shortcuts are applied from the live QAction inventory.  Writing them here
    # would overwrite occupied bindings before the conflict preview can show
    # the user what is about to change.


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
    in FreeCAD's own preferences dialog. Reapply FMF (or `force`) is
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
        bootstrap.track_auto_created_document(document)
    Gui.activateWorkbench(bootstrap.fmf_workbench_for("PartDesignWorkbench"))
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
        child_added = _qt_enum(QtCore.QEvent, "Type", "ChildAdded")
        if event.type() == child_added:
            child = event.child() if hasattr(event, "child") else None
            if child is not None:
                _install_task_accept_target(child)
            return False
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


def _install_task_accept_target(target):
    """Watch one task-surface subtree without touching QApplication."""
    if target is None or target in _task_accept_targets:
        return
    if not hasattr(target, "installEventFilter"):
        return
    target.installEventFilter(_task_accept_filter)
    _task_accept_targets.append(target)
    widget_type = getattr(QtWidgets, "QWidget", None)
    if widget_type is not None and hasattr(target, "findChildren"):
        for child in target.findChildren(widget_type):
            _install_task_accept_target(child)


def install_task_accept_filter():
    global _task_accept_filter
    main_window = Gui.getMainWindow()
    if main_window is None:
        return False
    if _task_accept_filter is None:
        _task_accept_filter = _TaskAcceptFilter(main_window)

    widget_type = getattr(QtWidgets, "QWidget", None)
    if widget_type is None:
        return False
    task_surfaces = [
        widget
        for widget in main_window.findChildren(widget_type)
        if getattr(widget, "objectName", lambda: "")() in {"Tasks", "TaskView"}
        or getattr(widget, "windowTitle", lambda: "")().replace("&", "").strip().lower() == "tasks"
    ]
    for surface in task_surfaces:
        _install_task_accept_target(surface)
    # A task surface is created lazily. Startup is complete even when none is
    # present; edit-mode observers call this again after FreeCAD creates one.
    return True


# ---------------------------------------------------------------------------
# Adaptive panels
# ---------------------------------------------------------------------------


def load_manifest():
    global _manifest_cache
    if _manifest_cache is None:
        _manifest_cache = bootstrap.layout_manifest()
    return _manifest_cache


def adaptive_workbenches_by_command():
    """Return the cached reverse index used by command-usage tracking."""
    global _adaptive_command_workbenches_cache
    if _adaptive_command_workbenches_cache is None:
        reverse = {}
        for workbench in load_manifest().get("adaptivePins", {}):
            for _panel, group in adaptive_groups(workbench):
                for command in group.get("commands", {}):
                    reverse.setdefault(command, []).append(workbench)
        _adaptive_command_workbenches_cache = {
            command: tuple(workbenches) for command, workbenches in reverse.items()
        }
    return _adaptive_command_workbenches_cache


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
    workbenches = _usage_cache["workbenches"]
    if bootstrap.owned_workbenches_enabled():
        for legacy, owned in bootstrap.LEGACY_OWNED_WORKBENCH.items():
            if owned not in workbenches and legacy in workbenches:
                workbenches[owned] = workbenches.pop(legacy)
        for owned, native in bootstrap.OWNED_TO_NATIVE_WORKBENCH.items():
            if owned not in workbenches and native in workbenches:
                workbenches[owned] = workbenches.pop(native)
        for history in workbenches.values():
            if not isinstance(history, dict):
                continue
            migrated = {
                bootstrap._canonical_command_name(command): value
                for command, value in history.items()
            }
            history.clear()
            history.update(migrated)
        pins = _usage_cache.get("pins", {})
        for legacy, owned in bootstrap.LEGACY_OWNED_WORKBENCH.items():
            if owned not in pins and legacy in pins:
                pins[owned] = pins.pop(legacy)
        for workbench_pins in pins.values():
            migrated = {
                bootstrap._canonical_panel_name(name): value
                for name, value in workbench_pins.items()
            }
            workbench_pins.clear()
            workbench_pins.update(migrated)
            for record in workbench_pins.values():
                if isinstance(record, dict):
                    record["kept"] = [
                        bootstrap._canonical_command_name(command)
                        for command in record.get("kept", [])
                    ]
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
    if not bootstrap.is_enabled():
        return
    candidates = adaptive_workbenches_by_command().get(command, ())
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
    """The adaptive sections of a workbench, as (panel name, group) pairs."""
    config = load_manifest().get("adaptivePins", {}).get(workbench) or {}
    return list(config.get("panels", {}).items())


def group_is_whole(group):
    """Whether this group owns its whole section or only permutes its slots.

    A whole-panel group -- FREQUENT -- replaces the section's contents with
    whatever has risen to the top. A slot group leaves the section's command
    list alone and only decides which of two alternatives gets the prominent
    slot. A workbench can have both: Sketcher promotes within CREATE and
    MODIFY and keeps a FREQUENT section as well.
    """
    return bool(group.get("whole", False))


#: A FREQUENT section's shape: the first two slots are large, the rest small.
#: Taking each slot's size from the command promoted into it made the section
#: change shape as habits changed, moving buttons out from under the hand that
#: had learned where they were. It is also meaningless now that the candidates
#: are the whole ribbon: a command's declared size describes the section it
#: normally lives in, not this one.
WHOLE_PANEL_SLOT_SIZES = ("large", "large")


def _slot_size(index):
    if index < len(WHOLE_PANEL_SLOT_SIZES):
        return WHOLE_PANEL_SLOT_SIZES[index]
    return "small"


def _pin_record(workbench, panel_name):
    """Where a section remembers what the user put in it, and what we wrote."""
    return load_usage().setdefault("pins", {}).setdefault(workbench, {}).setdefault(panel_name, {})


def pinned_commands(workbench, panel_name):
    kept = _pin_record(workbench, panel_name).get("kept", [])
    return list(kept) if isinstance(kept, list) else []


def _panel_metadata(ribbon, workbench, panel_name, command):
    """Everything a slot needs to draw `command`, read from the live ribbon.

    A command dragged in from elsewhere arrives without the icon and label a
    candidate carries, but the section it was just dropped into knows all of
    it.
    """
    try:
        entry = ribbon["workbenches"][workbench]["toolbars"][panel_name]["commands"][command]
        sources = dict(ribbon["newPanels"][workbench][panel_name])
    except (KeyError, TypeError, ValueError):
        return None
    if command not in sources or not isinstance(entry, dict):
        return None
    return [
        sources[command],
        entry.get("size", "small"),
        entry.get("text", command),
        entry.get("icon", ""),
    ]


def reconcile_pins(workbench, panel_name, group, ribbon):
    """Learn what the user put into this section by hand, and keep it there.

    A FREQUENT section rewrites itself from what gets used, so a command
    dragged into it would be swept away again at the next workbench switch --
    which is what makes people conclude the section cannot be populated at
    all. Comparing what is in the panel now against what was last written
    identifies the commands the user placed there and the ones they threw out,
    so a deliberate choice outranks a measured habit.
    """
    record = _pin_record(workbench, panel_name)
    try:
        current = list(ribbon["workbenches"][workbench]["toolbars"][panel_name]["order"])
    except (KeyError, TypeError):
        return []
    written = record.get("written")
    if not isinstance(written, list):
        # Nothing has been written here yet, so what is in the section is what
        # was shipped rather than anything the user chose.
        record["written"] = current
        schedule_usage_write()
        return pinned_commands(workbench, panel_name)

    # A pinned command that is no longer there was taken out on purpose.
    kept = [command for command in pinned_commands(workbench, panel_name) if command in current]
    meta = record.get("meta")
    meta = dict(meta) if isinstance(meta, dict) else {}
    for command in current:
        if command in written or command in kept:
            continue
        if command not in group.get("commands", {}):
            details = _panel_metadata(ribbon, workbench, panel_name, command)
            if details is None:
                continue
            meta[command] = details
        kept.append(command)
    # The newest choice wins a contested slot; an older pin drops back to
    # competing on how much it gets used, like everything else.
    kept = kept[-int(group.get("capacity", 4)) :]
    record["kept"] = kept
    record["meta"] = {command: meta[command] for command in kept if command in meta}
    schedule_usage_write()
    return kept


def _adaptive_group_selection(workbench, config, pinned=()):
    now = _utc_now()
    usage = load_usage().get("workbenches", {}).get(workbench, {})
    defaults = config.get("defaults", [])
    default_rank = {command: index for index, command in enumerate(defaults)}

    def rank(command):
        measured = _decayed_score(usage.get(command, {}), now)
        baseline = PROMOTION_BASELINE if command in default_rank else 0.0
        return (max(measured, baseline), -default_rank.get(command, len(defaults)))

    capacity = int(config.get("capacity", 4))
    pinned = list(pinned)[:capacity]
    commands = [command for command in config.get("commands", {}) if command not in pinned]
    commands.sort(key=rank, reverse=True)
    return (pinned + commands)[:capacity]


def adaptive_selection(workbench):
    """What each adaptive section of `workbench` should hold, keyed by panel."""
    return {
        panel: _adaptive_group_selection(
            workbench,
            group,
            pinned_commands(workbench, panel) if group_is_whole(group) else (),
        )
        for panel, group in adaptive_groups(workbench)
    }


def _adaptive_refresh_fingerprint(workbench):
    """Describe the inputs that can change an adaptive ribbon projection."""
    stat = os.stat(RIBBON_PATH)
    selections = adaptive_selection(workbench)
    return (
        stat.st_mtime_ns,
        stat.st_size,
        tuple((panel, tuple(commands)) for panel, commands in sorted(selections.items())),
    )


def _rewrite_slots(ribbon, workbench, panel_name, group, promoted):
    """Permute adaptive candidates inside the slots they already occupy."""
    toolbar = ribbon["workbenches"][workbench]["toolbars"][panel_name]
    current_order = list(toolbar["order"])
    candidate_set = set(group.get("commands", {}))
    candidate_positions = [
        index for index, command in enumerate(current_order) if command in candidate_set
    ]
    reordered = promoted + [
        command for command in current_order if command in candidate_set and command not in promoted
    ]
    if not candidate_positions:
        # Responsive projections may replace an entire slot group with a
        # compound/dropdown command. The group is simply inapplicable there.
        return False
    if len(reordered) != len(candidate_positions):
        # Silently truncating here would drop a promoted command from the
        # panel; report the mismatch and leave this panel untouched instead.
        _record_problem(
            "adaptive panel {}/{} has {} candidates for {} slots".format(
                workbench, panel_name, len(reordered), len(candidate_positions)
            )
        )
        return False
    changed = False
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
            return False
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


def _rewrite_whole_panel(ribbon, workbench, panel_name, group, selected):
    """Replace a FREQUENT section's contents with the current selection."""
    toolbar = ribbon["workbenches"][workbench]["toolbars"][panel_name]
    metadata = dict(group.get("commands", {}))
    metadata.update(_pin_record(workbench, panel_name).get("meta", {}))
    selected = [command for command in selected if command in metadata]
    if not selected:
        return False
    sizes = [_slot_size(index) for index in range(len(selected))]
    already_shaped = all(
        toolbar.get("commands", {}).get(command, {}).get("size") == size
        for command, size in zip(selected, sizes, strict=True)
    )
    if toolbar.get("order") == selected and already_shaped:
        return False
    toolbar["order"] = list(selected)
    toolbar["panelMenu"] = list(selected)
    toolbar["overflow"] = []
    toolbar["pinCount"] = len(selected)
    toolbar["commands"] = {
        command: {
            "size": size,
            "text": metadata[command][2],
            "icon": metadata[command][3],
            "IsExtra": True,
        }
        for command, size in zip(selected, sizes, strict=True)
    }
    ribbon["newPanels"][workbench][panel_name] = [
        [command, metadata[command][0]] for command in selected
    ]
    _pin_record(workbench, panel_name)["written"] = list(selected)
    schedule_usage_write()
    return True


def refresh_adaptive_panel(workbench):
    groups = adaptive_groups(workbench)
    if not groups or not os.path.isfile(RIBBON_PATH):
        return False
    try:
        fingerprint = _adaptive_refresh_fingerprint(workbench)
        if _adaptive_refresh_fingerprints.get(workbench) == fingerprint:
            return False
        with open(RIBBON_PATH, encoding="utf-8") as stream:
            ribbon = json.load(stream)
        changed = False
        for panel_name, group in groups:
            whole = group_is_whole(group)
            pinned = ()
            if whole:
                # Reconcile first: a command the user dragged in is a stronger
                # statement than anything the counters have to say.
                pinned = reconcile_pins(workbench, panel_name, group, ribbon)
            promoted = _adaptive_group_selection(workbench, group, pinned)
            if not promoted:
                continue
            if whole:
                rewritten = _rewrite_whole_panel(ribbon, workbench, panel_name, group, promoted)
            else:
                rewritten = _rewrite_slots(ribbon, workbench, panel_name, group, promoted)
            changed = rewritten or changed
        if not changed:
            _adaptive_refresh_fingerprints[workbench] = _adaptive_refresh_fingerprint(workbench)
            return False
        temporary = RIBBON_PATH + ".tmp"
        with open(temporary, "w", encoding="utf-8") as stream:
            json.dump(ribbon, stream, indent=2)
        os.replace(temporary, RIBBON_PATH)
        # Keep the recorded digest current so a future mismatch means a genuine
        # edit from outside the add-on rather than our own adaptive rewrite.
        bootstrap.update_ribbon_hash()
        _adaptive_refresh_fingerprints[workbench] = _adaptive_refresh_fingerprint(workbench)
        # Housekeeping, not something the user acts on -- keep it in the log only.
        App.Console.PrintLog(
            "FMF updated FREQUENT for {}; it appears on the next ribbon reload.\n".format(workbench)
        )
        return True
    except (OSError, KeyError, TypeError, ValueError) as error:
        _record_problem("adaptive pins were not updated: {}".format(error))
        return False


# ---------------------------------------------------------------------------
# Shortcuts
# ---------------------------------------------------------------------------


def reconcile_actions(main_window=None):
    """Connect usage tracking and apply only an approved shortcut plan."""
    global _pending_shortcut_conflicts, _usage_action_connections
    explicit_window = main_window is not None
    main_window = main_window if main_window is not None else Gui.getMainWindow()
    if main_window is None:
        return False
    # One pass. Asking every action for its shortcut once per shortcut we set
    # meant thirteen sweeps of a tree with thousands of actions in it, twice
    # per sketch -- entering an edit activates Sketcher and leaving activates
    # PartDesign again -- and all of it on the thread that draws the window.
    registry = bootstrap.native_action_registry()
    actions = registry.inventory(force=explicit_window)
    try:
        by_name = _action_map(actions)
    except RuntimeError:
        # Ribbon rebuilds can delete QAction wrappers without changing FreeCAD's
        # command registry. Refresh only when a cached wrapper proves stale.
        actions = registry.inventory(force=True)
        by_name = _action_map(actions)
    adaptive_commands = {
        command
        for workbench in load_manifest().get("adaptivePins", {})
        for _panel, config in adaptive_groups(workbench)
        for command in config.get("commands", {})
    }
    for command in adaptive_commands:
        connected = registry.connect_triggered(
            command,
            "runtime",
            lambda checked=False, name=command: record_usage(name),
        )
        _usage_action_connections += int(connected)

    if not PREFERENCES.GetBool("SetShortcuts", True):
        restore_shortcuts(main_window)
        return True

    plan = _shortcut_plan(actions)
    _pending_shortcut_conflicts = [_conflict_dict(item) for item in plan.conflicts]
    if plan.conflicts and PREFERENCES.GetString("ShortcutPresetApproval", "") != (
        _shortcut_plan_fingerprint(plan)
    ):
        App.Console.PrintMessage(
            "FMF found {} occupied shortcut{}; use Review FMF Shortcuts to preview them. "
            "No shortcuts were changed.\n".format(
                len(plan.conflicts), "" if len(plan.conflicts) == 1 else "s"
            )
        )
        schedule_status_write()
        return True
    _apply_shortcut_plan(plan, by_name)
    return True


def _shortcut_plan(actions):
    records = [
        {
            "id": _action_locator(action),
            "name": action.text() or action.objectName() or "(unnamed action)",
            "shortcut": _portable(action.shortcut().toString()),
        }
        for action in actions
    ]
    desired = {command: _portable(sequence) for command, sequence in SHORTCUTS.items()}
    return plan_shortcuts(desired, records)


def _action_locator(action):
    """Return a restorable identity for native and unnamed Qt actions."""
    name = action.objectName()
    if name:
        return name
    text = action.text() or "(unnamed action)"
    return "@text:" + text


def _action_map(actions):
    """Index actions by command ID and by the label fallback used in plans."""
    result = {}
    for action in actions:
        result.setdefault(_action_locator(action), action)
    return result


def _conflict_dict(conflict):
    return {
        "sequence": conflict.sequence,
        "from": conflict.owner_id or conflict.owner_name,
        "to": conflict.target_id,
    }


def _shortcut_plan_fingerprint(plan):
    payload = {
        "assignments": sorted(plan.assignments.items()),
        "conflicts": [(item.sequence, item.owner_id, item.target_id) for item in plan.conflicts],
    }
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def _apply_shortcut_plan(plan, by_name=None):
    """Apply one accepted plan and persist its exact pre-change bindings."""
    global _displaced_shortcuts, _pending_shortcut_conflicts
    if by_name is None:
        by_name = _action_map(bootstrap.native_action_registry().inventory())
    encoded_prior = PREFERENCES.GetString("ShortcutPriorState", "")
    try:
        saved_prior = json.loads(encoded_prior) if encoded_prior else {}
    except (TypeError, ValueError):
        _record_problem("shortcut restore state was invalid and was rebuilt")
        saved_prior = {}
    for locator, shortcut in plan.prior.items():
        saved_prior.setdefault(locator, shortcut)
    PREFERENCES.SetString("ShortcutPriorState", json.dumps(saved_prior, sort_keys=True))
    shortcut_group = App.ParamGet("User parameter:BaseApp/Preferences/Shortcut")
    displaced = []
    for conflict in plan.conflicts:
        owner = by_name.get(conflict.owner_id)
        if owner is not None:
            owner.setShortcut(QtGui.QKeySequence())
        if not conflict.owner_id.startswith("@text:"):
            shortcut_group.SetString(conflict.owner_id, "")
        displaced.append(_conflict_dict(conflict))
    context = _application_shortcut_context()
    for command, shortcut in plan.assignments.items():
        target = by_name.get(command)
        if target is None:
            continue
        target.setShortcut(QtGui.QKeySequence(shortcut))
        target.setShortcutContext(context)
        shortcut_group.SetString(command, shortcut)
    _displaced_shortcuts = displaced
    _pending_shortcut_conflicts = []
    App.saveParameter()
    schedule_status_write()
    return True


def restore_shortcuts(main_window=None):
    """Restore the exact live bindings captured before preset acceptance."""
    global _displaced_shortcuts, _pending_shortcut_conflicts
    encoded = PREFERENCES.GetString("ShortcutPriorState", "")
    if not encoded:
        return False
    try:
        prior = json.loads(encoded)
    except (TypeError, ValueError):
        _record_problem("shortcut restore state is invalid")
        return False
    actions = bootstrap.native_action_registry().inventory(force=True)
    by_name = _action_map(actions)
    shortcut_group = App.ParamGet("User parameter:BaseApp/Preferences/Shortcut")
    for command, shortcut in prior.items():
        action = by_name.get(command)
        if action is not None:
            action.setShortcut(QtGui.QKeySequence(shortcut))
        if not command.startswith("@text:"):
            shortcut_group.SetString(command, shortcut)
    PREFERENCES.RemString("ShortcutPriorState")
    PREFERENCES.RemString("ShortcutPresetApproval")
    _displaced_shortcuts = []
    _pending_shortcut_conflicts = []
    App.saveParameter()
    schedule_status_write()
    return True


def review_shortcuts(confirm=None, main_window=None):
    """Preview conflicts and apply only after an explicit confirmation."""
    main_window = main_window if main_window is not None else Gui.getMainWindow()
    actions = bootstrap.native_action_registry().inventory(force=True)
    plan = _shortcut_plan(actions)
    lines = [
        "{}: {} → {}".format(item.sequence, item.owner_name, item.target_id)
        for item in plan.conflicts
    ]
    if confirm is None:
        text = "Apply the complete FMF shortcut preset?"
        if lines:
            text += "\n\nThese occupied bindings will move:\n" + "\n".join(lines)
        else:
            text += "\n\nNo occupied bindings were found."
        answer = QtWidgets.QMessageBox.question(main_window, "Review FMF Shortcuts", text)
        accepted = answer == QtWidgets.QMessageBox.Yes
    else:
        accepted = bool(confirm(lines))
    if not accepted:
        return False
    by_name = _action_map(actions)
    applied = _apply_shortcut_plan(plan, by_name)
    if applied:
        PREFERENCES.SetString("ShortcutPresetApproval", _shortcut_plan_fingerprint(plan))
        App.saveParameter()
    return applied


# ---------------------------------------------------------------------------
# Status reporting
# ---------------------------------------------------------------------------


def write_runtime_status(active_workbench=None):
    global _status_write_pending
    _status_write_pending = False
    active_workbench = _last_workbench if active_workbench is None else active_workbench
    try:
        manifest = load_manifest()
        expected = manifest.get("primaryCommands", [])
        available = bootstrap.native_action_registry().available(expected)
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
            "services": runtime_service_state(),
            "problems": list(_problems),
        }
        with open(STATUS_PATH + ".tmp", "w", encoding="utf-8") as stream:
            json.dump(status, stream, indent=2)
        os.replace(STATUS_PATH + ".tmp", STATUS_PATH)
        return True
    except Exception as error:
        App.Console.PrintWarning("FMF status check failed: {}\n".format(error))
        return False


def schedule_status_write(delay=750):
    """Coalesce status writes so a burst of workbench switches writes once."""
    global _status_write_pending
    if _status_write_pending:
        return
    _status_write_pending = True
    QtCore.QTimer.singleShot(delay, write_runtime_status)


def runtime_service_state(main_window=None, deep=False):
    """Return observable ownership state for every long-lived runtime service."""
    main_window = main_window if main_window is not None else Gui.getMainWindow()
    usage_connections = _usage_action_connections
    action_registry = bootstrap.native_action_registry().snapshot()
    if deep:
        usage_connections = action_registry["triggerConnections"]
    return {
        "workbenchSignalConnected": "runtime" in _transition_snapshot()["phases"],
        "transitionCoordinator": _transition_snapshot(),
        "taskAcceptFilterInstalled": _task_accept_filter is not None,
        "usageActionConnections": usage_connections,
        "ribbonActionBindings": bootstrap.ribbon_action_binding_count(),
        "actionRegistry": action_registry,
        "pendingDeferredTasks": sorted(_deferred_tokens),
        "problemCount": len(_problems),
        "displacedShortcutCount": len(_displaced_shortcuts),
        "pendingShortcutConflictCount": len(_pending_shortcut_conflicts),
    }


def _record_lifecycle_event(operation, outcome, **details):
    """Report runtime ownership changes without making lifecycle depend on logging."""
    try:
        import fmf_common as diagnostics

        diagnostics.event("info", "runtime", operation, outcome, **details)
    except Exception as error:
        App.Console.PrintLog("FMF: runtime diagnostic event failed: {}\n".format(error))


def _record_teardown_problem(service, error):
    """Surface cleanup failures without scheduling new runtime work during teardown."""
    text = "could not detach {}: {}".format(service, error)
    App.Console.PrintWarning("FMF: {}\n".format(text))
    if text not in _problems:
        _problems.append(text)
    _record_lifecycle_event("uninstall", "degraded", service=service, error=str(error))


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------


def after_workbench_activation(name):
    global _last_workbench
    if not bootstrap.is_enabled():
        return
    _last_workbench = name
    bootstrap.defer_ui_mode_sync()
    _run("adaptive pins", lambda: refresh_adaptive_panel(name))
    # Deferred, not immediate. Entering and leaving a sketch each activate a
    # workbench, so anything done here is done on the way in and on the way
    # out, while the window is frozen waiting for it.
    _defer("shortcut reconciliation", reconcile_actions)
    _defer("navigation cube", ensure_navigation_cube)
    _defer("model tree", ensure_model_tree)
    schedule_status_write()


def _transition_snapshot():
    try:
        import fmf_transitions

        return fmf_transitions.snapshot()
    except (ImportError, AttributeError):
        return {"connected": False, "phases": []}


def install():
    """Wire the runtime into the running FreeCAD session."""
    _run("preferences", apply_preferences)
    main_window = Gui.getMainWindow()
    import fmf_transitions

    fmf_transitions.register_phase("runtime", after_workbench_activation, order=30)
    _defer("starter design", ensure_starter_design)
    _defer("model tree", ensure_model_tree)
    _defer("navigation cube", ensure_navigation_cube)
    _defer("shortcut reconciliation", reconcile_actions)
    _defer("Enter-to-OK task handling", install_task_accept_filter)
    schedule_status_write(1500)
    App.Console.PrintMessage(
        "FMF {}: adaptive ribbon, smart dimensions, navigation cube, "
        "and shortcuts configured.\n".format(bootstrap.PACKAGE_VERSION)
    )
    _record_lifecycle_event("install", "installed", services=runtime_service_state(main_window))


def uninstall():
    """Disconnect live services so disabling FMF takes effect before restart."""
    global _task_accept_filter
    _deferred_tokens.clear()
    bootstrap.native_action_registry().disconnect_owner("runtime")
    main_window = Gui.getMainWindow()
    try:
        import fmf_transitions

        fmf_transitions.unregister_phase("runtime", after_workbench_activation)
    except Exception as error:
        _record_teardown_problem("workbench transition phase", error)
    if _task_accept_filter is not None:
        for target in tuple(_task_accept_targets):
            try:
                target.removeEventFilter(_task_accept_filter)
            except (AttributeError, RuntimeError) as error:
                _record_teardown_problem("task accept event filter", error)
        _task_accept_targets.clear()
        _task_accept_filter = None
    _record_lifecycle_event("uninstall", "uninstalled", services=runtime_service_state(main_window))


# Tests import this module for its logic and drive `install()` themselves.
if not os.environ.get("FMF_MY_FREECAD_NO_AUTOSTART"):
    install()
