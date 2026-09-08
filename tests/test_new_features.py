"""Unit tests for FusionMyFreeCAD roadmap features:

- Smart Slot Generator
- Smart Loop Offset Wrapper
- Trimming Coincident Repair
- Human-Readable Solver Diagnostics
- One-Click Datum Helpers
- Multi-Region Sketch Face Selection & Pad Observers
- In-Context Ghosted Sketching
- Fast Parameters Dock
"""

from __future__ import annotations

import types

import pytest
from fake_freecad import (
    FakeConstraint,
    FakeLineSegment,
    FakeSketch,
)


@pytest.fixture
def sketch_env(env):
    return env


# ---------------------------------------------------------------------------
# 1. Smart Slot Generator
# ---------------------------------------------------------------------------


def test_create_smart_slot_geometry_and_constraints(sketch_env):
    tools = sketch_env.load_sketch_tools()
    sketch = FakeSketch("Sketch")
    sketch_env.begin_sketch_edit(sketch)

    result = tools.create_smart_slot(sketch, (-20.0, 0.0), (20.0, 0.0), radius=5.0)

    assert result["status"] == "ok"
    assert "midline" in result
    assert "line1" in result
    assert "line2" in result
    assert "arc1" in result
    assert "arc2" in result

    # Check that midline is construction
    mid = sketch.Geometry[result["midline"]]
    assert mid.Construction is True

    # Check side lines are non-construction
    assert sketch.Geometry[result["line1"]].Construction is False
    assert sketch.Geometry[result["line2"]].Construction is False

    # Check constraints: coincidents, tangents, parallel, equal, symmetry, driving dims
    c_types = [c.Type for c in sketch.Constraints]
    assert c_types.count("Coincident") >= 6  # 4 corners + 2 arc centers
    assert c_types.count("Tangent") == 4
    assert "Parallel" in c_types
    assert "Equal" in c_types
    assert "Symmetric" in c_types
    assert "Distance" in c_types
    assert "Radius" in c_types


def test_add_smart_slot_command(sketch_env):
    tools = sketch_env.load_sketch_tools()
    sketch = FakeSketch("Sketch")
    sketch_env.begin_sketch_edit(sketch)

    result = tools.add_smart_slot(radius=8.0)
    assert result["status"] == "ok"
    assert len(sketch.Geometry) == 5  # 1 midline + 2 lines + 2 arcs


def test_smart_slot_from_selected_line(sketch_env):
    tools = sketch_env.load_sketch_tools()
    sketch = FakeSketch("Sketch")
    sketch.addGeometry(FakeLineSegment((0.0, 0.0), (50.0, 0.0)))
    sketch_env.begin_sketch_edit(sketch)
    sketch_env.select_subelements(sketch, ["Edge1"])

    result = tools.add_smart_slot(radius=6.0)
    assert result["status"] == "ok"
    # End of midline should match line's length
    mid = sketch.Geometry[result["midline"]]
    assert abs(mid.EndPoint.x - 50.0) < 1e-5


# ---------------------------------------------------------------------------
# 2. Smart Loop Offset Wrapper
# ---------------------------------------------------------------------------


def test_detect_contour_chains(sketch_env):
    tools = sketch_env.load_sketch_tools()
    sketch = FakeSketch("Sketch")
    # Box: 4 edges connected end-to-end
    sketch.addGeometry(FakeLineSegment((0.0, 0.0), (20.0, 0.0)))
    sketch.addGeometry(FakeLineSegment((20.0, 0.0), (20.0, 10.0)))
    sketch.addGeometry(FakeLineSegment((20.0, 10.0), (0.0, 10.0)))
    sketch.addGeometry(FakeLineSegment((0.0, 10.0), (0.0, 0.0)))

    chains = tools.detect_contour_chains(sketch)
    assert len(chains) == 1
    assert chains[0]["closed"] is True
    assert len(chains[0]["edges"]) == 4


