"""One-click Datum plane helpers for FMF.

In Autodesk Fusion, creating a midplane, plane at an angle, or tangent plane is a
direct 1-click operation from the Construct menu. In native FreeCAD PartDesign,
creating a datum plane requires manual configuration of AttachmentMode strings
and MapReversed flags.

This module automates the attachment configuration from active viewport/tree
selections in an atomic undo transaction.
"""

from __future__ import annotations

import FreeCAD as App
import FreeCADGui as Gui

from fmf_common import notify, transaction


def _active_body(document=None):
    """Find the active PartDesign::Body or the first body in document."""
    doc = document or getattr(App, "ActiveDocument", None)
    if doc is None:
        return None
    body = getattr(doc, "ActiveObject", None)
    if body and getattr(body, "TypeId", "") == "PartDesign::Body":
        return body
    for obj in getattr(doc, "Objects", []):
        if getattr(obj, "TypeId", "") == "PartDesign::Body":
            return obj
    return None


def create_midplane(face_refs=None, document=None):
    """Create a PartDesign::Plane between two selected faces."""
    doc = document or getattr(App, "ActiveDocument", None)
    if doc is None:
        _notify_datum("no active document.", error=True)
        return {"status": "no-document"}

    if face_refs is None:
        selection_ex = []
        getter = getattr(Gui.Selection, "getSelectionEx", None)
        if callable(getter):
            selection_ex = getter() or []

        face_refs = []
        for sel in selection_ex:
            obj = getattr(sel, "Object", None)
            for sub in getattr(sel, "SubElementNames", []) or []:
                if sub.startswith("Face"):
                    face_refs.append((obj, [sub]))

    if len(face_refs) < 2:
        _notify_datum("select two faces to create a midplane between them.", error=True)
        return {"status": "insufficient-selection", "error": "Need 2 faces"}

    try:
        with transaction(doc, "Create Midplane"):
            body = _active_body(doc)
            if body is None:
                body = doc.addObject("PartDesign::Body", "Body")
                body.Label = "Body"

            if hasattr(body, "newObject"):
                plane = body.newObject("PartDesign::Plane", "Midplane")
            else:
                plane = doc.addObject("PartDesign::Plane", "Midplane")
                if hasattr(body, "addObject"):
                    body.addObject(plane)

            plane.Label = "Midplane"
            plane.AttachmentSupport = [face_refs[0], face_refs[1]]
            plane.MapMode = "Plane between two faces"
            doc.recompute()
    except Exception as exc:
        _notify_datum(f"midplane creation failed: {exc}", error=True)
        return {"status": "error", "error": str(exc)}

    _notify_datum("created datum Midplane between faces.")
    return {"status": "ok", "plane": plane}


def create_plane_at_angle(face_ref=None, edge_ref=None, angle=45.0, document=None):
    """Create a PartDesign::Plane at an angle around a reference edge."""
    doc = document or getattr(App, "ActiveDocument", None)
    if doc is None:
        _notify_datum("no active document.", error=True)
        return {"status": "no-document"}

    if face_ref is None or edge_ref is None:
        getter = getattr(Gui.Selection, "getSelectionEx", None)
        if callable(getter):
            for sel in getter() or []:
                obj = getattr(sel, "Object", None)
                for sub in getattr(sel, "SubElementNames", []) or []:
                    if sub.startswith("Face") and face_ref is None:
                        face_ref = (obj, [sub])
                    elif sub.startswith("Edge") and edge_ref is None:
                        edge_ref = (obj, [sub])

    if face_ref is None or edge_ref is None:
        _notify_datum("select a planar face and a rotation axis edge.", error=True)
        return {"status": "insufficient-selection"}

    try:
        with transaction(doc, "Create Plane at Angle"):
            body = _active_body(doc)
            if body is None:
                body = doc.addObject("PartDesign::Body", "Body")
                body.Label = "Body"

            if hasattr(body, "newObject"):
                plane = body.newObject("PartDesign::Plane", "PlaneAtAngle")
            else:
                plane = doc.addObject("PartDesign::Plane", "PlaneAtAngle")
                if hasattr(body, "addObject"):
                    body.addObject(plane)

            plane.Label = "PlaneAtAngle"
            plane.AttachmentSupport = [face_ref, edge_ref]
            plane.MapMode = "Plane by an axis and an angle"
            if hasattr(plane, "Angle"):
                plane.Angle = float(angle)
            doc.recompute()
    except Exception as exc:
        _notify_datum(f"plane creation failed: {exc}", error=True)
        return {"status": "error", "error": str(exc)}

    _notify_datum(f"created datum Plane at {angle} deg.")
    return {"status": "ok", "plane": plane}


def create_plane_tangent(cylinder_ref=None, point_ref=None, document=None):
    """Create a PartDesign::Plane tangent to a cylinder/surface at a point."""
    doc = document or getattr(App, "ActiveDocument", None)
    if doc is None:
        _notify_datum("no active document.", error=True)
        return {"status": "no-document"}

    if cylinder_ref is None:
        getter = getattr(Gui.Selection, "getSelectionEx", None)
        if callable(getter):
            for sel in getter() or []:
                obj = getattr(sel, "Object", None)
                for sub in getattr(sel, "SubElementNames", []) or []:
                    if sub.startswith("Face") and cylinder_ref is None:
                        cylinder_ref = (obj, [sub])
                    elif sub.startswith("Vertex") and point_ref is None:
                        point_ref = (obj, [sub])

    if cylinder_ref is None:
        _notify_datum("select a curved face to attach tangent plane.", error=True)
        return {"status": "insufficient-selection"}

    try:
        with transaction(doc, "Create Tangent Plane"):
            body = _active_body(doc)
            if body is None:
                body = doc.addObject("PartDesign::Body", "Body")
                body.Label = "Body"
            if hasattr(body, "newObject"):
                plane = body.newObject("PartDesign::Plane", "TangentPlane")
            else:
                plane = doc.addObject("PartDesign::Plane", "TangentPlane")
                if hasattr(body, "addObject"):
                    body.addObject(plane)

            plane.Label = "TangentPlane"
            plane.AttachmentSupport = [cylinder_ref] + ([point_ref] if point_ref else [])
            plane.MapMode = "Tangent to surface"
            doc.recompute()
    except Exception as exc:
        _notify_datum(f"tangent plane creation failed: {exc}", error=True)
        return {"status": "error", "error": str(exc)}

    _notify_datum("created datum Tangent Plane.")
    return {"status": "ok", "plane": plane}


def _notify_datum(text: str, error: bool = False) -> None:
    notify("Datum", text, error=error)


class DatumMidplaneCommand:
    """``FMF_DatumMidplane`` ribbon command."""

    def GetResources(self):
        return {
            "Pixmap": "FMF_DatumMidplane",
            "MenuText": "Midplane",
            "ToolTip": ("Create a 1-click datum midplane centered between two selected faces."),
        }

    def IsActive(self):
        return getattr(App, "ActiveDocument", None) is not None

    def Activated(self):
        create_midplane()


def register(add_command=None):
    register_with = add_command or Gui.addCommand
    register_with("FMF_DatumMidplane", DatumMidplaneCommand())
