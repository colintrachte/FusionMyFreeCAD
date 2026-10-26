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