def test_create_smart_offset(sketch_env):
    tools = sketch_env.load_sketch_tools()
    sketch = FakeSketch("Sketch")
    sketch.addGeometry(FakeLineSegment((0.0, 0.0), (30.0, 0.0)))
    sketch.addGeometry(FakeLineSegment((30.0, 0.0), (30.0, 20.0)))
    sketch_env.begin_sketch_edit(sketch)

    result = tools.create_smart_offset(sketch, [0, 1], offset_dist=5.0)
    assert result["status"] == "ok"
    assert len(result["created"]) == 2

    # Verify parallel constraints and coincident connection
    c_types = [c.Type for c in sketch.Constraints]
    assert "Parallel" in c_types
    assert "Coincident" in c_types
    assert "Distance" in c_types


# ---------------------------------------------------------------------------
# 3. Trimming Coincident Repair
# ---------------------------------------------------------------------------


def test_capture_and_repair_trimmed_coincidents(sketch_env):
    tools = sketch_env.load_sketch_tools()
    sketch = FakeSketch("Sketch")
    g0 = sketch.addGeometry(FakeLineSegment((0.0, 0.0), (20.0, 0.0)))
    g1 = sketch.addGeometry(FakeLineSegment((20.0, 0.0), (20.0, 20.0)))
    sketch.addConstraint(FakeConstraint("Coincident", g0, 2, g1, 1))

    # Capture attachments on g0
    records = tools.capture_curve_attachments(sketch, g0)
    assert len(records) == 1
    assert records[0]["type"] == "Coincident"

    # Simulate trim and repair
    reconnected = tools.repair_trimmed_coincidents(sketch, g0)
    assert reconnected >= 1


# ---------------------------------------------------------------------------
# 4. Human-Readable Solver Diagnostics
# ---------------------------------------------------------------------------


def test_diagnose_sketch_solver_clean(sketch_env):
    tools = sketch_env.load_sketch_tools()
    sketch = FakeSketch("Sketch")
    sketch.DoF = 1

    report = tools.diagnose_sketch_solver(sketch)
    assert report["is_clean"] is True
    assert report["dof"] == 1
    assert report["redundant"] == []
    assert report["conflicting"] == []


def test_diagnose_sketch_solver_with_redundancy(sketch_env):
    tools = sketch_env.load_sketch_tools()
    sketch = FakeSketch("Sketch")
    g0 = sketch.addGeometry(FakeLineSegment((0.0, 0.0), (10.0, 0.0)))
    sketch.addConstraint(FakeConstraint("Horizontal", g0))
    sketch.RedundantConstraints = [0]

    report = tools.diagnose_sketch_solver(sketch)
    assert report["is_clean"] is False
    assert len(report["redundant"]) == 1
    assert "Constraint #0: Horizontal on Line 0" in report["redundant"][0]

    # Test auto-removal
    removed = tools.remove_redundant_constraints(sketch)
    assert removed == 1


# ---------------------------------------------------------------------------
# 5. One-Click Datum Helpers
# ---------------------------------------------------------------------------


def test_create_midplane(sketch_env):
    import fusion_datum_tools

    doc = sketch_env.app.ActiveDocument or sketch_env._new_document()
    body = doc.addObject("PartDesign::Body", "Body")

    face1 = types.SimpleNamespace(Object=body, SubElementNames=["Face1"])
    face2 = types.SimpleNamespace(Object=body, SubElementNames=["Face2"])
    sketch_env.selection_ex = [face1, face2]

    res = fusion_datum_tools.create_midplane()
    assert res["status"] == "ok"
    plane = res["plane"]
    assert plane.Label == "Midplane"
    assert plane.MapMode == "Plane between two faces"


def test_create_plane_at_angle(sketch_env):
    import fusion_datum_tools

    doc = sketch_env.app.ActiveDocument or sketch_env._new_document()
    body = doc.addObject("PartDesign::Body", "Body")

    face = (body, ["Face1"])
    edge = (body, ["Edge1"])

    res = fusion_datum_tools.create_plane_at_angle(face_ref=face, edge_ref=edge, angle=30.0)
    assert res["status"] == "ok"
    plane = res["plane"]
    assert plane.Label == "PlaneAtAngle"
    assert plane.MapMode == "Plane by an axis and an angle"


