#!/usr/bin/env python3
"""Offline semantic checks for the v3 setup payload."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
INSTALLER = ROOT / "installer"


def main() -> int:
    spec = json.loads((INSTALLER / "assets" / "layout-v2.json").read_text(encoding="utf-8"))
    manifest = json.loads(
        (ROOT / "prototype" / "freecad-1.1.3-command-manifest.json").read_text(encoding="utf-8")
    )
    runtime = json.loads(
        (INSTALLER / "assets" / "FusionMyFreeCAD" / "layout-manifest.json").read_text(encoding="utf-8")
    )
    known = set(manifest["commands"]) | {
        "FusionMyFreeCAD_CreateSketch",
        "FusionMyFreeCAD_ParameterTable",
    }
    referenced = set()
    for entries in spec["dropdownButtons"].values():
        referenced.update(entry[0] for entry in entries)
    for panels in spec["workbenches"].values():
        for panel in panels:
            referenced.update(entry[0] for entry in panel["commands"] if not entry[0].endswith("_ddb"))
    unknown = sorted(referenced - known)
    assert not unknown, f"commands absent from verified manifest: {unknown}"
    assert spec["layoutVersion"] == runtime["layoutVersion"] == "3.1.0"
    part = spec["workbenches"]["PartDesignWorkbench"]
    sketch = spec["workbenches"]["SketcherWorkbench"]
    surface = spec["workbenches"]["SurfaceWorkbench"]
    part_tools = spec["workbenches"]["PartWorkbench"]
    assert [panel["title"] for panel in part] == [
        "SKETCH", "CREATE", "MODIFY", "CONSTRUCT", "PARAMETERS", "FREQUENT", "INSPECT"
    ]
    assert [panel["title"] for panel in part_tools] == [
        "CREATE / IMPORT", "BOOLEAN", "SPLIT", "REPAIR", "FREQUENT", "INSPECT"
    ]
    assert [panel["title"] for panel in sketch] == [
        "CREATE", "MODIFY", "CONSTRAINTS", "CONFIGURE", "INSPECT", "INSERT", "SELECT", "SKETCH"
    ]
    assert [panel["title"] for panel in surface] == ["CREATE", "MODIFY", "FREQUENT", "INSPECT"]
    assert sketch[-1]["commands"][0][0] == "Sketcher_LeaveSketch"
    visible = {entry[0] for panels in spec["workbenches"].values() for panel in panels for entry in panel["commands"]}
    for required in (
        "FusionMyFreeCAD_CreateSketch", "FusionMyFreeCAD_ParameterTable", "PartDesign_SubShapeBinder",
        "PartDesign_Pad", "PartDesign_Pocket", "PartDesign_Hole", "PartDesign_Fillet",
        "PartDesign_Thickness", "Sketcher_Trimming", "Sketcher_Offset",
        "Sketcher_ConstrainTangent", "Sketcher_Dimension", "Sketcher_CreateRectangle_Center",
        "Sketcher_Symmetry", "Surface_Filling", "Part_BooleanFragments", "Part_SliceApart",
        "Part_RefineShape", "Part_Defeaturing",
    ):
        assert required in visible, f"primary command is not visible: {required}"
    assert sketch[0]["commands"][1][0] == "Sketcher_CreateRectangle_Center"
    assert any(entry[0] == "Sketcher_Symmetry" for entry in sketch[1]["commands"])
    sketch_commands = {entry[0] for panel in sketch for entry in panel["commands"]}
    assert not sketch_commands.intersection({"Sketcher_NewSketch", "Std_Measure", "Std_ViewFitAll", "FusionMyFreeCAD_Verify"})
    adaptive_sketch = runtime["adaptivePins"]["SketcherWorkbench"]
    adaptive_commands = {
        command
        for panel in adaptive_sketch["panels"].values()
        for command in panel["commands"]
    }
    assert "Sketcher_CreateRectangle_Center" not in adaptive_commands
    assert "Sketcher_Symmetry" not in adaptive_commands
    assert runtime["adaptivePins"]["PartWorkbench"]["defaults"] == [
        "Part_BooleanFragments", "Part_RefineShape", "Part_Defeaturing", "Part_CheckGeometry"
    ]
    panel_commands = {
        panel["name"]: {entry[0] for entry in panel["commands"]} for panel in sketch
    }
    for panel_name, adaptive in adaptive_sketch["panels"].items():
        assert set(adaptive["commands"]).issubset(panel_commands[panel_name])
    ET.parse(INSTALLER / "assets" / "FusionMyFreeCAD" / "package.xml")
    setup_source = (INSTALLER / "Setup-FusionMyFreeCAD.ps1").read_text(encoding="utf-8-sig")
    program_source = (INSTALLER / "Program.cs").read_text(encoding="utf-8-sig")
    entry_source = (INSTALLER / "assets" / "FusionMyFreeCAD" / "InitGui.py").read_text(encoding="utf-8")
    runtime_source = (INSTALLER / "assets" / "FusionMyFreeCAD" / "FusionRuntime.py").read_text(encoding="utf-8")
    assert 'spec_from_file_location' in entry_source
    assert 'FusionRuntime.py' in entry_source
    assert 'names = ("Combo View", "ComboView", "Model", "Tree view")' in runtime_source
    assert 'PREFERENCES.GetBool("CreateStarterDesign", True)' in runtime_source
    assert 'document.addObject("PartDesign::Body", "Body")' in runtime_source
    assert 'ribbon.SetInt("IconSize_Large", 72)' in runtime_source
    assert '$mergeTool = $script:SetupExecutable' in setup_source
    assert 'Join-Path (Split-Path -Parent $PSScriptRoot) "FusionMyFreeCAD Setup.exe"' not in setup_source
    assert "Environment.ProcessPath" in program_source
    assert 'args[0] == "--discover-freecad"' in program_source
    assert 'args[0] == "--smoke-ui"' in program_source
    assert 'args[0] == "--inspect-ui"' in program_source
    assert 'args[0] == "--screenshot-ui"' in program_source
    assert "FindPackageVersion(projectRoot)" in program_source
    assert 'Path.GetDirectoryName(Environment.ProcessPath ?? Application.ExecutablePath)' in program_source
    assert 'Upgrade to {packageVersion}' in program_source
    assert 'Reinstall {packageVersion}' in program_source
    assert 'Upgrade to 3.1.0' not in program_source
    assert "AutoScaleMode = AutoScaleMode.None" in program_source
    assert "FreeCadDiscovery.Discover" in program_source
    assert 'Text = "Add Build…"' not in program_source
    assert 'ConfigureLauncherButton(addBuildButton, "Add Build…"' in program_source
    assert '@"build\\debug\\bin\\FreeCAD.exe"' in program_source
    assert 'TryReadSourceVersion' in program_source
    assert 'RegistryKey.OpenBaseKey' in program_source
    assert 'WorkingDirectory = Path.GetDirectoryName(installation.ExecutablePath)!' in program_source
    assert program_source.index("Controls.AddRange([title, subtitle, tabs])") < program_source.index("BuildLauncherPage(launchPage)")
    assert '-SetupExecutable \\"{executable}\\"' in program_source
    assert "RECOVERED_STATE|" in setup_source
    assert "Copy-Item -LiteralPath $stateBackup -Destination $statePath -Force" in setup_source
    assert 'ribbon["authoritativeWorkbenches"]' in program_source
    for path in (
        INSTALLER / "layout_spec.py",
        INSTALLER / "layout_spec_v3.py",
        INSTALLER / "build_assets.py",
        INSTALLER / "assets" / "FusionMyFreeCAD" / "Init.py",
        INSTALLER / "assets" / "FusionMyFreeCAD" / "InitGui.py",
        INSTALLER / "assets" / "FusionMyFreeCAD" / "FusionRuntime.py",
    ):
        compile(path.read_text(encoding="utf-8"), str(path), "exec")
    print(f"VALID: layout {spec['layoutVersion']}; {len(visible)} visible entries; {len(referenced)} verified commands")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
