#!/usr/bin/env python3
"""Offline validation for the self-contained FreeCAD Addon Manager package."""

from __future__ import annotations

import importlib.util
import ast
import json
import sys
import tempfile
import types
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parent


class ParameterGroup:
    def __init__(self):
        self.values = {"String": {}, "Bool": {}, "Int": {}}

    def __getattr__(self, name):
        if name.startswith("Get") and name.endswith("s"):
            kind = name[3:-1]
            return lambda: list(self.values[kind])
        if name.startswith("Get"):
            kind = name[3:]
            return lambda key, default=None: self.values[kind].get(key, default)
        if name.startswith("Set"):
            kind = name[3:]
            return lambda key, value: self.values[kind].__setitem__(key, value)
        if name.startswith("Rem"):
            kind = name[3:]
            return lambda key: self.values[kind].pop(key, None)
        raise AttributeError(name)


def load_bootstrap(user_root: Path):
    groups = {}
    commands = {}
    gui_events = []
    freecad = types.ModuleType("FreeCAD")
    freecad.Version = lambda: ("1", "1", "3")
    freecad.getUserAppDataDir = lambda: str(user_root) + "/"
    freecad.ParamGet = lambda path: groups.setdefault(path, ParameterGroup())
    freecad.saveParameter = lambda: None
    freecad.ActiveDocument = None

    class FakeObject:
        def __init__(self, type_name, name):
            self.TypeId = type_name
            self.Name = name
            self.Label = name

        def isDerivedFrom(self, type_name):
            return type_name == self.TypeId

    class FakeSheet(FakeObject):
        def __init__(self, name):
            super().__init__("Spreadsheet::Sheet", name)
            self.cells = {}

        def set(self, cell, value):
            self.cells[cell] = value

        def setStyle(self, *_args):
            pass

        def setColumnWidth(self, *_args):
            pass

    class FakeDocument:
        def __init__(self):
            self.Name = "Untitled"
            self.Objects = []

        def addObject(self, type_name, name):
            obj = FakeSheet(name) if type_name == "Spreadsheet::Sheet" else FakeObject(type_name, name)
            self.Objects.append(obj)
            return obj

        def recompute(self):
            pass

    def new_document():
        freecad.ActiveDocument = FakeDocument()
        return freecad.ActiveDocument

    freecad.newDocument = new_document
    gui = types.ModuleType("FreeCADGui")
    menu_bar = types.SimpleNamespace(show=lambda: None)
    main_window = types.SimpleNamespace(menuBar=lambda: menu_bar)
    gui.getMainWindow = lambda: main_window
    gui.addCommand = lambda name, command: commands.__setitem__(name, command)
    gui.activateWorkbench = lambda name: gui_events.append(("workbench", name))
    gui.runCommand = lambda name: gui_events.append(("command", name))
    gui.Selection = types.SimpleNamespace(
        clearSelection=lambda: gui_events.append(("selection", "clear")),
        addSelection=lambda obj: gui_events.append(("selection", obj.Name)),
    )
    gui.activeDocument = lambda: types.SimpleNamespace(
        setEdit=lambda name: gui_events.append(("edit", name))
    )
    sys.modules["FreeCAD"] = freecad
    sys.modules["FreeCADGui"] = gui
    spec = importlib.util.spec_from_file_location("fusion_bootstrap_test", ROOT / "fusion_bootstrap.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    module._test_commands = commands
    module._test_gui_events = gui_events
    return module


def main() -> int:
    package = ET.parse(ROOT / "package.xml").getroot()
    namespace = {"p": "https://wiki.freecad.org/Package_Metadata"}
    assert package.findtext("p:name", namespaces=namespace) == "FusionMyFreeCAD"
    assert package.findtext("p:version", namespaces=namespace) == "3.1.0"
    assert package.findtext("p:license", namespaces=namespace) == "GPL-3.0-or-later"

    required = (
        ROOT / "Init.py",
        ROOT / "InitGui.py",
        ROOT / "fusion_bootstrap.py",
        ROOT / "LICENSE",
        ROOT / "THIRD_PARTY_NOTICES.md",
        ROOT / "Resources" / "FusionMyFreeCAD" / "RibbonStructure.json",
        ROOT / "Resources" / "FusionMyFreeCAD" / "layout-v3.json",
        ROOT / "Resources" / "FusionMyFreeCAD" / "layout-manifest.json",
        ROOT / "Resources" / "FusionMyFreeCAD" / "runtime.py",
        ROOT / "bundled-addons" / "FreeCAD-Ribbon" / "InitGui.py",
        ROOT / "bundled-addons" / "FreeCAD-Ribbon" / "LICENSE",
        ROOT / "bundled-addons" / "FreeCAD-Ribbon" / "Resources" / "FreeCAD Icons" / "PartDesign_Pad.svg",
        ROOT / "bundled-addons" / "SearchBar" / "InitGui.py",
        ROOT / "bundled-addons" / "SearchBar" / "LICENSE",
    )
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    assert not missing, "missing add-on files: {}".format(missing)

    for path in ROOT.rglob("*.py"):
        if any(part in {"setup-build", "bin", "obj"} for part in path.parts):
            continue
        compile(path.read_text(encoding="utf-8-sig"), str(path), "exec")

    cache_source = (ROOT / "bundled-addons" / "FreeCAD-Ribbon" / "CacheFunctions.py").read_text(
        encoding="utf-8"
    )
    cache_tree = ast.parse(cache_source)
    startup_check = next(
        node for node in cache_tree.body if isinstance(node, ast.FunctionDef) and node.name == "CheckDataFileVersion"
    )
    assert not any(
        isinstance(node, ast.Attribute) and node.attr == "Mbox" for node in ast.walk(startup_check)
    ), "Ribbon startup cache check must not show a modal dialog"
    assert "WindowCloseButtonHint, True" in cache_source

    runtime_source = (ROOT / "Resources" / "FusionMyFreeCAD" / "runtime.py").read_text(encoding="utf-8")
    assert 'search.SetBool("ShowChangeDialog", False)' in runtime_source
    assert 'search.SetString("DoNotShowAgain", "1.8")' in runtime_source
    assert 'DockWindows/ComboView").SetBool("Enabled", True)' in runtime_source
    assert 'MainWindow/DockWindows").SetBool("Std_ComboView", True)' in runtime_source
    assert 'names = ("Combo View", "ComboView", "Model", "Tree view")' in runtime_source
    assert 'QtWidgets.QTabWidget' in runtime_source
    assert 'PREFERENCES.GetBool("CreateStarterDesign", True)' in runtime_source
    assert 'document.addObject("PartDesign::Body", "Body")' in runtime_source
    installed_entry = (ROOT / "installer" / "assets" / "FusionMyFreeCAD" / "InitGui.py").read_text(
        encoding="utf-8"
    )
    installed_runtime = (ROOT / "installer" / "assets" / "FusionMyFreeCAD" / "FusionRuntime.py").read_text(encoding="utf-8")
    assert 'spec_from_file_location' in installed_entry
    assert 'FusionRuntime.py' in installed_entry
    assert 'Gui.addCommand("FusionMyFreeCAD_CreateSketch"' in installed_runtime
    assert 'Gui.addCommand("FusionMyFreeCAD_ParameterTable"' in installed_runtime
    assert 'DockWindows/ComboView").SetBool("Enabled", True)' in installed_runtime
    assert 'globals().get("__file__")' in installed_runtime
    assert 'MainWindow/DockWindows").SetBool("Std_ComboView", True)' in installed_runtime
    search_startup = (ROOT / "bundled-addons" / "SearchBar" / "InitGui.py").read_text(encoding="utf-8")
    assert "LoadChangeDialog_SearchBar.main()" not in search_startup
    assert 'SetBoolSetting("ShowChangeDialog", False)' in search_startup
    assert 'SetStringSetting("DoNotShowAgain", "1.8")' in search_startup
    ribbon_binding = (ROOT / "bundled-addons" / "FreeCAD-Ribbon" / "FCBinding.py").read_text(
        encoding="utf-8"
    )
    assert 'workbenchName in Dict.get("authoritativeWorkbenches", [])' in ribbon_binding
    assert "ListToolbars: list = []" in ribbon_binding

    layout = json.loads((ROOT / "Resources" / "FusionMyFreeCAD" / "layout-v3.json").read_text())
    assert layout["layoutVersion"] == "3.1.0"
    assert layout["workbenches"]["PartDesignWorkbench"][0]["commands"][0][0] == "FusionMyFreeCAD_CreateSketch"
    part_design = layout["workbenches"]["PartDesignWorkbench"]
    assert any(
        entry[0] == "PartDesign_SubShapeBinder"
        for panel in part_design
        for entry in panel["commands"]
    )
    assert any(
        entry[0] == "FusionMyFreeCAD_ParameterTable"
        for panel in part_design
        for entry in panel["commands"]
    )
    part_tools = layout["workbenches"]["PartWorkbench"]
    assert [panel["title"] for panel in part_tools] == [
        "CREATE / IMPORT", "BOOLEAN", "SPLIT", "REPAIR", "FREQUENT", "INSPECT"
    ]
    assert not list((ROOT / "bundled-addons").rglob(".git"))

    with tempfile.TemporaryDirectory() as temporary:
        bootstrap = load_bootstrap(Path(temporary))
        bootstrap.register_commands()
        create_sketch = bootstrap._test_commands["FusionMyFreeCAD_CreateSketch"]
        assert create_sketch.IsActive()
        create_sketch.Activated()
        assert sys.modules["FreeCAD"].ActiveDocument is not None
        assert sys.modules["FreeCAD"].ActiveDocument.Objects[0].TypeId == "PartDesign::Body"
        assert bootstrap._test_gui_events == [
            ("workbench", "PartDesignWorkbench"),
            ("command", "PartDesign_NewSketch"),
            ("workbench", "SketcherWorkbench"),
        ]
        sys.modules["FreeCAD"].ActiveDocument = None
        bootstrap._test_gui_events.clear()
        parameter_table = bootstrap._test_commands["FusionMyFreeCAD_ParameterTable"]
        assert parameter_table.IsActive()
        parameter_table.Activated()
        document = sys.modules["FreeCAD"].ActiveDocument
        assert document.Objects[0].cells == {
            "A1": "Parameter",
            "B1": "Value / Expression",
            "C1": "Notes",
        }
        assert bootstrap._test_gui_events == [
            ("workbench", "SpreadsheetWorkbench"),
            ("selection", "clear"),
            ("selection", "Parameters"),
            ("edit", "Parameters"),
        ]
        Path(bootstrap.RIBBON_DIR).mkdir(parents=True)
        Path(bootstrap.RIBBON_PATH).write_text('{"previous": true}', encoding="utf-8")
        view = sys.modules["FreeCAD"].ParamGet("User parameter:BaseApp/Preferences/View")
        view.SetString("NavigationStyle", "PreviousStyle")
        bootstrap.prepare()
        valid, checks = bootstrap.verify()
        assert valid, checks
        state = json.loads(Path(bootstrap.STATE_PATH).read_text(encoding="utf-8"))
        assert state["packageVersion"] == "3.1.0"
        generated = json.loads(Path(bootstrap.RIBBON_PATH).read_text(encoding="utf-8"))
        sketch = generated["workbenches"]["SketcherWorkbench"]
        assert "order" not in sketch
        assert sketch["toolbars"]["order"] == [panel["name"] for panel in layout["workbenches"]["SketcherWorkbench"]]
        assert sketch["toolbars"]["order"][0] == "Fusion Sketch Create_newPanel"
        assert "Views" not in sketch["toolbars"]["order"]
        assert "Fusion Sketch Entry_newPanel" not in sketch["toolbars"]
        assert "Fusion Sketch Frequent_newPanel" not in sketch["toolbars"]
        assert sketch["toolbars"]["order"][-1] == "Fusion Finish_newPanel"
        assert state["ribbonSha256"]
        view.SetString("NavigationStyle", "Gui::RevitNavigationStyle")
        removed = Path(bootstrap.restore())
        assert json.loads(Path(bootstrap.RIBBON_PATH).read_text(encoding="utf-8")) == {"previous": True}
        assert view.GetString("NavigationStyle") == "PreviousStyle"
        assert (removed / "FusionMyFreeCAD-addon-state.json").is_file()

    package_roots = (ROOT / "Resources", ROOT / "bundled-addons")
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
        for package_root in package_roots
        for path in package_root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix not in {".pyc", ".pyo"}
    )
    total_bytes = sum(path.stat().st_size for path in package_files)
    print("VALID: self-contained add-on 3.1.0; {:.1f} MiB unpacked".format(total_bytes / 1024 / 1024))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
