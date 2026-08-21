"""Load the authoritative v3 ribbon layout for FreeCAD 1.1.x."""

from __future__ import annotations

import json
from pathlib import Path


SPEC_PATH = Path(__file__).resolve().parent / "assets" / "layout-v2.json"
SPEC = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
LAYOUT_VERSION = SPEC["layoutVersion"]
DROPDOWNS = SPEC["dropdownButtons"]


def _workbench(panels):
    toolbars = {}
    new_panels = {}
    for panel in panels:
        entries = panel["commands"]
        order = [entry[0] for entry in entries]
        new_panels[panel["name"]] = [[entry[0], entry[1]] for entry in entries]
        toolbars[panel["name"]] = {
            "title": panel["title"],
            "Enabled": True,
            "order": order,
            "commands": {
                command: {
                    "size": size,
                    "text": label,
                    "icon": icon,
                    "IsExtra": True,
                }
                for command, _source, size, label, icon in entries
            },
        }
    toolbars["order"] = list(toolbars)
    return {"toolbars": toolbars}, new_panels


def build_overlay():
    workbenches = {}
    new_panels = {}
    for name, panels in SPEC["workbenches"].items():
        workbenches[name], new_panels[name] = _workbench(panels)
    return {
        "schemaVersion": 3,
        "layoutVersion": LAYOUT_VERSION,
        "targetFreeCAD": SPEC["targetFreeCAD"],
        "authoritativeWorkbenches": list(SPEC["workbenches"]),
        "dropdownButtons": DROPDOWNS,
        "newPanels": new_panels,
        "workbenches": workbenches,
    }


def expected_primary_commands():
    commands = {
        entry[0]
        for panels in SPEC["workbenches"].values()
        for panel in panels
        for entry in panel["commands"]
        if not entry[0].endswith("_ddb")
    }
    for entries in DROPDOWNS.values():
        commands.update(entry[0] for entry in entries)
    return sorted(commands)
