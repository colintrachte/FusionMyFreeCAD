"""Cross-platform installation, verification, restoration, and vendor loading."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import sys
import traceback
import xml.etree.ElementTree as ET
from datetime import UTC, datetime

import FreeCAD as App
import FreeCADGui as Gui

ADDON_ROOT = os.path.dirname(os.path.abspath(__file__))
RESOURCE_ROOT = os.path.join(ADDON_ROOT, "Resources", "FusionMyFreeCAD")
PACKAGE_PATH = os.path.join(ADDON_ROOT, "package.xml")
BASE_LAYOUT = os.path.join(RESOURCE_ROOT, "RibbonStructure.json")
LAYOUT_SPEC = os.path.join(RESOURCE_ROOT, "layout-v3.json")
MANIFEST = os.path.join(RESOURCE_ROOT, "layout-manifest.json")
RUNTIME = os.path.join(RESOURCE_ROOT, "runtime.py")
PREFERENCES_UI = os.path.join(RESOURCE_ROOT, "preferences.ui")
USER_ROOT = App.getUserAppDataDir()
RIBBON_DIR = os.path.join(USER_ROOT, "RibbonUI_Data")
RIBBON_PATH = os.path.join(RIBBON_DIR, "RibbonStructure.json")
STATE_PATH = os.path.join(USER_ROOT, "FusionMyFreeCAD-addon-state.json")
STARTUP_PATH = os.path.join(USER_ROOT, "FusionMyFreeCAD-startup.json")
STATUS_PATH = os.path.join(USER_ROOT, "FusionMyFreeCAD-runtime-status.json")
USAGE_PATH = os.path.join(USER_ROOT, "FusionMyFreeCAD-usage.json")
CUSTOMIZATION_PATH = os.path.join(USER_ROOT, "FusionMyFreeCAD-customization.json")
BACKUP_ROOT = os.path.join(USER_ROOT, "FusionMyFreeCAD-Backups")
# The baseline records the profile as it was before FusionMyFreeCAD first ran.
# It is written once and never rewritten, so a lost or corrupted state file can
# never cause FusionMyFreeCAD's own settings to be captured as the "previous UI".
BASELINE_PATH = os.path.join(BACKUP_ROOT, "baseline.json")
PREFERENCE_ROOT = "User parameter:BaseApp/Preferences/Mod/FusionMyFreeCAD"

STATE_SCHEMA = 2


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
            "FusionMyFreeCAD could not read {}: {}. Moved to {}.\n".format(path, error, quarantine)
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
    corresponding writes leaves the old FusionMyFreeCAD values in place.  This
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
    return customization if isinstance(workbenches, dict) else {}


def _reconcile_order(preferred, shipped):
    """Preserve known user order while inserting commands added by an update."""
    shipped = list(shipped)
    result = [item for item in preferred if item in shipped]
    result.extend(item for item in shipped if item not in result)
    return result


def _apply_customization(ribbon, spec, customization=None):
    customization = customization if customization is not None else _read_customization()
    customized = customization.get("workbenches", {})
    for workbench, panels in spec["workbenches"].items():
        saved_workbench = customized.get(workbench, {})
        toolbar_root = ribbon["workbenches"][workbench]["toolbars"]
        shipped_panel_order = [panel["name"] for panel in panels]
        toolbar_root["order"] = _reconcile_order(
            saved_workbench.get("panelOrder", []), shipped_panel_order
        )
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
    return ribbon


def _merge_layout(apply_customization=True):
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
    if apply_customization:
        _apply_customization(ribbon, spec)
    return ribbon, spec["layoutVersion"]


def record_customization(ribbon):
    """Persist safe user-owned layout choices after direct ribbon dragging."""
    spec = _load_json(LAYOUT_SPEC)
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
            saved_workbench["panels"][name] = {
                "order": order,
                "pinned": pinned,
                "enabled": bool(toolbar.get("Enabled", True)),
            }
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
    manifest = manifest if manifest is not None else _load_json(MANIFEST)
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
        spec = spec if spec is not None else _load_json(LAYOUT_SPEC)
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
            for key in ("panelMenu", "overflow", "responsive", "pinCount"):
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
    FusionMyFreeCAD, which an upgrade must not silently discard.
    """
    state = read_state()
    if state is None or not os.path.isfile(RIBBON_PATH):
        return False
    state["ribbonSha256"] = _sha256(RIBBON_PATH)
    state["ribbonHashUpdatedAt"] = _now()
    write_state(state)
    return True


