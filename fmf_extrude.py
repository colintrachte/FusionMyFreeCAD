"""Smart Extrude (FMF_SmartExtrude) for FusionMyFreeCAD.

Provides intelligent extrusion wrapping native FreeCAD PartDesign features:
- Automatically classifies Join (Pad) vs Cut (Pocket) vs New Body based on
  volumetric intersection and abutment with the active Body solid.
- Handles multi-region profiles and sketches containing external geometry
  wires by extracting closed InternalShape faces.
- Prevents silent empty-solid failures by verifying solid count and auto-reversing
  when the opposite direction produces a valid solid.
- All created objects are native PartDesign::Pad, PartDesign::Pocket, and
  PartDesign::Body, ensuring 100% document portability without FMF.
"""

from __future__ import annotations

from typing import Any

from fmf_common import event, notify, transaction


def _get_app() -> Any | None:
    try:
        import FreeCAD as App

        return App
    except ImportError:
        return None


def _get_gui() -> Any | None:
    try:
        import FreeCADGui as Gui

        return Gui
    except ImportError:
        return None


def _active_body(document: Any = None) -> Any:
    """Find the active PartDesign::Body or the first body in document."""
    app = _get_app()
    gui = _get_gui()
    doc = document or (getattr(app, "ActiveDocument", None) if app else None)
    if doc is None:
        return None

    # 1. Check active object in active view (standard FreeCAD PartDesign active body)
    active_view = (
        getattr(getattr(gui, "ActiveDocument", None), "ActiveView", None)
        if gui
        else None
    )
    if active_view and hasattr(active_view, "getActiveObject"):
        try:
            pd_body = active_view.getActiveObject("pdbody")
            if pd_body is not None:
                return pd_body
        except Exception:
            pass

    # 2. Check doc.ActiveObject
    body = getattr(doc, "ActiveObject", None)
    if body and getattr(body, "TypeId", "") == "PartDesign::Body":
        return body

    # 3. Check doc.Objects
    for obj in getattr(doc, "Objects", []):
        if getattr(obj, "TypeId", "") == "PartDesign::Body":
            return obj
    return None


def resolve_profile(
    selection_ex: list[Any] | None = None,
    document: Any = None,
) -> tuple[Any | None, list[str]]:
    """Resolve the selected object and sub-element profile for extrusion.

    Returns (profile_object, sub_elements_list).
    """
    gui = _get_gui()
    if selection_ex is None and gui:
        getter = getattr(getattr(gui, "Selection", None), "getSelectionEx", None)
        if callable(getter):
            selection_ex = getter() or []
        else:
            selection_ex = []

    if not selection_ex:
        return None, []

    for sel in selection_ex:
        obj = getattr(sel, "Object", None)
        if obj is None:
            continue
        subs = list(getattr(sel, "SubElementNames", []) or [])

        # Case A: SketchObject
        if getattr(obj, "TypeId", "").startswith("Sketcher::") or hasattr(obj, "Geometry"):
            # Check for face sub-elements
            face_subs = [s for s in subs if s.startswith("InternalFace") or s.startswith("Face")]
            if face_subs:
                return obj, face_subs

            # If whole sketch selected without sub-elements:
            # Check if external geometry / unclosed wires exist while InternalShape has valid faces
            shape = getattr(obj, "Shape", None)
            internal = getattr(obj, "InternalShape", None)
            if shape is not None and internal is not None:
                wires = getattr(shape, "Wires", [])
                faces = getattr(shape, "Faces", [])
                internal_faces = getattr(internal, "Faces", [])
                if len(wires) > 1 and len(faces) == 0 and len(internal_faces) > 0:
                    # Sketch has external geometry or unclosed wires; use InternalFace1
                    return obj, ["InternalFace1"]

            return obj, [""]

        # Case B: Face of a solid
        face_subs = [s for s in subs if s.startswith("Face")]
        if face_subs:
            return obj, face_subs

    # Fallback to first selected object
    first = getattr(selection_ex[0], "Object", None)
    return first, [""]


