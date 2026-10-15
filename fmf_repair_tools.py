"""Put a document back in agreement with itself.

Two commands live here. **Repair References** finds face and edge references
that no longer resolve and reattaches the ones it can identify. **Update
Model** rebuilds every feature, because a change upstream does not reliably
reach the features below it.

When a feature is edited, the faces and edges of everything downstream are
renumbered. FreeCAD's element map carries most references across, but not all
of them, and the ones it drops fail quietly: a sketch attached to a face stops
being placed, a chamfer stops finding its edge, a pad stops finding its
profile. The document keeps working, the Report view fills with lines like

    Sketch001.AttachmentSupport missing element reference Pad ... Face9
    Chamfer: Invalid edge link: ;#3c;:H8f7,E.Edge28

and the first the user knows of it is a feature that has silently disappeared.
Autodesk Fusion notices the same breakage and offers a dialog to re-pick the
reference; FreeCAD has everything needed to fix it -- `Sketcher_MapSketch` and
the Attachment dialog both re-point a sketch -- but it never offers.

This module closes that gap. It scans the document for references that no
longer resolve, and it repairs the one kind it can repair honestly.

An attachment can be repaired because the broken object still carries the
answer: its Placement was computed from the face it was attached to, so the
plane it sits on identifies which face on the new shape is the same face. That
is a measurement, not a guess.

Everything else is reported and left alone. There is nothing left in the
document that says which edge `Edge28` used to be, and a chamfer quietly
re-pointed at the wrong edge is worse than a chamfer that says it is broken.
"""

from __future__ import annotations

import time
from typing import Any

import FreeCAD as App
import FreeCADGui as Gui

from fmf_common import notify, transaction

#: Prefix each command's messages carry in the Report view.
LABEL = "Repair References"
UPDATE_LABEL = "Update Model"

#: Properties that name a subelement of another object's shape. Each is either
#: a link with a list of subelement names, or a list of such links.
LINK_SUB_PROPERTIES: tuple[str, ...] = (
    "AttachmentSupport",
    "Base",
    "Profile",
    "UpToFace",
    "UpToFace2",
)

#: Properties this module knows how to repair rather than only report.
REPAIRABLE_PROPERTIES: frozenset[str] = frozenset({"AttachmentSupport"})

#: Two directions count as the same when their dot product is this close to 1.
PARALLEL_TOLERANCE = 1e-6

#: How far off a plane a point may be and still be called on it, in mm. Loose
#: enough for a placement recomputed through a chain of features, tight enough
#: that two faces a hair apart are not confused.
COPLANAR_TOLERANCE = 1e-4


# ---------------------------------------------------------------------------
# Small vector helpers, duck-typed so the logic can be tested without OCC
# ---------------------------------------------------------------------------


def _xyz(vector) -> tuple[float, float, float] | None:
    for names in (("x", "y", "z"), ("X", "Y", "Z")):
        try:
            return tuple(float(getattr(vector, name)) for name in names)  # type: ignore[return-value]
        except (AttributeError, TypeError, ValueError):
            continue
    try:
        x, y, z = vector
        return float(x), float(y), float(z)
    except (TypeError, ValueError):
        return None


def _unit(vector) -> tuple[float, float, float] | None:
    if vector is None:
        return None
    length = sum(component * component for component in vector) ** 0.5
    if length <= 0.0:
        return None
    return tuple(component / length for component in vector)  # type: ignore[return-value]


def _dot(a, b) -> float:
    return sum(left * right for left, right in zip(a, b, strict=True))


def _difference(a, b) -> tuple[float, float, float]:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _distance(a, b) -> float:
    return sum(component * component for component in _difference(a, b)) ** 0.5


# ---------------------------------------------------------------------------
# Reading references off a document
# ---------------------------------------------------------------------------


