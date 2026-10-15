"""Regenerate the FREQUENT candidate pools from the shipped layout.

A FREQUENT section promotes whatever the user reaches for most, which it can
only do for commands it is allowed to consider. The pools were once a short
hand-picked list, so almost everything a user actually clicked was invisible to
the ranking and the section never changed. The pool is now simply "every
command this workbench's ribbon offers", derived from `layout-v3.json` so the
two cannot drift apart; `tests/test_package.py` enforces the same rule.

Run from the repository root:

    python tools/generate_frequent_pools.py
"""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
LAYOUT = ROOT / "Resources" / "FMF" / "layout-v3.json"
MANIFEST = ROOT / "Resources" / "FMF" / "layout-manifest.json"


def is_candidate(command: str) -> bool:
    """Whether a ribbon entry is a command a FREQUENT slot could hold.

    A `_ddb` entry is a dropdown container drawn by the ribbon rather than a
    FreeCAD command, so there is nothing to count uses of and nothing to
    trigger if it were promoted.
    """
    return not command.endswith("_ddb")


def pool_for(panels) -> dict:
    """Every command the workbench offers, with the metadata a slot needs."""
    pool = {}
    for panel in panels:
        entries = list(panel.get("commands", [])) + list(panel.get("overflow", []))
        for command, source, size, text, icon in entries:
            if not is_candidate(command):
                continue
            pool.setdefault(command, [source, size, text, icon])
    return pool


def groups_of(config):
    """(name, group, is_whole) for each adaptive group in a workbench config."""
    if "panels" in config:
        return [
            (name, group, bool(group.get("whole", False)))
            for name, group in config["panels"].items()
        ]
    panel = config.get("panel")
    return [(panel, config, True)] if panel else []


def main() -> int:
    layout = json.loads(LAYOUT.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    for workbench, config in manifest["adaptivePins"].items():
        panels = layout["workbenches"][workbench]
        for _name, group, is_whole in groups_of(config):
            if not is_whole:
                # A slot group permutes commands the section already holds, so
                # its pool is that section's own alternatives, chosen by hand.
                continue
            group["commands"] = pool_for(panels)

    manifest["workbenchPanelOrder"] = {
        workbench: [panel["name"] for panel in panels]
        for workbench, panels in layout["workbenches"].items()
    }
    MANIFEST.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    for workbench, config in manifest["adaptivePins"].items():
        for name, group, is_whole in groups_of(config):
            if is_whole:
                print("{}/{}: {} candidates".format(workbench, name, len(group["commands"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
