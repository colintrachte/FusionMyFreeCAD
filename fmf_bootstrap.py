"""Cross-platform installation, verification, restoration, and vendor loading."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import sys
import time
import traceback
import xml.etree.ElementTree as ET
from datetime import UTC, datetime

import FreeCAD as App
import FreeCADGui as Gui

from fmf_actions import CanonicalActionRegistry, NativeActionAdapter, RibbonActionBindingRegistry

ADDON_ROOT = os.path.dirname(os.path.abspath(__file__))
RESOURCE_ROOT = os.path.join(ADDON_ROOT, "Resources", "FMF")
PACKAGE_PATH = os.path.join(ADDON_ROOT, "package.xml")
BASE_LAYOUT = os.path.join(RESOURCE_ROOT, "RibbonStructure.json")
LAYOUT_SPEC = os.path.join(RESOURCE_ROOT, "layout-v3.json")
MANIFEST = os.path.join(RESOURCE_ROOT, "layout-manifest.json")
RUNTIME = os.path.join(RESOURCE_ROOT, "runtime.py")
PREFERENCES_UI = os.path.join(RESOURCE_ROOT, "preferences.ui")
USER_ROOT = App.getUserAppDataDir()
RIBBON_DIR = os.path.join(USER_ROOT, "RibbonUI_Data")
RIBBON_PATH = os.path.join(RIBBON_DIR, "RibbonStructure.json")
STATE_PATH = os.path.join(USER_ROOT, "FMF-addon-state.json")
STARTUP_PATH = os.path.join(USER_ROOT, "FMF-startup.json")
STATUS_PATH = os.path.join(USER_ROOT, "FMF-runtime-status.json")
USAGE_PATH = os.path.join(USER_ROOT, "FMF-usage.json")
CUSTOMIZATION_PATH = os.path.join(USER_ROOT, "FMF-customization.json")
BACKUP_ROOT = os.path.join(USER_ROOT, "FMF-Backups")
# The baseline records the profile as it was before FMF first ran.
# It is written once and never rewritten, so a lost or corrupted state file can
# never cause FMF's own settings to be captured as the "previous UI".
BASELINE_PATH = os.path.join(BACKUP_ROOT, "baseline.json")
PREFERENCE_ROOT = "User parameter:BaseApp/Preferences/Mod/FMF"
WORKBENCH_PREFERENCE_ROOT = "User parameter:BaseApp/Preferences/Workbenches"
ADDON_MANAGER_STOP_FILE = os.path.join(ADDON_ROOT, "ADDON_DISABLED")

# Keep upgrade-only names assembled from fragments so the retired brand cannot
# accidentally become a new public identifier. Existing installations still
# need their immutable restore baseline and preferences carried forward.
_PREVIOUS_PRODUCT_NAME = "Fusion" + "MyFreeCAD"
_PREVIOUS_PREFERENCE_ROOT = "User parameter:BaseApp/Preferences/Mod/" + _PREVIOUS_PRODUCT_NAME
_PREVIOUS_FILE_PATHS = {
    STATE_PATH: os.path.join(USER_ROOT, _PREVIOUS_PRODUCT_NAME + "-addon-state.json"),
    STARTUP_PATH: os.path.join(USER_ROOT, _PREVIOUS_PRODUCT_NAME + "-startup.json"),
    STATUS_PATH: os.path.join(USER_ROOT, _PREVIOUS_PRODUCT_NAME + "-runtime-status.json"),
    USAGE_PATH: os.path.join(USER_ROOT, _PREVIOUS_PRODUCT_NAME + "-usage.json"),
    CUSTOMIZATION_PATH: os.path.join(USER_ROOT, _PREVIOUS_PRODUCT_NAME + "-customization.json"),
}
_PREVIOUS_BACKUP_ROOT = os.path.join(USER_ROOT, _PREVIOUS_PRODUCT_NAME + "-Backups")
_PREVIOUS_BASELINE_PATH = os.path.join(_PREVIOUS_BACKUP_ROOT, "baseline.json")

STATE_SCHEMA = 2

OWNED_TO_NATIVE_WORKBENCH = {
    "FMFDesignWorkbench": "PartDesignWorkbench",
    "FMFPartWorkbench": "PartWorkbench",
    "FMFSketchWorkbench": "SketcherWorkbench",
    "FMFSurfaceWorkbench": "SurfaceWorkbench",
}
NATIVE_TO_OWNED_WORKBENCH = {native: owned for owned, native in OWNED_TO_NATIVE_WORKBENCH.items()}
RIBBON_CACHE_WORKBENCHES_ENV = "FREECAD_RIBBON_CACHE_WORKBENCHES"
LEGACY_OWNED_WORKBENCH = {
    "FusionDesignWorkbench": "FMFDesignWorkbench",
    "FusionPartWorkbench": "FMFPartWorkbench",
    "FusionSketchWorkbench": "FMFSketchWorkbench",
    "FusionSurfaceWorkbench": "FMFSurfaceWorkbench",
}


def _read_package_version():
    try:
        root = ET.parse(PACKAGE_PATH).getroot()
        for child in root:
            if child.tag.endswith("version") and child.text:
                return child.text.strip()
    except (OSError, ET.ParseError):
        pass
    return "0.0.0"


# package.xml is the single source of truth for the release version.
PACKAGE_VERSION = _read_package_version()


_ribbon_action_bindings = None
_native_action_registry = None
_native_toolbar_visibility = None
_addon_directory_watcher = None
_addon_recovery_started = False
_quit_hooked = False


def native_action_registry():
    """Return the one native-action registry shared by every FMF service."""
    global _native_action_registry
    if _native_action_registry is None:
        from PySide.QtGui import QAction

        _native_action_registry = CanonicalActionRegistry(Gui, QAction)
        import fmf_transitions

        fmf_transitions.register_phase(
            "action-registry", _native_action_registry.advance_generation, order=15
        )
    return _native_action_registry


def _action_bindings():
    """Return the process-wide registry used by the bundled ribbon renderer."""
    global _ribbon_action_bindings
    if _ribbon_action_bindings is None:
        from PySide.QtGui import QAction

        adapter = NativeActionAdapter(Gui, QAction, native_action_registry())
        _ribbon_action_bindings = RibbonActionBindingRegistry(adapter)
    return _ribbon_action_bindings


def bind_ribbon_button(command_id, button):
    """Mirror native action state onto an FMF ribbon button."""
    if not is_enabled():
        return False
    try:
        registry = native_action_registry()
        if registry.resolve(command_id, allow_scan=False) is None:
            default_action = (
                button.defaultAction() if hasattr(button, "defaultAction") else None
            )
            if default_action is not None:
                registry._remember(command_id, default_action)
    except Exception:
        pass
    return _action_bindings().bind(command_id, button)


def dispose_ribbon_action_bindings():
    """Disconnect every ribbon/action callback owned by FMF."""
    global _ribbon_action_bindings
    if _ribbon_action_bindings is not None:
        _ribbon_action_bindings.dispose()
        _ribbon_action_bindings = None


def dispose_native_action_registry():
    """Detach registry-owned usage callbacks and discard cached Qt wrappers."""
    global _native_action_registry
    if _native_action_registry is not None:
        try:
            import fmf_transitions

            fmf_transitions.unregister_phase(
                "action-registry", _native_action_registry.advance_generation
            )
        except (ImportError, AttributeError):
            pass
        _native_action_registry.dispose()
        _native_action_registry = None


def ribbon_action_binding_count():
    if _ribbon_action_bindings is None:
        return 0
    return _ribbon_action_bindings.count()


def capture_native_toolbar_visibility():
    """Remember this session's native toolbar visibility before Ribbon hides it."""
    global _native_toolbar_visibility
    if _native_toolbar_visibility is not None:
        return dict(_native_toolbar_visibility)
    from PySide import QtWidgets

    snapshot = {}
    for toolbar in Gui.getMainWindow().findChildren(QtWidgets.QToolBar):
        name = toolbar.objectName() if hasattr(toolbar, "objectName") else ""
        if name and name not in {"SearchBar", "SearchBarAtMouse"}:
            snapshot[name] = bool(toolbar.isVisible())
    _native_toolbar_visibility = snapshot
    return dict(snapshot)


def restore_native_toolbar_visibility():
    """Restore only toolbar visibility captured before FMF changed the chrome."""
    if _native_toolbar_visibility is None:
        return False
    from PySide import QtWidgets

    for toolbar in Gui.getMainWindow().findChildren(QtWidgets.QToolBar):
        name = toolbar.objectName() if hasattr(toolbar, "objectName") else ""
        if name in _native_toolbar_visibility:
            toolbar.setVisible(_native_toolbar_visibility[name])
    return True


def addon_disabled_by_manager():
    return os.path.isfile(ADDON_MANAGER_STOP_FILE)


def _on_about_to_quit():
    """Prevent Qt from persisting FMF's intentionally hidden native toolbars."""
    restore_native_toolbar_visibility()
    dispose_ribbon_action_bindings()
    dispose_native_action_registry()
    _set_searchbar_service(False)
    uninstall_activation_monitor()


def _on_addon_directory_changed(_path=""):
    """Restore usable native chrome when Addon Manager disables or removes FMF."""
    global _addon_recovery_started
    if os.path.isdir(ADDON_ROOT) and not addon_disabled_by_manager():
        return
    if _addon_recovery_started:
        return
    _addon_recovery_started = True
    try:
        disable()
        restore_native_toolbar_visibility()
        _restore_native_ui_now()
    except Exception as error:
        record_startup_failure("Addon Manager disable", error)


def install_lifecycle_guards():
    """Install one stop-file watcher and one shutdown persistence hook."""
    global _addon_directory_watcher, _quit_hooked
    from PySide import QtCore, QtWidgets

    if _addon_directory_watcher is None and os.path.isdir(ADDON_ROOT):
        watcher_type = getattr(QtCore, "QFileSystemWatcher", None)
        if watcher_type is not None:
            watcher = watcher_type()
            if watcher.addPath(ADDON_ROOT):
                watcher.directoryChanged.connect(_on_addon_directory_changed)
                _addon_directory_watcher = watcher
    if not _quit_hooked:
        application = QtWidgets.QApplication.instance()
        signal = getattr(application, "aboutToQuit", None)
        if signal is not None:
            signal.connect(_on_about_to_quit)
            _quit_hooked = True


STATUS_BAR_PREFERENCE = (
    "User parameter:BaseApp/Preferences/MainWindow",
    "StatusBar",
    "Bool",
)