def classify_operation(
    profile_obj: Any,
    sub_elements: list[str] | None = None,
    length: float = 10.0,
    reversed_dir: bool = False,
    target_body: Any = None,
) -> dict[str, Any]:
    """Classify the extrusion as join, cut, or new_body based on geometry."""
    app = _get_app()
    body_shape = getattr(target_body, "Shape", None) if target_body else None
    has_target_solids = (
        body_shape is not None
        and not getattr(body_shape, "isNull", lambda: True)()
        and len(getattr(body_shape, "Solids", [])) > 0
    )

    if not has_target_solids:
        return {
            "operation": "new_body" if target_body is None else "join",
            "auto_reverse": False,
            "reason": "Target body has no existing solid",
            "confidence": 1.0,
        }

    # Extract face for test extrusion
    face = None
    sub_list = sub_elements or [""]
    internal = getattr(profile_obj, "InternalShape", None)
    if internal is not None and any(s.startswith("InternalFace") for s in sub_list):
        int_faces = getattr(internal, "Faces", [])
        if int_faces:
            face = int_faces[0].copy() if hasattr(int_faces[0], "copy") else int_faces[0]

    if face is None and hasattr(profile_obj, "Shape"):
        prof_shape = profile_obj.Shape
        prof_faces = getattr(prof_shape, "Faces", [])
        if prof_faces:
            face = prof_faces[0].copy() if hasattr(prof_faces[0], "copy") else prof_faces[0]

    if face is None:
        return {
            "operation": "join",
            "auto_reverse": False,
            "reason": "Could not extract test face; defaulting to join",
            "confidence": 0.5,
        }

    try:
        # Placement alignment
        pl = getattr(profile_obj, "Placement", None)
        if pl is not None and hasattr(face, "Placement"):
            face.Placement = pl.multiply(face.Placement)

        # Normal vector
        normal = None
        if hasattr(face, "normalAt"):
            normal = face.normalAt(0, 0)
        if normal is None and app and hasattr(app, "Vector"):
            rot = getattr(getattr(face, "Placement", None), "Rotation", None)
            if rot and hasattr(rot, "multVec"):
                normal = rot.multVec(app.Vector(0, 0, 1))

        if normal is None:
            return {
                "operation": "join",
                "auto_reverse": False,
                "reason": "Normal calculation unavailable",
                "confidence": 0.5,
            }

        sign = -1.0 if reversed_dir else 1.0
        dir_vec = normal * (sign * abs(length))
        rev_vec = normal * (-sign * abs(length))

        prism = face.extrude(dir_vec)
        rev_prism = face.extrude(rev_vec)

        # 1. Volumetric penetration test (Cut)
        common_shape = body_shape.common(prism)
        common_vol = (
            getattr(common_shape, "Volume", 0.0)
            if not getattr(common_shape, "isNull", lambda: True)()
            else 0.0
        )
        prism_vol = (
            getattr(prism, "Volume", 0.0)
            if not getattr(prism, "isNull", lambda: True)()
            else 0.0
        )

        if common_vol > 1e-4 and (prism_vol <= 0.0 or common_vol > 0.01 * prism_vol):
            return {
                "operation": "cut",
                "auto_reverse": False,
                "reason": f"Profile penetrates body solid (overlap volume: {common_vol:.2f})",
                "confidence": 0.95,
            }

        # 2. Abutment / outward extension test (Join)
        dist_fn = getattr(body_shape, "distToShape", None)
        dist = dist_fn(prism)[0] if callable(dist_fn) else 0.0

        if dist <= 1e-4:
            fuse_fn = getattr(body_shape, "fuse", None)
            fused = fuse_fn(prism) if callable(fuse_fn) else None
            fused_solids = len(getattr(fused, "Solids", [])) if fused else 1
            if fused_solids == 1:
                return {
                    "operation": "join",
                    "auto_reverse": False,
                    "reason": "Profile abuts body and fuses into one solid",
                    "confidence": 0.95,
                }
            else:
                # Check reversed direction
                rev_fused = fuse_fn(rev_prism) if callable(fuse_fn) else None
                rev_fused_solids = len(getattr(rev_fused, "Solids", [])) if rev_fused else 0
                rev_common_vol = getattr(body_shape.common(rev_prism), "Volume", 0.0)
                if rev_common_vol > 1e-4:
                    return {
                        "operation": "cut",
                        "auto_reverse": True,
                        "reason": "Opposite direction penetrates body interior",
                        "confidence": 0.9,
                    }
                elif rev_fused_solids == 1:
                    return {
                        "operation": "join",
                        "auto_reverse": True,
                        "reason": "Opposite direction fuses cleanly into body solid",
                        "confidence": 0.95,
                    }
                return {
                    "operation": "join",
                    "auto_reverse": False,
                    "reason": "Abutting profile",
                    "confidence": 0.7,
                }

        # 3. Disjoint in current direction: test if opposite direction contacts body
        rev_dist = dist_fn(rev_prism)[0] if callable(dist_fn) else 999.0
        if rev_dist <= 1e-4:
            rev_common_vol = getattr(body_shape.common(rev_prism), "Volume", 0.0)
            if rev_common_vol > 1e-4:
                return {
                    "operation": "cut",
                    "auto_reverse": True,
                    "reason": "Current direction disconnected; opposite penetrates body",
                    "confidence": 0.9,
                }
            return {
                "operation": "join",
                "auto_reverse": True,
                "reason": "Current direction disconnected; opposite abuts body",
                "confidence": 0.9,
            }

        # 4. Disjoint in both directions -> New Body
        return {
            "operation": "new_body",
            "auto_reverse": False,
            "reason": "Profile does not contact active body in either direction",
            "confidence": 0.85,
        }

    except Exception as exc:
        return {
            "operation": "join",
            "auto_reverse": False,
            "reason": f"Geometric classification failed ({exc}); defaulting to join",
            "confidence": 0.5,
        }


