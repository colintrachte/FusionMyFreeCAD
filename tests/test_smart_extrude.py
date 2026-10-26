"""Unit tests for Smart Extrude (fmf_extrude.py)."""

from __future__ import annotations

import types

import pytest

import fmf_extrude


class MockVec:
    """Mock vector supporting math operators for geometric testing."""

    def __init__(self, x: float = 0.0, y: float = 0.0, z: float = 1.0, rev: bool = False):
        self.x = x
        self.y = y
        self.z = z
        self._rev = rev

    def __neg__(self) -> MockVec:
        return MockVec(-self.x, -self.y, -self.z, rev=True)

    def __mul__(self, other: float) -> MockVec:
        return MockVec(
            self.x * other,
            self.y * other,
            self.z * other,
            rev=self._rev or (other < 0),
        )


@pytest.fixture
def extrude_env(env):
    """Provide a document with Body and Sketch ready for extrusion tests."""
    doc = env.app.ActiveDocument or env._new_document()
    body = doc.addObject("PartDesign::Body", "Body")
    sketch = doc.addObject("Sketcher::SketchObject", "Sketch")
    body.addObject(sketch)
    return types.SimpleNamespace(env=env, doc=doc, body=body, sketch=sketch)


def test_command_resources_and_activation(extrude_env):
    cmd = fmf_extrude.SmartExtrudeCommand()
    res = cmd.GetResources()
    assert res["Pixmap"] == "PartDesign_Pad"
    assert "Smart Extrude" in res["MenuText"]
    assert cmd.IsActive() is True

    # When no doc exists
    extrude_env.env.app.ActiveDocument = None
    assert cmd.IsActive() is False


def test_resolve_profile_sketch_and_subelements(extrude_env):
    sketch = extrude_env.sketch

    # 1. Whole sketch selection
    sel = [types.SimpleNamespace(Object=sketch, SubElementNames=[])]
    obj, subs = fmf_extrude.resolve_profile(sel)
    assert obj == sketch
    assert subs == [""]

    # 2. Sub-element InternalFace1
    sel = [types.SimpleNamespace(Object=sketch, SubElementNames=["InternalFace1"])]
    obj, subs = fmf_extrude.resolve_profile(sel)
    assert obj == sketch
    assert subs == ["InternalFace1"]

    # 3. Sketch with external geometry (multiple wires, 0 shape faces, InternalShape has faces)
    sketch.Shape = types.SimpleNamespace(Wires=[object(), object()], Faces=[])
    sketch.InternalShape = types.SimpleNamespace(Faces=[object()])
    sel = [types.SimpleNamespace(Object=sketch, SubElementNames=[])]
    obj, subs = fmf_extrude.resolve_profile(sel)
    assert obj == sketch
    assert subs == ["InternalFace1"]

    # 4. Sketch with 1 unclosed external wire and 1 closed InternalShape face
    open_wire = types.SimpleNamespace(isClosed=lambda: False)
    sketch.Shape = types.SimpleNamespace(Wires=[open_wire], Faces=[])
    sketch.InternalShape = types.SimpleNamespace(Faces=[object()])
    obj, subs = fmf_extrude.resolve_profile(sel)
    assert obj == sketch
    assert subs == ["InternalFace1"]


def test_active_body_prefers_owning_body_in_multibody_document(extrude_env):
    """When a document has multiple bodies, _active_body selects the body owning the profile."""
    doc = extrude_env.doc
    body1 = extrude_env.body
    sketch_in_b1 = extrude_env.sketch
    body1.Group.remove(sketch_in_b1)

    body2 = doc.addObject("PartDesign::Body", "Body001")
    body2.addObject(sketch_in_b1)

    resolved = fmf_extrude._active_body(doc, profile_obj=sketch_in_b1)
    assert resolved == body2


