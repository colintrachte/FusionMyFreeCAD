"""Constraint-aware sketch mirroring for FMF.

``FMF_MirrorWithConstraints`` uses Sketcher's synchronous symmetry API
and then does two things native Symmetry does not do on FreeCAD 1.1.3, in order:

1. Copies the *boundary* constraints native Symmetry drops -- the ones that tie a
   mirrored endpoint to geometry outside the mirrored selection (an unchanged
   border line, a sketch axis, projected external geometry). Native Symmetry only
   reproduces constraints whose every endpoint is inside the mirrored selection,
   so a divider attached to its top and bottom edges would lose those
   attachments. They are also what let FreeCAD split the border edges and detect
   the enclosed regions for face selection and extrude, so they go on first.
2. For a mirrored element that did *not* get a border attachment -- free-floating
   geometry -- adds a live ``Symmetric`` link to its source across the mirror
   line, so dragging either one moves the other (``Equal`` keeps a mirrored
   circle or arc the same size). A ``Symmetric`` point constraint is two
   equations, and on FreeCAD 1.1.3 those always duplicate the degrees of freedom
   a border attachment already pins, over-constraining the sketch -- so an
   attached element (a divider) keeps the fillable profile and is left unlinked;
   add a ``Symmetric`` constraint by hand if a live link there is wanted. Links
   are still added one at a time and any the solver rejects are backed out.

The command is explicitly best-effort.  Every constraint it cannot safely
reproduce is reported rather than dropped in silence, matching the rest of the
add-on's "never fail quietly" contract.

The FreeCAD-touching helpers are deliberately small and isolated.  The synchronous
API and selection spellings are verified against FreeCAD 1.1.3; unsupported
selection forms are refused rather than guessed.
"""

from __future__ import annotations

import os

import FreeCAD as App
import FreeCADGui as Gui

from fmf_common import SketcherCommand, log_swallowed, notify

# Distance below which two sketch coordinates are treated as the same point.
TOLERANCE = 1e-6

# Constraint types whose reflection native Symmetry already handles when every
# referenced element is inside the mirrored selection.  We never touch these.
_WITHIN_SELECTION_TYPES = frozenset(
    {
        "Horizontal",
        "Vertical",
        "Parallel",
        "Perpendicular",
        "Tangent",
        "Equal",
        "Symmetric",
        "Radius",
        "Diameter",
        "Weight",
        "Angle",
        "Block",
        "InternalAlignment",
    }
)

# Constraint types we know how to reflect across a boundary.
_BOUNDARY_COPYABLE_TYPES = frozenset({"Coincident", "PointOnObject"})

# Sketcher point-position ids.  ``none`` = the edge itself, 1 = start, 2 = end,
# 3 = centre/third point.
_POS_NONE = 0
_POS_START = 1
_POS_END = 2
_POS_CENTER = 3


# ---------------------------------------------------------------------------
# Pure geometry helpers
# ---------------------------------------------------------------------------


def reflect_point(point, axis_a, axis_b):
    """Reflect ``point`` across the infinite line through ``axis_a`` and ``axis_b``.

    All three arguments are ``(x, y)`` pairs.  A degenerate axis (both points
    equal) returns the point unchanged.
    """
    px, py = point
    ax, ay = axis_a
    bx, by = axis_b
    dx, dy = bx - ax, by - ay
    length_squared = dx * dx + dy * dy
    if length_squared <= TOLERANCE * TOLERANCE:
        return (px, py)
    t = ((px - ax) * dx + (py - ay) * dy) / length_squared
    foot_x, foot_y = ax + t * dx, ay + t * dy
    return (2.0 * foot_x - px, 2.0 * foot_y - py)


def points_equal(first, second, tolerance=TOLERANCE):
    return abs(first[0] - second[0]) <= tolerance and abs(first[1] - second[1]) <= tolerance


def axis_is_orthogonal(axis_a, axis_b, tolerance=TOLERANCE):
    """True when the mirror axis is exactly horizontal or vertical."""
    dx = abs(axis_b[0] - axis_a[0])
    dy = abs(axis_b[1] - axis_a[1])
    return dx <= tolerance or dy <= tolerance


def distance_point_to_segment(point, seg_a, seg_b):
    """Shortest distance from ``point`` to the finite segment ``seg_a``-``seg_b``."""
    px, py = point
    ax, ay = seg_a
    bx, by = seg_b
    dx, dy = bx - ax, by - ay
    length_squared = dx * dx + dy * dy
    if length_squared <= TOLERANCE * TOLERANCE:
        return math_hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / length_squared
    t = max(0.0, min(1.0, t))
    foot_x, foot_y = ax + t * dx, ay + t * dy
    return math_hypot(px - foot_x, py - foot_y)


def distance_point_to_line(point, line_a, line_b):
    """Shortest distance from ``point`` to the infinite line through two points."""
    px, py = point
    ax, ay = line_a
    bx, by = line_b
    dx, dy = bx - ax, by - ay
    length = math_hypot(dx, dy)
    if length <= TOLERANCE:
        return math_hypot(px - ax, py - ay)
    return abs(dx * (ay - py) - (ax - px) * dy) / length


def math_hypot(dx, dy):
    return (dx * dx + dy * dy) ** 0.5


# ---------------------------------------------------------------------------
# Sketch introspection (best-effort, tolerant of partial fakes)
# ---------------------------------------------------------------------------


def _geometry_list(sketch):
    return list(getattr(sketch, "Geometry", []) or [])


def geometry_point(geo, pos_id):
    """Return the ``(x, y)`` of a geometry's start/end/centre point, or ``None``.

    Works with FreeCAD ``Part`` geometry (``Vector`` attributes) and with plain
    objects exposing ``StartPoint``/``EndPoint``/``Center``.
    """
    if hasattr(geo, "X") and hasattr(geo, "Y"):
        try:
            return (float(geo.X), float(geo.Y))
        except (TypeError, ValueError):
            pass
    attribute = {
        _POS_START: "StartPoint",
        _POS_END: "EndPoint",
        _POS_CENTER: "Center",
    }.get(pos_id)
    if attribute is None:
        return None
    vector = getattr(geo, attribute, None)
    if vector is None:
        return None
    try:
        return (float(vector.x), float(vector.y))
    except AttributeError:
        try:
            return (float(vector[0]), float(vector[1]))
        except (TypeError, IndexError, ValueError):
            return None


def geometry_endpoints(geo):
    """All resolvable named points of a geometry as ``{pos_id: (x, y)}``."""
    points = {}
    for pos_id in (_POS_START, _POS_END, _POS_CENTER):
        resolved = geometry_point(geo, pos_id)
        if resolved is not None:
            points[pos_id] = resolved
    return points


def point_on_axis(point, axis_a, axis_b, tolerance=TOLERANCE):
    """Whether `point` lies on the infinite mirror line."""
    return distance_point_to_line(point, axis_a, axis_b) <= tolerance


def boundary_open_ends(sketch, axis_a, axis_b, tolerance=TOLERANCE):
    """Profile endpoints sitting on the mirror line that nothing joins to.

    These are the joins a mirror is answerable for. An endpoint on the axis is
    where the original meets its reflection, so after mirroring it must be met
    by two edges. Anything still alone there is a gap the mirror opened, and the
    profile will not close.

    Endpoints away from the axis are deliberately ignored: mirroring an open
    chain and closing it afterwards is an ordinary thing to do, and refusing
    that would make the command useless.
    """
    return [
        (point, owners)
        for point, owners in _endpoint_owners(sketch, tolerance)
        if len(owners) < 2 and point_on_axis(point, axis_a, axis_b, tolerance)
    ]


def _endpoint_owners(sketch, tolerance=TOLERANCE):
    """Every profile endpoint with the edges meeting it."""
    counts = []
    for geoid, geo in enumerate(_geometry_list(sketch)):
        if is_construction(sketch, geoid, geo):
            continue
        points = geometry_endpoints(geo)
        start, end = points.get(_POS_START), points.get(_POS_END)
        if start is None or end is None:
            # A circle bounds itself and needs no partner.
            continue
        for point in (start, end):
            for existing in counts:
                if points_equal(existing[0], point, tolerance):
                    existing[1].append(geoid)
                    break
            else:
                counts.append((point, [geoid]))
    return [(point, sorted(set(owners))) for point, owners in counts]


def is_construction(sketch, geoid, geo=None):
    """Whether `geoid` is construction geometry, however this build spells it."""
    getter = getattr(sketch, "getConstruction", None)
    if callable(getter):
        try:
            return bool(getter(geoid))
        except Exception:
            pass
    if geo is None:
        geometry = _geometry_list(sketch)
        geo = geometry[geoid] if 0 <= geoid < len(geometry) else None
    return bool(getattr(geo, "Construction", False))


def open_endpoints(sketch, tolerance=TOLERANCE):
    """Endpoints of the profile that are not shared by exactly two edges.

    This is what decides whether a sketch can become a face. An endpoint met by
    one edge is a gap; by three or more, a branch. Either makes OpenCASCADE
    report "failed to close some wire" and the pad refuse.
    """
    return [
        (point, owners) for point, owners in _endpoint_owners(sketch, tolerance) if len(owners) != 2
    ]


def constraint_record(constraint, index):
    """Flatten a Sketcher constraint into a plain dict.

    Missing attributes default to ``-2000`` (FreeCAD's "GeoUndef") or ``None`` so
    the classifier never has to guess whether an attribute was absent or zero.
    """
    return {
        "index": index,
        "type": getattr(constraint, "Type", getattr(constraint, "TypeId", "")),
        "first": int(getattr(constraint, "First", -2000)),
        "first_pos": int(getattr(constraint, "FirstPos", _POS_NONE)),
        "second": int(getattr(constraint, "Second", -2000)),
        "second_pos": int(getattr(constraint, "SecondPos", _POS_NONE)),
        "third": int(getattr(constraint, "Third", -2000)),
        "third_pos": int(getattr(constraint, "ThirdPos", _POS_NONE)),
        "value": getattr(constraint, "Value", None),
        "name": getattr(constraint, "Name", "") or "",
        "driving": bool(getattr(constraint, "Driving", True)),
        "active": bool(getattr(constraint, "IsActive", True)),
    }


def _referenced_geoids(record):
    ids = []
    for key in ("first", "second", "third"):
        value = record[key]
        if value is not None and value > -2000:
            ids.append(value)
    return ids


def _is_real_geometry(geoid):
    """True for an ordinary in-sketch edge (not an axis, origin, or external)."""
    return geoid is not None and geoid >= 0


def _is_axis(geoid):
    """FreeCAD reserves -1 for the X axis and -2 for the Y axis / origin point."""
    return geoid in (-1, -2)


def _is_external(geoid):
    """External (projected) geometry uses ids at -3 and below, above GeoUndef."""
    return geoid is not None and -2000 < geoid <= -3


# ---------------------------------------------------------------------------
# Source-to-mirror geometry mapping
# ---------------------------------------------------------------------------


def build_geometry_mapping(before_geometry, after_geometry, source_indices, axis_a, axis_b):
    """Match each source geometry index to its mirrored counterpart.

    Native Symmetry appends the mirrored copies after the existing geometry, so
    the candidates are ``range(len(before_geometry), len(after_geometry))``.  Each
    source edge is matched to the appended edge whose named points equal the
    reflected named points of the source, within ``TOLERANCE``.

    Returns ``(mapping, unmatched)`` where ``mapping`` is ``{source_id: mirror_id}``
    and ``unmatched`` is the sorted list of source ids with no confident match.
    """
    first_new = len(before_geometry)
    new_indices = list(range(first_new, len(after_geometry)))
    mapping = {}
    used = set()
    unmatched = []

    for source_id in sorted(source_indices):
        if source_id < 0 or source_id >= len(before_geometry):
            unmatched.append(source_id)
            continue
        source_points = geometry_endpoints(before_geometry[source_id])
        reflected = {
            pos: reflect_point(point, axis_a, axis_b) for pos, point in source_points.items()
        }
        match = None
        for candidate_id in new_indices:
            if candidate_id in used:
                continue
            candidate_points = geometry_endpoints(after_geometry[candidate_id])
            if not reflected or set(candidate_points) != set(reflected):
                continue
            if all(points_equal(candidate_points[pos], reflected[pos]) for pos in reflected):
                match = candidate_id
                break
        if match is None:
            unmatched.append(source_id)
        else:
            mapping[source_id] = match
            used.add(match)

    return mapping, sorted(unmatched)