PREFERENCE_KEYS = (
    STATUS_BAR_PREFERENCE,
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
    ("User parameter:BaseApp/Preferences/Mod/FreeCAD-Ribbon", "UseToolsPanel", "Bool"),
    ("User parameter:BaseApp/Preferences/Mod/FreeCAD-Ribbon", "Link_IconSizes", "Bool"),
    ("User parameter:BaseApp/Preferences/Mod/FreeCAD-Ribbon", "IconSize_Small", "Int"),
    ("User parameter:BaseApp/Preferences/Mod/FreeCAD-Ribbon", "IconSize_Medium", "Int"),
    ("User parameter:BaseApp/Preferences/Mod/FreeCAD-Ribbon", "IconSize_Large", "Int"),
    (
        "User parameter:BaseApp/Preferences/Mod/Sketcher/dimensioning",
        "SingleDimensioningTool",
        "Bool",
    ),
    (
        "User parameter:BaseApp/Preferences/Mod/Sketcher/dimensioning",
        "SeparatedDimensioningTools",
        "Bool",
    ),
    (
        "User parameter:BaseApp/Preferences/Mod/Sketcher/dimensioning",
        "DimensioningDiameter",
        "Bool",
    ),
    ("User parameter:BaseApp/Preferences/Mod/Sketcher/dimensioning", "DimensioningRadius", "Bool"),
    ("User parameter:BaseApp/Preferences/Mod/Sketcher", "MakeInternals", "Bool"),
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
    return datetime.now(UTC).astimezone().isoformat()


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
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def _retire_previous_brand_installations():
    """Neutralize co-installed 1.8.0 add-on folders so they cannot clobber FMF."""
    import types

    legacy_mod_name = "fu" + "sion_bootstrap"
    if legacy_mod_name not in sys.modules:
        shim = types.ModuleType(legacy_mod_name)
        shim.start = lambda *args, **kwargs: None
        shim.prepare = lambda *args, **kwargs: "retired"
        shim.enable = lambda *args, **kwargs: "retired"
        shim.disable = lambda *args, **kwargs: ("retired", [])
        shim.verify = lambda *args, **kwargs: (True, {}, [])
        sys.modules[legacy_mod_name] = shim

    norm_addon = os.path.normpath(ADDON_ROOT)
    if os.path.basename(norm_addon) != "FMF":
        return
    mod_dir = os.path.dirname(norm_addon)
    if os.path.basename(mod_dir) != "Mod" or not os.path.isdir(mod_dir):
        return

    legacy_prefix = ("fu" + "sion_").lower()
    candidates = []
    legacy_folder = os.path.join(mod_dir, _PREVIOUS_PRODUCT_NAME)
    if os.path.exists(legacy_folder):
        candidates.append(legacy_folder)
    try:
        for entry in os.listdir(mod_dir):
            lower = entry.lower()
            if lower.startswith(legacy_prefix) and lower.endswith(".py"):
                candidates.append(os.path.join(mod_dir, entry))
    except OSError:
        pass

    if not candidates:
        return
    quarantine_dir = os.path.join(BACKUP_ROOT, "retired-mod-" + _timestamp())
    try:
        os.makedirs(quarantine_dir, exist_ok=True)
        for path in candidates:
            target = os.path.join(quarantine_dir, os.path.basename(path))
            if not os.path.exists(target):
                shutil.move(path, target)
    except OSError:
        pass


def _migrate_previous_brand_data():
    """Carry forward user state written under the previous product name.

    New FMF data always wins. The previous files remain untouched when both
    names exist, and an immutable baseline is copied only when FMF has none.
    """
    _retire_previous_brand_installations()
    for current, previous in _PREVIOUS_FILE_PATHS.items():
        if not os.path.exists(current) and os.path.isfile(previous):
            os.makedirs(os.path.dirname(current), exist_ok=True)
            shutil.copy2(previous, current)

    if not os.path.isfile(BASELINE_PATH) and os.path.isfile(_PREVIOUS_BASELINE_PATH):
        os.makedirs(BACKUP_ROOT, exist_ok=True)
        shutil.copy2(_PREVIOUS_BASELINE_PATH, BASELINE_PATH)

    previous_preferences = App.ParamGet(_PREVIOUS_PREFERENCE_ROOT)
    current_preferences = App.ParamGet(PREFERENCE_ROOT)
    for kind in ("String", "Bool", "Int", "Float", "Unsigned"):
        get_names = getattr(previous_preferences, "Get{}s".format(kind), None)
        get_value = getattr(previous_preferences, "Get{}".format(kind), None)
        set_value = getattr(current_preferences, "Set{}".format(kind), None)
        current_names = getattr(current_preferences, "Get{}s".format(kind), None)
        if not all((get_names, get_value, set_value, current_names)):
            continue
        existing = set(current_names())
        for name in get_names():
            if name not in existing:
                set_value(name, get_value(name))


def _layout_spec():
    """Return the owned-workbench layout or its temporary legacy projection."""
    spec = _load_json(LAYOUT_SPEC)
    if owned_workbenches_enabled():
        return spec
    spec["workbenches"] = {
        OWNED_TO_NATIVE_WORKBENCH.get(workbench, workbench): panels
        for workbench, panels in spec["workbenches"].items()
    }
    return spec


def _layout_manifest():
    """Keep adaptive and order metadata on the same identity set as the layout."""
    manifest = _load_json(MANIFEST)
    if owned_workbenches_enabled():
        return manifest
    for key in ("workbenchPanelOrder", "adaptivePins"):
        manifest[key] = {
            OWNED_TO_NATIVE_WORKBENCH.get(workbench, workbench): value
            for workbench, value in manifest.get(key, {}).items()
        }
    return manifest


def layout_spec():
    """Return layout data for the currently selected workbench identity mode."""
    return _layout_spec()


def layout_manifest():
    """Return manifest data for the currently selected workbench identity mode."""
    return _layout_manifest()


def _load_json_or_quarantine(path):
    """Read machine-local JSON, moving an unreadable file aside instead of raising.

    Startup must not fail because a state file was truncated by a crash or a
    half-finished profile copy. The recovery commands are worth more than the file.
    """
    if not os.path.isfile(path):
        return None
    try:
        return _load_json(path)
    except (OSError, ValueError) as error:
        quarantine = "{}.corrupt-{}".format(path, _timestamp())
        try:
            os.replace(path, quarantine)
        except OSError:
            quarantine = "(could not be moved aside)"
        App.Console.PrintWarning(
            "FMF could not read {}: {}. Moved to {}.\n".format(path, error, quarantine)
        )
        return None


# ---------------------------------------------------------------------------
# Startup problem reporting
# ---------------------------------------------------------------------------


def record_startup_failure(step, error):
    """Persist a startup failure so Verify UI can explain a partial installation."""
    try:
        report = _load_json_or_quarantine(STARTUP_PATH)
        failures = report.get("failures", []) if isinstance(report, dict) else []
        failures.append(
            {
                "step": step,
                "error": str(error),
                "traceback": traceback.format_exc(),
                "at": _now(),
                "packageVersion": PACKAGE_VERSION,
            }
        )
        _atomic_json(STARTUP_PATH, {"failures": failures[-20:], "updatedAt": _now()})
    except OSError:
        pass


def startup_failures():
    report = _load_json_or_quarantine(STARTUP_PATH)
    failures = report.get("failures", []) if isinstance(report, dict) else []
    return [entry for entry in failures if entry.get("packageVersion") == PACKAGE_VERSION]


def clear_startup_failures():
    try:
        if os.path.isfile(STARTUP_PATH):
            os.remove(STARTUP_PATH)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Preference capture and restoration
# ---------------------------------------------------------------------------


def _capture_preference(key):
    path, name, kind = key
    group = App.ParamGet(path)
    names = getattr(group, "Get{}s".format(kind))()
    return {
        "path": path,
        "name": name,
        "kind": kind,
        "existed": name in names,
        "value": getattr(group, "Get{}".format(kind))(name),
    }


def _capture_preferences():
    captured = []
    for key in PREFERENCE_KEYS:
        captured.append(_capture_preference(key))
    return captured


def _restore_preferences(entries):
    problems = []
    for entry in entries:
        try:
            group = App.ParamGet(entry["path"])
            method = "Set{}" if entry["existed"] else "Rem{}"
            function = getattr(group, method.format(entry["kind"]))
            if entry["existed"]:
                function(entry["name"], entry["value"])
            else:
                function(entry["name"])
        except (AttributeError, KeyError, TypeError) as error:
            # One unrestorable key must not abandon the remaining ones.
            problems.append("{}/{}: {}".format(entry.get("path"), entry.get("name"), error))
    App.saveParameter()
    return problems


def restore_preference_keys(keys):
    """Restore selected managed preferences from the immutable baseline.

    The preferences page exposes opt-outs for a few groups of defaults.  When a
    user disables one and explicitly reapplies the add-on, merely skipping the
    corresponding writes leaves the old FMF values in place.  This
    helper makes those opt-outs reversible without restoring unrelated settings.
    """
    baseline = _read_baseline()
    if baseline is None:
        return ["Original preference baseline is unavailable."]
    wanted = set(keys)
    entries = [
        entry
        for entry in baseline.get("preferences", [])
        if (entry.get("path"), entry.get("name")) in wanted
    ]
    present = {(entry.get("path"), entry.get("name")) for entry in entries}
    missing = sorted(wanted - present)
    problems = ["Baseline has no entry for {}/{}.".format(*key) for key in missing]
    problems.extend(_restore_preferences(entries))
    return problems


# ---------------------------------------------------------------------------
# Layout generation and verification
# ---------------------------------------------------------------------------


def _panel_entries(panel):
    """Return the complete panel inventory: pinned commands, then overflow."""
    return list(panel["commands"]) + list(panel.get("overflow", []))


def _read_customization():
    customization = _load_json_or_quarantine(CUSTOMIZATION_PATH)
    if not isinstance(customization, dict) or customization.get("schemaVersion") != 1:
        return {}
    workbenches = customization.get("workbenches")
    if not isinstance(workbenches, dict):
        return {}
    for legacy, canonical in LEGACY_OWNED_WORKBENCH.items():
        if canonical not in workbenches and legacy in workbenches:
            workbenches[canonical] = workbenches.pop(legacy)
    for saved_workbench in workbenches.values():
        panels = saved_workbench.get("panels", {})
        migrated_panels = {}
        for name, value in panels.items():
            if isinstance(value, dict):
                value["order"] = [
                    _canonical_command_name(command) for command in value.get("order", [])
                ]
                value["pinned"] = [
                    _canonical_command_name(command) for command in value.get("pinned", [])
                ]
            migrated_panels[_canonical_panel_name(name)] = value
        saved_workbench["panels"] = migrated_panels
        saved_workbench["panelOrder"] = [
            _canonical_panel_name(name) for name in saved_workbench.get("panelOrder", [])
        ]
    return customization


def _canonical_panel_name(name):
    if isinstance(name, str) and name.startswith("Fusion ") and name.endswith("_newPanel"):
        return "FMF " + name[len("Fusion ") :]
    return name


def _canonical_command_name(name):
    if not isinstance(name, str):
        return name
    previous_product_prefix = _PREVIOUS_PRODUCT_NAME + "_"
    previous_short_prefix = "Fu" + "sion_"
    if name.startswith(previous_product_prefix):
        return "FMF_" + name[len(previous_product_prefix) :]
    if name.startswith(previous_short_prefix):
        return "FMF_" + name[len(previous_short_prefix) :]
    return name


def _reconcile_order(preferred, shipped):
    """Preserve known user order while inserting commands added by an update."""
    shipped = list(shipped)
    result = [item for item in preferred if item in shipped]
    result.extend(item for item in shipped if item not in result)
    return result


def _apply_customization(ribbon, spec, customization=None):
    customization = customization if customization is not None else _read_customization()
    customized = customization.get("workbenches", {})
    # A saved panel order describes the sections of the layout it was recorded
    # against. When a release changes which sections exist or what order they
    # ship in, replaying the old order silently overrides the new one -- and
    # because the result then matches what is already on disk, verification
    # passes and the whole layout is never regenerated. Two releases of section
    # changes reached nobody that way. Per-panel settings still carry over;
    # only the order between sections is taken from the new layout.
    order_is_current = customization.get("layoutVersion") == spec["layoutVersion"]
    for workbench, panels in spec["workbenches"].items():
        alternate = OWNED_TO_NATIVE_WORKBENCH.get(workbench)
        if alternate is None:
            alternate = NATIVE_TO_OWNED_WORKBENCH.get(workbench)
        saved_workbench = customized.get(workbench) or customized.get(alternate, {})
        toolbar_root = ribbon["workbenches"][workbench]["toolbars"]
        shipped_panel_order = [panel["name"] for panel in panels]
        saved_order = saved_workbench.get("panelOrder", []) if order_is_current else []
        toolbar_root["order"] = _reconcile_order(saved_order, shipped_panel_order)
        saved_panels = saved_workbench.get("panels", {})
        for panel in panels:
            name = panel["name"]
            saved = saved_panels.get(name, {})
            toolbar = toolbar_root[name]
            shipped_order = [entry[0] for entry in _panel_entries(panel)]
            known_before = set(saved.get("order", []))
            toolbar["order"] = _reconcile_order(saved.get("order", []), shipped_order)
            new_commands = set(shipped_order) - known_before if known_before else set()
            shipped_pinned = {entry[0] for entry in panel["commands"]}
            saved_pinned = [
                command for command in saved.get("pinned", []) if command in shipped_order
            ]
            if saved_pinned or known_before:
                pinned = saved_pinned + [
                    command
                    for command in toolbar["order"]
                    if command in new_commands and command in shipped_pinned
                ]
            else:
                pinned = [command for command in toolbar["order"] if command in shipped_pinned]
            toolbar["overflow"] = [command for command in toolbar["order"] if command not in pinned]
            toolbar["pinCount"] = len(pinned)
            toolbar["panelMenu"] = list(toolbar["order"])
            if "enabled" in saved:
                toolbar["Enabled"] = bool(saved["enabled"])
            # A panel whose divider the user dragged carries its own column budget.
            # Absent, the Ribbon add-on falls back to its global preference.
            for key in ("maxColumns", "minWidth", "widthModel"):
                if key not in saved:
                    continue
                try:
                    toolbar[key] = max(1, int(saved[key]))
                except (TypeError, ValueError):
                    toolbar.pop(key, None)
    return ribbon


def _merge_layout(apply_customization=True):
    ribbon = _load_json(BASE_LAYOUT)
    spec = _layout_spec()
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
            entries = _panel_entries(panel)
            for command, source, size, text, icon in entries:
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
                "panelMenu": list(command_order),
                "overflow": [entry[0] for entry in panel.get("overflow", [])],
                "responsive": dict(panel.get("responsive", {})),
                "pinCount": len(panel["commands"]),
            }
        # FreeCAD-Ribbon stores panel order alongside the toolbar entries.
        # A top-level workbench "order" is ignored and causes the add-on to
        # rediscover and prepend every native FreeCAD toolbar.
        toolbars["order"] = order
        all_new_panels[workbench] = new_panels
        all_workbenches[workbench] = {"toolbars": toolbars}
    # FreeCAD-Ribbon adds a global "Tools" panel of Std_ commands to every
    # workbench. The UTILITIES section carries the same commands as part of the
    # layout, so it can be ordered, resized and reset; the global one belongs to
    # no workbench, so a divider drag on it had nothing to write to and said so.
    # The preference that recreates it is managed off in runtime.py.
    all_new_panels.get("Global", {}).pop("Tools_newPanel", None)
    if apply_customization:
        _apply_customization(ribbon, spec)
    return ribbon, spec["layoutVersion"]


def record_customization(ribbon):
    """Persist safe user-owned layout choices after direct ribbon dragging."""
    spec = _layout_spec()
    result = {
        "schemaVersion": 1,
        "layoutVersion": spec["layoutVersion"],
        "updatedAt": _now(),
        "workbenches": {},
    }
    for workbench, panels in spec["workbenches"].items():
        expected_panels = [panel["name"] for panel in panels]
        toolbar_root = ribbon.get("workbenches", {}).get(workbench, {}).get("toolbars", {})
        saved_workbench = {
            "panelOrder": _reconcile_order(toolbar_root.get("order", []), expected_panels),
            "panels": {},
        }
        for panel in panels:
            name = panel["name"]
            expected_commands = [entry[0] for entry in _panel_entries(panel)]
            toolbar = toolbar_root.get(name, {})
            order = _reconcile_order(toolbar.get("order", []), expected_commands)
            overflow = set(toolbar.get("overflow", []))
            pin_count = int(toolbar.get("pinCount", len(panel["commands"])))
            pinned = [command for command in order if command not in overflow][:pin_count]
            panel_state = {
                "order": order,
                "pinned": pinned,
                "enabled": bool(toolbar.get("Enabled", True)),
            }
            for key in ("maxColumns", "minWidth", "widthModel"):
                if toolbar.get(key) is None:
                    continue
                try:
                    panel_state[key] = max(1, int(toolbar[key]))
                except (TypeError, ValueError):
                    pass
            saved_workbench["panels"][name] = panel_state
        result["workbenches"][workbench] = saved_workbench
    _atomic_json(CUSTOMIZATION_PATH, result)
    state = read_state()
    if state is not None and os.path.isfile(RIBBON_PATH):
        state["ribbonSha256"] = _sha256(RIBBON_PATH)
        state["customizationUpdatedAt"] = result["updatedAt"]
        write_state(state)
    return result


def clear_customization():
    if os.path.isfile(CUSTOMIZATION_PATH):
        os.remove(CUSTOMIZATION_PATH)


def reset_panel_customization(workbench, panel_name):
    """Reset one panel without disturbing any other user-owned arrangement."""
    customization = _read_customization()
    saved_workbench = customization.get("workbenches", {}).get(workbench, {})
    saved_panels = saved_workbench.get("panels", {})
    saved_panels.pop(panel_name, None)
    if customization:
        customization["updatedAt"] = _now()
        _atomic_json(CUSTOMIZATION_PATH, customization)
    ribbon, _layout_version = _merge_layout()
    _atomic_json(RIBBON_PATH, ribbon)
    state = read_state()
    if state is not None:
        state["ribbonSha256"] = _sha256(RIBBON_PATH)
        state["customizationUpdatedAt"] = customization.get("updatedAt", _now())
        write_state(state)
    return ribbon


