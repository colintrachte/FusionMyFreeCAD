"""Validate the release metadata shared by local tooling and GitHub Actions."""

from __future__ import annotations

import argparse
import re
import xml.etree.ElementTree as ET
from pathlib import Path

VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")


def package_version(root: Path) -> str:
    package = ET.parse(root / "package.xml").getroot()
    version = next((child.text for child in package if child.tag.endswith("version")), None)
    if not version:
        raise RuntimeError("package.xml does not declare a version")
    return version.strip()


def validate(root: Path, version: str) -> None:
    if not VERSION_PATTERN.fullmatch(version):
        raise ValueError("Version must use X.Y.Z form without a leading v")
    packaged = package_version(root)
    if packaged != version:
        raise RuntimeError(f"Workflow version {version!r} does not match package.xml {packaged!r}")

    notes = root / "docs" / "release-notes" / f"RELEASE-NOTES-{version}.md"
    if not notes.is_file():
        raise RuntimeError(f"Missing {notes.relative_to(root)}")
    if "TODO" in notes.read_text(encoding="utf-8"):
        raise RuntimeError(f"Finish the TODO in {notes.relative_to(root)} before releasing")

    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    heading = re.compile(rf"^## {re.escape(version)}(?:\s|$)", re.MULTILINE)
    count = len(heading.findall(changelog))
    if count != 1:
        raise RuntimeError(f"CHANGELOG.md must have exactly one {version} section; found {count}")
    if "TODO" in changelog:
        raise RuntimeError("Finish every CHANGELOG.md TODO before releasing")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="Release version in X.Y.Z form")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        validate(args.root.resolve(), args.version)
    except (OSError, ET.ParseError, RuntimeError, ValueError) as error:
        print(f"ERROR: {error}")
        return 1
    print(f"Release metadata is complete for {args.version}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
