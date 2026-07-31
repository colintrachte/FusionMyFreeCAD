#!/usr/bin/env python3
"""Validate the FusionMyFreeCAD Ribbon prototype without importing it into FreeCAD."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ALLOWED_SIZES = {"small", "medium", "large"}
SPECIAL_WORKBENCHES = {"General", "Global", "Standard"}


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot load {path}: {exc}") from exc


def validate_pair(
    pair: Any, context: str, known_commands: set[str], dropdowns: set[str], errors: list[str]
) -> None:
    if not isinstance(pair, list) or len(pair) != 2:
        errors.append(f"{context}: expected [command, workbench]")
        return
    command, workbench = pair
    if not isinstance(command, str) or not command:
        errors.append(f"{context}: command must be a non-empty string")
    elif command not in known_commands and command not in dropdowns:
        errors.append(f"{context}: unknown command {command!r}")
    if not isinstance(workbench, str) or not workbench:
        errors.append(f"{context}: workbench must be a non-empty string")


def validate(preset: dict[str, Any], manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    known_commands = set(manifest.get("commands", []))

    dropdown_map = preset.get("dropdownButtons")
    panel_map = preset.get("newPanels")
    workbench_map = preset.get("workbenches")
    if not isinstance(dropdown_map, dict):
        errors.append("dropdownButtons must be an object")
        dropdown_map = {}
    if not isinstance(panel_map, dict):
        errors.append("newPanels must be an object")
        panel_map = {}
    if not isinstance(workbench_map, dict):
        errors.append("workbenches must be an object")
        workbench_map = {}

    dropdowns = set(dropdown_map)
    for name, items in dropdown_map.items():
        if not name.endswith("_ddb"):
            errors.append(f"dropdownButtons.{name}: name must end in _ddb")
        if not isinstance(items, list) or not items:
            errors.append(f"dropdownButtons.{name}: must contain at least one command")
            continue
        for index, pair in enumerate(items):
            validate_pair(pair, f"dropdownButtons.{name}[{index}]", known_commands, dropdowns, errors)

    for workbench, panels in panel_map.items():
        if not isinstance(panels, dict):
            errors.append(f"newPanels.{workbench}: must be an object")
            continue
        for panel_name, items in panels.items():
            if not panel_name.endswith("_newPanel"):
                errors.append(f"newPanels.{workbench}.{panel_name}: name must end in _newPanel")
            if not isinstance(items, list) or not items:
                errors.append(f"newPanels.{workbench}.{panel_name}: must contain commands")
                continue
            for index, pair in enumerate(items):
                validate_pair(
                    pair,
                    f"newPanels.{workbench}.{panel_name}[{index}]",
                    known_commands,
                    dropdowns,
                    errors,
                )

    for workbench, definition in workbench_map.items():
        if not isinstance(definition, dict):
            errors.append(f"workbenches.{workbench}: must be an object")
            continue
        toolbars = definition.get("toolbars")
        toolbar_order = definition.get("order")
        if not isinstance(toolbars, dict):
            errors.append(f"workbenches.{workbench}.toolbars: must be an object")
            continue
        if not isinstance(toolbar_order, list):
            errors.append(f"workbenches.{workbench}.order: must be a list")
            toolbar_order = []
        if set(toolbar_order) != set(toolbars):
            errors.append(f"workbenches.{workbench}: toolbar order does not match toolbar names")

        declared_panels = set(panel_map.get(workbench, {}))
        if declared_panels != set(toolbars):
            errors.append(f"workbenches.{workbench}: newPanels and toolbars do not define the same panels")

        for toolbar_name, toolbar in toolbars.items():
            context = f"workbenches.{workbench}.toolbars.{toolbar_name}"
            if not isinstance(toolbar, dict):
                errors.append(f"{context}: must be an object")
                continue
            order = toolbar.get("order")
            commands = toolbar.get("commands")
            if not isinstance(order, list) or not isinstance(commands, dict):
                errors.append(f"{context}: order must be a list and commands must be an object")
                continue
            if set(order) != set(commands):
                errors.append(f"{context}: command order does not match command metadata")

            panel_pairs = panel_map.get(workbench, {}).get(toolbar_name, [])
            panel_commands = [pair[0] for pair in panel_pairs if isinstance(pair, list) and pair]
            if order != panel_commands:
                errors.append(f"{context}: order differs from the matching newPanels command order")

            for command, metadata in commands.items():
                if command not in known_commands and command not in dropdowns:
                    errors.append(f"{context}: unknown command metadata key {command!r}")
                if not isinstance(metadata, dict):
                    errors.append(f"{context}.commands.{command}: must be an object")
                    continue
                if metadata.get("size") not in ALLOWED_SIZES:
                    errors.append(f"{context}.commands.{command}: invalid size {metadata.get('size')!r}")

    referenced_workbenches = {
        pair[1]
        for items in list(dropdown_map.values())
        for pair in items
        if isinstance(pair, list) and len(pair) == 2 and isinstance(pair[1], str)
    }
    referenced_workbenches.update(
        pair[1]
        for panels in panel_map.values()
        for items in panels.values()
        for pair in items
        if isinstance(pair, list) and len(pair) == 2 and isinstance(pair[1], str)
    )
    suspicious = sorted(
        name
        for name in referenced_workbenches
        if name not in SPECIAL_WORKBENCHES and not name.endswith("Workbench")
    )
    if suspicious:
        errors.append(f"unexpected workbench identifiers: {', '.join(suspicious)}")

    return errors


def main() -> int:
    directory = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser()
    parser.add_argument("--preset", type=Path, default=directory / "fusion-ribbon-freecad-1.1.3.json")
    parser.add_argument(
        "--manifest", type=Path, default=directory / "freecad-1.1.3-command-manifest.json"
    )
    args = parser.parse_args()

    try:
        preset = load_json(args.preset)
        manifest = load_json(args.manifest)
        if not isinstance(preset, dict) or not isinstance(manifest, dict):
            raise ValueError("preset and manifest roots must be JSON objects")
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    errors = validate(preset, manifest)
    if errors:
        print(f"INVALID: {len(errors)} problem(s)")
        for error in errors:
            print(f"- {error}")
        return 1

    dropdown_count = len(preset["dropdownButtons"])
    panel_count = sum(len(panels) for panels in preset["newPanels"].values())
    command_count = len(manifest["commands"])
    print(
        f"VALID: FreeCAD {manifest['freecadVersion']} prototype; "
        f"{dropdown_count} dropdowns, {panel_count} panels, {command_count} verified commands"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
