"""Build the tracked third-party runtime payload from ignored upstream snapshots."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "vendor"
DESTINATION_ROOT = ROOT / "bundled-addons"
ICON_SOURCE_MANIFEST = ROOT / "Resources" / "FusionMyFreeCAD" / "source-icons.json"

RIBBON_MODULES = (
    "CacheFunctions.py",
    "CustomWidgets.py",
    "FCBinding.py",
    "InitGui.py",
    "LoadAddCommands.py",
    "LoadCombinePanel_Ribbon.py",
    "LoadDesign_Ribbon.py",
    "LoadLicenseForm_Ribbon.py",
    "LoadSettings_Ribbon.py",
    "Parameters_Ribbon.py",
    "RibbonUI.py",
    "Serialize_Ribbon.py",
    "Standard_Functions_Ribbon.py",
    "StyleMapping_Ribbon.py",
)

SEARCH_MODULES = (
    "BuiltInSearchResults.py",
    "GetItemGroups.py",
    "IndentedItemDelegate.py",
    "InitGui.py",
    "MouseBar.py",
    "Parameters_SearchBar.py",
    "RefreshTools.py",
    "ResultsDocument.py",
    "ResultsPreferences.py",
    "ResultsRefreshTools.py",
    "ResultsToolbar.py",
    "SafeViewer.py",
    "SearchBox.py",
    "SearchBoxLight.py",
    "SearchResults.py",
    "Serialize_SearchBar.py",
    "StyleMapping_SearchBar.py",
)


def copy_file(source_root: Path, destination_root: Path, relative: str | Path) -> None:
    relative = Path(relative)
    source = source_root / relative
    if not source.is_file():
        raise FileNotFoundError(f"Required vendor file is missing: {source}")
    destination = destination_root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def copy_tree(source_root: Path, destination_root: Path, relative: str | Path) -> None:
    relative = Path(relative)
    source = source_root / relative
    if not source.is_dir():
        raise FileNotFoundError(f"Required vendor directory is missing: {source}")
    shutil.copytree(source, destination_root / relative)


def configured_icon_names() -> set[str]:
    """Return the exact FreeCAD icon resources referenced by the shipped layout."""
    layout_path = ROOT / "Resources" / "FusionMyFreeCAD" / "layout-v3.json"
    layout = json.loads(layout_path.read_text(encoding="utf-8"))
    return {
        Path(entry[4]).stem
        for panels in layout["workbenches"].values()
        for panel in panels
        for entry in panel["commands"] + panel.get("overflow", [])
    }


ICON_SOURCE_OVERRIDES = {
    # FreeCAD has a generic icon with the same name; Std_Measure uses this one.
    "umf-measurement": Path("src/Mod/Measure/Gui/Resources/icons/umf-measurement.svg"),
    # TechDraw carries private copies of these standard theme icons.
    "edit-copy": Path("src/Gui/Icons/edit-copy.svg"),
    "edit-cut": Path("src/Gui/Icons/edit-cut.svg"),
    "edit-paste": Path("src/Gui/Icons/edit-paste.svg"),
    "edit-undo": Path("src/Gui/Icons/edit-undo.svg"),
    "process-stop": Path("src/Gui/Icons/process-stop.svg"),
}


def canonical_svg_bytes(path: Path) -> bytes:
    """Return SVG bytes with repository-standard LF line endings."""
    return path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def freecad_icon_sources(freecad_source: Path) -> dict[str, Path]:
    """Find the configured icons in an official FreeCAD source checkout."""
    freecad_source = freecad_source.resolve()
    source_tree = freecad_source / "src"
    if not source_tree.is_dir():
        raise FileNotFoundError(
            "FreeCAD source checkout has no src directory: {}".format(freecad_source)
        )

    required = configured_icon_names()
    candidates: dict[str, list[Path]] = {name: [] for name in required}
    for path in source_tree.rglob("*.svg"):
        if path.stem in candidates:
            candidates[path.stem].append(path)

    selected: dict[str, Path] = {}
    missing = []
    ambiguous = []
    for name, paths in candidates.items():
        override = ICON_SOURCE_OVERRIDES.get(name)
        if override is not None:
            preferred = freecad_source / override
            if preferred.is_file():
                selected[name] = preferred
                continue
        if len(paths) == 1:
            selected[name] = paths[0]
        elif not paths:
            missing.append(name)
        else:
            ambiguous.append("{}: {}".format(name, ", ".join(map(str, paths))))

    if missing or ambiguous:
        raise RuntimeError(
            "Could not select FreeCAD icons (missing={}, ambiguous={}).".format(
                sorted(missing), sorted(ambiguous)
            )
        )
    return selected


def sync_layout_icons(freecad_source: Path, destination: Path) -> dict[str, Path]:
    """Refresh only the curated FreeCAD command icons used by the layout."""
    icon_destination = destination / "Resources" / "FreeCAD Icons"
    icon_destination.mkdir(parents=True, exist_ok=True)
    sources = freecad_icon_sources(freecad_source)
    required = {"{}.svg".format(name) for name in sources}
    for path in icon_destination.iterdir():
        if path.is_file() and path.name not in required:
            path.unlink()
    for name, source_icon in sources.items():
        (icon_destination / "{}.svg".format(name)).write_bytes(canonical_svg_bytes(source_icon))
    return sources


def sync_ribbon(freecad_source: Path) -> dict[str, Path]:
    source = SOURCE_ROOT / "FreeCAD-Ribbon"
    destination = DESTINATION_ROOT / "FreeCAD-Ribbon"
    for name in (
        *RIBBON_MODULES,
        "CreateStructure.txt",
        "Toolbar name mapping.json",
        "LICENSE",
        "package.xml",
    ):
        copy_file(source, destination, name)

    for relative in (
        "Resources/icons",
        "Resources/packages",
        "Resources/stylesheets",
        "Resources/ui",
    ):
        copy_tree(source, destination, relative)

    translations = source / "translations"
    for translation in translations.glob("*.qm"):
        copy_file(source, destination, translation.relative_to(source))

    # Ribbon asks its local command-icon directory before every source workbench is
    # guaranteed to have registered Qt resources. Copy only the icons used by the
    # current layout, sourced from FreeCAD's official repository checkout.
    return sync_layout_icons(freecad_source, destination)


def write_source_icon_manifest(freecad_source: Path, sources: dict[str, Path]) -> None:
    """Record the official source file and content hash behind every bundled icon."""
    freecad_source = freecad_source.resolve()
    icons = {
        name: {
            "path": source.relative_to(freecad_source).as_posix(),
            "sha256": hashlib.sha256(canonical_svg_bytes(source)).hexdigest(),
        }
        for name, source in sorted(sources.items())
    }
    ICON_SOURCE_MANIFEST.write_text(
        json.dumps(
            {
                "_comment": (
                    "Generated by tools/sync_bundled_addons.py from an official "
                    "FreeCAD source checkout."
                ),
                "icons": icons,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def sync_search() -> None:
    source = SOURCE_ROOT / "SearchBar"
    destination = DESTINATION_ROOT / "SearchBar"
    for name in (*SEARCH_MODULES, "LICENSE", "package.xml"):
        copy_file(source, destination, name)
    copy_tree(source, destination, "Resources/Icons")
    copy_file(source, destination, "Resources/ui/PreferencesUI_SearchBar.ui")


def strip_python_dependencies() -> list[str]:
    """Drop declared third-party Python requirements the local patches removed.

    Bundling exists so installation needs nothing from PyPI. Upstream metadata still
    advertises lxml, so re-applying this mechanically keeps a refresh from quietly
    reintroducing an install-time requirement the runtime no longer has.
    """
    pattern = re.compile(
        r"[ \t]*<depend type=\"python\"(?![^>]*optional=\"true\")>(?P<name>[^<]+)</depend>\r?\n"
    )
    removed = []
    for addon in ("FreeCAD-Ribbon", "SearchBar"):
        path = DESTINATION_ROOT / addon / "package.xml"
        text = path.read_text(encoding="utf-8")
        removed.extend(f"{addon}: {match.group('name')}" for match in pattern.finditer(text))
        stripped = pattern.sub("", text)
        if stripped != text:
            path.write_text(stripped, encoding="utf-8")
    return removed


def assert_minimal_freecad_icons() -> None:
    """Fail unless the bundle contains exactly the icons used by the layout."""
    directory = DESTINATION_ROOT / "FreeCAD-Ribbon" / "Resources" / "FreeCAD Icons"
    bundled = {path.stem for path in directory.iterdir() if path.is_file()}
    required = configured_icon_names()
    if bundled != required:
        raise RuntimeError(
            "Bundled Ribbon icons differ from the layout (missing={}, extra={}).".format(
                sorted(required - bundled), sorted(bundled - required)
            )
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--freecad-source",
        type=Path,
        default=ROOT.parent / "FreeCAD",
        help="Official FreeCAD source checkout (default: sibling ../FreeCAD)",
    )
    parser.add_argument(
        "--icons-only",
        action="store_true",
        help="Refresh the curated command icons without replacing the bundled add-ons",
    )
    arguments = parser.parse_args()
    destination = DESTINATION_ROOT.resolve()
    expected = (ROOT / "bundled-addons").resolve()
    if destination != expected or destination.parent != ROOT.resolve():
        raise RuntimeError(f"Refusing to replace unexpected destination: {destination}")
    if arguments.icons_only:
        icon_sources = sync_layout_icons(
            arguments.freecad_source, DESTINATION_ROOT / "FreeCAD-Ribbon"
        )
        write_source_icon_manifest(arguments.freecad_source, icon_sources)
        assert_minimal_freecad_icons()
        print("Refreshed {} curated FreeCAD icons.".format(len(icon_sources)))
        return
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir()
    icon_sources = sync_ribbon(arguments.freecad_source)
    write_source_icon_manifest(arguments.freecad_source, icon_sources)
    sync_search()
    removed = strip_python_dependencies()
    assert_minimal_freecad_icons()
    file_count = sum(1 for path in destination.rglob("*") if path.is_file())
    byte_count = sum(path.stat().st_size for path in destination.rglob("*") if path.is_file())
    print(f"Bundled {file_count} runtime files ({byte_count / 1024 / 1024:.2f} MiB).")
    print(f"Stripped Python dependencies: {removed or 'none'}")
    print(
        "FreeCAD command icons: {} layout icons copied from {}.".format(
            len(configured_icon_names()), arguments.freecad_source.resolve()
        )
    )


if __name__ == "__main__":
    main()
