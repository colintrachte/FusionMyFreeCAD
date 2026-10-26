"""Tests for multi-region Pad selection and empty-shape recovery."""

from __future__ import annotations

import types

import pytest


@pytest.fixture
def sketch_env(env):
    """Provide a document with an active sketch and pad setup."""
    doc = env.app.ActiveDocument or env._new_document()
    body = doc.addObject("PartDesign::Body", "Body")
    sketch = doc.addObject("Sketcher::SketchObject", "Sketch")
    body.addObject(sketch)

    pad = doc.addObject("PartDesign::Pad", "Pad")
    pad.Profile = (sketch, [""])
    pad.Shape = types.SimpleNamespace(isNull=lambda: False, Solids=[object()])
    body.addObject(pad)
    return types.SimpleNamespace(env=env, doc=doc, body=body, sketch=sketch, pad=pad)


def test_pad_region_accumulation_and_toggle(sketch_env):
    import fmf_bootstrap

    obs = fmf_bootstrap._PadSelectionObserver()
    doc = sketch_env.doc
    sketch = sketch_env.sketch
    pad = sketch_env.pad

    # 1. Click region 1 -> accumulates
    obs.addSelection(doc.Name, sketch.Name, "Sketch.InternalFace1")
    assert pad.Profile == (sketch, ["InternalFace1"])

    # 2. Click region 2 -> accumulates alongside region 1
    obs.addSelection(doc.Name, sketch.Name, "Sketch.InternalFace2")
    assert pad.Profile == (sketch, ["InternalFace1", "InternalFace2"])

    # 3. Click region 1 again -> toggles off, leaves region 2
    obs.addSelection(doc.Name, sketch.Name, "Sketch.InternalFace1")
    assert pad.Profile == (sketch, ["InternalFace2"])

    # 4. Click region 2 again -> toggles off, reverts to whole sketch [""]
    obs.addSelection(doc.Name, sketch.Name, "Sketch.InternalFace2")
    assert pad.Profile == (sketch, [""])


def test_pad_auto_reversal_recovery_on_empty_shape(sketch_env):
    """When a Pad direction yields an empty solid, auto-flip to valid direction."""
    import fmf_bootstrap

    obs = fmf_bootstrap._PadSelectionObserver()
    doc = sketch_env.doc
    sketch = sketch_env.sketch
    pad = sketch_env.pad

    # Simulate: Reversed=True produces empty solid (isNull or Solids=[]),
    # but Reversed=False produces a valid solid.
    pad.Reversed = True

    def mock_recompute():
        if pad.Reversed:
            pad.Shape = types.SimpleNamespace(isNull=lambda: False, Solids=[])
        else:
            pad.Shape = types.SimpleNamespace(isNull=lambda: False, Solids=[object()])

    pad.recompute = mock_recompute

    obs.addSelection(doc.Name, sketch.Name, "Sketch.InternalFace1")

    # Observer should have auto-flipped Reversed from True to False and kept the profile!
    assert pad.Reversed is False
    assert pad.Profile == (sketch, ["InternalFace1"])
    assert len(pad.Shape.Solids) == 1


def test_pad_reverts_if_neither_direction_is_valid(sketch_env):
    """When neither direction produces a solid, revert to previous state."""
    import fmf_bootstrap

    obs = fmf_bootstrap._PadSelectionObserver()
    doc = sketch_env.doc
    sketch = sketch_env.sketch
    pad = sketch_env.pad

    pad.Profile = (sketch, [""])
    pad.Reversed = False
    pad.Shape = types.SimpleNamespace(isNull=lambda: False, Solids=[object()])

    # Simulate: both directions fail to produce a solid
    def fail_recompute():
        pad.Shape = types.SimpleNamespace(isNull=lambda: True, Solids=[])

    pad.recompute = fail_recompute

    obs.addSelection(doc.Name, sketch.Name, "Sketch.InternalFace1")

    # Should have reverted to the previous valid profile
    assert pad.Profile == (sketch, [""])
    assert pad.Reversed is False


def test_sketch_repair_observer_auto_upgrades_single_region_with_open_wires(sketch_env):
    """When native Pad is created on a 1-region sketch with open external-geometry wires,
    _SketchRepairObserver upgrades Profile to ['InternalFace1'] and recovers 1-solid direction.
    """
    import fmf_bootstrap

    obs = fmf_bootstrap._SketchRepairObserver()
    sketch = sketch_env.sketch
    pad = sketch_env.pad

    open_wire = types.SimpleNamespace(isClosed=lambda: False)
    closed_wire = types.SimpleNamespace(isClosed=lambda: True)
    sketch.Shape = types.SimpleNamespace(Wires=[closed_wire, open_wire], Faces=[])
    sketch.InternalShape = types.SimpleNamespace(Faces=[object()])

    pad.Profile = (sketch, [])
    pad.Reversed = False

    # Simulate Spool Holder.FCStd: Reversed=False produces 2 disconnected solids,
    # Reversed=True fuses cleanly into 1 solid.
    def mock_recompute():
        if pad.Reversed:
            pad.Shape = types.SimpleNamespace(isNull=lambda: False, Solids=[object()])
        else:
            pad.Shape = types.SimpleNamespace(isNull=lambda: False, Solids=[object(), object()])

    pad.recompute = mock_recompute

    obs.slotChangedObject(pad, "Profile")

    assert pad.Profile == (sketch, ["InternalFace1"])
    assert pad.Reversed is True
    assert len(pad.Shape.Solids) == 1