def test_smart_extrude_negative_length_and_pocket_normal_inversion(extrude_env):
    """Negative length flips direction, and auto-cut accounts for Pocket normal inversion."""
    doc = extrude_env.doc
    body = extrude_env.body
    sketch = extrude_env.sketch

    body_shape = types.SimpleNamespace(
        isNull=lambda: False,
        Solids=[object()],
        Volume=1000.0,
    )
    body_shape.common = lambda prism: types.SimpleNamespace(
        isNull=lambda: False,
        Volume=200.0 if getattr(prism, "_is_neg", False) else 0.0,
    )
    body_shape.distToShape = lambda prism: (0.0,)
    body.Shape = body_shape

    def mock_extrude(vec):
        return types.SimpleNamespace(
            isNull=lambda: False,
            Volume=250.0,
            _is_neg=(vec.z < 0),
        )

    mock_face = types.SimpleNamespace(
        extrude=mock_extrude,
        normalAt=lambda u, v: MockVec(0, 0, 1),
    )
    sketch.Shape = types.SimpleNamespace(Faces=[mock_face], Wires=[])
    sketch.InternalShape = None

    # Extruding -10.0 along -Z penetrates body -> auto-classified as Cut (PartDesign::Pocket)
    # Since Pocket extrudes along -normal when Reversed=False, Reversed should be False.
    res = fmf_extrude.smart_extrude(
        operation="auto",
        length=-10.0,
        reversed_dir=False,
        profile=(sketch, []),
        document=doc,
    )
    assert res["status"] == "ok"
    assert res["operation"] == "cut"
    assert res["feature"].TypeId == "PartDesign::Pocket"
    assert res["feature"].Length == 10.0
    assert res["feature"].Reversed is False


def test_classify_operation_no_body():
    """Without an active body or existing solid, extrude defaults to New Body."""
    sketch = types.SimpleNamespace(Shape=None, InternalShape=None)
    result = fmf_extrude.classify_operation(profile_obj=sketch, target_body=None)
    assert result["operation"] == "new_body"
    assert result["auto_reverse"] is False


def test_classify_operation_cut_penetration():
    """When the candidate prism penetrates body solid, auto-classify as cut."""
    body_shape = types.SimpleNamespace(
        isNull=lambda: False,
        Solids=[object()],
        Volume=1000.0,
    )
    # Common shape has non-trivial volume
    body_shape.common = lambda prism: types.SimpleNamespace(isNull=lambda: False, Volume=200.0)
    body_shape.distToShape = lambda prism: (0.0,)

    body = types.SimpleNamespace(Shape=body_shape)

    mock_prism = types.SimpleNamespace(isNull=lambda: False, Volume=250.0)
    mock_face = types.SimpleNamespace(
        extrude=lambda vec: mock_prism,
        normalAt=lambda u, v: MockVec(0, 0, 1),
        Placement=types.SimpleNamespace(multiply=lambda p: p),
    )
    sketch = types.SimpleNamespace(
        Shape=types.SimpleNamespace(Faces=[mock_face]),
        InternalShape=None,
        Placement=None,
    )

    result = fmf_extrude.classify_operation(
        profile_obj=sketch,
        target_body=body,
        length=10.0,
    )
    assert result["operation"] == "cut"
    assert result["auto_reverse"] is False


def test_classify_operation_join_abutment():
    """When the candidate prism abuts the body and fuses to 1 solid, classify as join."""
    body_shape = types.SimpleNamespace(
        isNull=lambda: False,
        Solids=[object()],
        Volume=1000.0,
    )
    # Zero common volume (outward)
    body_shape.common = lambda prism: types.SimpleNamespace(isNull=lambda: False, Volume=0.0)
    body_shape.distToShape = lambda prism: (0.0,)
    # Fuse yields 1 contiguous solid
    body_shape.fuse = lambda prism: types.SimpleNamespace(Solids=[object()])

    body = types.SimpleNamespace(Shape=body_shape)

    mock_prism = types.SimpleNamespace(isNull=lambda: False, Volume=250.0)
    mock_face = types.SimpleNamespace(
        extrude=lambda vec: mock_prism,
        normalAt=lambda u, v: MockVec(0, 0, 1),
        Placement=types.SimpleNamespace(multiply=lambda p: p),
    )
    sketch = types.SimpleNamespace(
        Shape=types.SimpleNamespace(Faces=[mock_face]),
        InternalShape=None,
        Placement=None,
    )

    result = fmf_extrude.classify_operation(
        profile_obj=sketch,
        target_body=body,
        length=10.0,
    )
    assert result["operation"] == "join"
    assert result["auto_reverse"] is False