def adaptive_candidates(manifest=None):
    """Map {workbench: {panel: set(commands)}} that the runtime may promote.

    Verification has to tolerate the runtime's adaptive edits, so it needs to know
    exactly which commands are allowed to move or change size.
    """
    manifest = manifest if manifest is not None else _layout_manifest()
    result = {}
    for workbench, config in manifest.get("adaptivePins", {}).items():
        panels = {}
        if "panels" in config:
            for panel, group in config["panels"].items():
                panels[panel] = set(group.get("commands", {}))
        elif config.get("panel"):
            panels[config["panel"]] = set(config.get("commands", {}))
        if panels:
            result[workbench] = panels
    return result


def _verify_layout(path, spec=None, candidates=None):
    """Check the generated ribbon against the layout spec it was built from.

    Returns (valid, checks, problems). Every structural expectation is derived from
    layout-v3.json, so renaming a panel cannot silently bypass verification.
    """
    problems = []
    try:
        spec = spec if spec is not None else _layout_spec()
        candidates = candidates if candidates is not None else adaptive_candidates()
        ribbon = _load_json(path)
        expected_ribbon, _layout_version = _merge_layout()
    except (OSError, ValueError) as error:
        return False, {"layoutReadable": False}, ["{}: {}".format(path, error)]

    checks = {
        "layoutReadable": True,
        "panelOrder": True,
        "panelContents": True,
        "commandLabels": True,
        "dropdownButtons": True,
        "authoritativeWorkbenches": True,
        "sourceMapping": True,
    }

    workbenches = ribbon.get("workbenches", {})
    new_panels = ribbon.get("newPanels", {})
    for workbench, panels in spec["workbenches"].items():
        definition = workbenches.get(workbench)
        if not isinstance(definition, dict) or not isinstance(definition.get("toolbars"), dict):
            checks["panelOrder"] = checks["panelContents"] = False
            problems.append("{}: workbench is missing from the generated ribbon".format(workbench))
            continue
        toolbars = definition["toolbars"]
        expected_toolbars = expected_ribbon["workbenches"][workbench]["toolbars"]
        expected_order = expected_toolbars["order"]
        if toolbars.get("order") != expected_order:
            checks["panelOrder"] = False
            problems.append(
                "{}: panel order is {} but the layout declares {}".format(
                    workbench, toolbars.get("order"), expected_order
                )
            )
        workbench_candidates = candidates.get(workbench, {})
        sources_by_panel = new_panels.get(workbench, {})
        for panel in panels:
            name = panel["name"]
            toolbar = toolbars.get(name)
            if not isinstance(toolbar, dict):
                checks["panelContents"] = False
                problems.append("{}/{}: panel is missing".format(workbench, name))
                continue
            expected_commands = expected_toolbars[name]["order"]
            movable = workbench_candidates.get(name, set())
            actual_order = toolbar.get("order", [])
            # Adaptive panels may permute their candidate commands, so compare
            # membership there and exact order everywhere else.
            ordered_ok = (
                sorted(actual_order) == sorted(expected_commands)
                if movable
                else actual_order == expected_commands
            )
            if not ordered_ok:
                checks["panelContents"] = False
                problems.append(
                    "{}/{}: commands are {} but the layout declares {}".format(
                        workbench, name, actual_order, expected_commands
                    )
                )
            if toolbar.get("title") != panel["title"]:
                checks["commandLabels"] = False
                problems.append(
                    "{}/{}: title is {!r} but the layout declares {!r}".format(
                        workbench, name, toolbar.get("title"), panel["title"]
                    )
                )
            commands = toolbar.get("commands", {})
            sources = dict(sources_by_panel.get(name, []))
            for command, source, size, text, icon in _panel_entries(panel):
                entry = commands.get(command)
                if not isinstance(entry, dict):
                    checks["panelContents"] = False
                    problems.append("{}/{}: {} is missing".format(workbench, name, command))
                    continue
                if entry.get("text") != text or entry.get("icon") != icon:
                    checks["commandLabels"] = False
                    problems.append(
                        "{}/{}/{}: label/icon is {!r}/{!r} but the layout "
                        "declares {!r}/{!r}".format(
                            workbench,
                            name,
                            command,
                            entry.get("text"),
                            entry.get("icon"),
                            text,
                            icon,
                        )
                    )
                if command not in movable and entry.get("size") != size:
                    checks["commandLabels"] = False
                    problems.append(
                        "{}/{}/{}: size is {!r} but the layout declares {!r}".format(
                            workbench, name, command, entry.get("size"), size
                        )
                    )
                if sources.get(command) != source:
                    checks["sourceMapping"] = False
                    problems.append(
                        "{}/{}/{}: source workbench is {!r} but the layout declares {!r}".format(
                            workbench, name, command, sources.get(command), source
                        )
                    )
            if movable and toolbar.get("panelMenu") != actual_order:
                checks["panelContents"] = False
                problems.append(
                    "{}/{}: panelMenu is {!r} but adaptive order is {!r}".format(
                        workbench, name, toolbar.get("panelMenu"), actual_order
                    )
                )
            for key in ("overflow", "responsive", "pinCount"):
                if toolbar.get(key) != expected_toolbars[name].get(key):
                    checks["panelContents"] = False
                    problems.append(
                        "{}/{}: {} is {!r} but expected {!r}".format(
                            workbench,
                            name,
                            key,
                            toolbar.get(key),
                            expected_toolbars[name].get(key),
                        )
                    )

    declared = ribbon.get("authoritativeWorkbenches", [])
    if sorted(declared) != sorted(spec["workbenches"]):
        checks["authoritativeWorkbenches"] = False
        problems.append(
            "authoritativeWorkbenches is {} but the layout declares {}".format(
                sorted(declared), sorted(spec["workbenches"])
            )
        )

    generated_dropdowns = ribbon.get("dropdownButtons", {})
    for name, commands in spec["dropdownButtons"].items():
        if generated_dropdowns.get(name) != commands:
            checks["dropdownButtons"] = False
            problems.append("dropdownButtons/{}: does not match the layout".format(name))

    return all(checks.values()), checks, problems


# ---------------------------------------------------------------------------
# Installation
# ---------------------------------------------------------------------------


def _read_baseline():
    baseline = _load_json_or_quarantine(BASELINE_PATH)
    if isinstance(baseline, dict) and baseline.get("preferences") is not None:
        return baseline
    return None


def _write_baseline(backup_root, had_ribbon):
    """Capture the pre-installation profile exactly once, ever."""
    existing = _read_baseline()
    if existing is not None:
        return existing
    baseline = {
        "schemaVersion": STATE_SCHEMA,
        "capturedAt": _now(),
        "backupRoot": backup_root,
        "ribbonHadExisting": had_ribbon,
        "preferences": _capture_preferences(),
    }
    _atomic_json(BASELINE_PATH, baseline)
    return baseline


def _migrate_baseline_from_state(state):
    """Preserve restoration data written before baseline.json existed."""
    existing = _read_baseline()
    if existing is not None:
        return existing
    preferences = state.get("preferences")
    backup_root = state.get("backupRoot")
    if not isinstance(preferences, list) or not backup_root:
        return None
    baseline = {
        "schemaVersion": STATE_SCHEMA,
        "capturedAt": state.get("installedAt") or state.get("updatedAt") or _now(),
        "backupRoot": backup_root,
        "ribbonHadExisting": bool(state.get("ribbonHadExisting")),
        "preferences": preferences,
        "migratedFromState": True,
    }
    _atomic_json(BASELINE_PATH, baseline)
    return baseline


def _extend_baseline_with_status_bar():
    """Add the newly managed status-bar preference without recapturing old keys."""
    baseline = _read_baseline()
    if baseline is None:
        return None
    preferences = baseline.get("preferences", [])
    wanted = STATUS_BAR_PREFERENCE[:2]
    if any((entry.get("path"), entry.get("name")) == wanted for entry in preferences):
        return baseline
    preferences.append(_capture_preference(STATUS_BAR_PREFERENCE))
    baseline["preferences"] = preferences
    baseline["statusBarBaselineAddedAt"] = _now()
    _atomic_json(BASELINE_PATH, baseline)
    return baseline


def _state_from_baseline(baseline, recovered):
    return {
        "schemaVersion": STATE_SCHEMA,
        "installedAt": baseline["capturedAt"],
        "backupRoot": baseline["backupRoot"],
        "ribbonHadExisting": baseline["ribbonHadExisting"],
        "preferences": baseline["preferences"],
        "recoveredFromBaseline": recovered,
        "updates": [],
    }


def read_state():
    state = _load_json_or_quarantine(STATE_PATH)
    return state if isinstance(state, dict) else None


def write_state(state):
    _atomic_json(STATE_PATH, state)


def update_ribbon_hash():
    """Re-record the generated ribbon's digest after a legitimate rewrite.

    The runtime rewrites the ribbon when adaptive panels change. Recording the new
    digest keeps a later mismatch meaningful: it then indicates an edit made outside
    FMF, which an upgrade must not silently discard.
    """
    state = read_state()
    if state is None or not os.path.isfile(RIBBON_PATH):
        return False
    state["ribbonSha256"] = _sha256(RIBBON_PATH)
    state["ribbonHashUpdatedAt"] = _now()
    write_state(state)
    return True


def prepare():
    _migrate_previous_brand_data()
    version = tuple(int(part) for part in App.Version()[:2])
    if version < (1, 1):
        raise RuntimeError("FMF requires FreeCAD 1.1 or newer.")
    for required in (BASE_LAYOUT, LAYOUT_SPEC, MANIFEST, RUNTIME):
        if not os.path.isfile(required):
            raise RuntimeError("FMF package is incomplete: {}".format(required))

    spec = _layout_spec()
    candidates = adaptive_candidates()
    state = read_state()
    if state is not None and not state.get("backupRoot"):
        # Schema drift or a hand-edited file: fall back to the reinstall path
        # rather than raising during FreeCAD startup.
        App.Console.PrintWarning(
            "FMF state is missing its backup location; reinstalling from the baseline.\n"
        )
        state = None

    if state is not None:
        _migrate_baseline_from_state(state)
    _extend_baseline_with_status_bar()

    if state is not None and state.get("packageVersion") == PACKAGE_VERSION:
        valid, _checks, _problems = _verify_layout(RIBBON_PATH, spec, candidates)
        if valid:
            return "unchanged"

    os.makedirs(RIBBON_DIR, exist_ok=True)
    had_ribbon = os.path.isfile(RIBBON_PATH)

    if state is None:
        baseline = _read_baseline()
        recovered = baseline is not None
        if baseline is None:
            backup_root = os.path.join(BACKUP_ROOT, "addon-" + _timestamp())
            os.makedirs(backup_root, exist_ok=True)
            if had_ribbon:
                shutil.copy2(RIBBON_PATH, os.path.join(backup_root, "RibbonStructure.json"))
            baseline = _write_baseline(backup_root, had_ribbon)
        else:
            App.Console.PrintWarning(
                "FMF state was missing; reusing the original baseline at {}.\n".format(
                    BASELINE_PATH
                )
            )
            os.makedirs(baseline["backupRoot"], exist_ok=True)
        state = _state_from_baseline(baseline, recovered)
        outcome = "recovered" if recovered else "installed"
    else:
        outcome = "updated"
        if had_ribbon:
            update_path = os.path.join(
                state["backupRoot"], "updates", _timestamp() + "-RibbonStructure.json"
            )
            os.makedirs(os.path.dirname(update_path), exist_ok=True)
            shutil.copy2(RIBBON_PATH, update_path)
            state.setdefault("updates", []).append(update_path)
            recorded = state.get("ribbonSha256")
            if recorded and recorded != _sha256(RIBBON_PATH):
                # The ribbon changed outside FMF. Replacing it is still
                # correct for an upgrade, but the user must be able to find the copy.
                state["externalRibbonEdit"] = update_path
                # The bundled Ribbon add-on re-serializes this file on its own, so
                # a digest change is usually its normalisation rather than a real
                # user edit. Keep the note in the log and reachable from Verify UI
                # instead of announcing it on every launch.
                App.Console.PrintLog(
                    "FMF replaced a ribbon layout that changed outside the add-on. "
                    "The previous layout is kept at {}.\n".format(update_path)
                )

    ribbon, layout_version = _merge_layout()
    _atomic_json(RIBBON_PATH, ribbon)
    valid, checks, problems = _verify_layout(RIBBON_PATH, spec, candidates)
    if not valid:
        raise RuntimeError(
            "FMF generated an invalid ribbon: {}; {}".format(checks, "; ".join(problems))
        )
    state.update(
        {
            "schemaVersion": STATE_SCHEMA,
            "packageVersion": PACKAGE_VERSION,
            "layoutVersion": layout_version,
            "updatedAt": _now(),
            "ribbonSha256": _sha256(RIBBON_PATH),
        }
    )
    write_state(state)
    return outcome


def verify():
    """Report installation health as (valid, checks, problems)."""
    _valid, checks, problems = _verify_layout(RIBBON_PATH)
    state = read_state() or {}
    checks["stateVersion"] = state.get("packageVersion") == PACKAGE_VERSION
    if not checks["stateVersion"]:
        problems.append(
            "Installed state records version {!r}; this package is {!r}.".format(
                state.get("packageVersion"), PACKAGE_VERSION
            )
        )
    checks["restorePointPresent"] = _read_baseline() is not None
    if not checks["restorePointPresent"]:
        problems.append(
            "No restore baseline at {}. Disable FMF cannot recover the original profile.".format(
                BASELINE_PATH
            )
        )
    for label, relative in (
        ("bundledRibbon", ("bundled-addons", "FreeCAD-Ribbon", "InitGui.py")),
        ("bundledSearch", ("bundled-addons", "SearchBar", "InitGui.py")),
    ):
        checks[label] = os.path.isfile(os.path.join(ADDON_ROOT, *relative))
        if not checks[label]:
            problems.append("Bundled payload is missing: {}".format(os.path.join(*relative)))

    failures = startup_failures()
    checks["startupClean"] = not failures
    for failure in failures:
        problems.append(
            "Startup step {!r} failed: {}".format(failure.get("step"), failure.get("error"))
        )

    report = _load_json_or_quarantine(STATUS_PATH)
    if isinstance(report, dict):
        runtime_problems = report.get("problems", [])
        checks["runtimeClean"] = not runtime_problems
        problems.extend("Runtime: {}".format(entry) for entry in runtime_problems)
        for entry in report.get("displacedShortcuts", []):
            problems.append(
                "Shortcut {} was taken from {} and given to {}.".format(
                    entry.get("sequence"), entry.get("from"), entry.get("to")
                )
            )

    return all(checks.values()), checks, problems


