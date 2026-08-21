"""Declarative Fusion-familiar ribbon layout for FreeCAD 1.1.x."""

from __future__ import annotations


LAYOUT_VERSION = "3.0.0"  # Legacy v2 generator; build_assets.py uses layout_spec_v3.py.


DROPDOWNS = {
    "Fusion_MoreCreate_ddb": [
        ("PartDesign_CompPrimitiveAdditive", "PartDesignWorkbench"),
        ("PartDesign_Body", "PartDesignWorkbench"),
    ],
    "Fusion_Pattern_ddb": [
        ("PartDesign_Mirrored", "PartDesignWorkbench"),
        ("PartDesign_LinearPattern", "PartDesignWorkbench"),
        ("PartDesign_PolarPattern", "PartDesignWorkbench"),
        ("PartDesign_MultiTransform", "PartDesignWorkbench"),
    ],
    "Fusion_MoreSketchCreate_ddb": [
        ("Sketcher_CreatePolyline", "SketcherWorkbench"),
        ("Sketcher_CreateBSpline", "SketcherWorkbench"),
        ("Sketcher_CompCreateArc", "SketcherWorkbench"),
    ],
    "Fusion_MoreConstraints_ddb": [
        ("Sketcher_ConstrainBlock", "SketcherWorkbench"),
        ("Sketcher_ConstrainSymmetric", "SketcherWorkbench"),
        ("Sketcher_CompDimensionTools", "SketcherWorkbench"),
        ("Sketcher_CompConstrainTools", "SketcherWorkbench"),
    ],
}


# command, source workbench, ribbon size, familiar label, icon
PART_DESIGN = [
    (
        "Fusion Create_newPanel",
        "CREATE",
        [
            ("PartDesign_NewSketch", "PartDesignWorkbench", "large", "Create Sketch", "PartDesign_NewSketch"),
            ("PartDesign_Pad", "PartDesignWorkbench", "large", "Extrude", "PartDesign_Pad"),
            ("PartDesign_Pocket", "PartDesignWorkbench", "large", "Cut", "PartDesign_Pocket"),
            ("PartDesign_Revolution", "PartDesignWorkbench", "large", "Revolve", "PartDesign_Revolution"),
            ("PartDesign_Hole", "PartDesignWorkbench", "large", "Hole", "PartDesign_Hole"),
            ("PartDesign_AdditivePipe", "PartDesignWorkbench", "small", "Sweep", "PartDesign_AdditivePipe"),
            ("PartDesign_AdditiveLoft", "PartDesignWorkbench", "small", "Loft", "PartDesign_AdditiveLoft"),
            ("Fusion_Pattern_ddb", "General", "small", "Pattern", "PartDesign_LinearPattern"),
            ("Fusion_MoreCreate_ddb", "General", "small", "More", "PartDesign_CompPrimitiveAdditive"),
        ],
    ),
    (
        "Fusion Modify_newPanel",
        "MODIFY",
        [
            ("PartDesign_Fillet", "PartDesignWorkbench", "large", "Fillet", "PartDesign_Fillet"),
            ("PartDesign_Chamfer", "PartDesignWorkbench", "large", "Chamfer", "PartDesign_Chamfer"),
            ("PartDesign_Thickness", "PartDesignWorkbench", "large", "Shell", "PartDesign_Thickness"),
            ("PartDesign_Draft", "PartDesignWorkbench", "small", "Draft", "PartDesign_Draft"),
            ("PartDesign_Boolean", "PartDesignWorkbench", "small", "Combine", "PartDesign_Boolean"),
        ],
    ),
    (
        "Fusion Construct_newPanel",
        "CONSTRUCT",
        [
            ("PartDesign_Plane", "PartDesignWorkbench", "large", "Plane", "PartDesign_Plane"),
            ("PartDesign_Line", "PartDesignWorkbench", "small", "Axis", "PartDesign_Line"),
            ("PartDesign_Point", "PartDesignWorkbench", "small", "Point", "PartDesign_Point"),
            ("PartDesign_CoordinateSystem", "PartDesignWorkbench", "small", "Coordinate System", "PartDesign_CoordinateSystem"),
        ],
    ),
    (
        "Fusion Inspect_newPanel",
        "INSPECT",
        [
            ("Std_Measure", "Global", "large", "Measure", "Std_Measure"),
            ("Part_CheckGeometry", "PartWorkbench", "small", "Check Geometry", "Part_CheckGeometry"),
            ("Std_ViewFitAll", "Global", "small", "Fit All", "Std_ViewFitAll"),
        ],
    ),
]


