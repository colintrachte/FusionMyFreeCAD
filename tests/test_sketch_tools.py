"""Constraint-aware sketch mirroring: geometry mapping, policy, and the command.

These exercise the offline logic of ``fusion_sketch_tools``.  The fake implements
the synchronous ``SketchObject.addSymmetric`` API, so what is checked here is
the source-to-mirror mapping, the compatibility policy, redundant-copy cleanup,
explicit-axis validation, and single-transaction wrapping.
"""

from __future__ import annotations

import types

import pytest
from fake_freecad import FakeConstraint, FakeLineSegment, FakeSketch

V_AXIS = ((0.0, 0.0), (0.0, 1.0))
POS_START = 1
POS_END = 2


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tools(sketch_tools):
    return sketch_tools


def _card_box(divider_x_values):
    """A profile: a bottom border, a top border, then vertical dividers.

    Each divider's endpoints are pinned to the borders with Point-on-Object, the
    exact constraints native Symmetry drops because the borders are outside the
    mirrored selection.
    """
    sketch = FakeSketch("Sketch")
    sketch.addGeometry(FakeLineSegment((-50.0, 0.0), (50.0, 0.0)))  # geo 0: bottom
    sketch.addGeometry(FakeLineSegment((-50.0, 30.0), (50.0, 30.0)))  # geo 1: top
    divider_ids = []
    for x in divider_x_values:
        geoid = sketch.addGeometry(FakeLineSegment((x, 0.0), (x, 30.0)))
        divider_ids.append(geoid)
        sketch.addConstraint(FakeConstraint("PointOnObject", geoid, POS_START, 0))
        sketch.addConstraint(FakeConstraint("PointOnObject", geoid, POS_END, 1))
    return sketch, divider_ids


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_reflect_point_across_vertical_axis(tools):
    assert tools.reflect_point((20.0, 5.0), *V_AXIS) == pytest.approx((-20.0, 5.0))


def test_axis_orthogonality(tools):
    assert tools.axis_is_orthogonal((0.0, 0.0), (0.0, 10.0))
    assert tools.axis_is_orthogonal((0.0, 0.0), (10.0, 0.0))
    assert not tools.axis_is_orthogonal((0.0, 0.0), (10.0, 10.0))


# ---------------------------------------------------------------------------
# Source-to-mirror geometry mapping
# ---------------------------------------------------------------------------


def test_geometry_mapping_pairs_each_source_with_its_reflection(tools):
    sketch, dividers = _card_box([10.0, 20.0, 30.0])
    before = list(sketch.Geometry)
    sketch.mirror_selected(dividers, *V_AXIS)
    after = list(sketch.Geometry)

    mapping, unmatched = tools.build_geometry_mapping(before, after, dividers, *V_AXIS)

    assert unmatched == []
    assert mapping == {2: 5, 3: 6, 4: 7}
    for source_id, mirror_id in mapping.items():
        source_x = sketch.Geometry[source_id].StartPoint.x
        assert sketch.Geometry[mirror_id].StartPoint.x == pytest.approx(-source_x)


def test_geometry_mapping_reports_a_source_with_no_reflection(tools):
    sketch, dividers = _card_box([10.0, 20.0])
    before = list(sketch.Geometry)
    # Only mirror the first divider; the second has no counterpart.
    sketch.mirror_selected([dividers[0]], *V_AXIS)
    after = list(sketch.Geometry)

    mapping, unmatched = tools.build_geometry_mapping(before, after, dividers, *V_AXIS)

    assert set(mapping) == {2}
    assert unmatched == [3]


# ---------------------------------------------------------------------------
# Compatibility policy
# ---------------------------------------------------------------------------


def _record(tools, constraint, index=0):
    return tools.constraint_record(constraint, index)


def test_point_on_object_to_an_unchanged_border_is_copied(tools):
    sketch, dividers = _card_box([20.0])
    before = list(sketch.Geometry)
    sketch.mirror_selected(dividers, *V_AXIS)
    mapping, _ = tools.build_geometry_mapping(before, list(sketch.Geometry), dividers, *V_AXIS)

    record = _record(tools, FakeConstraint("PointOnObject", 2, POS_START, 0))
    action, reason, spec = tools.classify_constraint(
        record, set(dividers), mapping, before, *V_AXIS
    )

    assert action == "copy"
    assert spec["type"] == "PointOnObject"
    assert spec["first"] == mapping[2]
    assert spec["second"] == 0
    assert "geometry 0" in reason


