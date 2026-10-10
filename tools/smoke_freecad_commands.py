"""Non-destructively verify behavior-sensitive commands in a real FreeCAD GUI session.

Run this file with FreeCAD's GUI executable. It activates the required workbenches to make their
commands register, but does not create, open, save, or modify any document.
"""

from __future__ import annotations

import sys
from pathlib import Path

import FreeCAD as App
import FreeCADGui as Gui

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from validate_layout_contracts import COMMAND_CONTRACTS, validate  # noqa: E402


def main() -> int:
    validate(ROOT)
    missing = []
    by_workbench = {}
    for role, contract in COMMAND_CONTRACTS.items():
        by_workbench.setdefault(contract["workbench"], []).append((role, contract["command"]))

    for workbench, commands in by_workbench.items():
        Gui.activateWorkbench(workbench)
        available = set(Gui.listCommands())
        missing.extend(
            f"{role}: {command} ({workbench})"
            for role, command in commands
            if command not in available
        )

    if missing:
        App.Console.PrintError(
            "FusionMyFreeCAD command smoke check failed:\n  " + "\n  ".join(missing) + "\n"
        )
        return 1
    App.Console.PrintMessage("FusionMyFreeCAD command smoke check passed.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