def test_classify_operation_auto_reverse_recovery():
    """When current direction yields disconnected solids but reverse direction fuses cleanly."""
    body_shape = types.SimpleNamespace(
        isNull=lambda: False,
        Solids=[object()],
        Volume=1000.0,
    )
    body_shape.common = lambda prism: types.SimpleNamespace(isNull=lambda: False, Volume=0.0)

    # Current direction produces 2 solids (disconnected), reversed direction produces 1 solid
    def mock_fuse(prism):
        if getattr(prism, "_is_rev", False):
            return types.SimpleNamespace(Solids=[object()])
        return types.SimpleNamespace(Solids=[object(), object()])

    body_shape.fuse = mock_fuse
    body_shape.distToShape = lambda prism: (0.0,)

    body = types.SimpleNamespace(Shape=body_shape)

    fwd_prism = types.SimpleNamespace(isNull=lambda: False, Volume=250.0, _is_rev=False)
    rev_prism = types.SimpleNamespace(isNull=lambda: False, Volume=250.0, _is_rev=True)

    def mock_extrude(vec):
        return rev_prism if getattr(vec, "_rev", False) else fwd_prism

    mock_face = types.SimpleNamespace(
        extrude=mock_extrude,
        normalAt=lambda u, v: MockVec(0, 0, 1),
        Placement=types.SimpleNamespace(multiply=lambda p: p),
    )
    sketch = types.SimpleNamespace(
        Shape=types.SimpleNamespace(Faces=[mock_face]),
        InternalShape=None,
        Placement=None,
    )

    result = fmf_extrude.classify_operation(
        profile_obj=sketch,
        target_body=body,
        length=10.0,
    )
    assert result["operation"] == "join"
    assert result["auto_reverse"] is True


def test_smart_extrude_join_creates_native_pad(extrude_env):
    doc = extrude_env.doc
    sketch = extrude_env.sketch

    res = fmf_extrude.smart_extrude(
        operation="join",
        length=15.0,
        reversed_dir=False,
        profile=(sketch, ["InternalFace1"]),
        document=doc,
    )

    assert res["status"] == "ok"
    assert res["operation"] == "join"
    pad = res["feature"]
    assert pad.TypeId == "PartDesign::Pad"
    assert pad.Length == 15.0
    assert pad.Profile == (sketch, ["InternalFace1"])
    assert pad.Reversed is False


def test_smart_extrude_cut_creates_native_pocket(extrude_env):
    doc = extrude_env.doc
    sketch = extrude_env.sketch

    res = fmf_extrude.smart_extrude(
        operation="cut",
        length=8.0,
        reversed_dir=True,
        profile=(sketch, [""]),
        document=doc,
    )

    assert res["status"] == "ok"
    assert res["operation"] == "cut"
    pocket = res["feature"]
    assert pocket.TypeId == "PartDesign::Pocket"
    assert pocket.Length == 8.0
    assert pocket.Profile == (sketch, [""])
    assert pocket.Reversed is True


def test_smart_extrude_new_body_creates_body_and_pad(extrude_env):
    doc = extrude_env.doc
    sketch = extrude_env.sketch

    res = fmf_extrude.smart_extrude(
        operation="new_body",
        length=20.0,
        profile=(sketch, [""]),
        document=doc,
    )

    assert res["status"] == "ok"
    assert res["operation"] == "new_body"
    body = res["body"]
    assert body.TypeId == "PartDesign::Body"
    pad = res["feature"]
    assert pad.TypeId == "PartDesign::Pad"
    assert pad.Length == 20.0