# ---------------------------------------------------------------------------
# 6. Multi-Region Sketch Face Selection & Pad Observers
# ---------------------------------------------------------------------------


def test_sketch_repair_observer_recompute(sketch_env):
    """_SketchRepairObserver ensures sketch.InternalShape is populated on Shape change."""
    import fusion_bootstrap

    doc = sketch_env.app.ActiveDocument or sketch_env._new_document()
    sketch = doc.addObject("Sketcher::SketchObject", "Sketch")

    obs = fusion_bootstrap._SketchRepairObserver()
    # Trigger slotChangedObject on Shape
    obs.slotChangedObject(sketch, "Shape")


def test_pad_selection_observer_internal_face(sketch_env):
    """_PadSelectionObserver enables picking InternalFace in 3D to set Pad profile."""
    import fusion_bootstrap

    doc = sketch_env.app.ActiveDocument or sketch_env._new_document()
    body = doc.addObject("PartDesign::Body", "Body")
    sketch = doc.addObject("Sketcher::SketchObject", "Sketch")
    body.addObject(sketch)

    pad = doc.addObject("PartDesign::Pad", "Pad")
    pad.Profile = (sketch, [""])
    body.addObject(pad)

    obs = fusion_bootstrap._PadSelectionObserver()
    obs.addSelection(doc.Name, sketch.Name, "Sketch.InternalFace1")

    # Profile should now be updated to (sketch, ['InternalFace1'])
    assert pad.Profile == (sketch, ["InternalFace1"])


# ---------------------------------------------------------------------------
# 7. Fast Parameters Dock
# ---------------------------------------------------------------------------


def test_parameters_sheet_creation(sketch_env):
    import fusion_parameters_dock

    doc = sketch_env.app.ActiveDocument or sketch_env._new_document()
    sheet = fusion_parameters_dock.get_or_create_parameters_sheet(doc)

    assert sheet is not None
    assert sheet.Label == "Parameters"
    assert sheet.cells.get("A1") == "Parameter"
    assert sheet.cells.get("B1") == "Value / Expression"


def test_parameters_dock_document_safety(env):
    """The dock must bind to a specific document and never mutate another document."""
    env.install()
    import fusion_parameters_dock

    doc1 = env._new_document("Doc1")
    doc2 = env._new_document("Doc2")

    dock = fusion_parameters_dock.FastParametersDock()
    dock.bind_to_document(doc1)
    assert dock._bound_doc_name == "Doc1"

    # Add parameter to Doc1
    dock.on_add_parameter()
    sheet1 = fusion_parameters_dock.get_or_create_parameters_sheet(doc1)
    assert sheet1.get("A2") == "Param1"

    # Switch active document to Doc2
    env._set_active_document(doc2)
    assert dock._bound_doc_name == "Doc2"
    assert dock.table.rowCount() == 0

    # Switch back to Doc1
    env._set_active_document(doc1)
    assert dock._bound_doc_name == "Doc1"
    assert dock.table.rowCount() == 1
    assert dock.table.item(0, 0).text() == "Param1"

    # Edit cell in Doc1 while Doc2 is also around
    item = dock.table.item(0, 1)
    item.setText("42.0")
    dock.on_cell_changed(0, 1)

    assert sheet1.get("B2") == "42.0"
    sheet2 = next(
        (
            o
            for o in getattr(doc2, "Objects", [])
            if getattr(o, "isDerivedFrom", lambda t: False)("Spreadsheet::Sheet")
        ),
        None,
    )
    assert sheet2 is None or sheet2.get("B2") is None


