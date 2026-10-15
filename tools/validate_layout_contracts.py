"""Validate behavior-sensitive FreeCAD command mappings in the shipped ribbon."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

# These are semantic contracts, not a complete command inventory. Each entry exists because
# choosing a nearby, valid command ID changes user-visible behavior without necessarily failing.
COMMAND_CONTRACTS = {
    "coincident": {
        "command": "Sketcher_ConstrainCoincidentUnified",
        "workbench": "FMFSketchWorkbench",
        "panel": "FMF Sketch Constraints_newPanel",
    },
    "mirror": {
        "command": "Sketcher_Symmetry",
        "workbench": "FMFSketchWorkbench",
        "panel": "FMF Sketch Modify_newPanel",
    },
    "create-sketch": {
        "command": "FMF_CreateSketch",
        "workbench": "FMFDesignWorkbench",
        "panel": "FMF Sketch Entry_newPanel",
    },
    "pad": {
        "command": "PartDesign_Pad",
        "workbench": "FMFDesignWorkbench",
        "panel": "FMF Create_newPanel",
    },
    "pocket": {
        "command": "PartDesign_Pocket",
        "workbench": "FMFDesignWorkbench",
        "panel": "FMF Create_newPanel",
    },
}


def validate(root: Path) -> None:
    resources = root / "Resources" / "FMF"
    layout = json.loads((resources / "layout-v3.json").read_text(encoding="utf-8"))
    manifest = json.loads((resources / "layout-manifest.json").read_text(encoding="utf-8"))
    primary = set(manifest["primaryCommands"])

    for role, contract in COMMAND_CONTRACTS.items():
        workbench = contract["workbench"]
        panels = {panel["name"]: panel for panel in layout["workbenches"].get(workbench, [])}
        panel = panels.get(contract["panel"])
        if panel is None:
            raise RuntimeError(f"{role} contract panel is missing: {workbench}/{contract['panel']}")
        visible = {entry[0] for entry in panel["commands"]}
        command = contract["command"]
        if command not in visible:
            raise RuntimeError(f"{role} must use {command} in {workbench}/{contract['panel']}")
        if command not in primary:
            raise RuntimeError(f"{role} command {command} is missing from primaryCommands")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        validate(args.root.resolve())
    except (OSError, ValueError, RuntimeError) as error:
        print(f"ERROR: {error}")
        return 1
    print("Behavior-sensitive layout command contracts are valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