def smart_extrude(
    operation: str = "auto",
    length: float = 10.0,
    reversed_dir: bool = False,
    profile: tuple[Any, list[str]] | None = None,
    document: Any = None,
) -> dict[str, Any]:
    """Execute smart extrusion with automatic classification and fail-safe recovery."""
    app = _get_app()
    doc = document or (getattr(app, "ActiveDocument", None) if app else None)
    if doc is None:
        notify("Extrude", "No active document.", error=True)
        return {"status": "no-document"}

    if profile is None:
        profile_obj, sub_elements = resolve_profile(document=doc)
    else:
        profile_obj, sub_elements = profile

    if profile_obj is None:
        notify("Extrude", "Select a sketch or face to extrude.", error=True)
        return {"status": "no-selection"}

    target_body = _active_body(doc)

    effective_op = operation.lower()
    auto_reversed = False

    if effective_op == "auto":
        cls_result = classify_operation(
            profile_obj=profile_obj,
            sub_elements=sub_elements,
            length=length,
            reversed_dir=reversed_dir,
            target_body=target_body,
        )
        effective_op = cls_result["operation"]
        if cls_result.get("auto_reverse", False):
            reversed_dir = not reversed_dir
            auto_reversed = True

    try:
        with transaction(doc, f"Smart Extrude ({effective_op.title()})"):
            if effective_op == "new_body" or target_body is None:
                # Create a new PartDesign::Body
                new_body = doc.addObject("PartDesign::Body", "Body")
                new_body.Label = "Body"
                if hasattr(profile_obj, "isDerivedFrom") and profile_obj.isDerivedFrom(
                    "Sketcher::SketchObject"
                ):
                    # If sketch was not in a body, move to new body
                    if hasattr(new_body, "addObject"):
                        new_body.addObject(profile_obj)

                if hasattr(new_body, "newObject"):
                    feat = new_body.newObject("PartDesign::Pad", "Pad")
                else:
                    feat = doc.addObject("PartDesign::Pad", "Pad")
                    if hasattr(new_body, "addObject"):
                        new_body.addObject(feat)

                feat.Profile = (profile_obj, sub_elements)
                feat.Length = abs(length)
                feat.Reversed = reversed_dir
                if hasattr(feat, "recompute"):
                    feat.recompute()
                doc.recompute()
                notify("Extrude", f"Created new Body with Pad ({abs(length):.1f} mm).")
                return {
                    "status": "ok",
                    "operation": "new_body",
                    "body": new_body,
                    "feature": feat,
                    "auto_reversed": auto_reversed,
                }

            elif effective_op == "cut":
                if hasattr(target_body, "newObject"):
                    feat = target_body.newObject("PartDesign::Pocket", "Pocket")
                else:
                    feat = doc.addObject("PartDesign::Pocket", "Pocket")
                    if hasattr(target_body, "addObject"):
                        target_body.addObject(feat)

                feat.Profile = (profile_obj, sub_elements)
                feat.Length = abs(length)
                feat.Reversed = reversed_dir
                if hasattr(feat, "recompute"):
                    feat.recompute()
                doc.recompute()

                notify("Extrude", f"Created Pocket cut ({abs(length):.1f} mm).")
                return {
                    "status": "ok",
                    "operation": "cut",
                    "body": target_body,
                    "feature": feat,
                    "auto_reversed": auto_reversed,
                }

            else:  # "join"
                if hasattr(target_body, "newObject"):
                    feat = target_body.newObject("PartDesign::Pad", "Pad")
                else:
                    feat = doc.addObject("PartDesign::Pad", "Pad")
                    if hasattr(target_body, "addObject"):
                        target_body.addObject(feat)

                feat.Profile = (profile_obj, sub_elements)
                feat.Length = abs(length)
                feat.Reversed = reversed_dir
                if hasattr(feat, "recompute"):
                    feat.recompute()
                doc.recompute()

                # Guard against empty solid failure
                shape = getattr(feat, "Shape", None)
                if shape is not None:
                    has_solids = (
                        not getattr(shape, "isNull", lambda: False)()
                        and len(getattr(shape, "Solids", ())) > 0
                    )
                    if not has_solids and hasattr(feat, "Reversed"):
                        feat.Reversed = not reversed_dir
                        if hasattr(feat, "recompute"):
                            feat.recompute()
                        doc.recompute()
                        flipped_shape = getattr(feat, "Shape", None)
                        flipped_has_solids = (
                            flipped_shape is not None
                            and not getattr(flipped_shape, "isNull", lambda: True)()
                            and len(getattr(flipped_shape, "Solids", ())) > 0
                        )
                        if flipped_has_solids:
                            auto_reversed = True
                            event("info", "extrude", "auto_reverse", "recovered_empty_solid")
                        else:
                            # Revert if flipping didn't help
                            feat.Reversed = reversed_dir
                            if hasattr(feat, "recompute"):
                                feat.recompute()
                            doc.recompute()

                notify("Extrude", f"Created Pad join ({abs(length):.1f} mm).")
                return {
                    "status": "ok",
                    "operation": "join",
                    "body": target_body,
                    "feature": feat,
                    "auto_reversed": auto_reversed,
                }

    except Exception as exc:
        notify("Extrude", f"Smart Extrude failed: {exc}", error=True)
        return {"status": "error", "error": str(exc)}


