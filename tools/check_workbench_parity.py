"""Generate FMF layout coverage and optionally cross-check FreeCAD workbench source."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SOURCE_ONLY_DISPOSITIONS = {
    "PartDesign_CircularPattern": "use the pinned PartDesign_PolarPattern command",
    "PartDesign_Defeaturing": "use searchable Part_Defeaturing in the Part workbench",
    "PartDesign_MoveFeature": "use the native selection-dependent tree context menu",
    "PartDesign_MoveFeatureInTree": "use the native selection-dependent tree context menu",
    "PartDesign_MoveTip": "use the native Body tree context menu",
    "PartDesign_PathPattern": "not exposed as a QAction by this supported source build",
    "PartDesign_PointPattern": "not exposed as a QAction by this supported source build",
    "Part_Box_Parametric": "use the FMF primitive/create path",
    "Std_DuplicateSelection": "use searchable PartDesign_DuplicateSelection",
    "Std_ToggleFreeze": "use the native selection-dependent tree context menu",
    "Part_LinkArrays": "use the searchable native array commands exposed by the group",
    "Sketcher_CompConstrainRadDia": "use the pinned context-sensitive Sketcher_Dimension command",
    "Sketcher_ConstrainCoincident": (
        "use pinned Sketcher_ConstrainCoincidentUnified, which dispatches Coincident or "
        "Point-on-object from the current selection"
    ),
    "Sketcher_ConstrainPointOnObject": "use pinned Sketcher_ConstrainCoincidentUnified",
    "Sketcher_CreateDraftLine": "the host source comments this command out",
    "Sketcher_ProfilesHexagon1": "use the searchable regular-polygon/profile commands",
    "Surface_Cut": "the host source comments this command out",
}


def commands(panel):
    return [entry[0] for entry in panel["commands"] + panel.get("overflow", [])]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--freecad-source", type=Path)
    parser.add_argument(
        "--action-inventory",
        type=Path,
        help="JSON emitted by the isolated real-FreeCAD workbench probe",
    )
    parser.add_argument("--check", action="store_true", help="fail if the report is incomplete")
    parser.add_argument("--out", type=Path, default=ROOT / "docs/dev-guide/workbench-parity.md")
    args = parser.parse_args()
    if args.check:
        report = args.out.read_text("utf-8")
        if "- [ ]" in report or "Requires disposition" in report:
            raise SystemExit("Workbench parity report still has unresolved dispositions")
        print(args.out)
        return

    layout = json.loads((ROOT / "Resources/FusionMyFreeCAD/layout-v3.json").read_text("utf-8"))
    inventory = None
    if args.action_inventory:
        inventory = json.loads(args.action_inventory.read_text("utf-8"))
        if inventory.get("error"):
            raise SystemExit(inventory["error"])
    lines = [
        "# Stock-to-FMF workbench parity",
        "",
        "Generated command coverage baseline. Commands not pinned in FMF remain available through",
        "FreeCAD's native menus and command search when a live QAction was observed. Source-only",
        "literals are retained as intentional omissions until the supported host exposes an",
        "action.",
        "",
    ]
    mapping = {
        "PartDesignWorkbench": "src/Mod/PartDesign/Gui/Workbench.cpp",
        "PartWorkbench": "src/Mod/Part/Gui/Workbench.cpp",
        "SketcherWorkbench": "src/Mod/Sketcher/Gui/Workbench.cpp",
        "SurfaceWorkbench": "src/Mod/Surface/Gui/Workbench.cpp",
    }
    for workbench, panels in layout["workbenches"].items():
        present = sorted({command for panel in panels for command in commands(panel)})
        lines += ["## {}".format(workbench), "", "- FMF commands: {}".format(len(present))]
        if args.freecad_source:
            source = (args.freecad_source / mapping[workbench]).read_text("utf-8", errors="ignore")
            pattern = r'"((?:PartDesign|Part|Sketcher|Surface|Std)_[A-Za-z0-9_]+)"'
            native = sorted(set(re.findall(pattern, source)))
            missing = [command for command in native if command not in present]
            lines += [
                "- Source command literals: {}".format(len(native)),
                "- Not in FMF layout: {}".format(len(missing)),
                "",
            ]
            if inventory is None:
                lines += ["### Requires disposition", ""] + [
                    "- [ ] `{}`".format(item) for item in missing
                ]
            else:
                actions = set(inventory["workbenches"][workbench]["actions"])
                searchable = [item for item in missing if item in actions]
                source_only = [item for item in missing if item not in actions]
                undocumented = [
                    item for item in source_only if item not in SOURCE_ONLY_DISPOSITIONS
                ]
                if undocumented:
                    raise SystemExit(
                        "Source-only commands need explicit dispositions: {}".format(
                            ", ".join(undocumented)
                        )
                    )
                lines += [
                    "- Live actions after activation: {}".format(len(actions)),
                    "- Searchable/native-menu dispositions: {}".format(len(searchable)),
                    "- Intentional source-only omissions: {}".format(len(source_only)),
                    "- Activation time: {} ms".format(
                        inventory["workbenches"][workbench]["activationMilliseconds"]
                    ),
                    "",
                    "### Verified dispositions",
                    "",
                ]
                lines += [
                    "- **Searchable/native menu:** `{}` — deliberately not pinned; the live native "
                    "action remains available without weakening FMF's curated layout.".format(item)
                    for item in searchable
                ]
                lines += [
                    "- **Intentional omission:** `{}` — no QAction appeared after activating this "
                    "workbench; {}.".format(
                        item,
                        SOURCE_ONLY_DISPOSITIONS.get(
                            item, "use the related native command group when the host exposes it"
                        ),
                    )
                    for item in source_only
                ]
        lines += ["", "### FMF inventory", ""] + ["- `{}`".format(item) for item in present] + [""]
    args.out.write_text("\n".join(lines), encoding="utf-8")
    print(args.out)


if __name__ == "__main__":
    main()
