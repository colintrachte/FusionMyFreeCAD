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
    import fmf_repair_tools

    return fmf_repair_tools


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
    assert result == {"repaired": [], "suggestions": [], "unresolved": []}
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


# ---------------------------------------------------------------------------
# What a real document taught these tests
#
# Everything below came out of running the scan against Chicken Dumper Hinge
# rather than out of imagination. Two of them are bugs the fakes never caught:
# the commonest attachment in any document read as broken, and the evidence
# the repair was built on turned out not to survive the failure it repairs.
# ---------------------------------------------------------------------------


def test_a_sketch_on_an_origin_plane_is_not_broken(repair):
    """The commonest attachment there is, and it has no shape behind it.

    A sketch on XY_Plane links to the Origin object with the plane's *name*,
    and an Origin has no Shape at all, so asking its shape for a subelement
    called every such sketch broken. On a real document that was two false
    positives out of three findings.
    """
    plane = _obj("XY_Plane")
    origin = _obj("Origin", OriginFeatures=[plane, _obj("XZ_Plane"), _obj("X_Axis")])
    assert repair.subelement_resolves(origin, "XY_Plane") is True
    assert repair.subelement_resolves(origin, "YZ_Plane") is False


def test_a_child_named_with_a_trailing_dot_still_resolves(repair):
    """FreeCAD writes object paths with a trailing separator."""
    origin = _obj("Origin", OutList=[_obj("XY_Plane")])
    assert repair.subelement_resolves(origin, "XY_Plane.") is True


def test_freecads_own_question_mark_is_taken_as_the_answer(repair):
    """FreeCAD renames a subelement it cannot resolve to "?Face9"."""
    pad = _obj("Pad", Shape=_shape(names=["?Face9", "Face9"]))
    assert repair.subelement_resolves(pad, "?Face9") is False


def test_the_marker_is_not_repeated_back_to_the_user(repair):
    pad = _obj("Pad")
    finding = {
        "object": _obj("Sketch001"),
        "property": "AttachmentSupport",
        "target": pad,
        "sub": "?Face9",
    }
    assert repair._describe(finding) == "Sketch001.AttachmentSupport -> Pad.Face9"


def test_sharing_a_plane_is_not_enough_to_be_the_face(repair):
    """The tabletop and the boss standing on it are not the same face."""
    wanted = ((5.0, 0.0, 6.0), (0.0, 0.0, 1.0))
    elsewhere = _face((0, 0, 6), (0, 0, 1), centre=(0, 0, 6), contains=False)
    assert repair.face_match_rank(wanted, elsewhere) is None


def test_a_placement_that_was_never_set_is_not_evidence(repair):
    """An attachment failure resets the placement; it does not preserve it.

    This is the correction that matters most: the repair was built on the
    belief that a broken object still carries the plane of the face it lost.
    Measured against a real document, a sketch that had been on the side of a
    pad came back sitting at the origin, unrotated, with nothing left to
    measure.
    """
    assert repair.placement_is_unset(_placement((0, 0, 0))) is True
    assert repair.placement_is_unset(_placement((0, 0, 6))) is False
    assert repair.placement_is_unset(_placement((0, 0, 0), normal=(0, -1, 0))) is False


def test_a_reset_placement_is_offered_rather_than_applied(repair):
    """Naming the likely face helps; moving the sketch there would be a guess."""
    top = _face((0, 0, 0), (0, 0, 1), centre=(0, 0, 0), contains=True)
    pad = _obj("Pad", Shape=_shape(faces=[top], names=["Face1"]))
    sketch = _obj(
        "Sketch001", AttachmentSupport=[(pad, ["?Face9"])], Placement=_placement((0, 0, 0))
    )
    document = types.SimpleNamespace(Objects=[pad, sketch])

    plan = repair.plan_repairs(document)
    assert plan["repairs"] == []
    assert [(s["object"].Name, s["replacement"]) for s in plan["suggestions"]] == [
        ("Sketch001", "Face1")
    ]


def test_a_suggestion_never_moves_anything(repair):
    top = _face((0, 0, 0), (0, 0, 1), centre=(0, 0, 0), contains=True)
    pad = _obj("Pad", Shape=_shape(faces=[top], names=["Face1"]))
    sketch = _obj(
        "Sketch001", AttachmentSupport=[(pad, ["?Face9"])], Placement=_placement((0, 0, 0))
    )
    log = []
    document = types.SimpleNamespace(
        Objects=[pad, sketch],
        openTransaction=lambda label: log.append("open"),
        commitTransaction=lambda: log.append("commit"),
        recompute=lambda: log.append("recompute"),
    )

    result = repair.repair_document(document)
    assert result["repaired"] == []
    assert len(result["suggestions"]) == 1
    assert sketch.AttachmentSupport == [(pad, ["?Face9"])]
    assert log == []