def test_enhance_active_extrude_signed_drag():
    class MockSignal:
        def __init__(self):
            self.callbacks = []

        def connect(self, cb):
            self.callbacks.append(cb)

        def emit(self, val):
            for cb in self.callbacks:
                cb(val)

    class MockSpinBox:
        def __init__(self):
            self._min = 0.0
            self.value = 10.0
            self.valueChanged = MockSignal()

        def minimum(self):
            return self._min

        def setMinimum(self, val):
            self._min = val

        def setValue(self, val):
            self.value = val

    class MockCheckBox:
        def __init__(self):
            self._checked = False

        def isChecked(self):
            return self._checked

        def setChecked(self, checked):
            self._checked = checked

    sb = MockSpinBox()
    cb = MockCheckBox()

    info = {
        "spinbox": sb,
        "checkbox_reversed": cb,
    }

    ok = fmf_extrude.enhance_active_extrude(info)
    assert ok is True
    assert sb.minimum() < 0.0

    # User drags backward past zero into negative distance
    assert cb.isChecked() is False
    sb.valueChanged.emit(-12.5)

    # Signal hook toggles reversed direction and normalizes distance to positive
    assert cb.isChecked() is True
    assert sb.value == 12.5

    # Second enhance call returns False (already hooked)
    assert fmf_extrude.enhance_active_extrude(info) is False


def test_smart_extrude_hud_signed_distance_and_operation_controls(env):
    """Cursor HUD synchronizes signed distances (+/-), operations, and Enter/Esc keys."""

    class MockSpin:
        def __init__(self, val=10.0):
            self._val = val

        def value(self):
            return self._val

        def setValue(self, val):
            self._val = float(val)

    class MockCheck:
        def __init__(self, checked=False):
            self._checked = checked

        def isChecked(self):
            return self._checked

        def setChecked(self, val):
            self._checked = bool(val)

    sb = MockSpin(15.0)
    cb = MockCheck(False)
    hud = fmf_extrude.show_extrude_hud({"spinbox": sb, "checkbox_reversed": cb})
    assert hud is not None
    assert fmf_extrude.get_active_extrude_hud() is hud
    assert hud.is_visible() is True
    assert hud.distance() == 15.0
    assert hud.operation() == "auto"

    # Typing a negative distance in the HUD sets Reversed=True and Length=abs(val)
    hud.set_distance(-22.5)
    assert cb.isChecked() is True
    assert sb.value() == 22.5
    assert hud.distance() == -22.5

    # Typing a positive distance sets Reversed=False
    hud.set_distance(30.0)
    assert cb.isChecked() is False
    assert sb.value() == 30.0
    assert hud.distance() == 30.0

    # Operation selector supports Auto / Join / Cut / New Body
    for op in ("join", "cut", "new_body", "auto"):
        hud.set_operation(op)
        assert hud.operation() == op

    with pytest.raises(ValueError):
        hud.set_operation("invalid_op")

    # Enter accepts and closes the HUD; Esc cancels and closes the HUD
    accepted_calls = []
    rejected_calls = []
    env.gui.Control = types.SimpleNamespace(
        accept=lambda: accepted_calls.append(True),
        reject=lambda: rejected_calls.append(True),
    )
    assert hud.handle_key("Enter") is True
    assert len(accepted_calls) == 1
    assert fmf_extrude.get_active_extrude_hud() is None

    hud2 = fmf_extrude.show_extrude_hud({"spinbox": sb, "checkbox_reversed": cb})
    assert hud2 is not None
    assert hud2.handle_key("Escape") is True
    assert len(rejected_calls) == 1
    assert fmf_extrude.get_active_extrude_hud() is None


