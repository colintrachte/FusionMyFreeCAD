"""Build the tracked third-party runtime payload from ignored upstream snapshots."""

from __future__ import annotations

import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "vendor"
DESTINATION_ROOT = ROOT / "bundled-addons"

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
    layout_path = ROOT / "Resources" / "FusionMyFreeCAD" / "layout-v3.json"
    layout = json.loads(layout_path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for panels in layout["workbenches"].values():
        for panel in panels:
            for command, _workbench, _size, _label, icon in panel["commands"]:
                names.add(command)
                names.add(Path(icon).name)
    for commands in layout["dropdownButtons"].values():
        names.update(command for command, _workbench in commands)
    return names


def sync_ribbon() -> None:
    source = SOURCE_ROOT / "FreeCAD-Ribbon"
    destination = DESTINATION_ROOT / "FreeCAD-Ribbon"
    for name in (*RIBBON_MODULES, "CreateStructure.txt", "Toolbar name mapping.json", "LICENSE", "package.xml"):
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

    icon_source = source / "Resources" / "FreeCAD Icons"
    selected_names = configured_icon_names()
    selected_icons = [path for path in icon_source.iterdir() if path.is_file() and path.stem in selected_names]
    if not selected_icons:
        raise RuntimeError("No configured FreeCAD command icons were selected")
    for icon in selected_icons:
        copy_file(source, destination, icon.relative_to(source))


def sync_search() -> None:
    source = SOURCE_ROOT / "SearchBar"
    destination = DESTINATION_ROOT / "SearchBar"
    for name in (*SEARCH_MODULES, "LICENSE", "package.xml"):
        copy_file(source, destination, name)
    copy_tree(source, destination, "Resources/Icons")
    copy_file(source, destination, "Resources/ui/PreferencesUI_SearchBar.ui")


def main() -> None:
    destination = DESTINATION_ROOT.resolve()
    expected = (ROOT / "bundled-addons").resolve()
    if destination != expected or destination.parent != ROOT.resolve():
        raise RuntimeError(f"Refusing to replace unexpected destination: {destination}")
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir()
    sync_ribbon()
    sync_search()
    file_count = sum(1 for path in destination.rglob("*") if path.is_file())
    byte_count = sum(path.stat().st_size for path in destination.rglob("*") if path.is_file())
    print(f"Bundled {file_count} runtime files ({byte_count / 1024 / 1024:.2f} MiB).")


if __name__ == "__main__":
    main()