def link_entries(value) -> list[tuple[Any, str]]:
    """Flatten a link property into (target object, subelement name) pairs.

    A link with no subelement names still yields one entry with an empty name,
    because a link to a whole object can be dangling too.
    """
    if value is None:
        return []
    if isinstance(value, tuple) and len(value) == 2 and not isinstance(value[0], (tuple, list)):
        value = [value]
    entries: list[tuple[Any, str]] = []
    for link in value if isinstance(value, (list, tuple)) else []:
        if not isinstance(link, (list, tuple)) or len(link) != 2:
            continue
        target, subs = link
        if target is None:
            continue
        if isinstance(subs, str):
            subs = [subs]
        subs = [sub for sub in (subs or []) if sub] or [""]
        entries.extend((target, sub) for sub in subs)
    return entries


def names_a_child_object(target, sub: str) -> bool:
    """Whether `sub` names a child object rather than a piece of a shape.

    A sketch on an origin plane links to the Origin object with the plane's
    name, and an Origin has no Shape at all -- so asking its shape for a
    subelement said every such sketch was broken, which is the commonest
    attachment in any document. Its children are the answer.
    """
    wanted = sub.rstrip(".")
    for attribute in ("OriginFeatures", "Group", "OutList"):
        for child in getattr(target, attribute, None) or []:
            if getattr(child, "Name", None) == wanted:
                return True
    return False


def subelement_resolves(target, sub: str) -> bool:
    """Whether `sub` still names something on `target`.

    Tried against the object first, because a Sketch's InternalFaces live on
    its InternalShape rather than on its Shape and only the object knows that.
    """
    if not sub:
        return getattr(target, "Shape", None) is not None
    if sub.startswith("?"):
        # FreeCAD rewrites a subelement name it could not resolve with a
        # leading "?". That is the answer, straight from the source.
        return False
    if names_a_child_object(target, sub):
        return True
    for source in (target, getattr(target, "Shape", None)):
        getter = getattr(source, "getSubObject", None) or getattr(source, "getElement", None)
        if not callable(getter):
            continue
        try:
            found = getter(sub)
        except Exception:
            continue
        if found is None:
            continue
        is_null = getattr(found, "isNull", None)
        if callable(is_null) and is_null():
            continue
        return True
    return False


def broken_references(document) -> list[dict]:
    """Every subelement reference in `document` that no longer resolves."""
    findings = []
    for obj in getattr(document, "Objects", []) or []:
        for name in LINK_SUB_PROPERTIES:
            if not hasattr(obj, name):
                continue
            try:
                value = getattr(obj, name)
            except Exception:
                continue
            for target, sub in link_entries(value):
                if subelement_resolves(target, sub):
                    continue
                findings.append(
                    {
                        "object": obj,
                        "property": name,
                        "target": target,
                        "sub": sub,
                        "repairable": name in REPAIRABLE_PROPERTIES,
                    }
                )
    return findings


# ---------------------------------------------------------------------------
# Matching a face to the plane an object is sitting on
# ---------------------------------------------------------------------------


def face_plane(face) -> tuple[tuple[float, float, float], tuple[float, float, float]] | None:
    """(a point on the face, its unit normal), or None if it is not planar."""
    surface = getattr(face, "Surface", None)
    position = _xyz(getattr(surface, "Position", None))
    normal = _unit(_xyz(getattr(surface, "Axis", None)))
    if position is not None and normal is not None:
        return position, normal
    centre = _xyz(getattr(face, "CenterOfMass", None))
    normal_at = getattr(face, "normalAt", None)
    if centre is not None and callable(normal_at):
        try:
            normal = _unit(_xyz(normal_at(0.0, 0.0)))
        except Exception:
            normal = None
        if normal is not None:
            return centre, normal
    return None


