"""Finding and mending references FreeCAD lost track of.

The failure these tests describe is the one that quietly ruins a session: a
feature is edited, the faces downstream are renumbered, and a sketch attached
to one of them stops being placed. Nothing crashes, nothing is offered, and
the sketch simply is not there any more.

The rule the tests hold the module to is that it only repairs what it can
measure. A sketch's own Placement was computed from the face it was attached
to, so it still says which plane that face was on -- that is a measurement. An
edge name in a chamfer says nothing about where the edge was, so that is left
alone and reported, because a chamfer silently moved to the wrong edge is
worse than one that admits it is broken.
"""

from __future__ import annotations

import types

import pytest


@pytest.fixture
def repair(env):
    import fusion_repair_tools

    return fusion_repair_tools


class _Vector:
    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.x, self.y, self.z = float(x), float(y), float(z)

    def __iter__(self):
        return iter((self.x, self.y, self.z))


def _face(point, normal, centre=None, contains=None):
    """A planar face described the way OpenCASCADE describes one."""
    centre = centre if centre is not None else point
    face = types.SimpleNamespace(
        Surface=types.SimpleNamespace(Position=_Vector(*point), Axis=_Vector(*normal)),
        CenterOfMass=_Vector(*centre),
    )
    if contains is not None:
        face.isInside = lambda vector, _tolerance, _closed, inside=contains: inside
    return face


def _placement(base, normal=(0.0, 0.0, 1.0)):
    return types.SimpleNamespace(
        Base=_Vector(*base),
        Rotation=types.SimpleNamespace(multVec=lambda _vector, n=normal: _Vector(*n)),
    )


def _shape(faces=(), names=()):
    """An object shape that resolves only the subelement names it was given."""
    resolvable = set(names)

    def get_element(name):
        return object() if name in resolvable else None

    return types.SimpleNamespace(Faces=list(faces), getElement=get_element)


def _obj(name, **attributes):
    obj = types.SimpleNamespace(Name=name)
    for key, value in attributes.items():
        setattr(obj, key, value)
    return obj


# ---------------------------------------------------------------------------
# Reading links
# ---------------------------------------------------------------------------


def test_a_single_link_and_a_list_of_links_read_the_same(repair):
    pad = _obj("Pad")
    assert repair.link_entries((pad, ["Face9"])) == [(pad, "Face9")]
    assert repair.link_entries([(pad, ["Face9", "Face4"])]) == [(pad, "Face9"), (pad, "Face4")]


def test_a_link_to_a_whole_object_is_still_a_link(repair):
    """A dangling whole-object link is as broken as a dangling face."""
    pad = _obj("Pad")
    assert repair.link_entries((pad, [])) == [(pad, "")]


def test_nothing_and_nonsense_read_as_no_links(repair):
    assert repair.link_entries(None) == []
    assert repair.link_entries("Face1") == []
    assert repair.link_entries([("only-one-part",)]) == []


# ---------------------------------------------------------------------------
# Deciding what is broken
# ---------------------------------------------------------------------------


def test_a_face_that_still_exists_is_not_reported(repair):
    pad = _obj("Pad", Shape=_shape(names=["Face9"]))
    assert repair.subelement_resolves(pad, "Face9") is True


def test_a_face_that_has_been_renumbered_away_is_reported(repair):
    pad = _obj("Pad", Shape=_shape(names=["Face1", "Face2"]))
    assert repair.subelement_resolves(pad, "Face9") is False


def test_an_internal_face_is_looked_for_on_the_object_not_only_the_shape(repair):
    """A sketch's InternalFaces live on InternalShape; only the object knows."""
    sketch = _obj(
        "Sketch",
        Shape=_shape(names=["Face1"]),
        getSubObject=lambda name: object() if name == "InternalFace1" else None,
    )
    assert repair.subelement_resolves(sketch, "InternalFace1") is True
    assert repair.subelement_resolves(sketch, "InternalFace7") is False


