"""Create a compact, deterministic FreeCAD add-on archive."""

from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "FusionMyFreeCAD"
PACKAGE_FILES = (
    "Init.py",
    "InitGui.py",
    "fusion_bootstrap.py",
    "package.xml",
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    "README.md",
    "docs/INSTALL-FREECAD-ADDON.md",
)
PACKAGE_DIRECTORIES = ("Resources", "bundled-addons")


def package_version() -> str:
    root = ET.parse(ROOT / "package.xml").getroot()
    version = next((child.text for child in root if child.tag.endswith("version")), None)
    if not version:
        raise RuntimeError("package.xml does not declare a version")
    return version


def package_sources() -> list[Path]:
    paths = [ROOT / relative for relative in PACKAGE_FILES]
    for relative in PACKAGE_DIRECTORIES:
        directory = ROOT / relative
        if not directory.is_dir():
            raise FileNotFoundError(f"Required package directory is missing: {directory}")
        paths.extend(
            path
            for path in directory.rglob("*")
            if path.is_file()
            and "__pycache__" not in path.parts
            and path.suffix not in {".pyc", ".pyo"}
        )
    missing = [path for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError("Required package files are missing: " + ", ".join(map(str, missing)))
    return sorted(set(paths), key=lambda path: path.relative_to(ROOT).as_posix())


def write_archive(output: Path, sources: list[Path]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for source in sources:
            relative = source.relative_to(ROOT).as_posix()
            info = zipfile.ZipInfo(f"{PACKAGE_NAME}/{relative}", date_time=(2026, 8, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, source.read_bytes(), compresslevel=9)


def verify_archive(output: Path, sources: list[Path]) -> None:
    expected = {f"{PACKAGE_NAME}/{path.relative_to(ROOT).as_posix()}" for path in sources}
    with zipfile.ZipFile(output) as archive:
        actual = set(archive.namelist())
        if actual != expected:
            raise RuntimeError(f"Archive contents differ from package inputs: {actual ^ expected}")
        bad = archive.testzip()
        if bad:
            raise RuntimeError(f"Archive CRC check failed for {bad}")
        required = {
            f"{PACKAGE_NAME}/InitGui.py",
            f"{PACKAGE_NAME}/package.xml",
            f"{PACKAGE_NAME}/bundled-addons/FreeCAD-Ribbon/InitGui.py",
            f"{PACKAGE_NAME}/bundled-addons/SearchBar/InitGui.py",
        }
        if not required.issubset(actual):
            raise RuntimeError("Archive is missing one or more FreeCAD runtime entry points")


def main() -> None:
    version = package_version()
    sources = package_sources()
    output = ROOT / "dist" / f"{PACKAGE_NAME}-{version}.zip"
    write_archive(output, sources)
    verify_archive(output, sources)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    checksum = output.with_suffix(output.suffix + ".sha256")
    checksum.write_text(f"{digest}  {output.name}\n", encoding="ascii")
    print(f"Created {output} with {len(sources)} files ({output.stat().st_size / 1024 / 1024:.2f} MiB).")
    print(f"SHA-256: {digest}")


if __name__ == "__main__":
    main()