def restore():
    """Undo everything FMF changed, using the immutable baseline.

    Returns (recovery_directory, problems). Every step is independent so a single
    failure cannot abandon the rest of the restoration.
    """
    baseline = _read_baseline()
    state = read_state()
    source = baseline or state
    if source is None:
        raise RuntimeError(
            "FMF has no restoration data. Neither {} nor {} is readable.".format(
                BASELINE_PATH, STATE_PATH
            )
        )
    # This marker is deliberately outside the baseline-owned preference list.
    # Restoring the old profile must not let the next startup silently enable
    # FMF again while the add-on remains installed.
    App.ParamGet(PREFERENCE_ROOT).SetBool("Enabled", False)
    App.saveParameter()
    backup_root = source.get("backupRoot") or BACKUP_ROOT
    removed = os.path.join(backup_root, "removed-" + _timestamp())
    os.makedirs(removed, exist_ok=True)

    problems = []
    try:
        if os.path.isfile(RIBBON_PATH):
            shutil.move(RIBBON_PATH, os.path.join(removed, "RibbonStructure.json"))
        prior = os.path.join(backup_root, "RibbonStructure.json")
        if source.get("ribbonHadExisting") and os.path.isfile(prior):
            shutil.copy2(prior, RIBBON_PATH)
    except OSError as error:
        problems.append("Ribbon layout: {}".format(error))

    problems.extend(_restore_preferences(source.get("preferences", [])))

    # Machine-local runtime files are regenerated on demand and must not survive a
    # restore. Move rather than delete so nothing is destroyed outright.
    for path in (STATE_PATH, STARTUP_PATH, STATUS_PATH, USAGE_PATH, CUSTOMIZATION_PATH):
        if os.path.isfile(path):
            try:
                shutil.move(path, os.path.join(removed, os.path.basename(path)))
            except OSError as error:
                problems.append("{}: {}".format(path, error))

    try:
        # Clearing the applied marker means a later reinstall reapplies its defaults.
        App.ParamGet(PREFERENCE_ROOT).RemString("AppliedVersion")
        App.saveParameter()
    except Exception as error:
        problems.append("Applied-version marker: {}".format(error))

    try:
        import fmf_viewport

        fmf_viewport.restore_all_appearance()
    except Exception as error:
        problems.append("Appearance restoration: {}".format(error))

    try:
        main_window = Gui.getMainWindow()
        main_window.menuBar().show()
        from PySide import QtWidgets

        ribbon = main_window.findChild(QtWidgets.QDockWidget, "Ribbon")
        if ribbon is not None:
            ribbon.hide()
        for toolbar in main_window.findChildren(QtWidgets.QToolBar):
            name = toolbar.objectName() if hasattr(toolbar, "objectName") else ""
            if name in {"SearchBar", "SearchBarAtMouse"}:
                toolbar.hide()
            else:
                toolbar.show()
    except Exception as error:  # pragma: no cover - needs a live Qt main window
        problems.append("Native toolbars: {}".format(error))

    return removed, problems


def is_enabled():
    """Whether FMF should load its managed UI and runtime services."""
    return App.ParamGet(PREFERENCE_ROOT).GetBool("Enabled", True)


def owned_workbenches_enabled():
    """Whether the migration pilot should expose FMF-owned workbench identities."""
    return App.ParamGet(PREFERENCE_ROOT).GetBool("UseOwnedWorkbenches", True)


def register_owned_workbenches():
    """Register namespaced FMF workbenches without replacing native workbenches."""
    if not owned_workbenches_enabled():
        return False
    _migrate_owned_identity_preferences()
    import fmf_workbenches

    enabled = is_enabled()
    set_owned_workbench_visibility(enabled)
    fmf_workbenches.register()
    sync_start_workbench(enabled)
    return True


def _workbench_list(value):
    return [item.strip() for item in value.split(",") if item.strip()]


def _write_workbench_list(group, name, values):
    group.SetString(name, ",".join(dict.fromkeys(values)))


def _migrate_owned_identity_preferences():
    """Move persisted 1.8-development workbench IDs to their FMF names."""
    general = App.ParamGet("User parameter:BaseApp/Preferences/General")
    autoload = general.GetString("AutoloadModule", "")
    if autoload in LEGACY_OWNED_WORKBENCH:
        general.SetString("AutoloadModule", LEGACY_OWNED_WORKBENCH[autoload])

    workbenches = App.ParamGet(WORKBENCH_PREFERENCE_ROOT)
    for key in ("Disabled", "Ordered"):
        values = _workbench_list(workbenches.GetString(key, ""))
        migrated = [LEGACY_OWNED_WORKBENCH.get(value, value) for value in values]
        if migrated != values:
            _write_workbench_list(workbenches, key, migrated)
    App.saveParameter()


def set_owned_workbench_visibility(enabled):
    """Expose FMF workbenches or their stock counterparts, never both families."""
    group = App.ParamGet(WORKBENCH_PREFERENCE_ROOT)
    preferences = App.ParamGet(PREFERENCE_ROOT)
    disabled = _workbench_list(group.GetString("Disabled", ""))
    owned = tuple(OWNED_TO_NATIVE_WORKBENCH)
    native = tuple(OWNED_TO_NATIVE_WORKBENCH.values())

    if enabled:
        disabled = [workbench for workbench in disabled if workbench not in owned]
        for workbench in native:
            if workbench not in disabled:
                disabled.append(workbench)
        ribbon_group = App.ParamGet("User parameter:BaseApp/Preferences/Mod/FreeCAD-Ribbon")
        ribbon_order = _workbench_list(ribbon_group.GetString("TabOrder", ""))
        ribbon_order = list(owned) + [
            workbench
            for workbench in ribbon_order
            if workbench not in owned and workbench not in LEGACY_OWNED_WORKBENCH
        ]
        _write_workbench_list(ribbon_group, "TabOrder", ribbon_order)
    else:
        for workbench in owned:
            if workbench not in disabled:
                disabled.append(workbench)
        disabled = [workbench for workbench in disabled if workbench not in native]

    # Remove state written by the earlier optional-hide implementation. Visibility
    # is now an invariant of FMF's enabled state rather than a second preference.
    preferences.RemString("NativeHiddenByFMF")
    preferences.RemBool("HideNativeWorkbenches")

    _write_workbench_list(group, "Disabled", disabled)
    App.saveParameter()


def sync_start_workbench(enabled):
    """Keep FreeCAD's startup workbench within the currently visible family."""
    preferences = App.ParamGet(PREFERENCE_ROOT)
    general = App.ParamGet("User parameter:BaseApp/Preferences/General")
    autoload = general.GetString("AutoloadModule", "")

    if enabled and preferences.GetBool("SetStartWorkbench", True):
        general.SetString("AutoloadModule", "FMFDesignWorkbench")
    elif autoload in OWNED_TO_NATIVE_WORKBENCH:
        general.SetString("AutoloadModule", OWNED_TO_NATIVE_WORKBENCH[autoload])
    App.saveParameter()


def active_workbench_name():
    try:
        return Gui.activeWorkbench().name()
    except Exception:
        return ""


def show_ribbon_context(workbench_name):
    """Select an FMF Ribbon context without changing FreeCAD's workbench."""
    try:
        from PySide import QtWidgets

        main_window = Gui.getMainWindow()
        ribbon_dock = main_window.findChild(QtWidgets.QDockWidget, "Ribbon")
        ribbon = ribbon_dock.widget() if ribbon_dock is not None else None
        select_context = getattr(ribbon, "selectFmfWorkbenchContext", None)
        return bool(select_context and select_context(workbench_name))
    except (AttributeError, RuntimeError, TypeError):
        return False


def fmf_workbench_for(native_workbench):
    """Return the matching FMF identity when the owned interface is active."""
    if is_enabled() and owned_workbenches_enabled():
        return NATIVE_TO_OWNED_WORKBENCH.get(native_workbench, native_workbench)
    return native_workbench


# Compatibility for third-party macros written against the 1.8.0 development builds.
fmf_workbench_for = fmf_workbench_for


def activate_owned_workbench(workbench):
    """Apply FMF chrome only while an FMF-owned workbench is active."""
    if not is_enabled() or not owned_workbenches_enabled():
        return
    import fmf_chrome

    fmf_chrome.get_chrome_controller().apply(
        fmf_chrome.ChromeState(
            toolbars_hidden=True,
            menubar_hidden=True,
            ribbon_visible=True,
            family_enabled=True,
        )
    )


def set_ribbon_workbench_family(enabled):
    """Show exactly one FMF/stock workbench family without hiding the Ribbon."""
    from PySide import QtWidgets

    ribbon_dock = Gui.getMainWindow().findChild(QtWidgets.QDockWidget, "Ribbon")
    ribbon = ribbon_dock.widget() if ribbon_dock is not None else None
    tab_bar = ribbon.tabBar() if ribbon is not None and hasattr(ribbon, "tabBar") else None
    if tab_bar is None or not hasattr(tab_bar, "setTabVisible"):
        return False

    owned = set(OWNED_TO_NATIVE_WORKBENCH)
    native = set(OWNED_TO_NATIVE_WORKBENCH.values())
    active = fmf_workbench_for(active_workbench_name()) if enabled else active_workbench_name()
    active_index = None
    for index in range(tab_bar.count()):
        workbench = tab_bar.tabData(index)
        if workbench in owned:
            tab_bar.setTabVisible(index, enabled)
        elif workbench in native:
            tab_bar.setTabVisible(index, not enabled)
        if workbench == active:
            active_index = index
    if active_index is not None:
        if ribbon is not None:
            ribbon._fmfProgrammaticTabChange = True
        try:
            tab_bar.setCurrentIndex(active_index)
        finally:
            if ribbon is not None:
                ribbon._fmfProgrammaticTabChange = False
    ribbon_dock.show()
    Gui.getMainWindow().menuBar().hide()
    return True


def defer_ribbon_workbench_family(enabled):
    """Apply tab visibility after Ribbon has finished building its categories."""
    from PySide import QtCore

    QtCore.QTimer.singleShot(0, lambda: set_ribbon_workbench_family(enabled))


def sync_ui_mode_to_active_workbench():
    """Keep the Ribbon active and synchronize its FMF/stock tab family."""
    set_ribbon_workbench_family(is_enabled() and owned_workbenches_enabled())


def defer_ui_mode_sync():
    """Wait for FreeCAD to finish switching workbenches before changing chrome."""
    from PySide import QtCore

    QtCore.QTimer.singleShot(0, sync_ui_mode_to_active_workbench)


def _set_searchbar_service(enabled):
    """Start or stop the already-loaded bundled SearchBar services."""
    module = sys.modules.get("_fmf_vendor_SearchBar")
    callback = getattr(module, "install" if enabled else "uninstall", None)
    if callback is not None:
        callback()


def _configure_ribbon_cache_scope():
    """Keep Ribbon cache initialization inside FMF's curated workbenches."""
    os.environ[RIBBON_CACHE_WORKBENCHES_ENV] = ",".join(OWNED_TO_NATIVE_WORKBENCH.values())


def enable():
    """Enable FMF persistently and prepare its state for the next launch."""
    App.ParamGet(PREFERENCE_ROOT).SetBool("Enabled", True)
    App.saveParameter()
    register_commands()
    register_owned_workbenches()
    outcome = prepare()
    run_runtime()
    load_vendor("SearchBar", os.path.join(ADDON_ROOT, "bundled-addons", "SearchBar"))
    _set_searchbar_service(True)
    # First-run Ribbon cache creation otherwise activates every installed
    # workbench.  FMF owns four curated contexts; loading unrelated workbenches
    # here adds large startup cost and can block on third-party workbenches.
    _configure_ribbon_cache_scope()
    load_vendor("FreeCAD_Ribbon", os.path.join(ADDON_ROOT, "bundled-addons", "FreeCAD-Ribbon"))
    active = active_workbench_name()
    replacement = NATIVE_TO_OWNED_WORKBENCH.get(active)
    if replacement:
        Gui.activateWorkbench(replacement)
    defer_ui_mode_sync()
    return outcome


def disable():
    """Disable owned FMF workbenches without dismantling FreeCAD's native UI."""
    if not owned_workbenches_enabled():
        return restore()
    active = active_workbench_name()
    replacement = OWNED_TO_NATIVE_WORKBENCH.get(active)
    baseline = _read_baseline()
    problems = (
        _restore_preferences(baseline.get("preferences", []))
        if baseline is not None
        else ["Original preference baseline is unavailable; managed preferences were not restored."]
    )
    preferences = App.ParamGet(PREFERENCE_ROOT)
    preferences.RemString("AppliedVersion")
    preferences.SetBool("Enabled", False)
    _set_searchbar_service(False)
    dispose_ribbon_action_bindings()
    set_owned_workbench_visibility(False)
    sync_start_workbench(False)
    runtime = sys.modules.get("_fmf_my_freecad_runtime")
    if runtime is not None and hasattr(runtime, "restore_shortcuts"):
        try:
            runtime.restore_shortcuts(Gui.getMainWindow())
        except Exception as error:
            problems.append("Shortcut restoration: {}".format(error))
    if runtime is not None and hasattr(runtime, "uninstall"):
        try:
            runtime.uninstall()
        except Exception as error:
            problems.append("Runtime teardown: {}".format(error))
    dispose_native_action_registry()
    unregister_feature_observers()
    try:
        import fmf_chrome

        fmf_chrome.get_chrome_controller().restore()
    except Exception as error:
        problems.append("Chrome restoration: {}".format(error))
    try:
        import fmf_persistence

        fmf_persistence.flush_parameters(force=True)
    except Exception as error:
        problems.append("Parameter flush: {}".format(error))
    try:
        import fmf_viewport

        fmf_viewport.restore_all_appearance()
    except Exception as error:
        problems.append("Appearance restoration: {}".format(error))
    if replacement:
        Gui.activateWorkbench(replacement)
    defer_ribbon_workbench_family(False)
    install_lifecycle_menu()
    return "FMF is disabled. FMF settings remain available at {}.".format(BASELINE_PATH), problems


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def _exec(dialog):
    """Show a dialog on either Qt binding FreeCAD may provide."""
    runner = getattr(dialog, "exec", None) or dialog.exec_
    return runner()


def _message(title, text, error=False):
    from PySide import QtWidgets

    icon = QtWidgets.QMessageBox.Critical if error else QtWidgets.QMessageBox.Information
    box = QtWidgets.QMessageBox(icon, title, text, parent=Gui.getMainWindow())
    _exec(box)