# ---------------------------------------------------------------------------
# Compatibility policy
# ---------------------------------------------------------------------------


def classify_constraint(record, source_set, mapping, before_geometry, axis_a, axis_b):
    """Decide what to do with one existing constraint.

    Returns ``(action, reason, spec)``:

    * ``action`` is ``"native"`` (leave it to Symmetry), ``"copy"`` (reproduce it
      with ``spec``), or ``"skip"`` (cannot reproduce safely; report it).
    * ``spec`` is a constraint spec dict for ``"copy"``, otherwise ``None``.
    """
    ctype = record["type"]
    all_ids = (record["first"], record["second"], record["third"])
    real_referenced = [g for g in _referenced_geoids(record) if _is_real_geometry(g)]
    in_source = [g for g in real_referenced if g in source_set]
    out_source = [g for g in real_referenced if g not in source_set]
    touches_axis = any(_is_axis(g) for g in all_ids)
    touches_external = any(_is_external(g) for g in all_ids)

    if not in_source:
        # The constraint names no mirrored element, so mirroring cannot have
        # broken it -- even if it happens to touch a sketch axis or the origin.
        return "native", "constraint does not touch the mirrored selection", None

    # "Fully inside" means every element the constraint names is being mirrored:
    # no unchanged edge, no sketch axis, no projected external geometry.
    fully_inside = bool(in_source) and not out_source and not touches_axis and not touches_external
    if fully_inside and ctype in _WITHIN_SELECTION_TYPES:
        return "native", "reflected by native Symmetry", None

    if fully_inside and ctype in _BOUNDARY_COPYABLE_TYPES:
        return "native", "internal coincidence is reflected by Symmetry", None

    # Dimensions.
    if ctype in ("DistanceX", "DistanceY"):
        internal_distance = len([g for g in real_referenced if g in source_set]) >= 2
        if fully_inside and internal_distance:
            return "native", "distance between mirrored points is reflected by Symmetry", None
        if not axis_is_orthogonal(axis_a, axis_b):
            return (
                "skip",
                "global {} dimension under an angled mirror is unsafe".format(ctype),
                None,
            )
        return (
            "skip",
            "global {} dimension is not reproduced automatically".format(ctype),
            None,
        )

    if fully_inside and ctype == "Distance":
        return "native", "distance between mirrored elements is reflected by Symmetry", None

    if ctype in ("Distance", "Angle", "Radius", "Diameter"):
        return (
            "skip",
            "{} dimension across the mirror boundary needs manual review".format(ctype),
            None,
        )

    if ctype not in _BOUNDARY_COPYABLE_TYPES:
        return "skip", "{} constraint across the mirror boundary is unsupported".format(ctype), None

    # Coincident / PointOnObject that ties a mirrored point to an unchanged
    # border, a sketch axis, or projected external geometry.
    return _plan_boundary_point_copy(record, source_set, mapping, before_geometry, axis_a, axis_b)


def _plan_boundary_point_copy(record, source_set, mapping, before_geometry, axis_a, axis_b):
    ctype = record["type"]

    # Identify which side is the mirrored point and which is the border.
    sides = [
        (record["first"], record["first_pos"]),
        (record["second"], record["second_pos"]),
    ]
    mirrored_side = None
    border_side = None
    for geoid, pos in sides:
        if _is_real_geometry(geoid) and geoid in source_set:
            mirrored_side = (geoid, pos)
        else:
            border_side = (geoid, pos)
    if mirrored_side is None or border_side is None:
        return "skip", "could not identify the mirrored endpoint of the constraint", None

    source_geoid, source_pos = mirrored_side
    if source_geoid not in mapping:
        return (
            "skip",
            "mirrored counterpart of geometry {} was not found".format(source_geoid),
            None,
        )
    mirror_geoid = mapping[source_geoid]

    # Where does the mirrored point land?
    source_point = geometry_point(before_geometry[source_geoid], source_pos)
    reflected_point = (
        reflect_point(source_point, axis_a, axis_b) if source_point is not None else None
    )

    border_geoid, border_pos = border_side

    if _is_axis(border_geoid):
        # A point on the mirror axis reflects onto the same axis.
        if reflected_point is not None and source_point is not None:
            on_axis = distance_point_to_line(source_point, axis_a, axis_b) <= 1e-4
            if not on_axis:
                return (
                    "skip",
                    "coincidence with an axis that is not the mirror axis needs review",
                    None,
                )
        return (
            "copy",
            "point-on-axis coincidence reflects onto the same axis",
            _constraint_spec(ctype, mirror_geoid, source_pos, border_geoid, border_pos, record),
        )

    if _is_external(border_geoid):
        return (
            "skip",
            "projected external geometry cannot be validated safely by this command",
            None,
        )

    validated = None
    if reflected_point is not None and _is_real_geometry(border_geoid):
        border_geo = before_geometry[border_geoid] if border_geoid < len(before_geometry) else None
        border_points = geometry_endpoints(border_geo) if border_geo is not None else {}
        if len(border_points) >= 2:
            ordered = [border_points[p] for p in sorted(border_points)][:2]
            gap = distance_point_to_segment(reflected_point, ordered[0], ordered[1])
            validated = gap <= 1e-4
            if validated is False:
                return (
                    "skip",
                    "reflected point does not lie on border geometry {} (gap {:.4g})".format(
                        border_geoid, gap
                    ),
                    None,
                )

    reason = "boundary {} reflected onto geometry {}".format(ctype.lower(), border_geoid)
    if validated is None:
        reason += " (geometry not verified offline)"
    return (
        "copy",
        reason,
        _constraint_spec(ctype, mirror_geoid, source_pos, border_geoid, border_pos, record),
    )


def _constraint_spec(ctype, point_geoid, point_pos, edge_geoid, edge_pos, source_record):
    """Build a constraint spec dict for :func:`apply_constraint_copies`."""
    spec = {
        "type": ctype,
        "first": point_geoid,
        "first_pos": point_pos,
        "second": edge_geoid,
        "second_pos": edge_pos if ctype == "Coincident" else _POS_NONE,
        "source_index": source_record["index"],
        "driving": source_record["driving"],
        "active": source_record["active"],
    }
    if source_record["name"]:
        # Names must stay unique; a reused name silently detaches an expression.
        spec["name"] = "{}_mirror".format(source_record["name"])
    return spec


def plan_constraint_copies(records, source_set, mapping, before_geometry, axis_a, axis_b):
    """Classify every existing constraint.

    Returns ``(copies, skipped)``.  ``copies`` is a list of spec dicts;
    ``skipped`` is a list of ``{"index", "type", "reason"}``.
    """
    copies = []
    skipped = []
    for record in records:
        action, reason, spec = classify_constraint(
            record, source_set, mapping, before_geometry, axis_a, axis_b
        )
        if action == "copy" and spec is not None:
            spec["reason"] = reason
            copies.append(spec)
        elif action == "skip":
            skipped.append({"index": record["index"], "type": record["type"], "reason": reason})
    return copies, skipped


# ---------------------------------------------------------------------------
# Applying the plan to a live sketch
# ---------------------------------------------------------------------------


def _new_constraint(spec):
    """Instantiate a ``Sketcher.Constraint`` from a spec dict."""
    import Sketcher

    ctype = spec["type"]
    if ctype == "PointOnObject":
        return Sketcher.Constraint(
            "PointOnObject", spec["first"], spec["first_pos"], spec["second"]
        )
    if ctype == "Symmetric":
        # point1, point2 symmetric about the mirror line ``third`` (a real edge
        # geoid, or -1 / -2 for the sketch X / Y axis).
        return Sketcher.Constraint(
            "Symmetric",
            spec["first"],
            spec["first_pos"],
            spec["second"],
            spec["second_pos"],
            spec["third"],
        )
    if ctype == "Equal":
        return Sketcher.Constraint("Equal", spec["first"], spec["second"])
    return Sketcher.Constraint(
        "Coincident",
        spec["first"],
        spec["first_pos"],
        spec["second"],
        spec["second_pos"],
    )


# Solver diagnostics. A *conflicting* or *malformed* constraint breaks the
# sketch and must always come back out. A *fully redundant* one adds nothing and
# is quietly dropped. A *partially* redundant one still removes a degree of
# freedom (only part of it duplicates something) so it is kept -- an endpoint
# symmetry link onto an already-attached mirror is the usual case.
_CONFLICTING_ATTRS = ("ConflictingConstraints", "MalformedConstraints", "Conflicting", "Malformed")
_FULLY_REDUNDANT_ATTRS = ("RedundantConstraints", "Redundant")
_ALL_BAD_ATTRS = _CONFLICTING_ATTRS + _FULLY_REDUNDANT_ATTRS + ("PartiallyRedundantConstraints",)


def _flagged_indices(sketch, attributes):
    flagged = set()
    for attribute in attributes:
        for value in getattr(sketch, attribute, []) or []:
            try:
                flagged.add(int(value))
            except (TypeError, ValueError):
                continue
    return flagged


def _bad_constraint_indices(sketch):
    """Redundant/conflicting/malformed constraint indices the solver flagged."""
    return _flagged_indices(sketch, _ALL_BAD_ATTRS)


def apply_constraint_copies(sketch, specs):
    """Add each planned constraint, then drop any the solver rejects.

    Returns ``(added, removed)``.  ``added`` is the list of specs that stuck;
    ``removed`` is a list of ``{"type", "reason"}`` for copies pulled back out
    because they became redundant or conflicting.
    """
    added = []
    added_indices = []
    for spec in specs:
        before = len(list(getattr(sketch, "Constraints", []) or []))
        try:
            new_index = sketch.addConstraint(_new_constraint(spec))
        except Exception as error:
            spec["reason"] = "FreeCAD rejected the constraint: {}".format(error)
            spec["_failed"] = True
            continue
        if not isinstance(new_index, int):
            new_index = before
        added.append(spec)
        added_indices.append(new_index)
        name = spec.get("name")
        if name:
            try:
                sketch.renameConstraint(new_index, name)
            except Exception:
                pass
        state_updates = (
            ("setDriving", spec.get("driving")),
            ("setActive", spec.get("active")),
        )
        for method, value in state_updates:
            setter = getattr(sketch, method, None)
            if callable(setter) and value is not None:
                try:
                    setter(new_index, bool(value))
                except Exception:
                    pass

    _recompute(sketch)

    removed = []
    bad = _bad_constraint_indices(sketch)
    if bad:
        survivors = []
        survivor_indices = []
        rejected = {index for index in added_indices if index in bad}
        for spec, index in zip(added, added_indices, strict=False):
            if index in bad:
                removed.append(
                    {
                        "type": spec["type"],
                        "reason": "copy became redundant or conflicting and was removed",
                    }
                )
            else:
                survivors.append(spec)
                survivor_indices.append(index)
        # Delete backwards so removing one constraint cannot shift the index of
        # another rejected copy.
        for index in sorted(rejected, reverse=True):
            try:
                sketch.delConstraint(index)
            except Exception as exc:
                log_swallowed(f"delConstraint({index}) during boundary copy rollback", exc)
        added, added_indices = survivors, survivor_indices
        _recompute(sketch)

    failed = [
        {"type": spec["type"], "reason": spec["reason"]} for spec in specs if spec.get("_failed")
    ]
    return added, removed + failed