def placement_plane(
    placement,
) -> tuple[tuple[float, float, float], tuple[float, float, float]] | None:
    """The plane an attached object is sitting on, from its own Placement.

    This is the whole reason an attachment can be repaired without guessing:
    the placement was computed from the face that has gone, so it still
    describes where that face was.
    """
    if placement is None:
        return None
    base = _xyz(getattr(placement, "Base", None))
    if base is None:
        return None
    rotation = getattr(placement, "Rotation", None)
    multiply = getattr(rotation, "multVec", None)
    normal = None
    if callable(multiply):
        try:
            normal = _unit(_xyz(multiply(App.Vector(0, 0, 1))))
        except Exception:
            normal = None
    if normal is None:
        axis = _unit(_xyz(getattr(rotation, "Axis", None)))
        angle = getattr(rotation, "Angle", None)
        # No rotation applied, so the object's normal is still the Z axis.
        if axis is None or not angle:
            normal = (0.0, 0.0, 1.0)
        else:
            return None
    return base, normal


def face_match_rank(wanted, face) -> tuple | None:
    """How good a replacement `face` is for the plane in `wanted`, or None.

    Lower sorts better. Sharing a plane is not enough: the object's own origin
    has to fall within the face. Two bosses of the same height share a plane,
    and so does the tabletop they stand on, so coplanarity alone would pick
    whichever came first in the shape. Containment is the test that says
    *this* face.
    """
    plane = face_plane(face)
    if plane is None:
        return None
    wanted_point, wanted_normal = wanted
    point, normal = plane
    if abs(abs(_dot(wanted_normal, normal)) - 1.0) > PARALLEL_TOLERANCE:
        return None
    offset = abs(_dot(_difference(wanted_point, point), normal))
    if offset > COPLANAR_TOLERANCE:
        return None
    contains = getattr(face, "isInside", None)
    if callable(contains):
        try:
            if not contains(App.Vector(*wanted_point), COPLANAR_TOLERANCE, True):
                return None
        except Exception:
            pass
    centre = _xyz(getattr(face, "CenterOfMass", None))
    distance = _distance(wanted_point, centre) if centre is not None else float("inf")
    return (distance,)


def placement_is_unset(placement) -> bool:
    """Whether a Placement is the untouched default, and so says nothing.

    When an attachment fails, FreeCAD does not preserve the placement the
    lost face produced -- a sketch that was on the side of a pad comes back
    sitting at the origin, unrotated. Measured against a real document that
    is what `Sketch001` looks like, so an identity placement has to be read
    as "never placed" rather than as evidence about where the face was.
    """
    plane = placement_plane(placement)
    if plane is None:
        return True
    point, normal = plane
    return (
        max(abs(component) for component in point) <= COPLANAR_TOLERANCE
        and abs(normal[2] - 1.0) <= PARALLEL_TOLERANCE
    )


def suggest_attachment_face(obj, target) -> str | None:
    """The face of `target` that the plane of `obj` is sitting on."""
    wanted = placement_plane(getattr(obj, "Placement", None))
    if wanted is None:
        return None
    faces = getattr(getattr(target, "Shape", None), "Faces", None) or []
    best = None
    for index, face in enumerate(faces, start=1):
        rank = face_match_rank(wanted, face)
        if rank is None:
            continue
        if best is None or rank < best[0]:
            best = (rank, "Face{}".format(index))
    return best[1] if best else None


# ---------------------------------------------------------------------------
# Planning and applying
# ---------------------------------------------------------------------------


def sketch_regions(target) -> int:
    """How many regions a sketch currently divides itself into."""
    return len(getattr(getattr(target, "InternalShape", None), "Faces", None) or [])