class VerifyCommand:
    def GetResources(self):
        return {
            "Pixmap": "Std_DlgParameter",
            "MenuText": "Verify FMF",
            "ToolTip": "Check the installed UI package",
        }

    def IsActive(self):
        return True

    def Activated(self):
        valid, checks, problems = verify()
        lines = [
            "{}: {}".format(name, "OK" if result else "FAILED") for name, result in checks.items()
        ]
        if problems:
            lines.extend(["", "Details:"])
            lines.extend("- {}".format(problem) for problem in problems)
        if not valid:
            lines.extend(
                [
                    "",
                    "Suggested next step: run Reset FMF, then restart FreeCAD.",
                    "If that does not help, disable FMF and reinstall the add-on.",
                ]
            )
        _message("FMF verification", "\n".join(lines), not valid)


class ReapplyCommand:
    """Reinstall the layout and re-apply managed defaults on request.

    Managed preferences are applied once per version so the add-on does not
    overwrite the user's own changes at every launch. This command is the supported
    way back to the shipped defaults.
    """

    def GetResources(self):
        return {
            "Pixmap": "Std_DlgParameter",
            "MenuText": "Reset FMF",
            "ToolTip": "Reset FMF's layout, preferences, and shortcuts to its defaults",
        }

    def IsActive(self):
        return is_enabled()

    def Activated(self):
        from PySide import QtWidgets

        answer = QtWidgets.QMessageBox.question(
            Gui.getMainWindow(),
            "Reset FMF",
            "Reset FMF's ribbon layout, managed preferences, and shortcuts?\n\n"
            "Your own changes to those settings will be replaced.",
        )
        if answer != QtWidgets.QMessageBox.Yes:
            return
        try:
            _message("FMF", reapply(), False)
        except Exception as error:
            _message("FMF could not reapply", str(error), True)


def reapply():
    """Force a full re-application of the layout and managed defaults."""
    clear_customization()
    App.ParamGet(PREFERENCE_ROOT).RemString("AppliedVersion")
    App.saveParameter()
    state = read_state()
    if state is not None:
        state.pop("packageVersion", None)
        write_state(state)
    clear_startup_failures()
    outcome = prepare()
    runtime = sys.modules.get("_fmf_my_freecad_runtime")
    if runtime is not None and hasattr(runtime, "apply_preferences"):
        runtime.apply_preferences(force=True)
    return "Defaults reapplied ({}). Restart FreeCAD to load the regenerated ribbon.".format(
        outcome
    )


class DisableCommand:
    def GetResources(self):
        return {
            "Pixmap": "applications-accessories",
            "MenuText": "Disable FMF",
            "ToolTip": "Disable FMF and return to the previous FreeCAD UI",
        }

    def IsActive(self):
        return is_enabled()

    def Activated(self):
        from PySide import QtWidgets

        answer = QtWidgets.QMessageBox.question(
            Gui.getMainWindow(),
            "Disable FMF",
            "Disable FMF and return to the UI settings from before it was enabled?",
        )
        if answer != QtWidgets.QMessageBox.Yes:
            return
        try:
            location, problems = disable()
            text = [
                "FMF is disabled. The standard FreeCAD workbenches are active.",
                location,
                "Restart FreeCAD to refresh the workbench selector and finish teardown.",
            ]
            if problems:
                text.extend(["", "Some items could not be restored:"])
                text.extend("- {}".format(problem) for problem in problems)
            _message("FMF disabled", "\n".join(text), bool(problems))
        except Exception as error:
            _message("Could not disable FMF", str(error), True)


class EnableCommand:
    def GetResources(self):
        return {
            "Pixmap": "Std_DlgParameter",
            "MenuText": "Enable FMF",
            "ToolTip": "Enable FMF and prepare its interface for the next launch",
        }

    def IsActive(self):
        return not is_enabled()

    def Activated(self):
        try:
            outcome = enable()
            _message(
                "FMF enabled",
                "FMF is enabled ({}). Restart FreeCAD to load its interface.".format(outcome),
            )
        except Exception as error:
            _message("Could not enable FMF", str(error), True)


class ReviewShortcutsCommand:
    def GetResources(self):
        return {
            "Pixmap": "applications-accessories",
            "MenuText": "Review FMF Shortcuts",
            "ToolTip": "Preview occupied keys before applying the FMF shortcut preset",
        }

    def IsActive(self):
        return is_enabled()

    def Activated(self):
        runtime = sys.modules.get("_fmf_my_freecad_runtime")
        if runtime is None or not hasattr(runtime, "review_shortcuts"):
            _message("FMF shortcuts", "FMF's runtime is not available yet.", True)
            return
        runtime.review_shortcuts()


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
        created_document = App.ActiveDocument is None
        if App.ActiveDocument is None:
            App.newDocument()
        document = App.ActiveDocument
        if not any(obj.isDerivedFrom("PartDesign::Body") for obj in document.Objects):
            document.addObject("PartDesign::Body", "Body")
            document.recompute()
        if created_document:
            track_auto_created_document(document)
        had_selection = bool(getattr(Gui, "Selection", None) and Gui.Selection.getSelection())
        Gui.activateWorkbench(fmf_workbench_for("PartDesignWorkbench"))
        Gui.runCommand("PartDesign_NewSketch")
        # Keep Part Design active while FreeCAD's attachment task displays its
        # selectable origin planes. Switching workbenches here destroys the
        # Fusion-like plane-picking presentation before the user has chosen one.
        # Only frame the origin planes if no existing feature/face was selected.
        if not had_selection:
            try:
                from PySide import QtCore

                QtCore.QTimer.singleShot(0, _frame_origin_planes)
            except ImportError:
                _frame_origin_planes()


class RecentDocumentsCommand:
    """Open FreeCAD's native Start page and its authoritative recent-file list."""

    def GetResources(self):
        return {
            "Pixmap": "document-properties",
            "MenuText": "Recent Documents",
            "ToolTip": "Show FreeCAD's Start page with recent documents",
        }

    def IsActive(self):
        return "Start_Start" in Gui.listCommands()

    def Activated(self):
        if self.IsActive():
            Gui.runCommand("Start_Start")


def _default_camera_scale():
    try:
        scale = App.ParamGet("User parameter:BaseApp/Preferences/View").GetFloat(
            "NewDocumentCameraScale", 100.0
        )
        return max(scale, 10.0) if scale > 0 else 100.0
    except Exception:
        return 100.0


def _center_camera(view, center=(0.0, 0.0, 0.0), height=100.0):
    """Center the camera on a 3D target point with a specific visible range/height.

    Avoids fitAll's upward/rightward pan caused by asymmetric [0, +size] origin plane bounds.
    """
    if view is None:
        return
    if hasattr(view, "setCameraCenter"):
        view.setCameraCenter(center, height)
    cam = getattr(view, "getCameraNode", lambda: None)()
    if cam is None:
        return

    try:
        center_vec = App.Vector(center[0], center[1], center[2]) if hasattr(App, "Vector") else None
        orient_field = getattr(cam, "orientation", None)
        if orient_field is None or center_vec is None or not hasattr(App, "Rotation"):
            return
        q = orient_field.getValue().getValue()
        rot = App.Rotation(*q)
        # Vector pointing from target center back toward the camera eye
        v_cam = rot.multVec(App.Vector(0.0, 0.0, 1.0))

        if hasattr(cam, "height"):
            # Orthographic camera
            focal_dist = (
                float(cam.focalDistance.getValue())
                if hasattr(cam, "focalDistance")
                else float(height)
            )
            focal_dist = max(focal_dist, float(height))
            pos = center_vec + v_cam * focal_dist
            cam.position.setValue([pos.x, pos.y, pos.z])
            if hasattr(cam, "focalDistance"):
                cam.focalDistance.setValue(focal_dist)
            cam.height.setValue(float(height))
        elif hasattr(cam, "heightAngle"):
            # Perspective camera
            import math

            angle = float(cam.heightAngle.getValue())
            focal_dist = (
                (float(height) / 2.0) / math.tan(angle / 2.0) if angle > 0 else float(height)
            )
            pos = center_vec + v_cam * focal_dist
            cam.position.setValue([pos.x, pos.y, pos.z])
            if hasattr(cam, "focalDistance"):
                cam.focalDistance.setValue(focal_dist)
    except Exception:
        pass


def _frame_origin_planes():
    """Give FreeCAD's temporary origin planes a predictable, visible camera centered at origin."""
    document = getattr(Gui, "ActiveDocument", None)
    if document is None:
        return
    if getattr(document, "getInEdit", lambda: None)() is not None:
        return
    view = getattr(document, "ActiveView", None)
    if view is None:
        return
    view.viewAxonometric()
    # Center on the origin (0, 0, 0) with default scale (~100x100mm) instead of fitAll,
    # which shifts up/right due to asymmetric [0, +size] origin plane bounds.
    _center_camera(view, center=(0.0, 0.0, 0.0), height=_default_camera_scale())


class _SketchEditWorkbenchObserver:
    """Present Sketch tools without taking ownership of FreeCAD's workbench state."""

    def __init__(self):
        self._transition_serial = 0
        self._return_context = "FMFDesignWorkbench"

    def slotInEdit(self, view_provider):
        def install_task_filter():
            runtime = sys.modules.get("_fmf_my_freecad_runtime")
            if runtime is not None and hasattr(runtime, "install_task_accept_filter"):
                runtime.install_task_accept_filter()

        try:
            from PySide import QtCore

            QtCore.QTimer.singleShot(0, install_task_filter)
        except ImportError:
            install_task_filter()

        obj = getattr(view_provider, "Object", None)
        if obj is not None and obj.isDerivedFrom("PartDesign::Feature"):
            def _on_partdesign_feature_in_edit():
                show_ribbon_context(fmf_workbench_for("PartDesignWorkbench"))
                try:
                    import fmf_extrude

                    fmf_extrude.enhance_active_extrude()
                except Exception:
                    pass

            try:
                from PySide import QtCore

                QtCore.QTimer.singleShot(0, _on_partdesign_feature_in_edit)
                QtCore.QTimer.singleShot(60, _on_partdesign_feature_in_edit)
            except ImportError:
                _on_partdesign_feature_in_edit()
            return
        if obj is None or not obj.isDerivedFrom("Sketcher::SketchObject"):
            return
        self._transition_serial += 1
        active = fmf_workbench_for(active_workbench_name())
        allowed_returns = {
            "FMFDesignWorkbench",
            "FMFPartWorkbench",
            "FMFSurfaceWorkbench",
        }
        self._return_context = active if active in allowed_returns else "FMFDesignWorkbench"
        # FreeCAD owns edit-mode workbench state. FMF changes only the visible
        # Ribbon category after setEdit returns, avoiding a re-entrant host
        # workbench activation while the edit transaction is still opening.
        try:
            from PySide import QtCore

            QtCore.QTimer.singleShot(0, lambda: self._on_sketch_in_edit(obj))
        except ImportError:
            self._on_sketch_in_edit(obj)

    def _on_sketch_in_edit(self, sketch_obj):
        show_ribbon_context("FMFSketchWorkbench")
        # If this is a newly created sketch (no geometry yet), ensure its view
        # is cleanly centered on the sketch plane origin with ~100x100mm range,
        # preventing off-center pan and extreme zoom.
        try:
            geo_count = len(getattr(sketch_obj, "Geometry", []))
            if geo_count == 0:
                document = getattr(Gui, "ActiveDocument", None)
                view = getattr(document, "ActiveView", None) if document else None
                if view is not None:
                    pla = (
                        sketch_obj.getGlobalPlacement()
                        if hasattr(sketch_obj, "getGlobalPlacement")
                        else getattr(sketch_obj, "Placement", None)
                    )
                    origin = (
                        (pla.Base.x, pla.Base.y, pla.Base.z)
                        if pla is not None and hasattr(pla, "Base")
                        else (0.0, 0.0, 0.0)
                    )
                    _center_camera(view, center=origin, height=_default_camera_scale())
        except Exception as error:
            record_startup_failure("center new sketch view", error)

    def slotResetEdit(self, view_provider):
        obj = getattr(view_provider, "Object", None)
        if obj is not None and obj.isDerivedFrom("PartDesign::Feature"):
            def _on_partdesign_feature_reset_edit():
                show_ribbon_context(fmf_workbench_for("PartDesignWorkbench"))
                try:
                    import fmf_extrude

                    if hasattr(fmf_extrude, "close_extrude_hud"):
                        fmf_extrude.close_extrude_hud()
                except Exception:
                    pass

            try:
                from PySide import QtCore

                QtCore.QTimer.singleShot(0, _on_partdesign_feature_reset_edit)
            except ImportError:
                _on_partdesign_feature_reset_edit()
            return
        if obj is None or not obj.isDerivedFrom("Sketcher::SketchObject"):
            return
        self._transition_serial += 1
        transition_serial = self._transition_serial
        return_context = self._return_context
        try:
            from PySide import QtCore

            def show_return_context():
                if transition_serial == self._transition_serial:
                    show_ribbon_context(return_context)

            QtCore.QTimer.singleShot(0, show_return_context)
        except ImportError:
            show_ribbon_context(return_context)
        try:
            import fmf_sketch_tools

            fmf_sketch_tools.repair_sketch_internal_faces(obj)
        except Exception as error:
            record_startup_failure("rebuild sketch faces after edit", error)
        # Clear whole-sketch selection so multi-region sketches don't trick the user
        # with an all-green highlight that fails when Extrude (Pad) is clicked.
        try:
            from PySide import QtCore

            QtCore.QTimer.singleShot(100, lambda: Gui.Selection.clearSelection())
        except Exception as error:
            record_startup_failure("clear sketch selection after edit", error)