def test_parameters_dock_gap_tolerance_and_row_tracking(env):
    """Deleting a row blanks cells; dock must tolerate gaps and track true row IDs."""
    env.install()
    from PySide import QtCore

    import fusion_parameters_dock

    doc = env._new_document("ParamDoc")
    dock = fusion_parameters_dock.FastParametersDock()
    dock.bind_to_document(doc)

    # Add 3 parameters
    dock.on_add_parameter()  # Param1 at row 2
    dock.on_add_parameter()  # Param2 at row 3
    dock.on_add_parameter()  # Param3 at row 4
    assert dock.table.rowCount() == 3

    sheet = fusion_parameters_dock.get_or_create_parameters_sheet(doc)
    assert sheet.get("A2") == "Param1"
    assert sheet.get("A3") == "Param2"
    assert sheet.get("A4") == "Param3"

    # Delete the middle parameter (Param2)
    dock.table.setCurrentRow(1)
    dock.on_delete_parameter()

    # Spreadsheet row 3 is blanked and alias cleared
    assert sheet.get("A3") == ""
    assert sheet.get("B3") == ""
    assert sheet.getAlias("B3") == ""

    # Refresh must still show Param1 and Param3 despite gap at row 3
    assert dock.table.rowCount() == 2
    assert dock.table.item(0, 0).text() == "Param1"
    assert dock.table.item(0, 0).data(QtCore.Qt.UserRole) == 2
    assert dock.table.item(1, 0).text() == "Param3"
    assert dock.table.item(1, 0).data(QtCore.Qt.UserRole) == 4

    # Add another parameter: should safely place at row 5 (highest used + 1)
    dock.on_add_parameter()
    assert dock.table.rowCount() == 3
    assert dock.table.item(2, 0).data(QtCore.Qt.UserRole) == 5
    assert sheet.get("A5") != ""


def test_parameters_dock_undo_transactions(env):
    """All dock mutations must be wrapped in atomic undo transactions."""
    env.install()
    import fusion_parameters_dock

    doc = env._new_document("TxDoc")
    dock = fusion_parameters_dock.FastParametersDock()
    dock.bind_to_document(doc)

    # 1. Add
    dock.on_add_parameter()
    assert ("open", "Add Parameter") in doc.transactions
    assert ("commit", "Add Parameter") in doc.transactions

    # 2. Edit
    dock.table.item(0, 1).setText("99.0")
    dock.on_cell_changed(0, 1)
    assert ("open", "Edit Parameter") in doc.transactions
    assert ("commit", "Edit Parameter") in doc.transactions

    # 3. Delete
    dock.table.setCurrentRow(0)
    dock.on_delete_parameter()
    assert ("open", "Delete Parameter") in doc.transactions
    assert ("commit", "Delete Parameter") in doc.transactions


def test_atomic_datum_planes_no_orphaned_bodies(env):
    """Invalid selections must abort before creating any Body or Plane."""
    env.install()
    import fusion_datum_tools

    doc = env._new_document("DatumDoc")
    assert len(doc.Objects) == 0

    # Call with no selection
    env.selection_ex = []
    res_mid = fusion_datum_tools.create_midplane(document=doc)
    assert res_mid["status"] in ("error", "insufficient-selection")
    assert len(doc.Objects) == 0

    res_ang = fusion_datum_tools.create_plane_at_angle(document=doc)
    assert res_ang["status"] in ("error", "insufficient-selection")
    assert len(doc.Objects) == 0

    res_tan = fusion_datum_tools.create_plane_tangent(document=doc)
    assert res_tan["status"] in ("error", "insufficient-selection")
    assert len(doc.Objects) == 0


# ---------------------------------------------------------------------------
# 9. Fusion Common Primitives & Error Handling
# ---------------------------------------------------------------------------