SKETCHER = [
    (
        "Fusion Sketch Create_newPanel",
        "CREATE",
        [
            ("Sketcher_CreateLine", "SketcherWorkbench", "large", "Line", "Sketcher_CreateLine"),
            ("Sketcher_CompCreateRectangles", "SketcherWorkbench", "large", "Rectangle", "Sketcher_CreateRectangle"),
            ("Sketcher_CompCreateConic", "SketcherWorkbench", "large", "Circle", "Sketcher_CreateCircle"),
            ("Sketcher_CreateArc", "SketcherWorkbench", "small", "Arc", "Sketcher_CreateArc"),
            ("Sketcher_CreateSlot", "SketcherWorkbench", "small", "Slot", "Sketcher_CreateSlot"),
            ("Fusion_MoreSketchCreate_ddb", "General", "small", "More", "Sketcher_CreateBSpline"),
        ],
    ),
    (
        "Fusion Sketch Modify_newPanel",
        "MODIFY",
        [
            ("Sketcher_CompCreateFillets", "SketcherWorkbench", "large", "Fillet", "Sketcher_CreateFillet"),
            ("Sketcher_Trimming", "SketcherWorkbench", "large", "Trim", "Sketcher_Trimming"),
            ("Sketcher_Extend", "SketcherWorkbench", "small", "Extend", "Sketcher_Extend"),
            ("Sketcher_Offset", "SketcherWorkbench", "large", "Offset", "Sketcher_Offset"),
            ("Sketcher_Symmetry", "SketcherWorkbench", "small", "Mirror", "Sketcher_Symmetry"),
            ("Sketcher_RectangularArray", "SketcherWorkbench", "small", "Pattern", "Sketcher_RectangularArray"),
            ("Sketcher_CompExternal", "SketcherWorkbench", "small", "Project", "Sketcher_Projection"),
        ],
    ),
    (
        "Fusion Sketch Constraints_newPanel",
        "CONSTRAINTS",
        [
            ("Sketcher_Dimension", "SketcherWorkbench", "large", "Dimension", "Sketcher_Dimension"),
            ("Sketcher_ConstrainHorVer", "SketcherWorkbench", "small", "Horizontal / Vertical", "Sketcher_ConstrainHorVer"),
            ("Sketcher_ConstrainCoincident", "SketcherWorkbench", "small", "Coincident", "Sketcher_ConstrainCoincident"),
            ("Sketcher_ConstrainTangent", "SketcherWorkbench", "small", "Tangent", "Sketcher_ConstrainTangent"),
            ("Sketcher_ConstrainEqual", "SketcherWorkbench", "small", "Equal", "Sketcher_ConstrainEqual"),
            ("Sketcher_ConstrainParallel", "SketcherWorkbench", "small", "Parallel", "Sketcher_ConstrainParallel"),
            ("Sketcher_ConstrainPerpendicular", "SketcherWorkbench", "small", "Perpendicular", "Sketcher_ConstrainPerpendicular"),
            ("Fusion_MoreConstraints_ddb", "General", "small", "More", "Sketcher_CompConstrainTools"),
        ],
    ),
    (
        "Fusion Sketch Configure_newPanel",
        "CONFIGURE",
        [
            ("Sketcher_ToggleConstruction", "SketcherWorkbench", "large", "Construction", "Sketcher_ToggleConstruction"),
            ("Sketcher_CompExternal", "SketcherWorkbench", "small", "Project / Include", "Sketcher_Projection"),
        ],
    ),
    (
        "Fusion Sketch Inspect_newPanel",
        "INSPECT",
        [
            ("Std_Measure", "Global", "large", "Measure", "Std_Measure"),
            ("Std_ViewFitAll", "Global", "small", "Fit All", "Std_ViewFitAll"),
        ],
    ),
    (
        "Fusion Finish_newPanel",
        "SKETCH",
        [("Sketcher_LeaveSketch", "SketcherWorkbench", "large", "Finish Sketch", "Sketcher_LeaveSketch")],
    ),
]


def _workbench(panels):
    toolbars = {}
    new_panels = {}
    for panel_name, title, entries in panels:
        order = [entry[0] for entry in entries]
        new_panels[panel_name] = [[entry[0], entry[1]] for entry in entries]
        toolbars[panel_name] = {
            "title": title,
            "Enabled": True,
            "order": order,
            "commands": {
                command: {
                    "size": size,
                    "text": text,
                    "icon": icon,
                    "IsExtra": True,
                }
                for command, _source, size, text, icon in entries
            },
        }
    return {"toolbars": toolbars, "order": list(toolbars)}, new_panels


def build_overlay():
    part_design, part_design_new = _workbench(PART_DESIGN)
    sketcher, sketcher_new = _workbench(SKETCHER)
    return {
        "schemaVersion": 2,
        "layoutVersion": LAYOUT_VERSION,
        "targetFreeCAD": "1.1.x",
        "dropdownButtons": {name: [list(item) for item in entries] for name, entries in DROPDOWNS.items()},
        "newPanels": {
            "PartDesignWorkbench": part_design_new,
            "SketcherWorkbench": sketcher_new,
        },
        "workbenches": {
            "PartDesignWorkbench": part_design,
            "SketcherWorkbench": sketcher,
        },
    }


def expected_primary_commands():
    commands = set()
    for panels in (PART_DESIGN, SKETCHER):
        for _panel_name, _title, entries in panels:
            commands.update(entry[0] for entry in entries if not entry[0].endswith("_ddb"))
    for entries in DROPDOWNS.values():
        commands.update(entry[0] for entry in entries)
    return sorted(commands)