class ParameterTableCommand:
    def GetResources(self):
        return {
            "Pixmap": "Spreadsheet",
            "MenuText": "Parameter Table",
            "ToolTip": (
                "Create or open a spreadsheet for model parameters, calculations, and reports"
            ),
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


def register_preferences_page():
    """Expose the opt-outs in FreeCAD's own preferences dialog.

    Without this the switches exist only as raw parameters, which is no help to
    the user who wants to turn one of them off.
    """
    if not os.path.isfile(PREFERENCES_UI):
        raise RuntimeError("FMF preferences page is missing: {}".format(PREFERENCES_UI))
    Gui.addPreferencePage(PREFERENCES_UI, "FMF")


_sketch_edit_observer = None
_sketch_repair_observer = None
_auto_created_document_observer = None


class _AutoCreatedDocumentObserver:
    """Discard only an untouched document that FMF created for Create Sketch."""

    def __init__(self):
        self._candidate = None

    @staticmethod
    def _snapshot(document):
        objects = tuple(getattr(document, "Objects", ()))
        get_undo_names = getattr(document, "getAvailableUndoNames", None)
        undo_names = tuple(get_undo_names()) if callable(get_undo_names) else None
        return (
            getattr(document, "Name", ""),
            getattr(document, "Label", None),
            undo_names,
            tuple(
                (
                    obj,
                    getattr(obj, "Name", None),
                    getattr(obj, "Label", None),
                    tuple(getattr(obj, "State", ())),
                    tuple(getattr(obj, "Group", ()))
                    if obj.isDerivedFrom("PartDesign::Body")
                    else None,
                    getattr(obj, "Tip", None) if obj.isDerivedFrom("PartDesign::Body") else None,
                )
                for obj in objects
            ),
        )

    def track(self, document):
        self._candidate = {
            "document": document,
            "name": getattr(document, "Name", ""),
            "snapshot": self._snapshot(document),
        }

    def _is_untouched(self, candidate):
        document = candidate["document"]
        return (
            not getattr(document, "FileName", "")
            and self._snapshot(document) == candidate["snapshot"]
        )

    def untouched_document(self):
        candidate = self._candidate
        if candidate is not None and self._is_untouched(candidate):
            return candidate["document"]
        return None

    def slotActivateDocument(self, document):
        candidate = self._candidate
        if candidate is None or document is candidate["document"]:
            return
        self._candidate = None
        if not self._is_untouched(candidate):
            return
        try:
            App.closeDocument(candidate["name"])
        except Exception as error:
            record_startup_failure("discard untouched auto-created document", error)

    # Compatibility aliases for older downstream bindings and existing macros.
    slotActiveDocument = slotActivateDocument
    slotActivatedDocument = slotActivateDocument

    def slotDeletedDocument(self, document):
        if self._candidate is not None and document is self._candidate["document"]:
            self._candidate = None

    slotDeleteDocument = slotDeletedDocument
    slotFinishInvDoc = slotDeletedDocument


def track_auto_created_document(document):
    """Mark an FMF-created placeholder for silent disposal if left untouched."""
    if _auto_created_document_observer is not None:
        _auto_created_document_observer.track(document)


def untouched_auto_created_document():
    """Return FMF's untouched placeholder document, if one is still tracked."""
    if _auto_created_document_observer is None:
        return None
    return _auto_created_document_observer.untouched_document()


class _SketchRepairObserver:
    """Ensure sketch.InternalShape contains all planar faces whenever a sketch recomputes."""

    _updating = False

    def slotChangedObject(self, obj, prop):
        if self._updating:
            return
        if (
            prop == "Shape"
            and hasattr(obj, "isDerivedFrom")
            and obj.isDerivedFrom("Sketcher::SketchObject")
        ):
            self._updating = True
            try:
                import fmf_sketch_tools

                # Not while the sketch is open for editing. The solver
                # recomputes on every frame of a drag, and rebuilding the face
                # decomposition there meant an OpenCASCADE boolean per frame --
                # which is what made editing slow down as a sketch grew. The
                # decomposition is only needed once the sketch is used as a
                # profile, so it is rebuilt on leaving edit instead.
                if fmf_sketch_tools.active_sketch() is not obj:
                    fmf_sketch_tools.repair_sketch_internal_faces(obj)
            except Exception as error:
                record_startup_failure("rebuild sketch faces after shape change", error)
            finally:
                self._updating = False
        elif (
            prop == "Profile"
            and hasattr(obj, "isDerivedFrom")
            and (obj.isDerivedFrom("PartDesign::Pad") or obj.isDerivedFrom("PartDesign::Pocket"))
        ):
            self._updating = True
            try:
                profile_tuple = getattr(obj, "Profile", None)
                if (
                    profile_tuple
                    and isinstance(profile_tuple, (tuple, list))
                    and len(profile_tuple) >= 2
                ):
                    sketch_obj, sub_elements = profile_tuple[0], profile_tuple[1]
                    is_empty_subs = (
                        not sub_elements or sub_elements == [""] or sub_elements == ("",)
                    )
                    if sketch_obj and hasattr(sketch_obj, "InternalShape") and is_empty_subs:
                        int_faces = getattr(sketch_obj.InternalShape, "Faces", []) or []
                        if len(int_faces) > 1:
                            sketch_obj.Visibility = True
                        elif len(int_faces) == 1:
                            sk_shape = getattr(sketch_obj, "Shape", None)
                            wires = getattr(sk_shape, "Wires", []) or []
                            has_open_or_multi_wires = len(wires) > 1 or any(
                                not getattr(w, "isClosed", lambda: True)() for w in wires
                            )
                            if has_open_or_multi_wires:
                                obj.Profile = (sketch_obj, ["InternalFace1"])
                                if hasattr(obj, "recompute"):
                                    obj.recompute()
                                doc = getattr(obj, "Document", None)
                                if doc is not None and hasattr(doc, "recompute"):
                                    doc.recompute()
                                shape = getattr(obj, "Shape", None)
                                if shape is not None and hasattr(obj, "Reversed"):
                                    solids = (
                                        getattr(shape, "Solids", ())
                                        if not getattr(shape, "isNull", lambda: False)()
                                        else ()
                                    )
                                    if len(solids) == 0 or len(solids) > 1:
                                        prev_rev = getattr(obj, "Reversed", False)
                                        obj.Reversed = not prev_rev
                                        if hasattr(obj, "recompute"):
                                            obj.recompute()
                                        if doc is not None and hasattr(doc, "recompute"):
                                            doc.recompute()
                                        flipped_shape = getattr(obj, "Shape", None)
                                        flipped_solids = (
                                            getattr(flipped_shape, "Solids", ())
                                            if flipped_shape is not None
                                            and not getattr(flipped_shape, "isNull", lambda: True)()
                                            else ()
                                        )
                                        if not (
                                            len(flipped_solids) == 1
                                            or (len(solids) == 0 and len(flipped_solids) > 0)
                                        ):
                                            obj.Reversed = prev_rev
                                            if hasattr(obj, "recompute"):
                                                obj.recompute()
                                            if doc is not None and hasattr(doc, "recompute"):
                                                doc.recompute()
            except Exception as error:
                record_startup_failure("restore multi-region Pad profile visibility", error)
            finally:
                self._updating = False


_sketch_edit_observer = None
_sketch_repair_observer = None
_pad_selection_observer = None


class _PadSelectionObserver:
    """Allow Fusion 360-style profile selection: click Extrude first, then click profile in 3D."""

    _busy = False

    def addSelection(self, doc_name, obj_name, sub_name, mouse_pos=None):
        if self._busy or not sub_name:
            return
        sub_part = sub_name.split(".")[-1]
        if not sub_part.startswith("InternalFace"):
            return

        try:
            doc = App.getDocument(doc_name) if hasattr(App, "getDocument") else None
            if not doc:
                return

            sketch_obj = None
            if "." in sub_name:
                sketch_obj = doc.getObject(sub_name.split(".")[0])
            if not sketch_obj:
                sketch_obj = doc.getObject(obj_name)
            if not sketch_obj or not (
                hasattr(sketch_obj, "isDerivedFrom")
                and sketch_obj.isDerivedFrom("Sketcher::SketchObject")
            ):
                return

            pads = [
                o
                for o in doc.Objects
                if hasattr(o, "isDerivedFrom") and o.isDerivedFrom("PartDesign::Pad")
            ]
            if not pads:
                return

            target_pad = None
            gui_doc = Gui.getDocument(doc_name) if hasattr(Gui, "getDocument") else None
            in_edit_obj = getattr(gui_doc, "InEdit", None) if gui_doc else None
            for p in pads:
                if p == in_edit_obj:
                    target_pad = p
                    break

            if not target_pad:
                for p in reversed(pads):
                    profile = getattr(p, "Profile", None)
                    if profile and isinstance(profile, (tuple, list)) and len(profile) >= 2:
                        if profile[0] == sketch_obj:
                            target_pad = p
                            break

            if target_pad:
                self._busy = True
                previous_profile = target_pad.Profile
                previous_reversed = getattr(target_pad, "Reversed", False)
                previous_visibility = getattr(sketch_obj, "Visibility", True)

                # Determine accumulated or toggled profile sub-elements
                current_subs = []
                if (
                    isinstance(previous_profile, (tuple, list))
                    and len(previous_profile) >= 2
                    and previous_profile[0] == sketch_obj
                ):
                    raw_subs = previous_profile[1]
                    if isinstance(raw_subs, (tuple, list)):
                        current_subs = [str(s) for s in raw_subs if s and s != ""]

                if sub_part in current_subs:
                    current_subs.remove(sub_part)
                else:
                    current_subs.append(sub_part)

                new_subs = current_subs if current_subs else [""]
                new_profile = (sketch_obj, new_subs)

                try:
                    target_pad.Profile = new_profile
                    target_pad.recompute()
                    doc.recompute()

                    # Guard against empty or disconnected multi-solid shape upon boolean fuse
                    shape = getattr(target_pad, "Shape", None)
                    if shape is not None:
                        solids = (
                            getattr(shape, "Solids", ())
                            if not getattr(shape, "isNull", lambda: False)()
                            else ()
                        )
                        needs_recovery = len(solids) == 0 or len(solids) > 1
                        if needs_recovery and hasattr(target_pad, "Reversed"):
                            target_pad.Reversed = not previous_reversed
                            target_pad.recompute()
                            doc.recompute()
                            flipped_shape = getattr(target_pad, "Shape", None)
                            flipped_solids = (
                                getattr(flipped_shape, "Solids", ())
                                if flipped_shape is not None
                                and not getattr(flipped_shape, "isNull", lambda: True)()
                                else ()
                            )
                            if len(flipped_solids) == 1 or (
                                len(solids) == 0 and len(flipped_solids) > 0
                            ):
                                try:
                                    import fmf_common as diagnostics

                                    diagnostics.event(
                                        "info",
                                        "pad",
                                        "auto_reverse",
                                        "recovered_empty_solid",
                                        reversed=target_pad.Reversed,
                                    )
                                except Exception:
                                    pass
                            elif len(solids) == 0:
                                # Revert if flipping also fails to produce any solid
                                target_pad.Reversed = previous_reversed
                                target_pad.Profile = previous_profile
                                target_pad.recompute()
                                doc.recompute()
                            else:
                                # Keep new profile in original direction if flipping didn't help
                                target_pad.Reversed = previous_reversed
                                target_pad.recompute()
                                doc.recompute()

                    sketch_obj.Visibility = False
                except Exception:
                    target_pad.Profile = previous_profile
                    if hasattr(target_pad, "Reversed"):
                        target_pad.Reversed = previous_reversed
                    sketch_obj.Visibility = previous_visibility
                    raise
                finally:
                    self._busy = False
                    try:
                        import fmf_extrude

                        fmf_extrude.enhance_active_extrude()
                    except Exception:
                        pass
        except Exception as error:
            record_startup_failure("assign selected sketch region to Pad", error)

    def removeSelection(self, doc_name, obj_name, sub_name, mouse_pos=None):
        pass

    def clearSelection(self, doc_name):
        pass

    def setSelection(self, doc_name):
        pass


_lifecycle_commands_registered = False
_feature_commands_registered = False


def register_lifecycle_commands():
    global _lifecycle_commands_registered
    if _lifecycle_commands_registered:
        return
    Gui.addCommand("FMF_Verify", VerifyCommand())
    Gui.addCommand("FMF_Reapply", ReapplyCommand())
    # Keep the historical command ID so saved toolbar/menu customizations continue
    # to resolve, but expose unambiguous enable/disable wording to users.
    Gui.addCommand("FMF_Restore", DisableCommand())
    Gui.addCommand("FMF_Enable", EnableCommand())
    Gui.addCommand("FMF_ReviewShortcuts", ReviewShortcutsCommand())
    Gui.addCommand("FMF_OpenDiagnostics", OpenDiagnosticsCommand())
    Gui.addCommand("FMF_CopyDiagnostics", CopyDiagnosticsCommand())
    _lifecycle_commands_registered = True


def install_lifecycle_menu():
    """Keep FMF activation controls discoverable when its ribbon is disabled."""
    from PySide import QtGui, QtWidgets

    main_window = Gui.getMainWindow()
    menu_bar = main_window.menuBar()
    if not hasattr(menu_bar, "addMenu"):
        return None
    menu = main_window.findChild(QtWidgets.QMenu, "FMF_LifecycleMenu")
    if menu is None:
        menu = menu_bar.addMenu("FMF")
        menu.setObjectName("FMF_LifecycleMenu")
    else:
        menu.clear()

    commands = (
        (("Enable FMF", "FMF_Enable"),)
        if not is_enabled()
        else (
            ("Verify FMF", "FMF_Verify"),
            ("Review FMF Shortcuts", "FMF_ReviewShortcuts"),
            ("Reset FMF", "FMF_Reapply"),
            ("Disable FMF", "FMF_Restore"),
        )
    )
    commands = (
        *commands,
        ("Copy Diagnostic Summary", "FMF_CopyDiagnostics"),
        ("Open Diagnostics Folder", "FMF_OpenDiagnostics"),
    )
    for label, command in commands:
        action = QtGui.QAction(label, menu)
        action.setObjectName(command + "_MenuAction")
        action.triggered.connect(
            lambda checked=False, command_name=command: Gui.runCommand(command_name)
        )
        menu.addAction(action)
    return menu


def _restore_native_ui_now():
    from PySide import QtCore, QtWidgets

    main_window = Gui.getMainWindow()
    was_maximized = main_window.isMaximized()
    flags = QtCore.Qt.WindowType
    main_window.setWindowFlag(flags.CustomizeWindowHint, False)
    for flag in (
        flags.WindowTitleHint,
        flags.WindowSystemMenuHint,
        flags.WindowMinimizeButtonHint,
        flags.WindowMaximizeButtonHint,
        flags.WindowCloseButtonHint,
    ):
        main_window.setWindowFlag(flag, True)

    main_window.menuBar().show()
    central_widget = main_window.centralWidget()
    if central_widget is not None:
        central_widget.show()
    ribbon = main_window.findChild(QtWidgets.QDockWidget, "Ribbon")
    if ribbon is not None:
        ribbon.hide()
    for toolbar in main_window.findChildren(QtWidgets.QToolBar):
        name = toolbar.objectName() if hasattr(toolbar, "objectName") else ""
        if name in {"SearchBar", "SearchBarAtMouse"}:
            toolbar.hide()
    if was_maximized:
        main_window.showMaximized()
    else:
        main_window.show()


def restore_disabled_native_ui():
    """Restore stock tabs while keeping the bundled Ribbon usable."""
    from PySide import QtCore

    # FreeCAD applies its persisted QMainWindow state after add-on InitGui files.
    # Run once the event loop starts so the native UI wins that ordering race.
    def restore_and_record():
        import fmf_common as diagnostics

        if owned_workbenches_enabled():
            set_owned_workbench_visibility(False)
            sync_start_workbench(False)
            set_ribbon_workbench_family(False)
        diagnostics.event("info", "ui", "disabled restoration", "healthy")
        diagnostics.set_status("healthy", enabled=False, stockTabsRestored=True)

    QtCore.QTimer.singleShot(0, restore_and_record)


_activation_parameter_group = None
_activation_monitor = None
_observed_enabled = None
_activation_transition = False


class _ActivationPreferenceObserver:
    """Bridge FreeCAD parameter notifications into FMF's activation state machine."""

    def onChange(self, _group, name, *details):
        # FreeCAD currently reports ``(group, name)`` while older bindings and
        # the parameter API's documented shape include the value type first.
        if name == "Enabled" or (details and details[0] == "Enabled"):
            reconcile_activation_preference()


def reconcile_activation_preference():
    """Apply an Enable FMF preference change immediately in the running GUI."""
    global _observed_enabled, _activation_transition
    enabled = is_enabled()
    if _activation_transition or enabled == _observed_enabled:
        return
    previous = _observed_enabled
    _observed_enabled = enabled
    _activation_transition = True
    try:
        if enabled:
            enable()
        else:
            disable()
    except Exception as error:
        App.ParamGet(PREFERENCE_ROOT).SetBool("Enabled", bool(previous))
        App.saveParameter()
        _observed_enabled = previous
        record_startup_failure("live activation preference", error)
        App.Console.PrintError("FMF: live activation preference failed: {}\n".format(error))
    finally:
        _activation_transition = False


def install_activation_monitor():
    """Observe the Preferences checkbox without keeping an idle timer alive."""
    global _activation_parameter_group, _activation_monitor, _observed_enabled
    if _activation_monitor is not None:
        return
    _observed_enabled = is_enabled()
    _activation_parameter_group = App.ParamGet(PREFERENCE_ROOT)
    _activation_monitor = _ActivationPreferenceObserver()
    _activation_parameter_group.Attach(_activation_monitor)
    try:
        import fmf_lifecycle as lifecycle

        lifecycle.register_observer(
            "parameter", "activation", _activation_parameter_group, _activation_monitor
        )
    except Exception:
        pass


def uninstall_activation_monitor():
    """Detach the long-lived parameter observer during application teardown."""
    global _activation_parameter_group, _activation_monitor
    if _activation_monitor is None:
        return
    try:
        _activation_parameter_group.Detach(_activation_monitor)
    except Exception:
        pass
    try:
        import fmf_lifecycle as lifecycle

        lifecycle.unregister_observer("parameter", "activation")
    except Exception:
        pass
    _activation_parameter_group = None
    _activation_monitor = None


def validate_enabled_ui():
    """Validate the chrome appropriate to the active owned or native workbench."""
    from PySide import QtCore, QtWidgets

    def validate():
        import fmf_common as diagnostics

        main_window = Gui.getMainWindow()
        ribbon = main_window.findChild(QtWidgets.QDockWidget, "Ribbon")

        def safe(function, default=None):
            try:
                return function()
            except Exception:
                return default

        active_workbench = safe(lambda: Gui.activeWorkbench().name(), "unknown")
        central_widget = safe(lambda: main_window.centralWidget())
        window_visible = safe(lambda: main_window.isVisible())
        window_minimized = safe(lambda: main_window.isMinimized(), False)
        snapshot = {
            "activeWorkbench": active_workbench,
            "windowFlags": safe(lambda: int(main_window.windowFlags())),
            "windowVisible": window_visible,
            "windowMinimized": window_minimized,
            "menuVisible": safe(lambda: main_window.menuBar().isVisible()),
            "centralWidgetVisible": bool(
                central_widget and safe(lambda: central_widget.isVisible(), False)
            ),
            "ribbonPresent": ribbon is not None,
            "ribbonVisible": bool(ribbon and safe(lambda: ribbon.isVisible(), False)),
            "ribbonHeight": safe(lambda: ribbon.height()) if ribbon is not None else None,
            "visibleToolbars": [
                safe(lambda toolbar=toolbar: toolbar.objectName(), "unknown")
                for toolbar in main_window.findChildren(QtWidgets.QToolBar)
                if safe(lambda toolbar=toolbar: toolbar.isVisible(), False)
            ],
        }
        # A hidden/background FreeCAD process cannot provide meaningful visual
        # health evidence. In particular, automation may intentionally launch
        # FreeCAD with a hidden top-level window. Do not turn a persistent user
        # preference off based on that diagnostic-only state.
        if window_visible is False or window_minimized:
            failures = startup_failures()
            state = "degraded" if failures else "validation_deferred"
            diagnostics.event("info", "ui", "enabled validation", state, **snapshot)
            diagnostics.set_status(state, startupFailures=failures, **snapshot)
            return

        owned_active = fmf_workbench_for(active_workbench) in OWNED_TO_NATIVE_WORKBENCH
        ribbon_usable = bool(
            ribbon
            and safe(lambda: ribbon.isVisible(), False)
            and (safe(lambda: ribbon.height(), 0) or 0) > 0
        )
        native_usable = bool(
            not owned_active
            and safe(lambda: main_window.menuBar().isVisible(), False)
            and central_widget
            and safe(lambda: central_widget.isVisible(), False)
        )
        if (owned_active and ribbon_usable) or native_usable:
            failures = startup_failures()
            state = "degraded" if failures else "healthy"
            diagnostics.event("info", "ui", "enabled validation", state, **snapshot)
            diagnostics.set_status(state, startupFailures=failures, **snapshot)
            return

        message = (
            "The active workbench did not produce usable application chrome; "
            "activation was rolled back"
        )
        App.Console.PrintError("FMF: {}.\n".format(message))
        record_startup_failure("enabled UI validation", RuntimeError(message))
        App.ParamGet(PREFERENCE_ROOT).SetBool("Enabled", False)
        App.saveParameter()
        diagnostics.event("error", "ui", "enabled validation", "rolled_back", **snapshot)
        diagnostics.set_status("activation_rolled_back", reason=message, **snapshot)
        _restore_native_ui_now()
        install_lifecycle_menu()

    # Ribbon construction is synchronous during InitGui, but FreeCAD applies
    # final visibility only when the event loop begins.
    QtCore.QTimer.singleShot(0, validate)


class OpenDiagnosticsCommand:
    def GetResources(self):
        return {"MenuText": "Open Diagnostics Folder", "ToolTip": "Open FMF diagnostic files"}

    def Activated(self):
        from PySide import QtCore, QtGui

        import fmf_common as diagnostics

        os.makedirs(diagnostics.DIAGNOSTICS_DIR, exist_ok=True)
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(diagnostics.DIAGNOSTICS_DIR))