def test_coincidence_fully_inside_the_selection_is_left_to_native(tools):
    sketch, dividers = _card_box([10.0, 20.0])
    before = list(sketch.Geometry)
    record = _record(
        tools, FakeConstraint("Coincident", dividers[0], POS_END, dividers[1], POS_START)
    )
    action, _reason, spec = tools.classify_constraint(record, set(dividers), {}, before, *V_AXIS)
    assert action == "native"
    assert spec is None


def test_coincidence_with_the_mirror_axis_is_copied(tools):
    sketch = FakeSketch("Sketch")
    sketch.addGeometry(FakeLineSegment((0.0, 0.0), (0.0, 20.0)))  # geo 0 on the Y axis
    before = list(sketch.Geometry)
    sketch.mirror_selected([0], *V_AXIS)
    mapping, _ = tools.build_geometry_mapping(before, list(sketch.Geometry), [0], *V_AXIS)

    # -2 is FreeCAD's Y axis / origin id.
    record = _record(tools, FakeConstraint("Coincident", 0, POS_START, -2, POS_START))
    action, reason, spec = tools.classify_constraint(record, {0}, mapping, before, *V_AXIS)

    assert action == "copy"
    assert spec["second"] == -2
    assert "axis" in reason


def test_point_far_along_the_infinite_mirror_axis_is_still_copied(tools):
    sketch = FakeSketch("Sketch")
    sketch.addGeometry(FakeLineSegment((0.0, 20.0), (0.0, 30.0)))
    before = list(sketch.Geometry)
    sketch.mirror_selected([0], *V_AXIS)
    mapping, _ = tools.build_geometry_mapping(before, list(sketch.Geometry), [0], *V_AXIS)
    record = _record(tools, FakeConstraint("Coincident", 0, POS_START, -2, POS_START))

    action, _reason, _spec = tools.classify_constraint(record, {0}, mapping, before, *V_AXIS)

    assert action == "copy"


def test_external_boundary_is_skipped_when_it_cannot_be_validated(tools):
    sketch, dividers = _card_box([20.0])
    before = list(sketch.Geometry)
    record = _record(tools, FakeConstraint("PointOnObject", dividers[0], POS_START, -3))

    action, reason, spec = tools.classify_constraint(
        record, set(dividers), {dividers[0]: 3}, before, *V_AXIS
    )

    assert action == "skip"
    assert spec is None
    assert "external" in reason


def test_global_x_dimension_under_an_angled_mirror_is_skipped_and_reported(tools):
    sketch, dividers = _card_box([20.0])
    before = list(sketch.Geometry)
    angled_axis = ((0.0, 0.0), (10.0, 10.0))

    record = _record(tools, FakeConstraint("DistanceX", dividers[0], POS_START, 25.0))
    action, reason, spec = tools.classify_constraint(
        record, set(dividers), {2: 3}, before, *angled_axis
    )

    assert action == "skip"
    assert spec is None
    assert "angled mirror" in reason


def test_unsupported_constraint_across_the_boundary_is_skipped(tools):
    sketch, dividers = _card_box([20.0])
    before = list(sketch.Geometry)
    # Perpendicular between a mirrored divider and an unchanged border.
    record = _record(tools, FakeConstraint("Perpendicular", dividers[0], 0, 0, 0))
    action, reason, spec = tools.classify_constraint(record, set(dividers), {2: 3}, before, *V_AXIS)
    assert action == "skip"
    assert spec is None
    assert "unsupported" in reason


# ---------------------------------------------------------------------------
# Applying the plan
# ---------------------------------------------------------------------------


def test_apply_removes_a_copy_the_solver_flags_as_redundant(tools):
    sketch, dividers = _card_box([20.0])
    sketch.mirror_selected(dividers, *V_AXIS)
    first_new_index = len(sketch.Constraints)
    # The solver will reject the first copy as redundant.
    sketch.Redundant = [first_new_index]

    specs = [
        {"type": "PointOnObject", "first": 3, "first_pos": POS_START, "second": 0, "second_pos": 0},
        {"type": "PointOnObject", "first": 3, "first_pos": POS_END, "second": 1, "second_pos": 0},
    ]
    added, removed = tools.apply_constraint_copies(sketch, specs)

    assert len(added) == 1
    assert len(removed) == 1
    assert "redundant" in removed[0]["reason"]
    # The redundant copy was actually taken back out of the sketch.
    assert len(sketch.Constraints) == first_new_index + 1