class SmartExtrudeCommand:
    """FMF_SmartExtrude ribbon/shortcut command."""

    def GetResources(self) -> dict[str, str]:
        return {
            "Pixmap": "PartDesign_Pad",
            "MenuText": "Smart Extrude",
            "ToolTip": "Intelligent Extrude (Auto-detects Join, Cut, or New Body)",
        }

    def IsActive(self) -> bool:
        app = _get_app()
        return getattr(app, "ActiveDocument", None) is not None if app else False

    def Activated(self) -> None:
        app = _get_app()
        gui = _get_gui()
        doc = getattr(app, "ActiveDocument", None) if app else None
        profile_obj, _ = resolve_profile(document=doc)
        if profile_obj is None:
            # If no selection, run native Pad if available
            if gui and hasattr(gui, "runCommand"):
                try:
                    gui.runCommand("PartDesign_Pad")
                    return
                except Exception:
                    pass
            notify("Extrude", "Select a sketch or face to extrude.", error=True)
            return

        smart_extrude(operation="auto", document=doc)


def register(add_command: Any = None) -> None:
    """Register FMF_SmartExtrude command."""
    gui = _get_gui()
    register_with = add_command or (getattr(gui, "addCommand", None) if gui else None)
    if callable(register_with):
        register_with("FMF_SmartExtrude", SmartExtrudeCommand())