class CopyDiagnosticsCommand:
    def GetResources(self):
        return {"MenuText": "Copy Diagnostic Summary", "ToolTip": "Copy FMF health summary"}

    def Activated(self):
        from PySide import QtWidgets

        import fmf_common as diagnostics

        QtWidgets.QApplication.clipboard().setText(diagnostics.diagnostic_summary())


def register_commands():
    global _feature_commands_registered
    global _auto_created_document_observer
    global _sketch_edit_observer, _sketch_repair_observer, _pad_selection_observer
    register_lifecycle_commands()
    if _feature_commands_registered:
        return
    Gui.addCommand("FMF_CreateSketch", CreateSketchCommand())
    Gui.addCommand("FMF_RecentDocuments", RecentDocumentsCommand())
    Gui.addCommand("FMF_ParameterTable", ParameterTableCommand())

    if _sketch_edit_observer is None and hasattr(Gui, "addDocumentObserver"):
        _sketch_edit_observer = _SketchEditWorkbenchObserver()
        Gui.addDocumentObserver(_sketch_edit_observer)
        try:
            import fmf_lifecycle as lifecycle

            lifecycle.register_observer("gui", "sketch_edit", Gui, _sketch_edit_observer)
        except Exception:
            pass
    if _sketch_repair_observer is None and hasattr(App, "addDocumentObserver"):
        _sketch_repair_observer = _SketchRepairObserver()
        App.addDocumentObserver(_sketch_repair_observer)
        try:
            import fmf_lifecycle as lifecycle

            lifecycle.register_observer("app", "sketch_repair", App, _sketch_repair_observer)
        except Exception:
            pass
    if _auto_created_document_observer is None and hasattr(App, "addDocumentObserver"):
        _auto_created_document_observer = _AutoCreatedDocumentObserver()
        App.addDocumentObserver(_auto_created_document_observer)
        try:
            import fmf_lifecycle as lifecycle

            lifecycle.register_observer(
                "app", "auto_created_doc", App, _auto_created_document_observer
            )
        except Exception:
            pass
    if (
        _pad_selection_observer is None
        and hasattr(Gui, "Selection")
        and hasattr(Gui.Selection, "addObserver")
    ):
        _pad_selection_observer = _PadSelectionObserver()
        Gui.Selection.addObserver(_pad_selection_observer)
        try:
            import fmf_lifecycle as lifecycle

            lifecycle.register_observer(
                "selection", "pad", getattr(Gui, "Selection", None), _pad_selection_observer
            )
        except Exception:
            pass

    import fmf_datum_tools
    import fmf_dressup_tools
    import fmf_export
    import fmf_extrude
    import fmf_parameters_dock
    import fmf_repair_tools
    import fmf_sketch_tools
    import fmf_viewport

    fmf_sketch_tools.register()
    fmf_datum_tools.register()
    fmf_dressup_tools.register()
    fmf_export.register()
    fmf_extrude.register()
    fmf_parameters_dock.register()
    fmf_repair_tools.register()
    fmf_viewport.register()
    _feature_commands_registered = True


def unregister_feature_observers():
    """Detach FMF observers and filters when disabling within a live session."""
    global _feature_commands_registered
    global _auto_created_document_observer
    global _sketch_edit_observer, _sketch_repair_observer, _pad_selection_observer
    if _sketch_edit_observer is not None and hasattr(Gui, "removeDocumentObserver"):
        try:
            Gui.removeDocumentObserver(_sketch_edit_observer)
        except Exception:
            pass
        _sketch_edit_observer = None
    try:
        import fmf_lifecycle as lifecycle

        lifecycle.unregister_observer("gui", "sketch_edit")
    except Exception:
        pass
    if _sketch_repair_observer is not None and hasattr(App, "removeDocumentObserver"):
        try:
            App.removeDocumentObserver(_sketch_repair_observer)
        except Exception:
            pass
        _sketch_repair_observer = None
    try:
        import fmf_lifecycle as lifecycle

        lifecycle.unregister_observer("app", "sketch_repair")
    except Exception:
        pass
    if _auto_created_document_observer is not None and hasattr(App, "removeDocumentObserver"):
        try:
            App.removeDocumentObserver(_auto_created_document_observer)
        except Exception:
            pass
        _auto_created_document_observer = None
    try:
        import fmf_lifecycle as lifecycle

        lifecycle.unregister_observer("app", "auto_created_doc")
    except Exception:
        pass
    if (
        _pad_selection_observer is not None
        and hasattr(Gui, "Selection")
        and hasattr(Gui.Selection, "removeObserver")
    ):
        try:
            Gui.Selection.removeObserver(_pad_selection_observer)
        except Exception:
            pass
        _pad_selection_observer = None
    try:
        import fmf_lifecycle as lifecycle

        lifecycle.unregister_observer("selection", "pad")
    except Exception:
        pass
    try:
        import fmf_dressup_tools

        fmf_dressup_tools.uninstall_dressup_enhancers()
    except Exception:
        pass
    try:
        import fmf_parameters_dock

        fmf_parameters_dock.close_parameters_dock()
    except Exception:
        pass
    # Commands may remain registered with FreeCAD, but the services installed
    # alongside them were deliberately detached. A live re-enable must run the
    # idempotent registration path again instead of treating this as installed.
    _feature_commands_registered = False


# ---------------------------------------------------------------------------
# Module loading
# ---------------------------------------------------------------------------


_loaded = set()
_vendor_provenance = {}


def get_vendor_provenance():
    """Return verified file paths of loaded or reused vendor modules."""
    return dict(_vendor_provenance)


# A standalone installation of either bundled add-on leaves these modules behind.
# Reusing it avoids duplicate ribbon docks and search toolbars.
VENDOR_SENTINELS = {
    "FreeCAD_Ribbon": ("FCBinding", "RibbonUI", "Parameters_Ribbon"),
    "SearchBar": ("Parameters_SearchBar", "SearchBox", "SearchBoxLight"),
}