def test_a_document_reports_every_dangling_reference(repair):
    pad = _obj("Pad", Shape=_shape(names=["Face1"]))
    pocket = _obj("Pocket", Shape=_shape(names=["Edge1"]))
    sketch = _obj(
        "Sketch001", AttachmentSupport=[(pad, ["Face9"])], Placement=_placement((0, 0, 6))
    )
    chamfer = _obj("Chamfer", Base=(pocket, ["Edge28"]))
    document = types.SimpleNamespace(Objects=[pad, pocket, sketch, chamfer])

    found = repair.broken_references(document)
    assert [(f["object"].Name, f["property"], f["sub"]) for f in found] == [
        ("Sketch001", "AttachmentSupport", "Face9"),
        ("Chamfer", "Base", "Edge28"),
    ]


# ---------------------------------------------------------------------------
# Finding the face an attachment was sitting on
# ---------------------------------------------------------------------------


def test_the_face_on_the_plane_the_sketch_sits_on_is_the_match(repair):
    pad = _obj(
        "Pad",
        Shape=_shape(
            faces=[
                _face((0, 0, 0), (0, 0, 1)),  # the bottom
                _face((0, 0, 6), (0, 0, 1)),  # the top: where the sketch is
                _face((10, 0, 3), (1, 0, 0)),  # a side
            ]
        ),
    )
    sketch = _obj("Sketch001", Placement=_placement((0, 0, 6)))
    assert repair.suggest_attachment_face(sketch, pad) == "Face2"


def test_the_face_the_sketch_actually_covers_beats_one_merely_on_its_plane(repair):
    """Two bosses of the same height share a plane; only one holds the sketch."""
    pad = _obj(
        "Pad",
        Shape=_shape(
            faces=[
                _face((0, 0, 6), (0, 0, 1), centre=(0, 0, 6), contains=False),
                _face((40, 0, 6), (0, 0, 1), centre=(40, 0, 6), contains=True),
            ]
        ),
    )
    sketch = _obj("Sketch001", Placement=_placement((40, 0, 6)))
    assert repair.suggest_attachment_face(sketch, pad) == "Face2"


def test_a_face_pointing_the_other_way_is_still_the_same_plane(repair):
    """Attachment cares which plane, not which side of it the normal faces."""
    pad = _obj("Pad", Shape=_shape(faces=[_face((0, 0, 6), (0, 0, -1))]))
    sketch = _obj("Sketch001", Placement=_placement((0, 0, 6)))
    assert repair.suggest_attachment_face(sketch, pad) == "Face1"


def test_a_parallel_face_at_a_different_height_is_not_the_match(repair):
    pad = _obj("Pad", Shape=_shape(faces=[_face((0, 0, 8), (0, 0, 1))]))
    sketch = _obj("Sketch001", Placement=_placement((0, 0, 6)))
    assert repair.suggest_attachment_face(sketch, pad) is None


def test_no_matching_plane_means_no_suggestion_rather_than_the_nearest_face(repair):
    """Guessing here would move a sketch somewhere the user never put it."""
    pad = _obj("Pad", Shape=_shape(faces=[_face((10, 0, 3), (1, 0, 0))]))
    sketch = _obj("Sketch001", Placement=_placement((0, 0, 6)))
    assert repair.suggest_attachment_face(sketch, pad) is None


def test_a_curved_face_is_never_offered_for_a_flat_attachment(repair):
    cylinder = types.SimpleNamespace(CenterOfMass=_Vector(0, 0, 6))
    pad = _obj("Pad", Shape=_shape(faces=[cylinder]))
    sketch = _obj("Sketch001", Placement=_placement((0, 0, 6)))
    assert repair.suggest_attachment_face(sketch, pad) is None


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------