def test_apply_removes_multiple_solver_rejections_without_index_shift(tools):
    sketch, dividers = _card_box([20.0])
    sketch.mirror_selected(dividers, *V_AXIS)
    first_new_index = len(sketch.Constraints)
    sketch.RedundantConstraints = [first_new_index, first_new_index + 1]
    specs = [
        {"type": "PointOnObject", "first": 3, "first_pos": POS_START, "second": 0},
        {"type": "PointOnObject", "first": 3, "first_pos": POS_END, "second": 1},
    ]

    added, removed = tools.apply_constraint_copies(sketch, specs)

    assert added == []
    assert len(removed) == 2
    assert len(sketch.Constraints) == first_new_index


def test_apply_preserves_reference_and_inactive_constraint_state(tools):
    sketch, dividers = _card_box([20.0])
    sketch.mirror_selected(dividers, *V_AXIS)
    specs = [
        {
            "type": "PointOnObject",
            "first": 3,
            "first_pos": POS_START,
            "second": 0,
            "driving": False,
            "active": False,
        }
    ]

    added, removed = tools.apply_constraint_copies(sketch, specs)

    assert len(added) == 1
    assert removed == []
    assert sketch.Constraints[-1].Driving is False
    assert sketch.Constraints[-1].IsActive is False


# ---------------------------------------------------------------------------
# The command
# ---------------------------------------------------------------------------


def test_command_is_inactive_without_a_sketch_being_edited(tools, env):
    command = tools.MirrorWithConstraintsCommand()
    assert command.IsActive() is False


def test_command_is_active_while_editing_a_sketch(tools, env):
    sketch, _ = _card_box([10.0])
    env.begin_sketch_edit(sketch)
    assert tools.MirrorWithConstraintsCommand().IsActive() is True


def test_is_active_never_touches_gui_edit_state(tools, env):
    """FreeCAD polls IsActive on a timer, including mid-setEdit; it must stay off
    getInEdit / view providers, whose C++ can fault uncatchably. This is what
    withdrew 1.3.2."""
    env._new_document()
    env.active_workbench = "PartDesignWorkbench"

    def explode():
        raise AssertionError("IsActive must not call getInEdit()")

    env.gui.ActiveDocument = types.SimpleNamespace(getInEdit=explode)
    assert tools.MirrorWithConstraintsCommand().IsActive() is False


def test_mirror_links_every_card_box_divider_to_its_source(tools, env):
    sketch, dividers = _card_box([-30.0, -20.0, -10.0, 5.0, 15.0, 25.0])
    env.begin_sketch_edit(sketch)
    env.select_subelements(sketch, ["Edge{}".format(g + 1) for g in dividers] + ["V_Axis"])

    result = tools.mirror_with_constraints()

    assert result["status"] == "ok"
    assert result["mirrored"] == 6
    assert result["linked_pairs"] == 6
    assert result["unmatched"] == []
    assert result["skipped"] == []
    # Two Symmetric links per divider (start and end), about the Y axis.
    symmetric = [c for c in sketch.Constraints if c.Type == "Symmetric"]
    assert len(symmetric) == 12
    assert all(c.Third == -2 for c in symmetric)
    # The link makes the copied boundary constraints redundant, so they are not
    # also added; every one is accounted for as covered.
    assert result["copied"] == []
    assert len(result["covered_by_link"]) == 12
    assert sum(1 for c in sketch.Constraints if c.Type == "PointOnObject") == 12


def test_boundary_constraint_is_copied_when_the_symmetry_link_is_rejected(tools, env):
    sketch, _dividers = _card_box([20.0])
    env.begin_sketch_edit(sketch)
    env.select_subelements(sketch, ["Edge3", "V_Axis"])
    # The solver rejects every Symmetric link the command tries to add.
    sketch._reject = lambda constraint: constraint.Type == "Symmetric"

    result = tools.mirror_with_constraints()

    assert result["status"] == "ok"
    assert result["linked_pairs"] == 0
    assert len(result["link_rolled_back"]) == 1
    # The pair's links were rolled back as a unit; nothing stayed behind.
    assert [c for c in sketch.Constraints if c.Type == "Symmetric"] == []
    # With no link, the divider's endpoint attachments are reproduced instead.
    assert [spec["type"] for spec in result["copied"]] == ["PointOnObject", "PointOnObject"]


def test_symmetry_link_is_rolled_back_as_a_unit_when_one_end_is_redundant(tools, env):
    """A half-linked pair distorts when the source moves, so a single redundant
    end rolls the whole pair back rather than leaving one link in place."""
    sketch, _dividers = _card_box([20.0])
    env.begin_sketch_edit(sketch)
    env.select_subelements(sketch, ["Edge3", "V_Axis"])
    # Only the end-point link of the pair (FirstPos == 2) comes back redundant.
    sketch._reject = lambda c: c.Type == "Symmetric" and c.FirstPos == POS_END

    result = tools.mirror_with_constraints()

    assert result["linked_pairs"] == 0
    assert len(result["link_rolled_back"]) == 1
    assert [c for c in sketch.Constraints if c.Type == "Symmetric"] == []