def apply_symmetry_links(sketch, link_specs):
    """Add the live ``Symmetric`` links one at a time, keeping only what helps.

    Run this *after* the boundary endpoint attachments have been copied onto the
    mirror. Each link is added on its own and the solver consulted:

    * conflicting / malformed -> remove it, the link cannot be made here;
    * fully redundant -> remove it, the mirror is already pinned at that point;
    * clean or only *partially* redundant -> keep it -- it still couples the
      mirror's position to its source, and on a divider already attached to a
      border the coordinate along the border is the only free part left, so
      FreeCAD notes the constraint as partially redundant. That note is
      informational; the sketch stays fully constrained.

    Returns ``(linked, dropped)``. ``linked`` is the link specs that stuck;
    ``dropped`` is ``[{"mirror", "reason"}]`` for links that could not be kept.
    """
    groups = {}
    for spec in link_specs:
        groups.setdefault(spec["_mirror"], []).append(spec)

    _recompute(sketch)
    conflicting_before = _flagged_indices(sketch, _CONFLICTING_ATTRS)
    linked = []
    dropped = []

    for mirror_id, specs in groups.items():
        for spec in specs:
            start = len(list(getattr(sketch, "Constraints", []) or []))
            try:
                index = sketch.addConstraint(_new_constraint(spec))
            except Exception as error:
                dropped.append(
                    {"mirror": mirror_id, "reason": "FreeCAD rejected a link: {}".format(error)}
                )
                continue
            if not isinstance(index, int):
                index = start
            _recompute(sketch)

            new_conflict = _flagged_indices(sketch, _CONFLICTING_ATTRS) - conflicting_before
            fully_redundant = _flagged_indices(sketch, _FULLY_REDUNDANT_ATTRS)
            if index in new_conflict:
                _drop_constraint(sketch, index)
                dropped.append(
                    {
                        "mirror": mirror_id,
                        "reason": "a live symmetry link here conflicts with an existing constraint",
                    }
                )
            elif index in fully_redundant:
                # The mirror is already pinned at this point; the link is a no-op.
                _drop_constraint(sketch, index)
            else:
                linked.append(spec)

    return linked, dropped


def _drop_constraint(sketch, index):
    try:
        sketch.delConstraint(index)
    except Exception as exc:
        log_swallowed(f"delConstraint({index}) during constraint drop", exc)
    _recompute(sketch)


def _recompute(sketch):
    for target, method in (
        (sketch, "solve"),
        (sketch, "recompute"),
        (getattr(App, "ActiveDocument", None), "recompute"),
    ):
        if target is None:
            continue
        function = getattr(target, method, None)
        if callable(function):
            try:
                function()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Session glue
# ---------------------------------------------------------------------------


def active_sketch():
    """Return the sketch object currently open for editing, or ``None``."""
    document = getattr(Gui, "ActiveDocument", None)
    if document is None:
        return None
    view_provider = None
    getter = getattr(document, "getInEdit", None)
    if callable(getter):
        try:
            view_provider = getter()
        except Exception:
            view_provider = None
    obj = getattr(view_provider, "Object", None)
    if obj is not None and _is_sketch(obj):
        return obj
    return None


def _is_sketch(obj):
    checker = getattr(obj, "isDerivedFrom", None)
    if callable(checker) and checker("Sketcher::SketchObject"):
        return True
    return getattr(obj, "TypeId", "") == "Sketcher::SketchObject"


def selected_source_geometry(sketch):
    """Return ``(sources, reference_geoid, reference_pos, axis, error)``.

    Select the geometry first and the mirror line last, or select the horizontal
    or vertical sketch axis.  Requiring an explicit reference avoids a dangerous
    silent fallback to the Y axis.
    """
    selection = []
    getter = getattr(Gui.Selection, "getSelectionEx", None)
    if callable(getter):
        try:
            selection = getter() or []
        except Exception:
            selection = []

    selected_edges = []
    mirror_axis_name = None
    for entry in selection:
        if getattr(entry, "Object", None) is not sketch and selection_object_name(entry) != getattr(
            sketch, "Name", None
        ):
            continue
        for sub in getattr(entry, "SubElementNames", []) or []:
            if sub.startswith("Edge"):
                try:
                    geoid = int(sub[4:]) - 1
                except ValueError:
                    continue
                if geoid not in selected_edges:
                    selected_edges.append(geoid)
            elif sub in ("H_Axis", "V_Axis", "RootPoint"):
                mirror_axis_name = sub

    if mirror_axis_name == "H_Axis":
        source = selected_edges
        reference_geoid, reference_pos = -1, _POS_NONE
        axis = ((0.0, 0.0), (1.0, 0.0))
    elif mirror_axis_name == "V_Axis":
        source = selected_edges
        reference_geoid, reference_pos = -2, _POS_NONE
        axis = ((0.0, 0.0), (0.0, 1.0))
    elif mirror_axis_name == "RootPoint":
        return [], None, None, None, "point symmetry is available from the original Mirror button"
    elif len(selected_edges) >= 2:
        mirror_edge = selected_edges[-1]
        source = selected_edges[:-1]
        points = geometry_endpoints(_geometry_list(sketch)[mirror_edge])
        ordered = [points[p] for p in sorted(points)][:2] if len(points) >= 2 else None
        if not ordered:
            return [], None, None, None, "the last selected edge cannot be used as a mirror line"
        reference_geoid, reference_pos = mirror_edge, _POS_NONE
        axis = tuple(ordered)
    else:
        return [], None, None, None, "select geometry and an explicit mirror line or sketch axis"

    if not source:
        return [], None, None, None, "select at least one geometry element to mirror"
    return source, reference_geoid, reference_pos, axis, None


def selection_object_name(entry):
    name = getattr(entry, "ObjectName", None)
    if name is not None:
        return name
    obj = getattr(entry, "Object", None)
    return getattr(obj, "Name", None)


def _notify(text: str, error: bool = False) -> None:
    notify("Mirror", text, error=error)


def _format_report(
    mirrored_count, linked_pairs, attached_pairs, dropped, added, skipped, removed, unmatched
):
    parts = ["mirrored {} element{}".format(mirrored_count, "" if mirrored_count == 1 else "s")]
    if attached_pairs:
        parts.append(
            "reattached {} to border{}".format(attached_pairs, "" if attached_pairs == 1 else "s")
        )
    if linked_pairs or not attached_pairs:
        parts.append(
            "linked {} pair{} symmetrically".format(linked_pairs, "" if linked_pairs == 1 else "s")
        )
    parts.append(
        "copied {} boundary constraint{}".format(len(added), "" if len(added) == 1 else "s")
    )
    if dropped:
        parts.append("{} link(s) not added".format(len(dropped)))
    if skipped:
        parts.append("skipped {}".format(len(skipped)))
    if removed:
        parts.append("removed {} redundant".format(len(removed)))
    if unmatched:
        parts.append(
            "{} unmapped element{}".format(len(unmatched), "" if len(unmatched) == 1 else "s")
        )
    summary = "; ".join(parts) + "."
    detail = []
    for item in dropped:
        detail.append("  geometry {} link not added: {}".format(item["mirror"], item["reason"]))
    for item in skipped:
        detail.append("  skipped {} #{}: {}".format(item["type"], item["index"], item["reason"]))
    for item in removed:
        detail.append("  removed {}: {}".format(item["type"], item["reason"]))
    return summary, detail


def _geometry_kind(geo):
    """Coarse classification of a Part geometry, tolerant of test fakes."""
    type_id = str(getattr(geo, "TypeId", "") or getattr(type(geo), "__name__", "") or "")
    if "Arc" in type_id:
        return "arc"
    if "Circle" in type_id or "Ellipse" in type_id:
        return "circle"
    if "LineSegment" in type_id:
        return "line"
    if hasattr(geo, "StartPoint") and hasattr(geo, "EndPoint") and not hasattr(geo, "Radius"):
        return "line"
    if hasattr(geo, "Radius") or hasattr(geo, "Center"):
        return "circle"
    return "other"


#: Sketches whose internal faces have already been rebuilt, keyed by name, with
#: the shape signature they were built from. Recomputing the decomposition when
#: nothing about the shape changed was the single most expensive thing this
#: add-on did: the observer below fires on every solve, and a solve happens on
#: every frame of a drag.
_internal_face_signatures = {}

#: Set False to stop rebuilding internal faces altogether. The feature exists so
#: multi-region sketches are selectable and padable; it is not worth paying for
#: on a sketch that has no interior edges.
REPAIR_INTERNAL_FACES = True


def _shape_signature(shape):
    """A cheap value that changes whenever the decomposition would.

    Edge and wire counts plus the bounding box catch every edit that can alter
    which regions exist, without touching OpenCASCADE booleans to find out.
    """
    try:
        box = shape.BoundBox
        return (
            len(shape.Edges),
            len(shape.Wires),
            round(box.XMin, 6),
            round(box.YMin, 6),
            round(box.XMax, 6),
            round(box.YMax, 6),
        )
    except Exception:
        return None


def _face_centre(face):
    """Where a region sits, from whichever measure the face can provide."""
    centre = getattr(face, "CenterOfMass", None)
    if centre is None:
        box = getattr(face, "BoundBox", None)
        centre = getattr(box, "Center", None) if box is not None else None
    if centre is None:
        return None
    try:
        return float(centre.x), float(centre.y)
    except (AttributeError, TypeError, ValueError):
        return None


def internal_face_order_key(face):
    """Where a region belongs in the compound handed to PartDesign.

    A Pad whose Profile names ``InternalFace2`` is naming an index into this
    list, so the order is what decides whether that reference still means the
    same region after the sketch is edited. OpenCASCADE returns the slices in
    whatever order the boolean produced them, which reshuffles on almost any
    change -- which is how a Pad built on a region came to report "Sub shape
    not found" after an unrelated trim, taking the chamfer and the sketch
    attached to its face down with it.

    Ordering by where a region *is* keeps the index attached to the region:
    moving a dimension shifts a centroid a little and the sequence survives.
    It cannot survive adding a region that sorts ahead of an existing one --
    only a real element map could -- but that is a deliberate edit, not the
    incidental churn that was breaking models.

    Area breaks a tie between concentric regions, largest first, so the outer
    one keeps the lower index.
    """
    centre = _face_centre(face)
    try:
        area = float(getattr(face, "Area", 0.0) or 0.0)
    except (TypeError, ValueError):
        area = 0.0
    if centre is None:
        # Nothing to place it by. Sort these last, together, rather than
        # letting an unmeasurable face displace the ones that can be placed.
        return (1, 0.0, 0.0, 0.0)
    return (0, round(centre[0], 4), round(centre[1], 4), -round(area, 4))


def clear_internal_face_cache(sketch=None):
    """Forget what was last built, for one sketch or all of them."""
    if sketch is None:
        _internal_face_signatures.clear()
        return
    _internal_face_signatures.pop(getattr(sketch, "Name", None), None)