def _sketch_with(regions):
    faces = [types.SimpleNamespace() for _ in range(regions)]
    return _obj("Sketch", InternalShape=types.SimpleNamespace(Faces=faces))


def test_a_profile_invalidated_mid_trim_is_restored(repair):
    """A marker left behind after the thing it complained about came back.

    FreeCAD's "?" prefix persists -- a real document still carried `?Face9`
    in an attachment. Where the element is unambiguously available again,
    clearing the marker restores the reference without choosing anything.
    """
    sketch = _sketch_with(1)
    assert repair.restore_invalidated(sketch, "?InternalFace1") == "InternalFace1"


def test_an_ambiguous_region_is_not_restored(repair):
    """With several regions there is nothing to say which one was meant."""
    assert repair.restore_invalidated(_sketch_with(3), "?InternalFace1") is None
    assert repair.restore_invalidated(_sketch_with(0), "?InternalFace1") is None


def test_a_renumbered_solid_face_is_never_restored_by_its_old_number(repair):
    """Face9 on a rebuilt pad is a different face, not the same one returning."""
    pad = _obj("Pad", Shape=_shape(names=["Face9"]))
    assert repair.restore_invalidated(pad, "?Face9") is None


def test_a_name_with_no_marker_is_not_a_restoration(repair):
    assert repair.restore_invalidated(_sketch_with(1), "InternalFace1") is None


def test_a_restored_profile_is_applied_not_merely_offered(repair):
    sketch = _sketch_with(1)
    pad = _obj("Pad", Profile=(sketch, ["?InternalFace1"]))
    document = types.SimpleNamespace(Objects=[sketch, pad])

    plan = repair.plan_repairs(document)
    assert [(r["object"].Name, r["replacement"]) for r in plan["repairs"]] == [
        ("Pad", "InternalFace1")
    ]
    assert plan["suggestions"] == [] and plan["unresolved"] == []


# ---------------------------------------------------------------------------
# Update Model
#
# FreeCAD's Refresh rebuilds only what is marked as needing it, and PartDesign
# clears that mark across the whole document when a feature dialog is
# accepted: the console shows App.getDocument(...).purgeTouched() immediately
# before its recompute. So a pad can change while the pocket cut out of it is
# told it is already current.
# ---------------------------------------------------------------------------


def _document(objects=(), recomputed=3):
    calls = []

    def recompute(objs=None, force=False, check_cycle=False):
        calls.append((objs, force, check_cycle))
        return recomputed

    return types.SimpleNamespace(Objects=list(objects), recompute=recompute, calls=calls)


def test_every_feature_is_marked_before_the_rebuild(repair):
    """`recompute(force=True)` does not force anything on its own.

    The source settles it: the flag only bypasses the document's
    SkipRecompute, and each object is then still asked `mustRecompute()` and
    skipped if it says no. Run against a real document it rebuilt nothing at
    all -- zero features -- until every object was marked first.
    """
    marks = []
    objects = [
        _obj("Pad", enforceRecompute=lambda: marks.append("Pad")),
        _obj("Pocket", enforceRecompute=lambda: marks.append("Pocket")),
    ]
    document = _document(objects)
    result = repair.update_model(document)
    assert marks == ["Pad", "Pocket"]
    assert document.calls == [(None, True, False)]
    assert result["recomputed"] == 3


def test_an_object_that_cannot_be_enforced_is_touched_instead(repair):
    marks = []
    obj = _obj("Old", touch=lambda: marks.append("Old"))
    repair.update_model(_document([obj]))
    assert marks == ["Old"]


def test_the_feature_that_failed_is_told_apart_from_the_ones_below_it(repair):
    """A failed recompute takes its whole downstream out of the queue.

    Reporting seven broken features hides that six of them are the
    consequence of the first. Naming the one that actually failed is the
    difference between a wall of red and one thing to go and fix.
    """
    culprit = _obj(
        "Sketch002",
        State=["Touched", "Invalid"],
        getStatusString=lambda: "Wire is not closed",
    )
    downstream = _obj("Pocket001", State=["Touched"])
    result = repair.update_model(_document([culprit, downstream]))
    assert [name for name, _status, _kind in result["failed"]] == ["Sketch002"]
    assert [name for name, _status, _kind in result["blocked"]] == ["Pocket001"]
    assert result["failed"][0][1] == "Wire is not closed"


def test_a_clean_document_reports_nothing_wrong(repair):
    fine = _obj("Pad", State=["Up-to-date"])
    assert repair.features_in_error(_document([fine])) == []


def test_a_rebuild_that_throws_does_not_take_the_command_with_it(repair):
    def explode(*_args):
        raise RuntimeError("OCC said no")

    document = types.SimpleNamespace(Objects=[], recompute=explode)
    assert repair.update_model(document)["recomputed"] == 0
