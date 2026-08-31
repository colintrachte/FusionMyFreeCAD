#!/usr/bin/env python3
"""Offline validation entry point for the FreeCAD add-on package.

The checks themselves live in `tests/` as a pytest suite so they can fail
individually and assert on behaviour rather than on the text of the source. This
script stays as the documented one-command entry point.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> int:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(ROOT / "tests"), "-q"],
        cwd=str(ROOT),
    )
    if result.returncode != 0:
        return result.returncode

    package_files = [
        ROOT / "Init.py",
        ROOT / "InitGui.py",
        ROOT / "fusion_bootstrap.py",
        ROOT / "package.xml",
        ROOT / "LICENSE",
        ROOT / "THIRD_PARTY_NOTICES.md",
    ]
    package_files.extend(
        path
        for package_root in (ROOT / "Resources", ROOT / "bundled-addons")
        for path in package_root.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix not in {".pyc", ".pyo"}
    )
    total = sum(path.stat().st_size for path in package_files)
    version = next(
        line.split(">")[1].split("<")[0]
        for line in (ROOT / "package.xml").read_text(encoding="utf-8").splitlines()
        if "<version>" in line
    )
    print(
        "VALID: self-contained add-on {}; {:.1f} MiB unpacked".format(version, total / 1024 / 1024)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