def prepare():
    version = tuple(int(part) for part in App.Version()[:2])
    if version < (1, 1):
        raise RuntimeError("FusionMyFreeCAD requires FreeCAD 1.1 or newer.")
    for required in (BASE_LAYOUT, LAYOUT_SPEC, MANIFEST, RUNTIME):
        if not os.path.isfile(required):
            raise RuntimeError("FusionMyFreeCAD package is incomplete: {}".format(required))

    spec = _load_json(LAYOUT_SPEC)
    candidates = adaptive_candidates()
    state = read_state()
    if state is not None and not state.get("backupRoot"):
        # Schema drift or a hand-edited file: fall back to the reinstall path
        # rather than raising during FreeCAD startup.
        App.Console.PrintWarning(
            "FusionMyFreeCAD state is missing its backup location; "
            "reinstalling from the baseline.\n"
        )
        state = None

    if state is not None:
        _migrate_baseline_from_state(state)

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
                "FusionMyFreeCAD state was missing; reusing the original baseline at {}.\n".format(
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
                # The ribbon changed outside FusionMyFreeCAD. Replacing it is still
                # correct for an upgrade, but the user must be able to find the copy.
                state["externalRibbonEdit"] = update_path
                App.Console.PrintWarning(
                    "FusionMyFreeCAD replaced a ribbon layout that was edited outside the add-on. "
                    "The previous layout is kept at {}.\n".format(update_path)
                )

    ribbon, layout_version = _merge_layout()
    _atomic_json(RIBBON_PATH, ribbon)
    valid, checks, problems = _verify_layout(RIBBON_PATH, spec, candidates)
    if not valid:
        raise RuntimeError(
            "FusionMyFreeCAD generated an invalid ribbon: {}; {}".format(
                checks, "; ".join(problems)
            )
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
            "No restore baseline at {}. Restore UI cannot recover the original profile.".format(
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
    """Undo everything FusionMyFreeCAD changed, using the immutable baseline.

    Returns (recovery_directory, problems). Every step is independent so a single
    failure cannot abandon the rest of the restoration.
    """
    baseline = _read_baseline()
    state = read_state()
    source = baseline or state
    if source is None:
        raise RuntimeError(
            "FusionMyFreeCAD has no restoration data. Neither {} nor {} is readable.".format(
                BASELINE_PATH, STATE_PATH
            )
        )
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
        main_window = Gui.getMainWindow()
        main_window.menuBar().show()
        from PySide import QtWidgets

        for toolbar in main_window.findChildren(QtWidgets.QToolBar):
            toolbar.show()
    except Exception as error:  # pragma: no cover - needs a live Qt main window
        problems.append("Native toolbars: {}".format(error))

    return removed, problems


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
            "MenuText": "Verify FusionMyFreeCAD",
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
                    "Suggested next step: run Reapply FusionMyFreeCAD, then restart FreeCAD.",
                    "If that does not help, run Restore UI and reinstall the add-on.",
                ]
            )
        _message("FusionMyFreeCAD verification", "\n".join(lines), not valid)


class ReapplyCommand:
    """Reinstall the layout and re-apply managed defaults on request.

    Managed preferences are applied once per version so the add-on does not
    overwrite the user's own changes at every launch. This command is the supported
    way back to the shipped defaults.
    """

    def GetResources(self):
        return {
            "Pixmap": "Std_DlgParameter",
            "MenuText": "Reapply FusionMyFreeCAD",
            "ToolTip": "Restore FusionMyFreeCAD's own ribbon layout, preferences, and shortcuts",
        }

    def IsActive(self):
        return True

    def Activated(self):
        from PySide import QtWidgets

        answer = QtWidgets.QMessageBox.question(
            Gui.getMainWindow(),
            "Reapply FusionMyFreeCAD",
            "Reapply FusionMyFreeCAD's ribbon layout, managed preferences, and shortcuts?\n\n"
            "Your own changes to those settings will be replaced.",
        )
        if answer != QtWidgets.QMessageBox.Yes:
            return
        try:
            _message("FusionMyFreeCAD", reapply(), False)
        except Exception as error:
            _message("FusionMyFreeCAD could not reapply", str(error), True)


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
    runtime = sys.modules.get("_fusion_my_freecad_runtime")
    if runtime is not None and hasattr(runtime, "apply_preferences"):
        runtime.apply_preferences(force=True)
    return "Defaults reapplied ({}). Restart FreeCAD to load the regenerated ribbon.".format(
        outcome
    )


class RestoreCommand:
    def GetResources(self):
        return {
            "Pixmap": "Std_DlgCustomize",
            "MenuText": "Restore Previous UI",
            "ToolTip": "Restore the UI from before FusionMyFreeCAD",
        }

    def IsActive(self):
        return True

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
            location, problems = restore()
            text = [
                "Previous UI restored. Remove FusionMyFreeCAD in Addon Manager, "
                "then restart FreeCAD.",
                "",
                "The removed configuration remains recoverable at:",
                location,
            ]
            if problems:
                text.extend(["", "Some items could not be restored:"])
                text.extend("- {}".format(problem) for problem in problems)
            _message("FusionMyFreeCAD restored", "\n".join(text), bool(problems))
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
        # Keep Part Design active while FreeCAD's attachment task displays its
        # selectable origin planes. Switching workbenches here destroys the
        # Fusion-like plane-picking presentation before the user has chosen one.
        try:
            from PySide import QtCore

            QtCore.QTimer.singleShot(0, _frame_origin_planes)
        except ImportError:
            _frame_origin_planes()


def _frame_origin_planes():
    """Give FreeCAD's temporary origin planes a predictable, visible camera."""
    document = getattr(Gui, "ActiveDocument", None)
    view = getattr(document, "ActiveView", None)
    if view is None:
        return
    view.viewAxonometric()
    view.fitAll()


class _SketchEditWorkbenchObserver:
    """Enter Sketcher only after attachment selection actually starts editing."""

    def slotInEdit(self, view_provider):
        obj = getattr(view_provider, "Object", None)
        if obj is not None and obj.isDerivedFrom("Sketcher::SketchObject"):
            Gui.activateWorkbench("SketcherWorkbench")


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
        raise RuntimeError("FusionMyFreeCAD preferences page is missing: {}".format(PREFERENCES_UI))
    Gui.addPreferencePage(PREFERENCES_UI, "FusionMyFreeCAD")


_sketch_edit_observer = None


def register_commands():
    global _sketch_edit_observer
    Gui.addCommand("FusionMyFreeCAD_CreateSketch", CreateSketchCommand())
    Gui.addCommand("FusionMyFreeCAD_ParameterTable", ParameterTableCommand())
    Gui.addCommand("FusionMyFreeCAD_Verify", VerifyCommand())
    Gui.addCommand("FusionMyFreeCAD_Reapply", ReapplyCommand())
    Gui.addCommand("FusionMyFreeCAD_Restore", RestoreCommand())
    if _sketch_edit_observer is None and hasattr(Gui, "addDocumentObserver"):
        _sketch_edit_observer = _SketchEditWorkbenchObserver()
        Gui.addDocumentObserver(_sketch_edit_observer)


# ---------------------------------------------------------------------------
# Module loading
# ---------------------------------------------------------------------------


_loaded = set()

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
        return
    _execute_module("_fusion_my_freecad_runtime", RUNTIME)
    _loaded.add("runtime")


def load_vendor(name, directory):
    if name in _loaded:
        return
    if any(module in sys.modules for module in VENDOR_SENTINELS.get(name, ())):
        _loaded.add(name)
        App.Console.PrintMessage("FusionMyFreeCAD is using the already active {}.\n".format(name))
        return
    init_gui = os.path.join(directory, "InitGui.py")
    if not os.path.isfile(init_gui):
        raise RuntimeError("FusionMyFreeCAD vendor payload is incomplete: {}".format(init_gui))
    if directory not in sys.path:
        sys.path.insert(0, directory)
    _execute_module("_fusion_vendor_{}".format(name), init_gui)
    _loaded.add(name)