def _vertical_divider_box():
    """A box with one divider that carries its own Vertical constraint -- the
    case where addSymmetric reproduces Vertical onto the copy."""
    sketch = FakeSketch("Sketch")
    sketch.addGeometry(FakeLineSegment((-50.0, 0.0), (50.0, 0.0)))  # 0 bottom
    sketch.addGeometry(FakeLineSegment((-50.0, 30.0), (50.0, 30.0)))  # 1 top
    divider = sketch.addGeometry(FakeLineSegment((20.0, 0.0), (20.0, 30.0)))  # 2
    sketch.addConstraint(FakeConstraint("PointOnObject", divider, POS_START, 0))
    sketch.addConstraint(FakeConstraint("PointOnObject", divider, POS_END, 1))
    sketch.addConstraint(FakeConstraint("Vertical", divider))
    return sketch, divider


def test_reproduced_orientation_constraint_on_the_copy_is_stripped_for_the_link(tools, env):
    sketch, _divider = _vertical_divider_box()
    env.begin_sketch_edit(sketch)
    env.select_subelements(sketch, ["Edge3", "V_Axis"])

    result = tools.mirror_with_constraints()

    assert result["linked_pairs"] == 1
    # addSymmetric put a Vertical on the copy (geo 3); the link replaces it.
    assert [c for c in sketch.Constraints if c.Type == "Vertical" and c.First == 3] == []
    assert len([c for c in sketch.Constraints if c.Type == "Symmetric"]) == 2


def test_stripped_orientation_constraint_is_restored_when_the_pair_rolls_back(tools, env):
    sketch, _divider = _vertical_divider_box()
    env.begin_sketch_edit(sketch)
    env.select_subelements(sketch, ["Edge3", "V_Axis"])
    sketch._reject = lambda c: c.Type == "Symmetric"

    result = tools.mirror_with_constraints()

    assert result["linked_pairs"] == 0
    # The copy is back exactly as addSymmetric left it: Vertical restored, no link.
    assert [c for c in sketch.Constraints if c.Type == "Symmetric"] == []
    assert len([c for c in sketch.Constraints if c.Type == "Vertical" and c.First == 3]) == 1


def test_missing_explicit_axis_leaves_the_sketch_unchanged(tools, env):
    sketch, _dividers = _card_box([10.0, 20.0])
    env.begin_sketch_edit(sketch)
    env.select_subelements(sketch, ["Edge3"])
    geometry_before = list(sketch.Geometry)
    constraints_before = list(sketch.Constraints)

    result = tools.mirror_with_constraints()

    assert result["status"] == "no-selection"
    assert sketch.Geometry == geometry_before
    assert sketch.Constraints == constraints_before
    assert env.app.ActiveDocument.transactions == []


def test_mirror_and_constraint_copy_are_one_transaction(tools, env):
    sketch, _dividers = _card_box([10.0, 20.0])
    env.begin_sketch_edit(sketch)
    env.select_subelements(sketch, ["Edge3", "Edge4", "V_Axis"])
    tools.mirror_with_constraints()

    assert env.app.ActiveDocument.transactions == [
        ("open", "Mirror with Constraints"),
        ("commit", "Mirror with Constraints"),
    ]


def test_unsupported_constraint_is_reported_not_dropped_silently(tools, env):
    sketch, dividers = _card_box([20.0])
    divider = dividers[0]
    # An angle dimension from a divider to a border cannot be mirrored safely.
    sketch.addConstraint(FakeConstraint("Angle", divider, POS_START, 0, POS_START, 0.75))
    env.begin_sketch_edit(sketch)
    env.select_subelements(sketch, ["Edge3", "V_Axis"])
    result = tools.mirror_with_constraints()

    assert result["status"] == "ok"
    assert any(item["type"] == "Angle" for item in result["skipped"])
    assert any("Angle" in message for message in env.console.messages)


def test_no_selection_is_refused_without_touching_the_sketch(tools, env):
    sketch, _ = _card_box([10.0])
    env.begin_sketch_edit(sketch)  # editing, but nothing selected

    result = tools.mirror_with_constraints()

    assert result["status"] == "no-selection"
    assert env.console.errors
