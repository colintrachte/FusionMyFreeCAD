"""Capture a repeatable, non-mutating FMF baseline; live timing requires FreeCAD."""

from __future__ import annotations

import argparse
import json
import platform
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def static_snapshot() -> dict:
    layout = json.loads((ROOT / "Resources/FMF/layout-v3.json").read_text("utf-8"))
    workbenches = {}
    for name, panels in layout["workbenches"].items():
        workbenches[name] = {
            "panels": len(panels),
            "pinned": sum(len(panel["commands"]) for panel in panels),
            "overflow": sum(len(panel.get("overflow", [])) for panel in panels),
        }
    return {
        "schema": 1,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "workbenches": workbenches,
        "liveFreeCAD": None,
    }


def live_snapshot(result: dict) -> None:
    try:
        import FreeCAD
        import FreeCADGui
    except ImportError as error:
        raise SystemExit("--live must run in FreeCAD's Python environment") from error
    started = time.perf_counter()
    workbenches = sorted(FreeCADGui.listWorkbenches())
    result["liveFreeCAD"] = {
        "version": list(FreeCAD.Version()),
        "activeWorkbench": FreeCADGui.activeWorkbench().name(),
        "listedWorkbenches": workbenches,
        "probeMilliseconds": round((time.perf_counter() - started) * 1000, 3),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--out", type=Path, default=ROOT / "tests/fixtures/fmf-baseline.json")
    args = parser.parse_args()
    result = static_snapshot()
    if args.live:
        live_snapshot(result)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(args.out)


if __name__ == "__main__":
    main()
