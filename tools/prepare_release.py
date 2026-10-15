"""Prepare FMF's versioned files for a human-authored release."""

from __future__ import annotations

import argparse
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")


def replace_once(text: str, pattern: str, replacement: str, label: str) -> str:
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE)
    if count != 1:
        raise RuntimeError(f"Could not find exactly one {label} in the expected format")
    return updated


def update_text_file(path: Path, transform) -> bool:
    original = path.read_text(encoding="utf-8")
    updated = transform(original)
    if updated == original:
        return False
    path.write_text(updated, encoding="utf-8", newline="\n")
    return True


def current_version(root: Path) -> str:
    package = (root / "package.xml").read_text(encoding="utf-8")
    match = re.search(r"<version>([^<]+)</version>", package)
    if not match:
        raise RuntimeError("package.xml does not contain a version")
    return match.group(1).strip()


def prepare(root: Path, version: str, release_date: str) -> list[Path]:
    if not VERSION_PATTERN.fullmatch(version):
        raise ValueError("Version must use the form X.Y.Z, for example 1.3.0")
    try:
        date.fromisoformat(release_date)
    except ValueError as error:
        raise ValueError("Date must use the form YYYY-MM-DD") from error

    changed: list[Path] = []

    package_path = root / "package.xml"

    def update_package(text: str) -> str:
        text = replace_once(
            text,
            r"<version>[^<]+</version>",
            f"<version>{version}</version>",
            "package version",
        )
        return replace_once(
            text,
            r"<date>[^<]+</date>",
            f"<date>{release_date}</date>",
            "package date",
        )

    if update_text_file(package_path, update_package):
        changed.append(package_path)

    for relative in (
        "Resources/FMF/layout-v3.json",
        "Resources/FMF/layout-manifest.json",
    ):
        path = root / relative
        if update_text_file(
            path,
            lambda text, relative=relative: replace_once(
                text,
                r'("layoutVersion"\s*:\s*")[^"]+("\s*,)',
                rf"\g<1>{version}\g<2>",
                f"layout version in {relative}",
            ),
        ):
            changed.append(path)

    readme_path = root / "README.md"

    def update_readme(text: str) -> str:
        status = (
            "## Status\n\n"
            f"Version **{version}** is available from\n"
            "[GitHub Releases](https://github.com/colintrachte/"
            f"FMF/releases/tag/v{version}) as a\n"
            "self-contained archive. FMF has not yet been submitted to FreeCAD's "
            "add-on index;\n"
            "catalog publication remains separate work.\n"
        )
        text, count = re.subn(
            r"## Status\n\n.*?(?=\n## Install\n)", status, text, count=1, flags=re.DOTALL
        )
        if count != 1:
            raise RuntimeError(f"Could not find the Status section in {readme_path}")
        return update_download_references(text, version, readme_path)

    def update_download_references(text: str, target: str, path: Path) -> str:
        replacements = (
            (r"FMF-[0-9]+\.[0-9]+\.[0-9]+\.zip", f"FMF-{target}.zip"),
            (r"\[[0-9]+\.[0-9]+\.[0-9]+ release\]", f"[{target} release]"),
            (r"/tag/v[0-9]+\.[0-9]+\.[0-9]+", f"/tag/v{target}"),
        )
        for pattern, replacement in replacements:
            text, count = re.subn(pattern, replacement, text, count=1)
            if count != 1:
                raise RuntimeError(
                    f"Could not find exactly one release reference matching {pattern!r} in {path}"
                )
        return text

    if update_text_file(readme_path, update_readme):
        changed.append(readme_path)

    install_path = root / "docs/user-guide/INSTALL-FREECAD-ADDON.md"
    if update_text_file(
        install_path, lambda text: update_download_references(text, version, install_path)
    ):
        changed.append(install_path)

    changelog_path = root / "CHANGELOG.md"
    changelog_heading = f"## {version} — {release_date}"
    if changelog_heading not in changelog_path.read_text(encoding="utf-8"):

        def add_changelog_section(text: str) -> str:
            marker = "All notable user-visible changes to FMF are recorded here.\n"
            if marker not in text:
                raise RuntimeError("Could not find the CHANGELOG introduction")
            section = (
                f"\n{changelog_heading}\n\n"
                "TODO: Summarize user-visible changes, fixes, and upgrade notes.\n"
            )
            return text.replace(marker, marker + section, 1)

        update_text_file(changelog_path, add_changelog_section)
        changed.append(changelog_path)

    notes_path = root / "docs" / "release-notes" / f"RELEASE-NOTES-{version}.md"
    notes_path.parent.mkdir(parents=True, exist_ok=True)
    if not notes_path.exists():
        notes_path.write_text(
            f"# FMF {version}\n\n"
            "TODO: Write a short release summary.\n\n"
            "## Install or update\n\n"
            f"Download `FMF-{version}.zip` and "
            f"`FMF-{version}.zip.sha256` from this release. Replace the entire "
            "existing `Mod/FMF` folder; do not merge it with an older version.\n\n"
            "See the [installation guide](https://github.com/colintrachte/"
            f"FMF/blob/v{version}/docs/user-guide/INSTALL-FREECAD-ADDON.md) and "
            "[full changelog](https://github.com/colintrachte/"
            f"FMF/blob/v{version}/CHANGELOG.md).\n",
            encoding="utf-8",
            newline="\n",
        )
        changed.append(notes_path)

    return changed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Update release metadata and create human-editable release notes."
    )
    parser.add_argument("version", help="Release version in X.Y.Z form (without a leading v)")
    parser.add_argument(
        "--date",
        default=date.today().isoformat(),
        dest="release_date",
        help="Release date in YYYY-MM-DD form (default: today)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        changed = prepare(ROOT, args.version, args.release_date)
    except (RuntimeError, ValueError) as error:
        print(f"ERROR: {error}")
        return 1

    if changed:
        print("Prepared these files:")
        for path in changed:
            print(f"  {path.relative_to(ROOT)}")
    else:
        print("Release metadata was already prepared.")
    print("\nNext: replace every TODO in CHANGELOG.md and the new release-notes file.")
    print("Then follow RELEASING.md to validate, commit, and upload the draft release.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