def test_open_wire_diagnostic_and_one_click_undoable_close(extrude_env, monkeypatch):
    """diagnose_open_wires and close_open_wire_gaps repair small gaps."""
    import fmf_sketch_tools

    sketch = extrude_env.sketch
    doc = extrude_env.doc

    def make_edge(p1, p2):
        return types.SimpleNamespace(
            StartPoint=types.SimpleNamespace(x=p1[0], y=p1[1]),
            EndPoint=types.SimpleNamespace(x=p2[0], y=p2[1]),
            Construction=False,
        )

    # Create a 10x10 rectangle with a 0.08 mm gap at the last corner (0.0, 0.08) -> (0.0, 0.0)
    sketch.Geometry = [
        make_edge((0.0, 0.0), (10.0, 0.0)),
        make_edge((10.0, 0.0), (10.0, 10.0)),
        make_edge((10.0, 10.0), (0.0, 10.0)),
        make_edge((0.0, 10.0), (0.0, 0.08)),
    ]
    sketch.Constraints = []
    added_lines = []

    def fake_add_line(sk, p1, p2, construction=False):
        edge = make_edge(p1, p2)
        sk.Geometry.append(edge)
        added_lines.append((p1, p2))
        return len(sk.Geometry) - 1

    monkeypatch.setattr(fmf_sketch_tools, "_add_line", fake_add_line)

    diag = fmf_sketch_tools.diagnose_open_wires(sketch, tolerance=0.5)
    assert diag["is_closed"] is False
    assert diag["open_endpoint_count"] == 2
    assert len(diag["closable_gaps"]) == 1
    assert abs(diag["closable_gaps"][0]["distance"] - 0.08) < 1e-4

    # Close the gap in a single transaction
    res = fmf_sketch_tools.close_open_wire_gaps(sketch, tolerance=0.5)
    assert res["status"] == "closed"
    assert res["closed_count"] == 1
    assert len(added_lines) == 1

    # Verify the sketch is now closed
    diag_after = fmf_sketch_tools.diagnose_open_wires(sketch, tolerance=0.5)
    assert diag_after["is_closed"] is True
    assert diag_after["open_endpoint_count"] == 0

    # Verify smart_extrude refuses a large unclosable gap (> 0.5 mm) with an actionable diagnostic
    sketch_large_gap = doc.addObject("Sketcher::SketchObject", "SketchLargeGap")
    sketch_large_gap.Geometry = [
        make_edge((0.0, 0.0), (10.0, 0.0)),
        make_edge((10.0, 0.0), (10.0, 10.0)),
        make_edge((10.0, 10.0), (0.0, 5.0)),
    ]
    sketch_large_gap.Constraints = []
    sketch_large_gap.Shape = types.SimpleNamespace(Faces=[], Wires=[])
    sketch_large_gap.InternalShape = None

    ext_res = fmf_extrude.smart_extrude(
        operation="join",
        length=10.0,
        profile=(sketch_large_gap, []),
        document=doc,
    )
    assert ext_res["status"] == "open-wire"
    assert "Wire is not closed" in ext_res["diagnosis"]["summary"]


def test_partdesign_feature_edit_and_transition_keep_fmf_workbench(
    env, bootstrap, monkeypatch
):
    """Native PartDesign/Sketcher activations map to FMF workbenches."""
    import sys

    import fmf_transitions
    import fmf_workbenches

    env.param("User parameter:BaseApp/Preferences/Mod/FMF").SetBool(
        "UseOwnedWorkbenches", True
    )
    assert (
        fmf_transitions._normalize_workbench_name("PartDesignWorkbench")
        == "FMFDesignWorkbench"
    )
    assert (
        fmf_transitions._normalize_workbench_name("SketcherWorkbench")
        == "FMFSketchWorkbench"
    )
    assert (
        fmf_transitions._normalize_workbench_name("PartWorkbench") == "FMFPartWorkbench"
    )
    assert (
        fmf_transitions._normalize_workbench_name("SurfaceWorkbench")
        == "FMFSurfaceWorkbench"
    )

    monkeypatch.setitem(sys.modules, "PartDesign", types.ModuleType("PartDesign"))
    monkeypatch.setitem(
        sys.modules, "PartDesignGui", types.ModuleType("PartDesignGui")
    )
    gear_mod = types.ModuleType("PartDesign.InvoluteGearFeature")
    gear_mod.CommandInvoluteGear = lambda: object()
    sprocket_mod = types.ModuleType("PartDesign.SprocketFeature")
    sprocket_mod.CommandSprocket = lambda: object()
    monkeypatch.setitem(sys.modules, "PartDesign.InvoluteGearFeature", gear_mod)
    monkeypatch.setitem(sys.modules, "PartDesign.SprocketFeature", sprocket_mod)

    wb = fmf_workbenches.FMFDesignWorkbench()
    wb.Initialize()
    assert "PartDesign_InvoluteGear" in env.commands
    assert "PartDesign_Sprocket" in env.commands

    bootstrap.set_owned_workbench_visibility(True)
    ordered = env.param(
        "User parameter:BaseApp/Preferences/Mod/FreeCAD-Ribbon"
    ).GetString("TabOrder", "")
    assert ordered.startswith(
        "FMFDesignWorkbench,FMFPartWorkbench,FMFSketchWorkbench,FMFSurfaceWorkbench"
    )
