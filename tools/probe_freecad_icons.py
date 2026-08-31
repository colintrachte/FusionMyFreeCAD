"""Ask a real FreeCAD which icon names it serves, and record the answer.

FusionMyFreeCAD vendors only the FreeCAD command icons named by `layout-v3.json`.
This script checks those names against a real installation via `Gui.getIcon()` and
writes `Resources/FusionMyFreeCAD/verified-icons.json`. The offline test suite then
asserts the layout only uses verified names and the bundle contains exactly that set.

**`Gui.getIcon()` never fails.** Given an unknown name it returns FreeCAD's
"unknown icon" placeholder, which is a perfectly valid non-null QIcon. Comparing
`isNull()` therefore reports success for names that are simply wrong — which is how
thirteen misspelled icons shipped unnoticed. This script fingerprints the
placeholder from deliberately impossible names and compares every candidate
against it.

Run it from the repository root, passing your FreeCAD executable:

    python tools/probe_freecad_icons.py --freecad "C:/Program Files/FreeCAD/bin/FreeCADCmd.exe"

Re-run it when targeting a new FreeCAD version, and commit the regenerated file.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAYOUT = ROOT / "Resources" / "FusionMyFreeCAD" / "layout-v3.json"
OUTPUT = ROOT / "Resources" / "FusionMyFreeCAD" / "verified-icons.json"

# Executed inside FreeCAD, which supplies FreeCAD/FreeCADGui.
PROBE = '''
import hashlib, json, os

OUT = os.environ["FMF_PROBE_OUT"]
LAYOUT = os.environ["FMF_PROBE_LAYOUT"]
WORKBENCHES = ("PartDesignWorkbench", "SketcherWorkbench", "PartWorkbench",
               "SurfaceWorkbench", "SpreadsheetWorkbench")
IMPOSSIBLE = ("ZZZ_NoSuchIcon_12345", "PartDesign_NotAReal_Command",
              "Sketcher_ThisDoesNotExist", "qqq_zzz_yyy")
report = {"error": None}


def fingerprint(name):
    """Hash an icon's rendered pixels, or None when FreeCAD returns nothing."""
    try:
        icon = Gui.getIcon(name)
    except Exception:
        return None
    if icon is None or icon.isNull():
        return None
    image = icon.pixmap(32, 32).toImage()
    raw = bytearray()
    for y in range(image.height()):
        for x in range(image.width()):
            raw += image.pixel(x, y).to_bytes(4, "little")
    return hashlib.sha256(bytes(raw)).hexdigest()[:16]


try:
    import FreeCAD as App
    import FreeCADGui as Gui

    Gui.showMainWindow()
    for workbench in WORKBENCHES:
        try:
            Gui.activateWorkbench(workbench)
        except Exception as error:
            report.setdefault("workbenchErrors", {})[workbench] = str(error)

    placeholders = {fingerprint(name) for name in IMPOSSIBLE}
    placeholders.discard(None)
    if len(placeholders) != 1:
        raise RuntimeError(
            "Could not fingerprint the not-found placeholder: %r" % (placeholders,)
        )
    placeholder = placeholders.pop()

    layout = json.load(open(LAYOUT, encoding="utf-8"))
    names = sorted({
        icon
        for panels in layout["workbenches"].values()
        for panel in panels
        for entry in panel["commands"] + panel.get("overflow", [])
        for icon in [entry[4]]
    })

    verified, missing = [], []
    for name in names:
        digest = fingerprint(name)
        if digest is None or digest == placeholder:
            missing.append(name)
        else:
            verified.append(name)

    report.update({
        "freeCADVersion": ".".join(str(part) for part in App.Version()[:3]),
        "placeholderSha": placeholder,
        "verified": verified,
        "missing": missing,
    })
except Exception:
    import traceback
    report["error"] = traceback.format_exc()

with open(OUT, "w", encoding="utf-8") as stream:
    json.dump(report, stream, indent=2)
print("FMF_PROBE_DONE")
'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--freecad",
        required=True,
        help="Path to FreeCADCmd(.exe), or FreeCAD(.exe) with --console support.",
    )
    parser.add_argument("--timeout", type=int, default=600, help="Seconds to allow FreeCAD to run.")
    parser.add_argument(
        "--scratch",
        help="Optional existing directory for probe files (useful in restricted environments).",
    )
    parser.add_argument(
        "--launcher",
        help="Optional command prefix used to supply the FreeCAD runtime environment.",
    )
    arguments = parser.parse_args()

    executable = Path(arguments.freecad)
    if not executable.is_file():
        print("No FreeCAD executable at {}".format(executable), file=sys.stderr)
        return 2

    scratch_context = (
        contextlib.nullcontext(arguments.scratch)
        if arguments.scratch
        else tempfile.TemporaryDirectory()
    )
    with scratch_context as scratch:
        scratch_path = Path(scratch)
        scratch_path.mkdir(parents=True, exist_ok=True)
        script = scratch_path / "probe.py"
        script.write_text(PROBE, encoding="utf-8")
        result_path = scratch_path / "result.json"

        environment = dict(os.environ)
        environment["FMF_PROBE_OUT"] = str(result_path)
        environment["FMF_PROBE_LAYOUT"] = str(LAYOUT)
        environment["FREECAD_USER_HOME"] = str(scratch_path)
        environment["FREECAD_USER_DATA"] = str(scratch_path)
        environment["FREECAD_USER_TEMP"] = str(scratch_path)

        # A throwaway config keeps the probe from touching the user's real profile.
        command = [
            *(shlex.split(arguments.launcher, posix=False) if arguments.launcher else []),
            str(executable),
            "-c",
            "-u",
            str(scratch_path / "user.cfg"),
            "-s",
            str(scratch_path / "system.cfg"),
            str(script),
        ]
        try:
            subprocess.run(
                command,
                env=environment,
                timeout=arguments.timeout,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except subprocess.TimeoutExpired:
            # FreeCAD's console mode lingers on an interactive prompt after the
            # script finishes, so a timeout is expected and harmless.
            pass

        if not result_path.is_file():
            print("FreeCAD produced no probe output.", file=sys.stderr)
            return 1
        report = json.loads(result_path.read_text(encoding="utf-8"))

    if report.get("error"):
        print(report["error"], file=sys.stderr)
        return 1

    if report["missing"]:
        print("These layout icon names render FreeCAD's placeholder:", file=sys.stderr)
        for name in report["missing"]:
            print("  {}".format(name), file=sys.stderr)
        print(
            "\nAsk FreeCAD what the command really declares:\n"
            "  Gui.Command.get('<command>').getInfo()['pixmap']",
            file=sys.stderr,
        )

    OUTPUT.write_text(
        json.dumps(
            {
                "_comment": (
                    "Generated by tools/probe_freecad_icons.py. Icon names verified to "
                    "render from FreeCAD's resources before entering the curated bundle."
                ),
                "freeCADVersion": report["freeCADVersion"],
                "verified": report["verified"],
                "missing": report["missing"],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        "Probed FreeCAD {}: {} verified, {} missing -> {}".format(
            report["freeCADVersion"],
            len(report["verified"]),
            len(report["missing"]),
            OUTPUT.relative_to(ROOT),
        )
    )
    return 1 if report["missing"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
