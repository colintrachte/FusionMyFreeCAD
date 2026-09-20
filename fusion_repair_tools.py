"""Find and mend references that FreeCAD lost track of.

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

from typing import Any

import FreeCAD as App
import FreeCADGui as Gui

from fusion_common import notify, transaction

#: Prefix every message from this command carries in the Report view.
LABEL = "Repair References"

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


def subelement_resolves(target, sub: str) -> bool:
    """Whether `sub` still names something on `target`.

    Tried against the object first, because a Sketch's InternalFaces live on
    its InternalShape rather than on its Shape and only the object knows that.
    """
    if not sub:
        return getattr(target, "Shape", None) is not None
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

    Lower sorts better. A face the point actually lies within beats one that
    merely shares its plane, which is what separates the top of one boss from
    the top of another at the same height.
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
    inside = 1
    contains = getattr(face, "isInside", None)
    if callable(contains):
        try:
            if contains(App.Vector(*wanted_point), COPLANAR_TOLERANCE, True):
                inside = 0
        except Exception:
            inside = 1
    centre = _xyz(getattr(face, "CenterOfMass", None))
    distance = _distance(wanted_point, centre) if centre is not None else float("inf")
    return (inside, distance)


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


def plan_repairs(document) -> dict:
    """What could be mended, and what could only be named."""
    repairs, unresolved = [], []
    for finding in broken_references(document):
        replacement = None
        if finding["repairable"]:
            replacement = suggest_attachment_face(finding["object"], finding["target"])
        if replacement:
            repairs.append(dict(finding, replacement=replacement))
        else:
            unresolved.append(finding)
    return {"repairs": repairs, "unresolved": unresolved}


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
    return "{}.{} -> {}.{}".format(
        getattr(finding["object"], "Name", "?"),
        finding["property"],
        getattr(finding["target"], "Name", "?"),
        finding["sub"] or "(whole object)",
    )


def repair_document(document=None) -> dict:
    """Mend what can be mended in `document`, and say what could not be.

    One transaction for the lot, so a single Undo puts everything back if the
    result is not what the user wanted.
    """
    document = document if document is not None else App.ActiveDocument
    if document is None:
        notify(LABEL, "no document is open.", error=True)
        return {"repaired": [], "unresolved": []}

    plan = plan_repairs(document)
    if not plan["repairs"] and not plan["unresolved"]:
        notify(LABEL, "every reference in this document resolves; nothing to repair.")
        return {"repaired": [], "unresolved": []}

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
            "FusionMyFreeCAD reattached {} to {}.\n".format(
                _describe(repair), repair["replacement"]
            )
        )
    for finding in plan["unresolved"]:
        App.Console.PrintWarning(
            "FusionMyFreeCAD could not repair {}.\n".format(_describe(finding))
        )
    _report(repaired, plan["unresolved"])
    return {"repaired": repaired, "unresolved": plan["unresolved"]}


def _report(repaired, unresolved) -> None:
    """One sentence in the status bar; the detail is already in the Report view."""
    if repaired and not unresolved:
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
                len(repaired), len(repaired) + len(unresolved)
            ),
            error=True,
        )
        return
    notify(
        LABEL,
        "found {} broken reference{} that cannot be reattached automatically; "
        "see the Report view.".format(len(unresolved), "" if len(unresolved) == 1 else "s"),
        error=True,
    )


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------


class RepairReferencesCommand:
    """Find references FreeCAD lost, and reattach the ones that can be placed."""

    def GetResources(self):
        return {
            "Pixmap": "FusionMyFreeCAD_RepairReferences",
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


def register(add_command=None):
    register_with = add_command or Gui.addCommand
    register_with("FusionMyFreeCAD_RepairReferences", RepairReferencesCommand())