def test_an_attachment_is_planned_and_a_dress_up_edge_is_only_named(repair):
    pad = _obj("Pad", Shape=_shape(faces=[_face((0, 0, 6), (0, 0, 1))], names=["Face1"]))
    pocket = _obj("Pocket", Shape=_shape(names=["Edge1"]))
    sketch = _obj(
        "Sketch001", AttachmentSupport=[(pad, ["Face9"])], Placement=_placement((0, 0, 6))
    )
    chamfer = _obj("Chamfer", Base=(pocket, ["Edge28"]))
    document = types.SimpleNamespace(Objects=[pad, pocket, sketch, chamfer])

    plan = repair.plan_repairs(document)
    assert [(r["object"].Name, r["replacement"]) for r in plan["repairs"]] == [
        ("Sketch001", "Face1")
    ]
    assert [(f["object"].Name, f["sub"]) for f in plan["unresolved"]] == [("Chamfer", "Edge28")]


def test_an_attachment_with_no_match_is_reported_not_repaired(repair):
    pad = _obj("Pad", Shape=_shape(faces=[_face((10, 0, 3), (1, 0, 0))]))
    sketch = _obj(
        "Sketch001", AttachmentSupport=[(pad, ["Face9"])], Placement=_placement((0, 0, 6))
    )
    document = types.SimpleNamespace(Objects=[pad, sketch])

    plan = repair.plan_repairs(document)
    assert plan["repairs"] == []
    assert len(plan["unresolved"]) == 1


# ---------------------------------------------------------------------------
# Applying
# ---------------------------------------------------------------------------


def test_only_the_broken_entry_is_rewritten(repair):
    """An attachment often names two references; the surviving one must not move."""
    pad = _obj("Pad")
    sketch = _obj("Sketch001", AttachmentSupport=[(pad, ["Face9", "Edge3"])])
    assert repair.apply_repair(
        {
            "object": sketch,
            "property": "AttachmentSupport",
            "target": pad,
            "sub": "Face9",
            "replacement": "Face2",
        }
    )
    assert sketch.AttachmentSupport == [(pad, ["Face2"]), (pad, ["Edge3"])]


def test_repairing_a_document_reattaches_and_recomputes(repair):
    pad = _obj("Pad", Shape=_shape(faces=[_face((0, 0, 6), (0, 0, 1))], names=["Face1"]))
    sketch = _obj(
        "Sketch001", AttachmentSupport=[(pad, ["Face9"])], Placement=_placement((0, 0, 6))
    )
    log = []
    document = types.SimpleNamespace(
        Objects=[pad, sketch],
        openTransaction=lambda label: log.append(("open", label)),
        commitTransaction=lambda: log.append(("commit",)),
        abortTransaction=lambda: log.append(("abort",)),
        recompute=lambda: log.append(("recompute",)),
    )

    result = repair.repair_document(document)
    assert sketch.AttachmentSupport == [(pad, ["Face1"])]
    assert len(result["repaired"]) == 1
    # One transaction, so a single Undo puts the whole repair back.
    assert [entry[0] for entry in log] == ["open", "recompute", "commit"]


def test_a_clean_document_is_left_alone(repair):
    pad = _obj("Pad", Shape=_shape(names=["Face1"]))
    sketch = _obj(
        "Sketch001", AttachmentSupport=[(pad, ["Face1"])], Placement=_placement((0, 0, 6))
    )
    log = []
    document = types.SimpleNamespace(
        Objects=[pad, sketch],
        openTransaction=lambda label: log.append("open"),
        commitTransaction=lambda: log.append("commit"),
        recompute=lambda: log.append("recompute"),
    )

    result = repair.repair_document(document)
    assert result == {"repaired": [], "unresolved": []}
    assert log == []


def test_a_document_that_only_has_unrepairable_breakage_is_not_touched(repair):
    pocket = _obj("Pocket", Shape=_shape(names=["Edge1"]))
    chamfer = _obj("Chamfer", Base=(pocket, ["Edge28"]))
    log = []
    document = types.SimpleNamespace(
        Objects=[pocket, chamfer],
        openTransaction=lambda label: log.append("open"),
        commitTransaction=lambda: log.append("commit"),
        recompute=lambda: log.append("recompute"),
    )

    result = repair.repair_document(document)
    assert result["repaired"] == []
    assert len(result["unresolved"]) == 1
    assert log == [], "nothing was mended, so nothing should be in the undo stack"