def restore_invalidated(target, sub: str) -> str | None:
    """The name behind a "?" marker, when it unambiguously exists again.

    FreeCAD rewrites a subelement name it cannot resolve with a leading "?",
    and that marker does persist: a real document carried `?Face9` in a
    sketch's AttachmentSupport long after the recompute that broke it. When a
    reference was invalidated by something momentary -- a sketch open for one
    recompute, say -- the element can be back while the marker is not.

    Restoring is only safe where the name can mean one thing. A sketch with
    exactly one region leaves nothing for `InternalFace1` to be mistaken for.
    Every other name is positional in a shape that has since been renumbered,
    so the old number no longer picks out the old feature, and this declines.

    Whether a Pad's Profile ever persists this form is unconfirmed; a headless
    reproduction against the document that prompted it kept the resolved name
    throughout, so the "Sub shape not found" lines in that session were
    transient rather than a lasting corruption.
    """
    if not sub.startswith("?"):
        return None
    name = sub[1:]
    if name != "InternalFace1" or sketch_regions(target) != 1:
        return None
    return name


def plan_repairs(document) -> dict:
    """Three buckets: mend, offer, and name.

    A reference is *mended* only on evidence: a "?" marker over a name that
    can mean exactly one thing again, or a placement that still records the
    plane of the face that went missing. Where the best candidate is merely
    plausible it is *offered* instead, because applying it would be guessing
    with the user's model. Everything else is *named*, and left alone.
    """
    repairs, suggestions, unresolved = [], [], []
    for finding in broken_references(document):
        restored = restore_invalidated(finding["target"], finding["sub"])
        if restored:
            repairs.append(dict(finding, replacement=restored))
            continue
        replacement = None
        if finding["repairable"]:
            replacement = suggest_attachment_face(finding["object"], finding["target"])
        if not replacement:
            unresolved.append(finding)
        elif placement_is_unset(getattr(finding["object"], "Placement", None)):
            suggestions.append(dict(finding, replacement=replacement))
        else:
            repairs.append(dict(finding, replacement=replacement))
    return {"repairs": repairs, "suggestions": suggestions, "unresolved": unresolved}


def apply_repair(repair) -> bool:
    """Point one attachment at the face that replaces the missing one."""
    obj = repair["object"]
    name = repair["property"]
    try:
        entries = link_entries(getattr(obj, name))
    except Exception:
        return False
    rebound = []
    for target, sub in entries:
        if target is repair["target"] and sub == repair["sub"]:
            rebound.append((target, [repair["replacement"]]))
        else:
            rebound.append((target, [sub] if sub else []))
    try:
        setattr(obj, name, rebound)
    except Exception:
        return False
    return True


def _describe(finding) -> str:
    # FreeCAD's own "?" marker for an unresolved name only gets in the way
    # once the message already says the reference is broken.
    sub = (finding["sub"] or "").lstrip("?")
    return "{}.{} -> {}.{}".format(
        getattr(finding["object"], "Name", "?"),
        finding["property"],
        getattr(finding["target"], "Name", "?"),
        sub or "(whole object)",
    )


def repair_document(document=None) -> dict:
    """Mend what can be mended in `document`, and say what could not be.

    One transaction for the lot, so a single Undo puts everything back if the
    result is not what the user wanted.
    """
    document = document if document is not None else App.ActiveDocument
    if document is None:
        notify(LABEL, "no document is open.", error=True)
        return {"repaired": [], "suggestions": [], "unresolved": []}

    plan = plan_repairs(document)
    outstanding = plan["suggestions"] + plan["unresolved"]
    if not plan["repairs"] and not outstanding:
        notify(LABEL, "every reference in this document resolves; nothing to repair.")
        return {"repaired": [], "suggestions": [], "unresolved": []}

    repaired = []
    if plan["repairs"]:
        with transaction(document, "Repair references"):
            for repair in plan["repairs"]:
                if apply_repair(repair):
                    repaired.append(repair)
            if repaired:
                document.recompute()

    for repair in repaired:
        App.Console.PrintMessage(
            "FMF reattached {} to {}.\n".format(
                _describe(repair), repair["replacement"]
            )
        )
    for finding in plan["suggestions"]:
        App.Console.PrintWarning(
            "FMF: {} looks like it belongs on {}, but its placement was "
            "reset when the reference broke, so it has been left alone. Select it and "
            "use Map Sketch to confirm.\n".format(_describe(finding), finding["replacement"])
        )
    for finding in plan["unresolved"]:
        App.Console.PrintWarning(
            "FMF could not repair {}; nothing in the document records "
            "where it was. Re-pick it by hand.\n".format(_describe(finding))
        )
    _report(repaired, outstanding)
    return {
        "repaired": repaired,
        "suggestions": plan["suggestions"],
        "unresolved": plan["unresolved"],
    }