def repair_sketch_internal_faces(sketch, force=False):
    """Ensure sketch.InternalShape contains all planar faces divided by internal edges.

    FreeCAD's native MakeInternals (WireJoiner.cpp) drops interior faces that share
    boundary edges with neighboring regions. This helper computes the complete planar
    face decomposition using FreeCAD's BOPTools.SplitAPI.slice() and assigns the
    compound of all resulting faces back to sketch.InternalShape so every enclosed
    region is selectable and padable in PartDesign.

    The faces are ordered by position rather than by the order the boolean
    produced them, because a feature built on one of them refers to it by
    index. See `internal_face_order_key`.

    The work is a full OpenCASCADE boolean per closed wire, so it is skipped
    unless the shape has actually changed since the last rebuild. Pass
    ``force=True`` to rebuild regardless.
    """
    if not REPAIR_INTERNAL_FACES and not force:
        return

    shape = getattr(sketch, "Shape", None)
    if shape is None or not hasattr(shape, "Wires") or not hasattr(shape, "Edges"):
        return

    name = getattr(sketch, "Name", None)
    signature = _shape_signature(shape)
    if not force and name and signature is not None:
        if _internal_face_signatures.get(name) == signature:
            return

    try:
        import BOPTools.SplitAPI
        import Part
    except ImportError:
        return

    closed_wires = [w for w in shape.Wires if hasattr(w, "isClosed") and w.isClosed()]
    if not closed_wires:
        if name and signature is not None:
            _internal_face_signatures[name] = signature
        return

    # Membership by identity hash rather than a scan: the previous form compared
    # every edge against every closed-wire edge with isSame(), which is O(n^2)
    # OpenCASCADE calls on a hot path.
    closed_wire_edges = {}
    for w in closed_wires:
        for edge in getattr(w, "Edges", []):
            closed_wire_edges[_edge_key(edge)] = edge

    interior_edges = [e for e in shape.Edges if _edge_key(e) not in closed_wire_edges]
    if not interior_edges:
        if name and signature is not None:
            _internal_face_signatures[name] = signature
        return

    if getattr(sketch, "MakeInternals", False) is False and hasattr(sketch, "MakeInternals"):
        try:
            sketch.MakeInternals = True
        except Exception:
            pass

    all_sliced_faces = []
    for w in closed_wires:
        try:
            face = Part.Face(w)
            split_result = BOPTools.SplitAPI.slice(face, interior_edges, "Split")
            all_sliced_faces.extend(getattr(split_result, "Faces", []))
        except Exception:
            pass

    # The index into this list is what a Pad's Profile records, so the order
    # has to come from the geometry rather than from the boolean.
    all_sliced_faces.sort(key=internal_face_order_key)

    if all_sliced_faces:
        try:
            sketch.InternalShape = Part.Compound(all_sliced_faces)
        except Exception:
            pass
    if name and signature is not None:
        _internal_face_signatures[name] = signature


def _edge_key(edge):
    """Identify an edge by its endpoints, cheaply and without OCC comparisons."""
    try:
        vertexes = edge.Vertexes
        points = sorted((round(v.X, 7), round(v.Y, 7), round(v.Z, 7)) for v in vertexes)
        return (round(edge.Length, 7), tuple(points))
    except Exception:
        return id(edge)


def plan_symmetry_links(mapping, before_geometry, reference_geoid):
    """One ``Symmetric`` constraint per shared named point of each mirrored pair.

    This is the live link the user expects from a mirror: drag either element and
    the other follows, reflected across the same line the mirror used. FreeCAD
    1.1.3's ``addSymmetric`` creates none of them, so the command adds them.

    Nothing is added that the point links already imply. A mirrored line is
    fully determined by its two endpoints, and a mirrored arc by its centre and
    endpoints; only a circle, linked by its centre alone, still needs ``Equal``
    to carry its radius across.

    Each spec carries ``_mirror`` (the mirrored geoid) so the caller can tell
    which pairs ended up coupled.
    """
    specs = []
    for source_id, mirror_id in sorted(mapping.items()):
        if not (0 <= source_id < len(before_geometry)):
            continue
        geo = before_geometry[source_id]
        points = sorted(geometry_endpoints(geo))
        for pos in points:
            specs.append(
                {
                    "type": "Symmetric",
                    "first": source_id,
                    "first_pos": pos,
                    "second": mirror_id,
                    "second_pos": pos,
                    "third": reference_geoid,
                    "reason": "live symmetry link across the mirror line",
                    "driving": True,
                    "active": True,
                    "_mirror": mirror_id,
                }
            )
        # Only where the point links leave the size free. A circle is linked
        # by its centre alone, so its radius still is; an arc is linked by its
        # centre *and* both endpoints, which already fix the radius. Adding
        # Equal there made every mirrored arc report a redundant constraint,
        # and the constraint the solver named was rarely the one to delete --
        # so removing it took a real constraint with it.
        if _geometry_kind(geo) in ("circle", "arc") and len(points) < 2:
            specs.append(
                {
                    "type": "Equal",
                    "first": source_id,
                    "first_pos": _POS_NONE,
                    "second": mirror_id,
                    "second_pos": _POS_NONE,
                    "reason": "keep the mirrored curve the same size as its source",
                    "driving": True,
                    "active": True,
                    "_mirror": mirror_id,
                }
            )
    return specs


def mirror_sketch_geometry(sketch, source_indices, reference_geoid, reference_pos, axis):
    """Synchronously mirror selected geometry and copy compatible constraints.

    This FreeCAD-API core is independent of GUI edit state and selection, which
    also makes it suitable for headless integration validation.
    """
    axis_a, axis_b = axis
    before_geometry = _geometry_list(sketch)
    before_count = len(before_geometry)
    records = [
        constraint_record(constraint, index)
        for index, constraint in enumerate(getattr(sketch, "Constraints", []) or [])
    ]

    new_ids = sketch.addSymmetric(source_indices, reference_geoid, reference_pos)
    after_geometry = _geometry_list(sketch)
    mirrored_count = len(after_geometry) - before_count
    if mirrored_count <= 0:
        raise RuntimeError("FreeCAD did not create mirrored geometry")

    try:
        new_ids = [int(value) for value in new_ids]
    except TypeError:
        new_ids = []
    if len(new_ids) == len(source_indices):
        mapping = dict(zip(source_indices, new_ids, strict=True))
        unmatched = []
    else:
        mapping, unmatched = build_geometry_mapping(
            before_geometry, after_geometry, source_indices, axis_a, axis_b
        )

    # 1. Live symmetry links between each mirrored element and its source.
    #    This is the Fusion 360 paradigm: moving the source dynamically moves
    #    the mirror, and the mirror receives no independent driving dimensions.
    link_specs = plan_symmetry_links(mapping, before_geometry, reference_geoid)
    mirrored_targets = {spec["_mirror"] for spec in link_specs}

    # addSymmetric auto-duplicates single-element orientation constraints
    # (Vertical, Horizontal, Block) onto the mirrored copy. When both endpoints
    # receive a Symmetric point link across the mirror axis, that auto-copied
    # orientation constraint is redundant and over-constrains FreeCAD's PlanGCS
    # solver. Remove them prior to adding symmetry links.
    auto_copied_indices = []
    for i, c in enumerate(getattr(sketch, "Constraints", []) or []):
        if (
            getattr(c, "First", None) in mirrored_targets
            and getattr(c, "Second", -2000) in (-2000, -1, -2)
            and getattr(c, "Type", "") in ("Vertical", "Horizontal", "Block")
        ):
            auto_copied_indices.append(i)
    for idx in sorted(auto_copied_indices, reverse=True):
        try:
            sketch.delConstraint(idx)
        except Exception:
            pass
    _recompute(sketch)

    linked, link_dropped = apply_symmetry_links(sketch, link_specs)
    _recompute(sketch)

    linked_mirror_ids = {spec["_mirror"] for spec in linked}
    linked_endpoints = {
        (spec["second"], spec["second_pos"]) for spec in linked if spec.get("type") == "Symmetric"
    }

    # 2. Boundary endpoint attachments (PointOnObject / Coincident).
    #    If an endpoint is already constrained by an active Symmetric link,
    #    it tracks its source symmetrically and does not need duplicate border
    #    attachments. For any endpoint without an active symmetry link, copy
    #    the boundary constraint.
    copies, skipped = plan_constraint_copies(
        records, set(source_indices), mapping, before_geometry, axis_a, axis_b
    )
    effective_copies = [
        spec
        for spec in copies
        if (spec.get("first"), spec.get("first_pos")) not in linked_endpoints
    ]
    added, removed = apply_constraint_copies(sketch, effective_copies)
    _recompute(sketch)

    # 3. Ensure all closed planar regions (including middle divider cells)
    #    are populated in sketch.InternalShape so every face can be padded.
    repair_sketch_internal_faces(sketch)

    attached_mirror_ids = {
        spec["first"] for spec in added if spec["first"] not in linked_mirror_ids
    }
    return {
        "mirrored": mirrored_count,
        "linked": linked,
        "link_dropped": link_dropped,
        "linked_pairs": len(linked_mirror_ids),
        "attached_pairs": len(attached_mirror_ids),
        "copied": added,
        "skipped": skipped,
        "removed": removed,
        "unmatched": unmatched,
        "mapping": mapping,
    }


def _report_unclosed(result, gaps_after, gaps_before):
    """Explain a refusal, naming what could not be carried across the mirror."""
    blockers = [entry for entry in result.get("skipped", []) if _blocks_closure(entry)]
    _notify(
        "did not mirror: the result would leave {} open end(s) in the profile, "
        "so nothing was changed.".format(len(gaps_after) - gaps_before),
        error=True,
    )
    if blockers:
        App.Console.PrintMessage("  joins that could not be carried across the mirror line:\n")
        for entry in blockers:
            App.Console.PrintMessage("    {}\n".format(_describe_skip(entry)))
        App.Console.PrintMessage(
            "  Mirror with FreeCAD's own Mirror and add those by hand, or move the\n"
            "  geometry so the join does not sit on the mirror line.\n"
        )
    for point, owners in gaps_after[:6]:
        App.Console.PrintMessage(
            "  open end near ({:.3f}, {:.3f}), edge(s) {}\n".format(
                point[0], point[1], ", ".join(str(owner) for owner in owners)
            )
        )
    return {
        "status": "unclosed",
        "open_ends": len(gaps_after),
        "open_ends_before": gaps_before,
        "blockers": blockers,
        **result,
    }


def _blocks_closure(entry):
    """Whether a skipped constraint is one that held the profile together."""
    ctype = entry[1] if len(entry) > 1 else ""
    return str(ctype) in {"Tangent", "Coincident", "PointOnObject", "Symmetric"}


def _describe_skip(entry):
    index = entry[0] if entry else "?"
    ctype = entry[1] if len(entry) > 1 else "?"
    reason = entry[2] if len(entry) > 2 else ""
    return "{} #{}: {}".format(ctype, index, reason)


def mirror_with_constraints():
    """Mirror synchronously, then copy constraints left on the boundary.

    Returns a result dict for tests; the interactive command shows it non-modally.
    """
    sketch = active_sketch()
    if sketch is None:
        _notify("start editing a sketch first.", error=True)
        return {"status": "no-sketch"}

    source_indices, reference_geoid, reference_pos, axis, selection_error = (
        selected_source_geometry(sketch)
    )
    if selection_error:
        _notify(selection_error + ".", error=True)
        return {"status": "no-selection"}
    document = getattr(App, "ActiveDocument", None)
    # Only joins on the mirror line count against this command: those are the
    # ones it is answerable for. Gaps the sketch already had, and open chains
    # away from the axis, are not its doing.
    axis_a, axis_b = axis
    gaps_before = len(boundary_open_ends(sketch, axis_a, axis_b))
    _open_transaction(document, "Mirror with Constraints")
    try:
        result = mirror_sketch_geometry(
            sketch, source_indices, reference_geoid, reference_pos, axis
        )
        gaps_after = boundary_open_ends(sketch, axis_a, axis_b)
        if len(gaps_after) > gaps_before:
            # Refuse rather than half-finish. A mirror that drops the joins
            # holding the two halves together leaves a profile that cannot
            # become a face, and reporting success on that sends the user off
            # to debug a pad that was never going to work.
            _abort_transaction(document)
            return _report_unclosed(result, gaps_after, gaps_before)
        _commit_transaction(document)
    except Exception as error:
        _abort_transaction(document)
        _notify("failed and was rolled back: {}".format(error), error=True)
        return {"status": "error", "error": str(error)}

    summary, detail = _format_report(
        result["mirrored"],
        result["linked_pairs"],
        result["attached_pairs"],
        result["link_dropped"],
        result["copied"],
        result["skipped"],
        result["removed"],
        result["unmatched"],
    )
    _notify(summary)
    for line in detail:
        App.Console.PrintMessage(line + "\n")
    return {
        "status": "ok",
        **result,
        "summary": summary,
    }


def _open_transaction(document, label):
    if document is not None and hasattr(document, "openTransaction"):
        document.openTransaction(label)


def _commit_transaction(document):
    if document is not None and hasattr(document, "commitTransaction"):
        document.commitTransaction()


