#!/usr/bin/env python3
"""Build the complete RibbonStructure.json shipped by the Windows installer."""

from __future__ import annotations

import json
from pathlib import Path

from layout_spec_v3 import LAYOUT_VERSION, build_overlay, expected_primary_commands


PROJECT = Path(__file__).resolve().parent.parent
BASE = PROJECT.parent / "FreeCAD UI Study" / "FreeCAD-Ribbon-main" / "CreateStructure.txt"
OUTPUT = PROJECT / "installer" / "assets" / "RibbonStructure-v3.json"
MANIFEST = PROJECT / "installer" / "assets" / "FusionMyFreeCAD" / "layout-manifest.json"


def main() -> None:
    base = json.loads(BASE.read_text(encoding="utf-8"))
    overlay = build_overlay()

    base.setdefault("dropdownButtons", {}).update(overlay["dropdownButtons"])
    base["authoritativeWorkbenches"] = overlay["authoritativeWorkbenches"]
    for workbench, panels in overlay["newPanels"].items():
        base.setdefault("newPanels", {}).setdefault(workbench, {}).update(panels)
    for workbench, definition in overlay["workbenches"].items():
        base.setdefault("workbenches", {})[workbench] = definition

    OUTPUT.write_text(json.dumps(base, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest["layoutVersion"] = LAYOUT_VERSION
    manifest["primaryCommands"] = expected_primary_commands()
    manifest["workbenchPanelOrder"] = {
        name: definition["toolbars"]["order"] for name, definition in overlay["workbenches"].items()
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(
        "BUILT: {} (layout {}, {} workbenches, {} dropdowns)".format(
            OUTPUT,
            LAYOUT_VERSION,
            len(base["workbenches"]),
            len(base["dropdownButtons"]),
        )
    )


if __name__ == "__main__":
    main()