def _report(repaired, outstanding) -> None:
    """One sentence in the status bar; the detail is already in the Report view."""
    if repaired and not outstanding:
        notify(
            LABEL,
            "reattached {} broken reference{}.".format(
                len(repaired), "" if len(repaired) == 1 else "s"
            ),
        )
        return
    if repaired:
        notify(
            LABEL,
            "reattached {} of {} broken references; the rest are listed in the "
            "Report view and need re-picking by hand.".format(
                len(repaired), len(repaired) + len(outstanding)
            ),
            error=True,
        )
        return
    notify(
        LABEL,
        "found {} broken reference{} that cannot be reattached automatically; "
        "see the Report view.".format(len(outstanding), "" if len(outstanding) == 1 else "s"),
        error=True,
    )


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------


class RepairReferencesCommand:
    """Find references FreeCAD lost, and reattach the ones that can be placed."""

    def GetResources(self):
        return {
            "Pixmap": "FMF_RepairReferences",
            "MenuText": "Repair References",
            "ToolTip": (
                "Find sketches, dress-ups and features whose face or edge references "
                "no longer resolve. A sketch attached to a face that has been renumbered "
                "is reattached to the face it is sitting on; anything that cannot be "
                "identified from the model is listed in the Report view for you to "
                "re-pick."
            ),
        }

    def IsActive(self):
        return App.ActiveDocument is not None

    def Activated(self):
        repair_document()


# ---------------------------------------------------------------------------
# Rebuilding what FreeCAD has been told is already up to date
# ---------------------------------------------------------------------------


#: Status flags that mean an object failed outright.
FAILED_STATES = ("Invalid", "Error")

#: Still marked as needing a rebuild after one was forced. A failed recompute
#: takes its whole downstream with it -- FreeCAD filters those out of the
#: queue -- so they come back untouched by the rebuild and still stale.
STALE_STATE = "Touched"


def _status_of(obj) -> str:
    getter = getattr(obj, "getStatusString", None)
    if callable(getter):
        try:
            text = getter()
        except Exception:
            text = ""
        if text:
            return str(text)
    state = getattr(obj, "State", None) or []
    return ", ".join(str(flag) for flag in state) or "no shape"


def features_in_error(document) -> list:
    """(name, status, kind) for everything that did not end up with a shape.

    `kind` separates the feature that actually failed from the ones that were
    never reached because of it. Saying which is which turns a list of seven
    broken features into one thing to go and fix.
    """
    problems = []
    for obj in getattr(document, "Objects", []) or []:
        state = [str(flag) for flag in (getattr(obj, "State", None) or [])]
        if any(flag in FAILED_STATES for flag in state):
            problems.append((getattr(obj, "Name", "?"), _status_of(obj), "failed"))
        elif STALE_STATE in state:
            problems.append((getattr(obj, "Name", "?"), _status_of(obj), "not reached"))
    return problems


def mark_for_recompute(document) -> int:
    """Tell every object it needs rebuilding, and say how many were told.

    Necessary because `recompute(force=True)` does not do what its name
    suggests. Reading the source settles it: the force flag only bypasses the
    document's SkipRecompute flag, and each object is then still asked
    `mustRecompute()` and skipped if it says no. Run against a real document
    that returned 0 -- nothing rebuilt at all. The mark has to be set on the
    objects themselves first.
    """
    marked = 0
    for obj in getattr(document, "Objects", []) or []:
        for method in ("enforceRecompute", "touch"):
            call = getattr(obj, method, None)
            if not callable(call):
                continue
            try:
                call()
            except Exception:
                continue
            marked += 1
            break
    return marked