def _abort_transaction(document):
    if document is not None and hasattr(document, "abortTransaction"):
        document.abortTransaction()


# ---------------------------------------------------------------------------
# Midline & Symmetry Axis tools
# ---------------------------------------------------------------------------


def _add_line(sketch, start_pt, end_pt, construction=False):
    """Add a LineSegment between start_pt and end_pt to sketch."""
    import Part

    sx, sy = float(start_pt[0]), float(start_pt[1])
    ex, ey = float(end_pt[0]), float(end_pt[1])
    line_seg = Part.LineSegment(App.Vector(sx, sy, 0.0), App.Vector(ex, ey, 0.0))
    try:
        geo_id = sketch.addGeometry(line_seg, construction)
    except TypeError:
        geo_id = sketch.addGeometry(line_seg)
    if construction:
        setter = getattr(sketch, "setConstruction", None)
        if callable(setter):
            try:
                setter(geo_id, True)
            except Exception:
                pass
    return geo_id


def _add_arc(sketch, center, start_pt, end_pt, construction=False):
    """Add an ArcOfCircle centered at center passing from start_pt to end_pt."""
    import math

    import Part

    cx, cy = float(center[0]), float(center[1])
    sx, sy = float(start_pt[0]), float(start_pt[1])
    ex, ey = float(end_pt[0]), float(end_pt[1])
    radius = math_hypot(sx - cx, sy - cy)
    a_start = math.atan2(sy - cy, sx - cx)
    a_end = math.atan2(ey - cy, ex - cx)
    try:
        circle = Part.Circle(App.Vector(cx, cy, 0.0), App.Vector(0.0, 0.0, 1.0), radius)
        arc = Part.ArcOfCircle(circle, a_start, a_end)
    except Exception:
        mid_angle = a_start + (a_end - a_start) / 2.0
        if a_end < a_start:
            mid_angle += math.pi
        mx = cx + radius * math.cos(mid_angle)
        my = cy + radius * math.sin(mid_angle)
        arc = Part.ArcOfCircle(
            App.Vector(sx, sy, 0.0), App.Vector(mx, my, 0.0), App.Vector(ex, ey, 0.0)
        )
    try:
        geo_id = sketch.addGeometry(arc, construction)
    except TypeError:
        geo_id = sketch.addGeometry(arc)
    if construction:
        setter = getattr(sketch, "setConstruction", None)
        if callable(setter):
            try:
                setter(geo_id, True)
            except Exception:
                pass
    return geo_id


def _add_construction_line(sketch, start_pt, end_pt):
    """Add a construction LineSegment between start_pt and end_pt to sketch."""
    return _add_line(sketch, start_pt, end_pt, construction=True)


def _safe_add_constraint(sketch, constraint):
    """Add a constraint to sketch, but back it out if it over-constrains or conflicts."""
    before_conflicts = _flagged_indices(sketch, _CONFLICTING_ATTRS)
    before_redundant = _flagged_indices(sketch, _FULLY_REDUNDANT_ATTRS)
    try:
        idx = sketch.addConstraint(constraint)
    except Exception:
        return False
    if not isinstance(idx, int):
        idx = len(list(getattr(sketch, "Constraints", []) or [])) - 1
    _recompute(sketch)
    new_conflicts = _flagged_indices(sketch, _CONFLICTING_ATTRS) - before_conflicts
    new_redundant = _flagged_indices(sketch, _FULLY_REDUNDANT_ATTRS) - before_redundant
    if new_conflicts or new_redundant:
        _drop_constraint(sketch, idx)
        return False
    return True


def selected_midline_references(sketch):
    """Identify geometry references for midline / symmetry axis generation.

    Returns:
        (kind, data, error)
        - ("points", [p1, p2], None) where each p is dict(geoid=..., posid=..., point=(x, y))
        - ("lines", [geo1, geo2], None)
        - ("line", geo, None)
        - (None, None, error_message)
    """
    selection = []
    getter = getattr(Gui.Selection, "getSelectionEx", None)
    if callable(getter):
        try:
            selection = getter() or []
        except Exception:
            selection = []

    selected_edges = []
    selected_points = []

    for entry in selection:
        if getattr(entry, "Object", None) is not sketch and selection_object_name(entry) != getattr(
            sketch, "Name", None
        ):
            continue
        for sub in getattr(entry, "SubElementNames", []) or []:
            if sub.startswith("Edge"):
                try:
                    geoid = int(sub[4:]) - 1
                except ValueError:
                    continue
                if geoid not in selected_edges:
                    selected_edges.append(geoid)
            elif sub.startswith("Vertex"):
                try:
                    v_idx = int(sub[6:]) - 1
                except ValueError:
                    continue
                geoid, posid = -2000, 0
                resolver = getattr(sketch, "getGeoVertexIndex", None)
                if callable(resolver):
                    try:
                        geoid, posid = resolver(v_idx)
                    except Exception:
                        geoid, posid = -2000, 0

                pt = None
                if geoid >= 0 and posid > 0:
                    pt_getter = getattr(sketch, "getPoint", None)
                    if callable(pt_getter):
                        try:
                            vec = pt_getter(geoid, posid)
                            pt = (float(vec.x), float(vec.y))
                        except Exception:
                            pt = None
                    if pt is None and 0 <= geoid < len(_geometry_list(sketch)):
                        pt = geometry_point(_geometry_list(sketch)[geoid], posid)
                else:
                    shape = getattr(sketch, "Shape", None)
                    vertexes = getattr(shape, "Vertexes", []) or []
                    if 0 <= v_idx < len(vertexes):
                        v_point = vertexes[v_idx].Point
                        pt = (float(v_point.x), float(v_point.y))
                        for g_i, g in enumerate(_geometry_list(sketch)):
                            pts = geometry_endpoints(g)
                            for p_pos, p_coords in pts.items():
                                if points_equal(pt, p_coords):
                                    geoid, posid = g_i, p_pos
                                    break
                            if geoid >= 0:
                                break

                if pt is not None and geoid >= 0 and posid > 0:
                    already_selected = any(
                        p["geoid"] == geoid and p["posid"] == posid for p in selected_points
                    )
                    if not already_selected:
                        selected_points.append({"geoid": geoid, "posid": posid, "point": pt})
            elif sub == "RootPoint":
                if not any(p["geoid"] == -1 and p["posid"] == 1 for p in selected_points):
                    selected_points.append({"geoid": -1, "posid": 1, "point": (0.0, 0.0)})

    geos = _geometry_list(sketch)

    # Circle/Arc center point support when 2 curves are selected
    if len(selected_edges) == 2 and not selected_points:
        if 0 <= selected_edges[0] < len(geos) and 0 <= selected_edges[1] < len(geos):
            g1, g2 = geos[selected_edges[0]], geos[selected_edges[1]]
            if _geometry_kind(g1) in ("circle", "arc") and _geometry_kind(g2) in ("circle", "arc"):
                c1 = geometry_point(g1, _POS_CENTER)
                c2 = geometry_point(g2, _POS_CENTER)
                if c1 is not None and c2 is not None:
                    selected_points = [
                        {"geoid": selected_edges[0], "posid": _POS_CENTER, "point": c1},
                        {"geoid": selected_edges[1], "posid": _POS_CENTER, "point": c2},
                    ]
                    selected_edges = []

    # 1. Two points
    if len(selected_points) == 2 and len(selected_edges) <= 1:
        if points_equal(selected_points[0]["point"], selected_points[1]["point"]):
            return None, None, "the two selected points are coincident"
        return "points", selected_points, None

    # 2. Two lines
    if len(selected_edges) == 2 and not selected_points:
        if 0 <= selected_edges[0] < len(geos) and 0 <= selected_edges[1] < len(geos):
            g1, g2 = geos[selected_edges[0]], geos[selected_edges[1]]
            if _geometry_kind(g1) == "line" and _geometry_kind(g2) == "line":
                return "lines", selected_edges, None
        return None, None, "select 2 lines or 2 points/centers"

    # 3. One line
    if len(selected_edges) == 1 and not selected_points:
        if 0 <= selected_edges[0] < len(geos) and _geometry_kind(geos[selected_edges[0]]) == "line":
            return "line", selected_edges[0], None
        return None, None, "select a line segment to create a perpendicular bisector"

    if not selected_edges and not selected_points:
        return None, None, "select 2 points, 2 lines, or 1 line first"

    return None, None, "select 2 points, 2 lines, or 1 line to create a midline or symmetry axis"