def _execute_module(module_name, path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError("Could not load {}".format(path))
    module = importlib.util.module_from_spec(spec)
    missing = object()
    previous = sys.modules.get(module_name, missing)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        # Import machinery normally removes a failed import.  Because this
        # loader manages sys.modules itself, it must provide the same guarantee
        # or a retry can observe and reuse a half-initialized module.
        if previous is missing:
            sys.modules.pop(module_name, None)
        else:
            sys.modules[module_name] = previous
        raise
    return module


def run_runtime():
    if "runtime" in _loaded:
        runtime = sys.modules.get("_fmf_my_freecad_runtime")
        if runtime is not None and hasattr(runtime, "install"):
            runtime.install()
        return
    _execute_module("_fmf_my_freecad_runtime", RUNTIME)
    _loaded.add("runtime")


def _install_ribbon_host_adapter():
    """Adapt bundled FreeCAD-Ribbon to FMF's workbench family and search styling."""
    params_mod = sys.modules.get("Parameters_Ribbon")
    if params_mod is not None and is_enabled() and owned_workbenches_enabled():
        params_cls = getattr(params_mod, "Parameters", None)
        if params_cls is not None:
            existing_order = _workbench_list(getattr(params_cls, "TAB_ORDER", ""))
            owned = list(OWNED_TO_NATIVE_WORKBENCH)
            merged_order = owned + [wb for wb in existing_order if wb not in owned]
            params_cls.TAB_ORDER = ",".join(dict.fromkeys(merged_order))

    fc_binding = sys.modules.get("FCBinding")
    if fc_binding is None:
        return
    modern_menu = getattr(fc_binding, "ModernMenu", None)
    if modern_menu is None or getattr(modern_menu, "_fmf_host_adapter_installed", False):
        return

    original_select = getattr(modern_menu, "selectFmfWorkbenchContext", None)
    if callable(original_select):

        def _adapted_select_fmf_workbench_context(
            self, workbenchName, buildIfNeeded=True
        ):
            target_name = fmf_workbench_for(workbenchName) or workbenchName
            try:
                tab_bar = self.tabBar() if hasattr(self, "tabBar") else None
                if tab_bar is not None and hasattr(tab_bar, "setTabVisible"):
                    family_enabled = is_enabled() and owned_workbenches_enabled()
                    owned_set = set(OWNED_TO_NATIVE_WORKBENCH)
                    native_set = set(OWNED_TO_NATIVE_WORKBENCH.values())
                    for idx in range(tab_bar.count()):
                        wb = tab_bar.tabData(idx)
                        if wb in owned_set:
                            tab_bar.setTabVisible(idx, family_enabled)
                        elif wb in native_set:
                            tab_bar.setTabVisible(idx, not family_enabled)
            except Exception:
                pass
            result = original_select(self, target_name, buildIfNeeded=buildIfNeeded)
            try:
                if hasattr(self, "rightToolBar") and self.rightToolBar() is not None:
                    self.rightToolBar().setEnabled(True)
            except Exception:
                pass
            return result

        modern_menu.selectFmfWorkbenchContext = _adapted_select_fmf_workbench_context

    original_auth = getattr(modern_menu, "_fmfAuthoritativeWorkbenchActive", None)
    if callable(original_auth):

        def _adapted_authoritative_workbench_active(self):
            if not is_enabled():
                return False
            auth_list = self.ribbonStructure.get("authoritativeWorkbenches", [])
            try:
                active = fmf_workbench_for(Gui.activeWorkbench().name())
                if active in auth_list:
                    return True
            except Exception:
                pass
            try:
                tab_bar = self.tabBar()
                current_tab = fmf_workbench_for(
                    tab_bar.tabData(tab_bar.currentIndex())
                )
                if current_tab in auth_list:
                    return True
            except Exception:
                pass
            return bool(original_auth(self))

        modern_menu._fmfAuthoritativeWorkbenchActive = (
            _adapted_authoritative_workbench_active
        )

    original_add_search = getattr(modern_menu, "AddSearchBar", None)
    if callable(original_add_search):

        def _adapted_add_search_bar(self):
            width = original_add_search(self)
            try:
                from PySide import QtWidgets

                right_tb = self.rightToolBar() if hasattr(self, "rightToolBar") else None
                if right_tb is not None:
                    right_tb.setEnabled(True)
                    for edit in right_tb.findChildren(QtWidgets.QLineEdit):
                        edit.setEnabled(True)
                        edit.setPlaceholderText("Search commands (/ or S)...")
                        edit.setStyleSheet(
                            "QLineEdit {"
                            "  background-color: palette(base);"
                            "  color: palette(text);"
                            "  border: 1px solid palette(mid);"
                            "  border-radius: 4px;"
                            "  padding: 2px 6px;"
                            "}"
                            "QLineEdit:focus {"
                            "  border: 1px solid #3b82f6;"
                            "}"
                        )
            except Exception:
                pass
            return width

        modern_menu.AddSearchBar = _adapted_add_search_bar

    modern_menu._fmf_host_adapter_installed = True


def _install_searchbar_host_adapter():
    """Eliminate SearchBar event-filter lag, click swallowing, and toolbar flicker."""
    mouse_bar_mod = sys.modules.get("MouseBar")
    if mouse_bar_mod is not None:
        inspector_cls = getattr(mouse_bar_mod, "EventInspector_SB", None)
        if inspector_cls is not None and not getattr(
            inspector_cls, "_fmf_host_adapter_installed", False
        ):

            def _adapted_event_filter(self, obj, event):
                try:
                    from PySide.QtCore import QEvent, Qt
                    from PySide.QtGui import QKeySequence
                    from PySide.QtWidgets import (
                        QAbstractSpinBox,
                        QApplication,
                        QDockWidget,
                        QLineEdit,
                        QPlainTextEdit,
                        QTextEdit,
                        QToolBar,
                    )
                except ImportError:
                    return False

                ev_type = event.type()
                if ev_type in (
                    QEvent.Type.MouseButtonRelease,
                    QEvent.Type.GraphicsSceneMouseRelease,
                ):
                    try:
                        mw = Gui.getMainWindow()
                        mouse_bar = (
                            mw.findChild(QToolBar, "SearchBarAtMouse")
                            if mw is not None
                            else None
                        )
                        if (
                            mouse_bar is not None
                            and mouse_bar.isVisible()
                            and not mouse_bar.underMouse()
                        ):
                            parent = mouse_bar.parent()
                            top = parent.parent() if parent is not None else None
                            if top is not None:
                                top.close()
                    except Exception:
                        pass
                    return False

                if ev_type != QEvent.Type.KeyPress:
                    return False

                key_val = event.key()
                if key_val == Qt.Key.Key_Escape:
                    try:
                        mw = Gui.getMainWindow()
                        mouse_bar = (
                            mw.findChild(QToolBar, "SearchBarAtMouse")
                            if mw is not None
                            else None
                        )
                        if (
                            mouse_bar is not None
                            and mouse_bar.isVisible()
                            and not mouse_bar.underMouse()
                        ):
                            parent = mouse_bar.parent()
                            top = parent.parent() if parent is not None else None
                            if top is not None:
                                top.close()
                    except Exception:
                        pass
                    return False

                focus_widget = QApplication.focusWidget()
                if isinstance(
                    focus_widget,
                    (QLineEdit, QAbstractSpinBox, QTextEdit, QPlainTextEdit),
                ):
                    return False

                shortcut_key = "S"
                try:
                    custom_shortcuts = App.ParamGet(
                        "User parameter:BaseApp/Preferences/Shortcut"
                    )
                    if "SearchBar" in custom_shortcuts.GetStrings():
                        shortcut_key = custom_shortcuts.GetString("SearchBar") or "S"
                except Exception:
                    pass

                modifier = None
                parts = shortcut_key.split("+")
                if len(parts) > 1:
                    mod_name = parts[0].strip().lower()
                    if mod_name == "alt":
                        modifier = Qt.KeyboardModifier.AltModifier
                    elif mod_name == "ctrl":
                        modifier = Qt.KeyboardModifier.ControlModifier
                    elif mod_name == "shift":
                        modifier = Qt.KeyboardModifier.ShiftModifier
                    target_seq = QKeySequence(parts[1].strip())
                else:
                    target_seq = QKeySequence(shortcut_key.strip())

                if modifier is not None:
                    if not (event.modifiers() & modifier) or key_val != target_seq:
                        return False
                else:
                    if (
                        event.modifiers()
                        & (
                            Qt.KeyboardModifier.ControlModifier
                            | Qt.KeyboardModifier.AltModifier
                        )
                    ) or key_val != target_seq:
                        return False

                mw = Gui.getMainWindow()
                if mw is None:
                    return False

                toolbar = mw.findChild(QToolBar, "SearchBar")
                if toolbar is not None and toolbar.isVisible() and toolbar.underMouse():
                    return False

                try:
                    dw = mw.findChild(QDockWidget, "Ribbon")
                    ribbon = dw.widget() if dw is not None else None
                    right_tb = (
                        ribbon.rightToolBar()
                        if ribbon is not None and hasattr(ribbon, "rightToolBar")
                        else None
                    )
                    if right_tb is not None and right_tb.underMouse():
                        return False
                except Exception:
                    pass

                Gui.runCommand("SearchBar")
                mouse_bar = mw.findChild(QToolBar, "SearchBarAtMouse")
                if mouse_bar is not None and mouse_bar.isVisible():
                    try:
                        import Parameters_SearchBar

                        if (
                            Parameters_SearchBar.Settings.GetBoolSetting(
                                "AutoFocusMouseBarEnabled", True
                            )
                            is True
                        ):
                            child = mouse_bar.findChild(QLineEdit)
                            if child is not None:
                                child.setFocus()
                    except Exception:
                        pass
                return True

            inspector_cls.eventFilter = _adapted_event_filter
            inspector_cls._fmf_host_adapter_installed = True

    search_vendor = sys.modules.get("_fmf_vendor_SearchBar")
    search_bar_cls = (
        getattr(search_vendor, "SearchBar", None) if search_vendor is not None else None
    )
    if search_bar_cls is not None and not getattr(
        search_bar_cls, "_fmf_host_adapter_installed", False
    ):
        original_add_tool = getattr(search_bar_cls, "addToolSearchBox", None)
        if callable(original_add_tool):

            def _adapted_add_tool_search_box():
                result = original_add_tool()
                try:
                    from PySide import QtWidgets

                    mw = Gui.getMainWindow()
                    if mw is not None and is_enabled():
                        ribbon_dock = mw.findChild(QtWidgets.QDockWidget, "Ribbon")
                        if ribbon_dock is not None:
                            tbr = mw.findChild(QtWidgets.QToolBar, "SearchBar")
                            if tbr is not None:
                                tbr.hide()
                except Exception:
                    pass
                return result

            search_bar_cls.addToolSearchBox = _adapted_add_tool_search_box
            search_bar_cls._fmf_host_adapter_installed = True

    search_box_mod = sys.modules.get("SearchBox")
    if search_box_mod is not None and not getattr(
        search_box_mod, "_fmf_host_adapter_installed", False
    ):
        orig_searchable = getattr(search_box_mod, "fmfSearchableText", None)
        orig_score = getattr(search_box_mod, "fmfSearchScore", None)
        if callable(orig_searchable):

            def _cached_searchable_text(group):
                if isinstance(group, dict):
                    cached = group.get("_fmf_searchable_cache")
                    if cached is not None:
                        return cached
                    computed = orig_searchable(group)
                    group["_fmf_searchable_cache"] = computed
                    return computed
                return orig_searchable(group)

            search_box_mod.fmfSearchableText = _cached_searchable_text
        if callable(orig_score):

            def _fast_search_score(group, search_text):
                if not (search_text or "").strip():
                    return 0.0
                return orig_score(group, search_text)

            search_box_mod.fmfSearchScore = _fast_search_score
        search_box_mod._fmf_host_adapter_installed = True


def _install_vendor_host_adapter(name):
    if name == "FreeCAD_Ribbon":
        _install_ribbon_host_adapter()
    elif name == "SearchBar":
        _install_searchbar_host_adapter()


def load_vendor(name, directory):
    import fmf_common as diagnostics

    started = datetime.now(UTC)
    if name in _loaded:
        _install_vendor_host_adapter(name)
        return
    if any(module in sys.modules for module in VENDOR_SENTINELS.get(name, ())):
        _loaded.add(name)
        for sentinel in VENDOR_SENTINELS.get(name, ()):
            mod = sys.modules.get(sentinel)
            if mod is not None and hasattr(mod, "__file__"):
                _vendor_provenance["{}:{}".format(name, sentinel)] = str(mod.__file__)
        _install_vendor_host_adapter(name)
        App.Console.PrintMessage("FMF is using the already active {}.\n".format(name))
        diagnostics.event("info", "vendor", name, "reused")
        return
    init_gui = os.path.join(directory, "InitGui.py")
    if not os.path.isfile(init_gui):
        raise RuntimeError("FMF vendor payload is incomplete: {}".format(init_gui))
    if directory not in sys.path:
        sys.path.insert(0, directory)
    try:
        _execute_module("_fmf_vendor_{}".format(name), init_gui)
        _install_vendor_host_adapter(name)
    except BaseException as error:
        diagnostics.diagnostic_exception("vendor", name, error, initGui=init_gui)
        raise
    _loaded.add(name)
    _vendor_provenance[name] = os.path.abspath(init_gui)
    diagnostics.event(
        "info",
        "vendor",
        name,
        "loaded",
        durationMs=round((datetime.now(UTC) - started).total_seconds() * 1000, 2),
        sentinels={module: module in sys.modules for module in VENDOR_SENTINELS.get(name, ())},
    )


def _startup_step(label, function, *arguments):
    """Run one startup step while preserving access to recovery commands."""
    import fmf_common as diagnostics

    started = time.perf_counter()
    diagnostics.event("info", "startup", label, "started", packageVersion=PACKAGE_VERSION)
    try:
        function(*arguments)
        diagnostics.event(
            "info",
            "startup",
            label,
            "completed",
            durationMs=round((time.perf_counter() - started) * 1000, 2),
            packageVersion=PACKAGE_VERSION,
        )
        return True
    except Exception as error:
        App.Console.PrintError("FMF: {} failed: {}\n".format(label, error))
        App.Console.PrintLog(traceback.format_exc())
        record_startup_failure(label, error)
        diagnostics.diagnostic_exception(
            "startup",
            label,
            error,
            durationMs=round((time.perf_counter() - started) * 1000, 2),
            packageVersion=PACKAGE_VERSION,
        )
        diagnostics.set_status("degraded", failedStep=label, error=str(error))
        return False


def start():
    """Initialize FMF from FreeCAD's function-scoped InitGui loader."""
    import fmf_common as diagnostics

    _migrate_previous_brand_data()
    clear_startup_failures()
    register_lifecycle_commands()
    register_preferences_page()
    install_lifecycle_menu()
    install_activation_monitor()
    _startup_step("lifecycle guards", install_lifecycle_guards)
    _startup_step("owned workbench registration", register_owned_workbenches)

    diagnostics.start_session(is_enabled(), PACKAGE_VERSION, App.Version())
    try:
        if is_enabled():
            _startup_step("native toolbar snapshot", capture_native_toolbar_visibility)
            _startup_step("feature command registration", register_commands)
            _startup_step("installation", prepare)
            _startup_step("runtime", run_runtime)
            _startup_step(
                "SearchBar",
                load_vendor,
                "SearchBar",
                os.path.join(ADDON_ROOT, "bundled-addons", "SearchBar"),
            )
            _startup_step("SearchBar services", _set_searchbar_service, True)
            _configure_ribbon_cache_scope()
            _startup_step(
                "FreeCAD Ribbon",
                load_vendor,
                "FreeCAD_Ribbon",
                os.path.join(ADDON_ROOT, "bundled-addons", "FreeCAD-Ribbon"),
            )
            _startup_step("UI mode synchronization", defer_ui_mode_sync)
            _startup_step("enabled UI validation", validate_enabled_ui)
        else:
            _startup_step("native UI restoration", restore_disabled_native_ui)
    except BaseException as error:
        App.Console.PrintError("FMF startup failed: {}\n".format(error))
        diagnostics.diagnostic_exception("startup", "top level", error)
        diagnostics.set_status("degraded", failedStep="top level", error=str(error))
    finally:
        diagnostics.flush_diagnostics()