def update_model(document=None) -> dict:
    """Rebuild every feature, whether or not FreeCAD thinks one is needed.

    FreeCAD's own Refresh rebuilds only what is marked as needing it, and
    PartDesign's task dialog clears that mark across the whole document the
    moment you press OK -- the Python console shows
    `App.getDocument(...).purgeTouched()` immediately before its recompute. So
    a change to a pad is applied to the pad, and the pocket cut out of it is
    told it is already current. Opening that pocket and pressing OK is the
    usual way back, one feature at a time, down the whole tree.

    Rebuilding regardless is the only thing that reliably carries a change
    downstream, so that is what this does: every object is marked as needing
    a recompute, and then the document is recomputed.
    """
    document = document if document is not None else App.ActiveDocument
    if document is None:
        notify(UPDATE_LABEL, "no document is open.", error=True)
        return {"recomputed": 0, "errors": [], "failed": [], "blocked": []}

    started = time.perf_counter()
    try:
        marked = mark_for_recompute(document)
        recomputed = document.recompute(None, True)
    except Exception as error:
        notify(
            UPDATE_LABEL,
            "the rebuild did not finish: {}: {}".format(type(error).__name__, error),
            error=True,
        )
        return {"recomputed": 0, "errors": [], "failed": [], "blocked": []}
    elapsed = time.perf_counter() - started

    try:
        recomputed = int(recomputed)
    except (TypeError, ValueError):
        recomputed = marked

    errors = features_in_error(document)
    failed = [entry for entry in errors if entry[2] == "failed"]
    blocked = [entry for entry in errors if entry[2] == "not reached"]
    for name, status, kind in errors:
        App.Console.PrintWarning(
            "FMF: {} {}: {}\n".format(
                name, "failed" if kind == "failed" else "was not reached", status
            )
        )

    summary = "rebuilt {} feature{} in {:.1f}s".format(
        recomputed, "" if recomputed == 1 else "s", elapsed
    )
    if failed:
        # Name the first failure: the ones below it are its consequence, and
        # fixing that one is usually the whole job.
        notify(
            UPDATE_LABEL,
            "{}; {} failed ({}: {}){}.".format(
                summary,
                len(failed),
                failed[0][0],
                failed[0][1],
                ", and {} below could not be reached".format(len(blocked)) if blocked else "",
            ),
            error=True,
        )
    elif blocked:
        notify(
            UPDATE_LABEL,
            "{}; {} still needs rebuilding and is named in the Report view.".format(
                summary, len(blocked)
            ),
            error=True,
        )
    else:
        notify(UPDATE_LABEL, "{}.".format(summary))
    return {"recomputed": recomputed, "errors": errors, "failed": failed, "blocked": blocked}


class UpdateModelCommand:
    """Rebuild the whole model so a change upstream reaches everything below it."""

    def GetResources(self):
        return {
            "Pixmap": "FMF_UpdateModel",
            "MenuText": "Update Model",
            "ToolTip": (
                "Rebuild every feature, so a change to one carries down to everything "
                "that depends on it. FreeCAD's Refresh only rebuilds what it has marked "
                "as needing it, and editing a feature clears that mark across the whole "
                "document -- which is why a pad can change without the pocket cut out of "
                "it following. Fusion calls this Compute All."
            ),
        }

    def IsActive(self):
        return App.ActiveDocument is not None

    def Activated(self):
        update_model()


def register(add_command=None):
    register_with = add_command or Gui.addCommand
    register_with("FMF_RepairReferences", RepairReferencesCommand())
    register_with("FMF_UpdateModel", UpdateModelCommand())