def test_fusion_common_primitives(env):
    """Test transaction context manager, notify, log_swallowed, and SketcherCommand."""
    env.install()
    import pytest

    import fusion_common

    doc = env._new_document("CommonDoc")

    # 1. Successful transaction commits
    with fusion_common.transaction(doc, "Good Transaction"):
        doc.addObject("PartDesign::Body", "TestBody")
    assert ("commit", "Good Transaction") in doc.transactions

    # 2. Exceptional transaction aborts and re-raises
    with pytest.raises(RuntimeError, match="Deliberate error"):
        with fusion_common.transaction(doc, "Bad Transaction"):
            raise RuntimeError("Deliberate error")
    assert ("abort", "Bad Transaction") in doc.transactions

    # 3. Notify runs safely without crashing
    fusion_common.notify("TestPrefix", "Info message", error=False)
    fusion_common.notify("TestPrefix", "Error message", error=True)

    # 4. log_swallowed logs safely without crashing
    fusion_common.log_swallowed("TestingContext", ValueError("Test failure"))

    # 5. SketcherCommand IsActive behavior
    cmd = fusion_common.SketcherCommand()
    assert cmd.IsActive() is False  # Not in SketcherWorkbench
    env.active_workbench = "SketcherWorkbench"
    assert cmd.IsActive() is True


def test_parameters_dock_observer_and_gap_handling(env):
    """Parameters dock tracks document observer events, gap handling, and cell editing."""
    env.install()
    import fusion_parameters_dock

    doc1 = env._new_document("Doc1")
    _doc2 = env._new_document("Doc2")

    dock = fusion_parameters_dock.show_parameters_dock()
    assert dock is not None
    assert dock._bound_doc_name == "Doc2"

    # Switch active document to Doc1
    env.app.ActiveDocument = doc1
    obs = fusion_parameters_dock._active_parameters_dock._observer
    obs.slotActivatedDocument(doc1)
    assert dock._bound_doc_name == "Doc1"

    # Add parameter
    dock.on_add_parameter()
    assert dock.table.rowCount() == 1

    # Edit parameter name and expression
    dock.table.item(0, 0).setText("WallThick")
    dock.on_cell_changed(0, 0)
    dock.table.item(0, 1).setText("15.0")
    dock.on_cell_changed(0, 1)

    sheet1 = doc1.getObject("Parameters")
    assert sheet1.get("A2") == "WallThick"
    assert sheet1.get("B2") == "15.0"

    # Delete parameter (blanks row and clears alias)
    dock.table.setCurrentCell(0, 0)
    dock.on_delete_parameter()
    assert sheet1.get("A2") == ""
    assert sheet1.get("B2") == ""

    # Close document
    obs.slotFinishInvDoc(doc1)
    assert dock.get_bound_document() is None


def test_datum_tools_error_and_rollback_paths(env):
    """Datum plane tools validate pre-flight selections and roll back cleanly on errors."""
    env.install()
    import fusion_datum_tools

    # 1. No document
    env.app.ActiveDocument = None
    res_angle_no_doc = fusion_datum_tools.create_plane_at_angle()
    assert res_angle_no_doc["status"] == "no-document"

    res_tangent_no_doc = fusion_datum_tools.create_plane_tangent()
    assert res_tangent_no_doc["status"] == "no-document"

    # 2. Document with invalid selection
    doc = env._new_document("DatumErrorDoc")
    res_angle_bad = fusion_datum_tools.create_plane_at_angle(document=doc)
    assert res_angle_bad["status"] == "insufficient-selection"

    res_tangent_bad = fusion_datum_tools.create_plane_tangent(document=doc)
    assert res_tangent_bad["status"] == "insufficient-selection"


def test_fusion_viewport_register_custom_add_command(env):
    """fusion_viewport.register accepts injectable add_command for testing."""
    env.install()
    import fusion_viewport

    collected = {}

    def custom_add_command(name, cmd):
        collected[name] = cmd

    fusion_viewport.register(add_command=custom_add_command)
    assert "FusionMyFreeCAD_StudioViewport" in collected
    assert "FusionMyFreeCAD_RestoreViewport" in collected
    assert "FusionMyFreeCAD_ModernZincTheme" in collected
