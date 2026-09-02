"""Constraint-aware sketch mirroring for FusionMyFreeCAD.

``FusionMyFreeCAD_MirrorWithConstraints`` uses Sketcher's synchronous symmetry API
and then copies the *boundary* constraints native Symmetry leaves behind: the ones
that tie a mirrored endpoint to geometry outside the mirrored selection (an
unchanged border line, a sketch axis, projected external geometry).  Native
Symmetry only reproduces constraints whose every endpoint is inside the mirrored
selection, so a profile whose dividers are attached to its top and bottom edges
loses those attachments on mirroring and the pad later fails to close.

The command is explicitly best-effort.  Every constraint it cannot safely
reproduce is reported rather than dropped in silence, matching the rest of the
add-on's "never fail quietly" contract.

The FreeCAD-touching helpers are deliberately small and isolated.  The synchronous
API and selection spellings are verified against FreeCAD 1.1.3; unsupported
selection forms are refused rather than guessed.
"""

from __future__ import annotations

import FreeCAD as App
import FreeCADGui as Gui

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

    if not in_source and not (touches_axis and ctype in _BOUNDARY_COPYABLE_TYPES):
        # Nothing mirrored here; not our concern.
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
    return Sketcher.Constraint(
        "Coincident",
        spec["first"],
        spec["first_pos"],
        spec["second"],
        spec["second_pos"],
    )


def _bad_constraint_indices(sketch):
    """Redundant/conflicting/malformed constraint indices the solver flagged."""
    flagged = set()
    for attribute in (
        "ConflictingConstraints",
        "RedundantConstraints",
        "MalformedConstraints",
        "PartiallyRedundantConstraints",
        # Compatibility with older FreeCAD builds and the lightweight test fake.
        "Conflicting",
        "Redundant",
        "Malformed",
    ):
        for value in getattr(sketch, attribute, []) or []:
            try:
                flagged.add(int(value))
            except (TypeError, ValueError):
                continue
    return flagged


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
            except Exception:
                pass
        added, added_indices = survivors, survivor_indices
        _recompute(sketch)

    failed = [
        {"type": spec["type"], "reason": spec["reason"]} for spec in specs if spec.get("_failed")
    ]
    return added, removed + failed


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


def _notify(text, error=False):
    """Show a non-modal result: report view line plus a transient status message."""
    printer = App.Console.PrintError if error else App.Console.PrintMessage
    printer("FusionMyFreeCAD Mirror: {}\n".format(text))
    try:
        window = Gui.getMainWindow()
        status_bar = window.statusBar() if window is not None else None
        if status_bar is not None:
            status_bar.showMessage("Mirror with Constraints: {}".format(text), 8000)
    except Exception:
        pass


def _format_report(mirrored_count, added, skipped, removed, unmatched):
    parts = [
        "mirrored {} element{}".format(mirrored_count, "" if mirrored_count == 1 else "s"),
        "copied {} boundary constraint{}".format(len(added), "" if len(added) == 1 else "s"),
    ]
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
    for item in skipped:
        detail.append("  skipped {} #{}: {}".format(item["type"], item["index"], item["reason"]))
    for item in removed:
        detail.append("  removed {}: {}".format(item["type"], item["reason"]))
    return summary, detail


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
    copies, skipped = plan_constraint_copies(
        records, set(source_indices), mapping, before_geometry, axis_a, axis_b
    )
    added, removed = apply_constraint_copies(sketch, copies)
    _recompute(sketch)
    return {
        "mirrored": mirrored_count,
        "copied": added,
        "skipped": skipped,
        "removed": removed,
        "unmatched": unmatched,
        "mapping": mapping,
    }


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
    _open_transaction(document, "Mirror with Constraints")
    try:
        result = mirror_sketch_geometry(
            sketch, source_indices, reference_geoid, reference_pos, axis
        )
        _commit_transaction(document)
    except Exception as error:
        _abort_transaction(document)
        _notify("failed and was rolled back: {}".format(error), error=True)
        return {"status": "error", "error": str(error)}

    summary, detail = _format_report(
        result["mirrored"],
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
# Command object
# ---------------------------------------------------------------------------


class MirrorWithConstraintsCommand:
    """``FusionMyFreeCAD_MirrorWithConstraints`` ribbon command."""

    def GetResources(self):
        return {
            "Pixmap": "Constraint_Symmetric",
            "MenuText": "Mirror + Constraints",
            "ToolTip": (
                "Advanced mirror: select geometry, then a mirror line or sketch axis. "
                "Creates the mirror and copies compatible endpoint constraints to "
                "unchanged borders or axes. Anything unsafe is reported. Use Mirror "
                "for FreeCAD's original interactive tool and live symmetry links."
            ),
        }

    def IsActive(self):
        return active_sketch() is not None

    def Activated(self):
        mirror_with_constraints()


def register(add_command=None):
    """Register the command with FreeCAD (or a supplied callable, for tests)."""
    register_with = add_command or Gui.addCommand
    register_with("FusionMyFreeCAD_MirrorWithConstraints", MirrorWithConstraintsCommand())