def create_midline_geometry(sketch, kind, data):
    """Construct a construction midline and apply symmetry constraints."""
    import Sketcher

    geos = _geometry_list(sketch)

    if kind == "points":
        p1, p2 = data
        x1, y1 = p1["point"]
        x2, y2 = p2["point"]
        mx, my = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        dx, dy = x2 - x1, y2 - y1
        dist = math_hypot(dx, dy)
        if dist <= TOLERANCE:
            raise ValueError("Selected points are coincident")
        nx, ny = -dy / dist, dx / dist
        span = max(dist * 1.5, 20.0)
        sx, sy = mx - (span / 2.0) * nx, my - (span / 2.0) * ny
        ex, ey = mx + (span / 2.0) * nx, my + (span / 2.0) * ny
        mid_id = _add_construction_line(sketch, (sx, sy), (ex, ey))
        c = Sketcher.Constraint(
            "Symmetric", p1["geoid"], p1["posid"], p2["geoid"], p2["posid"], mid_id
        )
        _safe_add_constraint(sketch, c)
        _recompute(sketch)
        return {"midline": mid_id, "kind": "points"}

    elif kind == "line":
        geoid = data
        g = geos[geoid]
        p1 = geometry_point(g, _POS_START)
        p2 = geometry_point(g, _POS_END)
        if p1 is None or p2 is None:
            raise ValueError("Could not read line endpoints")
        mx, my = (p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0
        dx, dy = p2[0] - p1[0], p2[1] - p1[1]
        dist = math_hypot(dx, dy)
        if dist <= TOLERANCE:
            raise ValueError("Line length is zero")
        nx, ny = -dy / dist, dx / dist
        span = max(dist * 1.5, 20.0)
        sx, sy = mx - (span / 2.0) * nx, my - (span / 2.0) * ny
        ex, ey = mx + (span / 2.0) * nx, my + (span / 2.0) * ny
        mid_id = _add_construction_line(sketch, (sx, sy), (ex, ey))
        c = Sketcher.Constraint("Symmetric", geoid, _POS_START, geoid, _POS_END, mid_id)
        _safe_add_constraint(sketch, c)
        _recompute(sketch)
        return {"midline": mid_id, "kind": "line"}

    elif kind == "lines":
        geo1, geo2 = data
        g1, g2 = geos[geo1], geos[geo2]
        a1 = geometry_point(g1, _POS_START)
        b1 = geometry_point(g1, _POS_END)
        a2 = geometry_point(g2, _POS_START)
        b2 = geometry_point(g2, _POS_END)
        if any(pt is None for pt in (a1, b1, a2, b2)):
            raise ValueError("Could not read lines endpoints")

        d_direct = math_hypot(a1[0] - a2[0], a1[1] - a2[1]) + math_hypot(
            b1[0] - b2[0], b1[1] - b2[1]
        )
        d_crossed = math_hypot(a1[0] - b2[0], a1[1] - b2[1]) + math_hypot(
            b1[0] - a2[0], b1[1] - a2[1]
        )

        if d_crossed < d_direct:
            p2a, pos2a = b2, _POS_END
            p2b, pos2b = a2, _POS_START
        else:
            p2a, pos2a = a2, _POS_START
            p2b, pos2b = b2, _POS_END

        ma = ((a1[0] + p2a[0]) / 2.0, (a1[1] + p2a[1]) / 2.0)
        mb = ((b1[0] + p2b[0]) / 2.0, (b1[1] + p2b[1]) / 2.0)

        dist_m = math_hypot(mb[0] - ma[0], mb[1] - ma[1])
        if dist_m <= TOLERANCE:
            v1x, v1y = b1[0] - a1[0], b1[1] - a1[1]
            v2x, v2y = p2b[0] - p2a[0], p2b[1] - p2a[1]
            l1, l2 = math_hypot(v1x, v1y), math_hypot(v2x, v2y)
            u1x, u1y = (v1x / l1, v1y / l1) if l1 > TOLERANCE else (1.0, 0.0)
            u2x, u2y = (v2x / l2, v2y / l2) if l2 > TOLERANCE else (1.0, 0.0)
            bx, by = u1x + u2x, u1y + u2y
            lb = math_hypot(bx, by)
            if lb <= TOLERANCE:
                bx, by = -u1y, u1x
                lb = math_hypot(bx, by)
            ubx, uby = bx / lb, by / lb
            span = max(l1, l2, 20.0)
            ma = (a1[0] - (span / 2.0) * ubx, a1[1] - (span / 2.0) * uby)
            mb = (a1[0] + (span / 2.0) * ubx, a1[1] + (span / 2.0) * uby)

        mid_id = _add_construction_line(sketch, ma, mb)

        # Apply primary symmetric link
        c1 = Sketcher.Constraint("Symmetric", geo1, _POS_START, geo2, pos2a, mid_id)
        _safe_add_constraint(sketch, c1)

        # Apply secondary symmetric link (or parallel if secondary is redundant)
        c2 = Sketcher.Constraint("Symmetric", geo1, _POS_END, geo2, pos2b, mid_id)
        if not _safe_add_constraint(sketch, c2):
            c_par = Sketcher.Constraint("Parallel", mid_id, geo1)
            _safe_add_constraint(sketch, c_par)

        # Attach endpoints to any crossing boundary edges if coincident (e.g. in a box/rectangle)
        for e_idx, e_geo in enumerate(geos):
            if e_idx in (geo1, geo2, mid_id):
                continue
            e_start = geometry_point(e_geo, _POS_START)
            e_end = geometry_point(e_geo, _POS_END)
            if e_start is not None and e_end is not None:
                if distance_point_to_segment(ma, e_start, e_end) <= TOLERANCE:
                    _safe_add_constraint(
                        sketch, Sketcher.Constraint("PointOnObject", mid_id, _POS_START, e_idx)
                    )
                if distance_point_to_segment(mb, e_start, e_end) <= TOLERANCE:
                    _safe_add_constraint(
                        sketch, Sketcher.Constraint("PointOnObject", mid_id, _POS_END, e_idx)
                    )

        _recompute(sketch)
        return {"midline": mid_id, "kind": "lines"}

    raise ValueError("Unsupported midline mode: {}".format(kind))


def add_midline():
    """Create a construction midline or symmetry axis from selection.

    Returns a result dict for tests; the interactive command notifies non-modally.
    """
    sketch = active_sketch()
    if sketch is None:
        _notify_midline("start editing a sketch first.", error=True)
        return {"status": "no-sketch"}

    kind, data, error = selected_midline_references(sketch)
    if error:
        _notify_midline(error + ".", error=True)
        return {"status": "no-selection", "error": error}

    document = getattr(App, "ActiveDocument", None)
    _open_transaction(document, "Add Midline")
    try:
        result = create_midline_geometry(sketch, kind, data)
        _commit_transaction(document)
    except Exception as exc:
        _abort_transaction(document)
        _notify_midline("failed and was rolled back: {}".format(exc), error=True)
        return {"status": "error", "error": str(exc)}

    msg = "created construction midline with symmetry constraint."
    _notify_midline(msg)
    return {"status": "ok", **result, "message": msg}


def _notify_midline(text: str, error: bool = False) -> None:
    notify("Midline", text, error=error)


# ---------------------------------------------------------------------------
# Command objects
# ---------------------------------------------------------------------------


class MirrorWithConstraintsCommand(SketcherCommand):
    """``FMF_MirrorWithConstraints`` ribbon command."""

    def GetResources(self):
        return {
            "Pixmap": "FMF_MirrorWithConstraints",
            "MenuText": "Mirror + Constraints",
            "ToolTip": (
                "Mirror like FreeCAD's Mirror, then add the constraints it leaves out: "
                "a live Symmetric link between each element and its copy so moving one "
                "moves the other, plus endpoint attachments to unchanged borders or "
                "axes. Select geometry, then a mirror line or sketch axis. Anything "
                "that cannot be reproduced safely is reported."
            ),
        }

    def Activated(self):
        mirror_with_constraints()


class AddMidlineCommand(SketcherCommand):
    """``FMF_AddMidline`` ribbon command."""

    def GetResources(self):
        return {
            "Pixmap": "FMF_AddMidline",
            "MenuText": "Midline",
            "ToolTip": (
                "Create a construction midline / symmetry axis from selected geometry:\n"
                "- 2 Points: perpendicular bisector symmetry axis between the points.\n"
                "- 2 Lines: centerline axis equidistant and parallel between them.\n"
                "- 1 Line: perpendicular bisector symmetry axis across line endpoints."
            ),
        }

    def Activated(self):
        add_midline()


def selected_midpoint_references(sketch):
    """Identify target geometry for a midpoint constraint.

    Supported patterns:
    - 1 Point + 1 Line: locks the point to the center of the line.
    - 3 Points: locks the middle point to the midpoint between the outer two.
    - 1 Line: creates a construction midpoint vertex on the line.
    - 2 Points: creates a construction midpoint vertex between the two points.
    """
    selected_edges = []
    selected_points = []
    pt_getter = getattr(sketch, "getPoint", None)

    selection = []
    getter = getattr(Gui.Selection, "getSelectionEx", None)
    if callable(getter):
        try:
            selection = getter() or []
        except Exception:
            selection = []

    for entry in selection:
        if getattr(entry, "Object", None) is not sketch and selection_object_name(entry) != getattr(
            sketch, "Name", None
        ):
            continue
        for sub in getattr(entry, "SubElementNames", []) or []:
            if sub.startswith("Edge") and sub[4:].isdigit():
                idx = int(sub[4:]) - 1
                if idx not in selected_edges:
                    selected_edges.append(idx)
            elif sub.startswith("Vertex") and sub[6:].isdigit():
                v_idx = int(sub[6:]) - 1
                geoid, posid, pt = -1, 0, None
                if callable(pt_getter):
                    mapper = getattr(sketch, "getGeoVertexIndex", None)
                    if callable(mapper):
                        try:
                            geoid, posid = mapper(v_idx)
                            vec = pt_getter(geoid, posid)
                            pt = (float(vec.x), float(vec.y))
                        except Exception:
                            pt = None
                    if pt is None and 0 <= geoid < len(_geometry_list(sketch)):
                        pt = geometry_point(_geometry_list(sketch)[geoid], posid)
                else:
                    shape = getattr(sketch, "Shape", None)
                    vertexes = getattr(shape, "Vertexes", []) or []
                    if 0 <= v_idx < len(vertexes):
                        v_point = vertexes[v_idx].Point
                        pt = (float(v_point.x), float(v_point.y))
                        for g_i, g in enumerate(_geometry_list(sketch)):
                            pts = geometry_endpoints(g)
                            for p_pos, p_coords in pts.items():
                                if points_equal(pt, p_coords):
                                    geoid, posid = g_i, p_pos
                                    break
                            if geoid >= 0:
                                break

                if pt is not None and geoid >= 0 and posid > 0:
                    already = any(
                        p["geoid"] == geoid and p["posid"] == posid for p in selected_points
                    )
                    if not already:
                        selected_points.append({"geoid": geoid, "posid": posid, "point": pt})
            elif sub == "RootPoint":
                if not any(p["geoid"] == -1 and p["posid"] == 1 for p in selected_points):
                    selected_points.append({"geoid": -1, "posid": 1, "point": (0.0, 0.0)})

    geos = _geometry_list(sketch)

    # 1. One point + One line
    if len(selected_points) == 1 and len(selected_edges) == 1:
        if 0 <= selected_edges[0] < len(geos):
            g = geos[selected_edges[0]]
            if _geometry_kind(g) == "line":
                return "point-line", (selected_points[0], selected_edges[0]), None
        return None, None, "select a line segment and a point to constrain to midpoint"

    # 2. Three points
    if len(selected_points) == 3 and not selected_edges:
        return "3-points", selected_points, None

    # 3. One line (no points) -> create construction midpoint vertex
    if len(selected_edges) == 1 and not selected_points:
        if 0 <= selected_edges[0] < len(geos) and _geometry_kind(geos[selected_edges[0]]) == "line":
            return "line", selected_edges[0], None
        return None, None, "select a line segment to create a midpoint point"

    # 4. Two points -> create construction midpoint vertex
    if len(selected_points) == 2 and not selected_edges:
        return "2-points", selected_points, None

    if not selected_edges and not selected_points:
        return None, None, "select 1 point and 1 line, 3 points, or 1 line first"

    return None, None, "select 1 point and 1 line, 3 points, or 1 line to constrain to midpoint"


def apply_midpoint_constraint(sketch, kind, data):
    """Apply a parametric midpoint constraint to the sketch."""
    import Part
    import Sketcher

    geos = _geometry_list(sketch)

    if kind == "point-line":
        pt, line_idx = data
        c = Sketcher.Constraint(
            "Symmetric", line_idx, _POS_START, line_idx, _POS_END, pt["geoid"], pt["posid"]
        )
        added = _safe_add_constraint(sketch, c)
        if not added:
            raise ValueError(
                "Midpoint constraint conflicts or is redundant with existing constraints"
            )
        _recompute(sketch)
        return {"kind": "point-line"}

    elif kind == "3-points":
        pts = data
        coords = [p["point"] for p in pts]
        d01 = math_hypot(coords[0][0] - coords[1][0], coords[0][1] - coords[1][1])
        d12 = math_hypot(coords[1][0] - coords[2][0], coords[1][1] - coords[2][1])
        d02 = math_hypot(coords[0][0] - coords[2][0], coords[0][1] - coords[2][1])
        if d01 >= d12 and d01 >= d02:
            p_out1, p_out2, p_mid = pts[0], pts[1], pts[2]
        elif d02 >= d01 and d02 >= d12:
            p_out1, p_out2, p_mid = pts[0], pts[2], pts[1]
        else:
            p_out1, p_out2, p_mid = pts[1], pts[2], pts[0]

        c = Sketcher.Constraint(
            "Symmetric",
            p_out1["geoid"],
            p_out1["posid"],
            p_out2["geoid"],
            p_out2["posid"],
            p_mid["geoid"],
            p_mid["posid"],
        )
        added = _safe_add_constraint(sketch, c)
        if not added:
            raise ValueError(
                "Midpoint constraint conflicts or is redundant with existing constraints"
            )
        _recompute(sketch)
        return {"kind": "3-points"}

    elif kind == "line":
        line_idx = data
        g = geos[line_idx]
        p1 = geometry_point(g, _POS_START)
        p2 = geometry_point(g, _POS_END)
        if p1 is None or p2 is None:
            raise ValueError("Could not determine line endpoints")
        mx, my = (p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0
        pt_geo = Part.Point(App.Vector(mx, my, 0.0))
        pt_id = sketch.addGeometry(pt_geo, True)
        set_const = getattr(sketch, "setConstruction", None)
        if callable(set_const):
            try:
                set_const(pt_id, True)
            except Exception:
                pass
        c = Sketcher.Constraint("Symmetric", line_idx, _POS_START, line_idx, _POS_END, pt_id, 1)
        _safe_add_constraint(sketch, c)
        _recompute(sketch)
        return {"kind": "line", "point": pt_id}

    elif kind == "2-points":
        p1, p2 = data
        x1, y1 = p1["point"]
        x2, y2 = p2["point"]
        mx, my = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        pt_geo = Part.Point(App.Vector(mx, my, 0.0))
        pt_id = sketch.addGeometry(pt_geo, True)
        set_const = getattr(sketch, "setConstruction", None)
        if callable(set_const):
            try:
                set_const(pt_id, True)
            except Exception:
                pass
        c = Sketcher.Constraint(
            "Symmetric", p1["geoid"], p1["posid"], p2["geoid"], p2["posid"], pt_id, 1
        )
        _safe_add_constraint(sketch, c)
        _recompute(sketch)
        return {"kind": "2-points", "point": pt_id}

    raise ValueError("Unknown midpoint constraint kind: {}".format(kind))


def constrain_midpoint(sketch=None):
    """Transactionally constrain selected geometry to a midpoint."""
    sketch = sketch or active_sketch()
    if sketch is None:
        _notify_midpoint("Open a sketch in edit mode first.", error=True)
        return {"status": "no-sketch"}

    kind, data, error = selected_midpoint_references(sketch)
    if error is not None:
        _notify_midpoint(error, error=True)
        return {"status": "no-selection", "message": error}

    document = getattr(App, "ActiveDocument", None)
    _open_transaction(document, "Constrain Midpoint")

    try:
        result = apply_midpoint_constraint(sketch, kind, data)
        _commit_transaction(document)
        msg = "applied midpoint constraint."
        _notify_midpoint(msg)
        return {"status": "ok", **result, "message": msg}
    except Exception as exc:
        _abort_transaction(document)
        _notify_midpoint(str(exc), error=True)
        return {"status": "error", "message": str(exc)}


def _notify_midpoint(text: str, error: bool = False) -> None:
    notify("Midpoint", text, error=error)


class ConstrainMidpointCommand(SketcherCommand):
    """``FMF_ConstrainMidpoint`` ribbon command."""

    def GetResources(self):
        return {
            "Pixmap": "FMF_ConstrainMidpoint",
            "MenuText": "Midpoint",
            "ToolTip": (
                "Constrain a point to the midpoint of a line segment, or between two points.\n"
                "- 1 Point + 1 Line: locks the point to the center of the line.\n"
                "- 3 Points: locks the middle point to the midpoint of the outer two.\n"
                "- 1 Line: inserts a construction midpoint vertex on the line."
            ),
        }

    def Activated(self):
        constrain_midpoint()


# ---------------------------------------------------------------------------
# Smart Slot Generator
# ---------------------------------------------------------------------------


def create_smart_slot(sketch, p1, p2, radius=5.0):
    """Construct a fully-constrained, parametric Center-to-Center Slot."""
    import Sketcher

    x1, y1 = float(p1[0]), float(p1[1])
    x2, y2 = float(p2[0]), float(p2[1])
    dx, dy = x2 - x1, y2 - y1
    length = math_hypot(dx, dy)
    if length <= TOLERANCE:
        x2 = x1 + 40.0
        dx = 40.0
        length = 40.0

    ux, uy = dx / length, dy / length
    nx, ny = -uy, ux

    # 1. Central construction midline
    mid_id = _add_line(sketch, (x1, y1), (x2, y2), construction=True)

    # 2. Side line 1
    s1 = (x1 + radius * nx, y1 + radius * ny)
    e1 = (x2 + radius * nx, y2 + radius * ny)
    line1_id = _add_line(sketch, s1, e1, construction=False)

    # 3. Side line 2
    s2 = (x2 - radius * nx, y2 - radius * ny)
    e2 = (x1 - radius * nx, y1 - radius * ny)
    line2_id = _add_line(sketch, s2, e2, construction=False)

    # 4. Arc 1 at p2 (connecting e1 to s2)
    arc1_id = _add_arc(sketch, (x2, y2), e1, s2, construction=False)

    # 5. Arc 2 at p1 (connecting e2 to s1)
    arc2_id = _add_arc(sketch, (x1, y1), e2, s1, construction=False)

    # Coincident connections to form closed contour
    _safe_add_constraint(
        sketch, Sketcher.Constraint("Coincident", line1_id, _POS_END, arc1_id, _POS_START)
    )
    _safe_add_constraint(
        sketch, Sketcher.Constraint("Coincident", arc1_id, _POS_END, line2_id, _POS_START)
    )
    _safe_add_constraint(
        sketch, Sketcher.Constraint("Coincident", line2_id, _POS_END, arc2_id, _POS_START)
    )
    _safe_add_constraint(
        sketch, Sketcher.Constraint("Coincident", arc2_id, _POS_END, line1_id, _POS_START)
    )

    # Arc centers attached to midline endpoints
    _safe_add_constraint(
        sketch, Sketcher.Constraint("Coincident", arc1_id, _POS_CENTER, mid_id, _POS_END)
    )
    _safe_add_constraint(
        sketch, Sketcher.Constraint("Coincident", arc2_id, _POS_CENTER, mid_id, _POS_START)
    )

    # Tangents between lines and arcs
    _safe_add_constraint(sketch, Sketcher.Constraint("Tangent", line1_id, arc1_id))
    _safe_add_constraint(sketch, Sketcher.Constraint("Tangent", arc1_id, line2_id))
    _safe_add_constraint(sketch, Sketcher.Constraint("Tangent", line2_id, arc2_id))
    _safe_add_constraint(sketch, Sketcher.Constraint("Tangent", arc2_id, line1_id))

    # Parallel & Equal lengths
    _safe_add_constraint(sketch, Sketcher.Constraint("Parallel", line1_id, mid_id))
    _safe_add_constraint(sketch, Sketcher.Constraint("Equal", line1_id, line2_id))
    _safe_add_constraint(sketch, Sketcher.Constraint("Equal", arc1_id, arc2_id))

    # Symmetry
    _safe_add_constraint(
        sketch, Sketcher.Constraint("Symmetric", line1_id, _POS_START, line2_id, _POS_END, mid_id)
    )

    # Driving dimensions
    _safe_add_constraint(sketch, Sketcher.Constraint("Distance", mid_id, length))
    _safe_add_constraint(sketch, Sketcher.Constraint("Radius", arc1_id, radius))

    _recompute(sketch)
    return {
        "status": "ok",
        "midline": mid_id,
        "line1": line1_id,
        "line2": line2_id,
        "arc1": arc1_id,
        "arc2": arc2_id,
    }


def add_smart_slot(radius=5.0):
    """Create a parametric smart slot from active sketch selection or defaults."""
    sketch = active_sketch()
    if sketch is None:
        _notify_slot("start editing a sketch first.", error=True)
        return {"status": "no-sketch"}

    kind, data, _error = selected_midline_references(sketch)
    p1, p2 = (-20.0, 0.0), (20.0, 0.0)
    if kind == "points" and len(data) == 2:
        p1 = data[0]["point"]
        p2 = data[1]["point"]
    elif kind == "line":
        geos = _geometry_list(sketch)
        if 0 <= data < len(geos):
            g = geos[data]
            sp = geometry_point(g, _POS_START)
            ep = geometry_point(g, _POS_END)
            if sp and ep:
                p1, p2 = sp, ep

    document = getattr(App, "ActiveDocument", None)
    _open_transaction(document, "Create Smart Slot")
    try:
        result = create_smart_slot(sketch, p1, p2, radius=radius)
        _commit_transaction(document)
    except Exception as exc:
        _abort_transaction(document)
        _notify_slot("failed and was rolled back: {}".format(exc), error=True)
        return {"status": "error", "error": str(exc)}

    _notify_slot("created parametric smart slot.")
    return result


def _notify_slot(text: str, error: bool = False) -> None:
    notify("Smart Slot", text, error=error)


class SmartSlotCommand(SketcherCommand):
    """``FMF_CreateSlot`` ribbon command."""

    def GetResources(self):
        return {
            "Pixmap": "FMF_CreateSlot",
            "MenuText": "Smart Slot",
            "ToolTip": (
                "Create a parametric Center-to-Center Slot with auto-applied tangency, "
                "equality, and symmetry constraints.\n"
                "- Select 2 points or 1 line to place the slot along reference geometry,\n"
                "- or click with no selection to generate a standard parametric slot."
            ),
        }

    def Activated(self):
        add_smart_slot()


# ---------------------------------------------------------------------------
# Smart Loop Offset Wrapper
# ---------------------------------------------------------------------------


def detect_contour_chains(sketch, edge_ids=None):
    """Walk sketch edges and return continuous connected chains."""
    geos = _geometry_list(sketch)
    if edge_ids is None:
        edge_ids = [i for i, g in enumerate(geos) if not getattr(g, "Construction", False)]
    if not edge_ids:
        return []

    remaining = list(edge_ids)
    chains = []

    while remaining:
        first = remaining.pop(0)
        chain = [{"geoid": first, "reversed": False}]
        g_first = geos[first]
        p_start = geometry_point(g_first, _POS_START)
        p_end = geometry_point(g_first, _POS_END)

        extended = True
        while extended:
            extended = False
            for idx, cand in enumerate(remaining):
                g_cand = geos[cand]
                cs = geometry_point(g_cand, _POS_START)
                ce = geometry_point(g_cand, _POS_END)
                if cs is not None and p_end is not None and points_equal(p_end, cs):
                    chain.append({"geoid": cand, "reversed": False})
                    remaining.pop(idx)
                    p_end = ce
                    extended = True
                    break
                elif ce is not None and p_end is not None and points_equal(p_end, ce):
                    chain.append({"geoid": cand, "reversed": True})
                    remaining.pop(idx)
                    p_end = cs
                    extended = True
                    break

        is_closed = False
        if p_start is not None and p_end is not None and points_equal(p_start, p_end):
            is_closed = True
        chains.append({"edges": chain, "closed": is_closed})

    return chains


def create_smart_offset(sketch, edge_ids, offset_dist=5.0):
    """Generate a parametric offset of the given edges, maintaining parallel/concentric intent."""
    import Sketcher

    geos = _geometry_list(sketch)
    if not edge_ids:
        return {"status": "no-edges"}

    chains = detect_contour_chains(sketch, edge_ids)
    if not chains:
        return {"status": "empty-chains"}

    created_geoids = []
    parent_child_map = {}

    for chain in chains:
        edges = chain["edges"]
        chain_created = []

        # 1. Compute raw offset points for each segment
        raw_offsets = []
        for item in edges:
            gid = item["geoid"]
            g = geos[gid]
            kind = _geometry_kind(g)
            if kind == "line":
                p1 = geometry_point(g, _POS_START)
                p2 = geometry_point(g, _POS_END)
                if p1 is None or p2 is None:
                    continue
                dx = p2[0] - p1[0]
                dy = p2[1] - p1[1]
                length = math_hypot(dx, dy)
                if length <= TOLERANCE:
                    continue
                nx, ny = -dy / length, dx / length
                sp = (p1[0] + offset_dist * nx, p1[1] + offset_dist * ny)
                ep = (p2[0] + offset_dist * nx, p2[1] + offset_dist * ny)
                raw_offsets.append(
                    {
                        "geoid": gid,
                        "kind": "line",
                        "start": sp,
                        "end": ep,
                        "dir": (dx / length, dy / length),
                    }
                )
            elif kind in ("circle", "arc"):
                center = geometry_point(g, _POS_CENTER)
                r = getattr(g, "Radius", 10.0)
                new_r = max(1.0, r + offset_dist)
                sp = geometry_point(g, _POS_START)
                ep = geometry_point(g, _POS_END)
                raw_offsets.append(
                    {
                        "geoid": gid,
                        "kind": kind,
                        "center": center,
                        "radius": new_r,
                        "start": sp,
                        "end": ep,
                    }
                )

        if not raw_offsets:
            continue

        # 2. Add offset geometry
        for item in raw_offsets:
            if item["kind"] == "line":
                new_id = _add_line(sketch, item["start"], item["end"], construction=False)
            elif item["kind"] == "arc":
                new_id = _add_arc(
                    sketch, item["center"], item["start"], item["end"], construction=False
                )
            else:
                new_id = _add_line(sketch, item["start"], item["end"], construction=False)
            chain_created.append((item["geoid"], new_id, item["kind"]))
            created_geoids.append(new_id)
            parent_child_map[item["geoid"]] = new_id

        # 3. Add Coincident constraints between adjacent offset segments
        for i in range(len(chain_created) - (0 if chain["closed"] else 1)):
            next_i = (i + 1) % len(chain_created)
            curr_child = chain_created[i][1]
            next_child = chain_created[next_i][1]
            _safe_add_constraint(
                sketch,
                Sketcher.Constraint("Coincident", curr_child, _POS_END, next_child, _POS_START),
            )

        # 4. Add Parallel constraints to parent lines & concentricity to parent arcs
        for p_id, c_id, kind in chain_created:
            if kind == "line":
                _safe_add_constraint(sketch, Sketcher.Constraint("Parallel", c_id, p_id))
            elif kind in ("arc", "circle"):
                _safe_add_constraint(
                    sketch, Sketcher.Constraint("Coincident", c_id, _POS_CENTER, p_id, _POS_CENTER)
                )

        # 5. Insert single driving dimension constraint between first parent and child
        if chain_created:
            p0, c0, k0 = chain_created[0]
            if k0 == "line":
                _safe_add_constraint(
                    sketch,
                    Sketcher.Constraint(
                        "Distance", p0, _POS_START, c0, _POS_START, abs(offset_dist)
                    ),
                )
            elif k0 in ("arc", "circle"):
                _safe_add_constraint(
                    sketch,
                    Sketcher.Constraint(
                        "Radius", c0, getattr(geos[p0], "Radius", 10.0) + offset_dist
                    ),
                )

    _recompute(sketch)
    return {
        "status": "ok",
        "created": created_geoids,
        "mapping": parent_child_map,
    }


def add_smart_offset(offset_dist=5.0):
    """Create a parametric loop offset from sketch selection."""
    sketch = active_sketch()
    if sketch is None:
        _notify_offset("start editing a sketch first.", error=True)
        return {"status": "no-sketch"}

    getter = getattr(Gui.Selection, "getSelectionEx", None)
    selected_edges = []
    if callable(getter):
        for entry in getter() or []:
            if getattr(entry, "Object", None) is sketch or selection_object_name(entry) == getattr(
                sketch, "Name", None
            ):
                for sub in getattr(entry, "SubElementNames", []) or []:
                    if sub.startswith("Edge"):
                        try:
                            selected_edges.append(int(sub[4:]) - 1)
                        except ValueError:
                            pass

    if not selected_edges:
        geos = _geometry_list(sketch)
        selected_edges = [i for i, g in enumerate(geos) if not getattr(g, "Construction", False)]

    if not selected_edges:
        _notify_offset("no sketch edges available to offset.", error=True)
        return {"status": "no-edges"}

    document = getattr(App, "ActiveDocument", None)
    _open_transaction(document, "Smart Loop Offset")
    try:
        result = create_smart_offset(sketch, selected_edges, offset_dist=offset_dist)
        _commit_transaction(document)
    except Exception as exc:
        _abort_transaction(document)
        _notify_offset("offset failed: {}".format(exc), error=True)
        return {"status": "error", "error": str(exc)}

    _notify_offset(f"offset {len(result.get('created', []))} segment(s) parametrically.")
    return result


def _notify_offset(text: str, error: bool = False) -> None:
    notify("Smart Offset", text, error=error)


class SmartOffsetCommand(SketcherCommand):
    """``FMF_SmartOffset`` ribbon command."""

    def GetResources(self):
        return {
            "Pixmap": "FMF_SmartOffset",
            "MenuText": "Smart Offset",
            "ToolTip": (
                "Create a parametric loop offset with preserved parallel, tangent, and "
                "coincident relationships driven by a single offset dimension."
            ),
        }

    def Activated(self):
        add_smart_offset()


# ---------------------------------------------------------------------------
# Trimming Coincident Repair
# ---------------------------------------------------------------------------


def capture_curve_attachments(sketch, geoid):
    """Record all coincident and point-on-object constraints touching geoid."""
    records = []
    for idx, c in enumerate(getattr(sketch, "Constraints", []) or []):
        ctype = getattr(c, "Type", "")
        if ctype in ("Coincident", "PointOnObject"):
            if c.First == geoid or c.Second == geoid or getattr(c, "Third", -2000) == geoid:
                records.append(
                    {
                        "index": idx,
                        "type": ctype,
                        "first": c.First,
                        "first_pos": getattr(c, "FirstPos", 0),
                        "second": c.Second,
                        "second_pos": getattr(c, "SecondPos", 0),
                        "third": getattr(c, "Third", -2000),
                    }
                )
    return records


def repair_trimmed_coincidents(sketch, target_geoid, new_endpoint=None):
    """Reconnect broken constraints after a trim operation."""
    import Sketcher

    attachments = capture_curve_attachments(sketch, target_geoid)
    if not attachments:
        return 0

    reconnected = 0
    geos = _geometry_list(sketch)
    if not (0 <= target_geoid < len(geos)):
        return 0

    for rec in attachments:
        ctype = rec["type"]
        other_id = rec["second"] if rec["first"] == target_geoid else rec["first"]
        other_pos = rec["second_pos"] if rec["first"] == target_geoid else rec["first_pos"]
        target_pos = rec["first_pos"] if rec["first"] == target_geoid else rec["second_pos"]

        if ctype == "Coincident":
            c = Sketcher.Constraint("Coincident", target_geoid, target_pos, other_id, other_pos)
            if _safe_add_constraint(sketch, c):
                reconnected += 1
        elif ctype == "PointOnObject":
            c = Sketcher.Constraint("PointOnObject", other_id, other_pos, target_geoid)
            if _safe_add_constraint(sketch, c):
                reconnected += 1

    _recompute(sketch)
    return reconnected


# ---------------------------------------------------------------------------
# Human-Readable Solver Diagnostics
# ---------------------------------------------------------------------------


def _format_constraint_readable(sketch, idx):
    """Return a human-readable description of the constraint at idx."""
    import math

    constraints = list(getattr(sketch, "Constraints", []) or [])
    if not (0 <= idx < len(constraints)):
        return f"Constraint #{idx}"
    c = constraints[idx]
    ctype = getattr(c, "Type", "Unknown")
    geos = _geometry_list(sketch)

    def describe_element(geoid, posid):
        if geoid == -1:
            return "X-Axis"
        if geoid == -2:
            return "Y-Axis"
        if geoid == -3:
            return "Origin"
        if 0 <= geoid < len(geos):
            g = geos[geoid]
            kind = _geometry_kind(g).capitalize()
            pos_name = {1: "Start", 2: "End", 3: "Center"}.get(posid, "")
            if pos_name:
                return f"{kind} {geoid} ({pos_name})"
            return f"{kind} {geoid}"
        return f"Geo {geoid}"

    first_str = describe_element(getattr(c, "First", -2000), getattr(c, "FirstPos", 0))
    second_id = getattr(c, "Second", -2000)
    second_str = (
        describe_element(second_id, getattr(c, "SecondPos", 0)) if second_id != -2000 else ""
    )
    val = getattr(c, "Value", 0.0)

    if val and ctype in ("Distance", "DistanceX", "DistanceY", "Radius", "Diameter", "Angle"):
        val_str = f" ({val:.2f} mm)" if ctype != "Angle" else f" ({math.degrees(val):.1f}°)"
    else:
        val_str = ""

    if second_str:
        return f"Constraint #{idx}: {ctype}{val_str} between {first_str} and {second_str}"
    return f"Constraint #{idx}: {ctype}{val_str} on {first_str}"


def diagnose_sketch_solver(sketch):
    """Analyze sketch solver state and return human-readable diagnostic report."""
    redundant = list(getattr(sketch, "RedundantConstraints", []) or [])
    conflicting = list(getattr(sketch, "ConflictingConstraints", []) or [])
    malformed = list(getattr(sketch, "MalformedConstraints", []) or [])
    partial = list(getattr(sketch, "PartiallyRedundantConstraints", []) or [])
    dof = getattr(sketch, "DoF", 0)

    report = {
        "is_clean": not (redundant or conflicting or malformed),
        "dof": dof,
        "redundant": [_format_constraint_readable(sketch, i) for i in redundant],
        "conflicting": [_format_constraint_readable(sketch, i) for i in conflicting],
        "malformed": [_format_constraint_readable(sketch, i) for i in malformed],
        "partial": [_format_constraint_readable(sketch, i) for i in partial],
        "raw_redundant": redundant,
        "raw_conflicting": conflicting,
    }
    return report


def remove_redundant_constraints(sketch):
    """Remove all flagged redundant constraints in one atomic transaction."""
    redundant = sorted(getattr(sketch, "RedundantConstraints", []) or [], reverse=True)
    if not redundant:
        return 0

    document = getattr(App, "ActiveDocument", None)
    _open_transaction(document, "Remove Redundant Constraints")
    removed = 0
    try:
        for idx in redundant:
            _drop_constraint(sketch, idx)
            removed += 1
        _recompute(sketch)
        _commit_transaction(document)
    except Exception:
        _abort_transaction(document)
        raise
    return removed


def run_solver_diagnostics():
    """Diagnose the active sketch and report readable diagnostic messages."""
    sketch = active_sketch()
    if sketch is None:
        _notify_diagnostics("start editing a sketch first.", error=True)
        return {"status": "no-sketch"}

    report = diagnose_sketch_solver(sketch)
    if report["is_clean"]:
        msg = f"Sketch is healthy: DoF {report['dof']}, 0 conflicts, 0 redundant constraints."
        _notify_diagnostics(msg)
        return {"status": "clean", "report": report}

    App.Console.PrintWarning("=== FMF Solver Diagnostics ===\n")
    if report["conflicting"]:
        App.Console.PrintError("Conflicting constraints:\n")
        for line in report["conflicting"]:
            App.Console.PrintError(f"  - {line}\n")
    if report["redundant"]:
        App.Console.PrintWarning("Redundant constraints:\n")
        for line in report["redundant"]:
            App.Console.PrintWarning(f"  - {line}\n")
        removed = remove_redundant_constraints(sketch)
        App.Console.PrintMessage(f"Auto-removed {removed} redundant constraint(s).\n")

    summary = (
        f"Diagnosed: {len(report['conflicting'])} conflicting, "
        f"{len(report['redundant'])} redundant."
    )
    _notify_diagnostics(summary, error=bool(report["conflicting"]))
    return {"status": "diagnosed", "report": report}


def _notify_diagnostics(text: str, error: bool = False) -> None:
    notify("Diagnostics", text, error=error)


class SolverDiagnosticsCommand(SketcherCommand):
    """``FMF_SolverDiagnostics`` ribbon command."""

    def GetResources(self):
        return {
            "Pixmap": "FMF_SolverDiagnostics",
            "MenuText": "Solver Diagnostics",
            "ToolTip": (
                "Inspect sketch solver conflicts and redundant constraints with "
                "human-readable geometry descriptions and 1-click auto-cleanup."
            ),
        }

    def Activated(self):
        run_solver_diagnostics()


def _register_icon_path():
    """Let FreeCAD resolve the command's authored icon by name in menus and search.

    The ribbon finds it by filename; menus and the command search use the bitmap
    factory, which needs the directory on its search path.
    """
    adder = getattr(Gui, "addIconPath", None)
    if not callable(adder):
        return
    directory = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "bundled-addons",
        "FreeCAD-Ribbon",
        "Resources",
        "FreeCAD Icons",
    )
    if os.path.isdir(directory):
        try:
            adder(directory)
        except Exception:
            pass


def register(add_command=None):
    """Register the commands with FreeCAD (or a supplied callable, for tests)."""
    _register_icon_path()
    register_with = add_command or Gui.addCommand
    register_with("FMF_MirrorWithConstraints", MirrorWithConstraintsCommand())
    register_with("FMF_AddMidline", AddMidlineCommand())
    register_with("FMF_ConstrainMidpoint", ConstrainMidpointCommand())
    register_with("FMF_CreateSlot", SmartSlotCommand())
    register_with("FMF_SmartOffset", SmartOffsetCommand())
    register_with("FMF_SolverDiagnostics", SolverDiagnosticsCommand())
