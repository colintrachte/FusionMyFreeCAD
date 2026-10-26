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

from typing import Any, ClassVar

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


def _get_qt() -> tuple[Any, Any, Any]:
    try:
        from PySide import QtCore, QtGui, QtWidgets

        return QtCore, QtGui, QtWidgets
    except ImportError:
        try:
            from PySide6 import QtCore, QtGui, QtWidgets

            return QtCore, QtGui, QtWidgets
        except ImportError:
            try:
                from PySide2 import QtCore, QtGui, QtWidgets

                return QtCore, QtGui, QtWidgets
            except ImportError:
                return None, None, None


def find_child(parent: Any, widget_type: Any, name: str) -> Any:
    """Find a child widget by class type and objectName safely."""
    if parent is None:
        return None
    if hasattr(parent, "findChild"):
        try:
            child = parent.findChild(widget_type, name)
            if child is not None:
                return child
        except Exception:
            pass
    if hasattr(parent, "findChildren"):
        try:
            for child in parent.findChildren(widget_type):
                if hasattr(child, "objectName") and child.objectName() == name:
                    return child
        except Exception:
            pass
    return None


def get_active_extrude_info() -> dict[str, Any] | None:
    """Detect whether a PartDesign Pad or Pocket task panel is currently active."""
    gui = _get_gui()
    _qt_core, _qt_gui, qt_widgets = _get_qt()
    if gui is None or qt_widgets is None:
        return None

    main_window = gui.getMainWindow() if hasattr(gui, "getMainWindow") else None
    if main_window is None:
        return None

    length_edit = find_child(main_window, qt_widgets.QWidget, "lengthEdit")
    check_reversed = find_child(main_window, qt_widgets.QWidget, "checkBoxReversed")
    length_edit2 = find_child(main_window, qt_widgets.QWidget, "lengthEdit2")

    if length_edit is not None and getattr(length_edit, "isVisible", lambda: False)():
        return {
            "spinbox": length_edit,
            "checkbox_reversed": check_reversed,
            "spinbox2": length_edit2,
        }
    return None


_active_extrude_hud: SmartExtrudeHud | None = None


class SmartExtrudeHud:
    """Compact floating on-canvas HUD for signed distance and operation selection."""

    OPERATIONS: ClassVar[tuple[str, ...]] = ("auto", "join", "cut", "new_body")
    OPERATION_LABELS: ClassVar[dict[str, str]] = {
        "auto": "Auto",
        "join": "Join",
        "cut": "Cut",
        "new_body": "New Body",
    }

    def __init__(
        self,
        spinbox: Any,
        checkbox_reversed: Any = None,
        parent: Any = None,
        operation: str = "auto",
    ) -> None:
        self.spinbox = spinbox
        self.checkbox_reversed = checkbox_reversed
        self.parent = parent
        self._operation = operation.lower() if operation else "auto"
        if self._operation not in self.OPERATIONS:
            self._operation = "auto"
        self._syncing = False
        self._visible = False
        self.widget: Any = None
        self.distance_input: Any = None
        self.operation_combo: Any = None
        self._build_widget()

    def _read_task_signed_distance(self) -> float:
        raw_val = 10.0
        if self.spinbox is not None and hasattr(self.spinbox, "value"):
            try:
                raw_val = float(self.spinbox.value())
            except Exception:
                raw_val = 10.0
        is_rev = False
        if self.checkbox_reversed is not None and hasattr(self.checkbox_reversed, "isChecked"):
            try:
                is_rev = bool(self.checkbox_reversed.isChecked())
            except Exception:
                is_rev = False
        return -abs(raw_val) if is_rev and raw_val >= 0.0 else raw_val

    def _build_widget(self) -> None:
        qt_core, qt_gui, qt_widgets = _get_qt()
        if (
            qt_widgets is None
            or not hasattr(qt_widgets, "QFrame")
            or not hasattr(qt_widgets, "QDoubleSpinBox")
        ):
            return
        try:
            frame = qt_widgets.QFrame(self.parent)
            frame.setObjectName("FMF_SmartExtrudeHud")
            if qt_core is not None and hasattr(qt_core, "Qt"):
                flags = getattr(qt_core.Qt, "WindowType", qt_core.Qt)
                tool_flag = getattr(flags, "ToolTip", None) or getattr(flags, "SubWindow", None)
                if tool_flag is not None and self.parent is None:
                    frame.setWindowFlags(tool_flag)
            frame.setStyleSheet(
                "QFrame#FMF_SmartExtrudeHud {"
                "  background-color: rgba(30, 34, 42, 235);"
                "  border: 1px solid #3b82f6;"
                "  border-radius: 6px;"
                "  padding: 4px 6px;"
                "}"
                "QLabel { color: #e2e8f0; font-size: 11px; font-weight: 600; }"
                "QDoubleSpinBox, QComboBox {"
                "  background-color: #0f172a;"
                "  color: #f8fafc;"
                "  border: 1px solid #475569;"
                "  border-radius: 4px;"
                "  padding: 2px 4px;"
                "  min-width: 72px;"
                "}"
            )
            layout = qt_widgets.QHBoxLayout(frame)
            layout.setContentsMargins(6, 4, 6, 4)
            layout.setSpacing(6)

            lbl = qt_widgets.QLabel("Dist:", frame)
            layout.addWidget(lbl)

            dist_spin = qt_widgets.QDoubleSpinBox(frame)
            dist_spin.setObjectName("FMF_ExtrudeHudDistance")
            dist_spin.setMinimum(-100000.0)
            dist_spin.setMaximum(100000.0)
            dist_spin.setDecimals(2)
            dist_spin.setSuffix(" mm")
            dist_spin.setValue(self._read_task_signed_distance())
            if hasattr(dist_spin, "valueChanged") and hasattr(dist_spin.valueChanged, "connect"):
                dist_spin.valueChanged.connect(self._on_hud_distance_changed)
            layout.addWidget(dist_spin)

            combo = qt_widgets.QComboBox(frame)
            combo.setObjectName("FMF_ExtrudeHudOperation")
            for op_key in self.OPERATIONS:
                combo.addItem(self.OPERATION_LABELS[op_key], op_key)
            combo.setCurrentIndex(self.OPERATIONS.index(self._operation))
            if hasattr(combo, "currentIndexChanged") and hasattr(
                combo.currentIndexChanged, "connect"
            ):
                combo.currentIndexChanged.connect(self._on_hud_operation_changed)
            layout.addWidget(combo)

            frame.adjustSize()
            if qt_gui is not None and hasattr(qt_gui, "QCursor"):
                cursor_pos = qt_gui.QCursor.pos()
                if self.parent is not None and hasattr(self.parent, "mapFromGlobal"):
                    local_pos = self.parent.mapFromGlobal(cursor_pos)
                    x = max(12, local_pos.x() + 18)
                    y = max(48, local_pos.y() + 18)
                    if hasattr(self.parent, "width") and hasattr(frame, "width"):
                        x = min(x, max(12, self.parent.width() - frame.width() - 16))
                    if hasattr(self.parent, "height") and hasattr(frame, "height"):
                        y = min(y, max(48, self.parent.height() - frame.height() - 16))
                    frame.move(x, y)

            self.widget = frame
            self.distance_input = dist_spin
            self.operation_combo = combo
        except Exception:
            self.widget = None

    def _on_hud_distance_changed(self, value: float) -> None:
        if self._syncing:
            return
        self.set_distance(value)

    def _on_hud_operation_changed(self, index: int) -> None:
        if 0 <= index < len(self.OPERATIONS):
            self._operation = self.OPERATIONS[index]

    def distance(self) -> float:
        """Return the current signed extrusion distance."""
        return self._read_task_signed_distance()

    def set_distance(self, signed_value: float) -> None:
        """Apply a signed distance (+ forward, - reversed) to the active task and HUD."""
        if self._syncing:
            return
        self._syncing = True
        try:
            want_reversed = signed_value < 0.0
            abs_val = abs(float(signed_value))
            if self.checkbox_reversed is not None and hasattr(self.checkbox_reversed, "setChecked"):
                self.checkbox_reversed.setChecked(want_reversed)
            if self.spinbox is not None and hasattr(self.spinbox, "setValue"):
                self.spinbox.setValue(abs_val)
            if self.distance_input is not None and hasattr(self.distance_input, "setValue"):
                try:
                    self.distance_input.setValue(float(signed_value))
                except Exception:
                    pass
        finally:
            self._syncing = False

    def sync_from_task(self) -> None:
        """Update HUD display when the task panel spinbox or reversed checkbox changes."""
        if self._syncing:
            return
        self._syncing = True
        try:
            signed = self._read_task_signed_distance()
            if self.distance_input is not None and hasattr(self.distance_input, "setValue"):
                self.distance_input.setValue(signed)
        finally:
            self._syncing = False

    def operation(self) -> str:
        return self._operation

    def set_operation(self, op_name: str) -> None:
        normalized = (op_name or "auto").strip().lower().replace(" ", "_")
        if normalized not in self.OPERATIONS:
            raise ValueError(f"Unsupported extrude operation: {op_name}")
        self._operation = normalized
        if self.operation_combo is not None and hasattr(self.operation_combo, "setCurrentIndex"):
            try:
                self.operation_combo.setCurrentIndex(self.OPERATIONS.index(self._operation))
            except Exception:
                pass

    def show(self) -> None:
        self._visible = True
        if self.widget is not None and hasattr(self.widget, "show"):
            try:
                self.widget.show()
                if hasattr(self.widget, "raise_"):
                    self.widget.raise_()
            except Exception:
                pass

    def is_visible(self) -> bool:
        if self.widget is not None and hasattr(self.widget, "isVisible"):
            try:
                return bool(self.widget.isVisible())
            except Exception:
                pass
        return self._visible

    def close(self) -> None:
        self._visible = False
        if self.widget is not None:
            try:
                if hasattr(self.widget, "hide"):
                    self.widget.hide()
                if hasattr(self.widget, "deleteLater"):
                    self.widget.deleteLater()
            except Exception:
                pass
            self.widget = None

    def accept(self) -> bool:
        """Accept the active extrude task on Enter/Return and close the HUD."""
        gui = _get_gui()
        control = getattr(gui, "Control", None) if gui is not None else None
        accepted = False
        if control is not None and hasattr(control, "accept"):
            try:
                control.accept()
                accepted = True
            except Exception:
                accepted = False
        close_extrude_hud()
        return accepted

    def cancel(self) -> bool:
        """Cancel the active extrude task on Escape and close the HUD."""
        gui = _get_gui()
        control = getattr(gui, "Control", None) if gui is not None else None
        rejected = False
        if control is not None and hasattr(control, "reject"):
            try:
                control.reject()
                rejected = True
            except Exception:
                rejected = False
        close_extrude_hud()
        return rejected

    def handle_key(self, key: str) -> bool:
        """Process 'Enter'/'Return' or 'Escape' keyboard shortcuts on the HUD."""
        norm = (key or "").strip().lower()
        if norm in ("enter", "return"):
            self.accept()
            return True
        if norm in ("esc", "escape"):
            self.cancel()
            return True
        return False


def get_active_extrude_hud() -> SmartExtrudeHud | None:
    """Return the active floating extrude HUD, if any."""
    return _active_extrude_hud


def close_extrude_hud() -> None:
    """Close and dispose the active floating extrude HUD."""
    global _active_extrude_hud
    if _active_extrude_hud is not None:
        _active_extrude_hud.close()
        _active_extrude_hud = None


def show_extrude_hud(
    info: dict[str, Any] | None = None, operation: str = "auto"
) -> SmartExtrudeHud | None:
    """Create or refresh the floating cursor HUD for the active extrude task."""
    global _active_extrude_hud
    if info is None:
        info = get_active_extrude_info()
    if not info or info.get("spinbox") is None:
        return None
    spinbox = info["spinbox"]
    checkbox = info.get("checkbox_reversed")
    gui = _get_gui()
    main_window = gui.getMainWindow() if gui is not None and hasattr(gui, "getMainWindow") else None
    if (
        _active_extrude_hud is not None
        and _active_extrude_hud.spinbox is spinbox
        and _active_extrude_hud.is_visible()
    ):
        _active_extrude_hud.sync_from_task()
        return _active_extrude_hud

    close_extrude_hud()
    hud = SmartExtrudeHud(
        spinbox=spinbox,
        checkbox_reversed=checkbox,
        parent=main_window,
        operation=operation,
    )
    hud.show()
    _active_extrude_hud = hud
    return hud


def enhance_active_extrude(info: dict[str, Any] | None = None, operation: str = "auto") -> bool:
    """Enable signed direction dragging, numeric input, and cursor HUD on active extrude."""
    if info is None:
        info = get_active_extrude_info()
    if not info:
        return False

    spinbox = info.get("spinbox")
    checkbox = info.get("checkbox_reversed")
    if spinbox is None:
        return False

    # Expand minimum bounds to allow dragging past zero into negative values
    if hasattr(spinbox, "minimum") and hasattr(spinbox, "setMinimum"):
        try:
            if spinbox.minimum() >= 0.0:
                spinbox.setMinimum(-100000.0)
        except Exception:
            pass

    hooked = False
    # Hook value change so crossing zero flips reversed direction
    if (
        checkbox is not None
        and hasattr(spinbox, "valueChanged")
        and not getattr(spinbox, "_fmf_signed_hooked", False)
    ):
        try:

            def _on_value_changed(val: float) -> None:
                if val < 0.0:
                    if hasattr(checkbox, "isChecked") and hasattr(checkbox, "setChecked"):
                        checkbox.setChecked(not checkbox.isChecked())
                    if hasattr(spinbox, "setValue"):
                        spinbox.setValue(abs(val))
                if _active_extrude_hud is not None:
                    _active_extrude_hud.sync_from_task()

            if hasattr(spinbox.valueChanged, "connect"):
                spinbox.valueChanged.connect(_on_value_changed)
            spinbox._fmf_signed_hooked = True
            hooked = True
        except Exception:
            pass

    show_extrude_hud(info, operation=operation)
    return hooked


def _activate_body_tip_visibility(body: Any, feat: Any, profile_obj: Any = None) -> None:
    """Ensure the newly created feature is the visible Tip of its Body."""
    if body is not None:
        try:
            body.Tip = feat
        except Exception:
            pass
        if hasattr(body, "Visibility"):
            try:
                body.Visibility = True
            except Exception:
                pass
    base_feat = getattr(feat, "BaseFeature", None)
    if base_feat is not None and hasattr(base_feat, "Visibility"):
        try:
            base_feat.Visibility = False
        except Exception:
            pass
    if (
        profile_obj is not None
        and profile_obj is not feat
        and hasattr(profile_obj, "Visibility")
        and getattr(profile_obj, "TypeId", "").startswith("Sketcher::")
    ):
        try:
            profile_obj.Visibility = False
        except Exception:
            pass
    if feat is not None and hasattr(feat, "Visibility"):
        try:
            feat.Visibility = True
        except Exception:
            pass


def _owning_body(profile_obj: Any, document: Any = None) -> Any | None:
    """Return the PartDesign::Body that directly owns profile_obj, if any."""
    if profile_obj is None:
        return None
    for parent in getattr(profile_obj, "InList", ()) or ():
        if getattr(parent, "TypeId", "") == "PartDesign::Body":
            return parent
    if document is not None:
        for obj in getattr(document, "Objects", ()) or ():
            if getattr(obj, "TypeId", "") == "PartDesign::Body":
                group = getattr(obj, "Group", ()) or ()
                if profile_obj in group:
                    return obj
    return None


def _active_body(document: Any = None, profile_obj: Any = None) -> Any:
    """Find the owning PartDesign::Body for profile_obj, the active body, or the first body."""
    app = _get_app()
    gui = _get_gui()
    doc = document or (getattr(app, "ActiveDocument", None) if app else None)
    if doc is None:
        return None

    # 1. Prefer the body that directly owns the profile object
    owner = _owning_body(profile_obj, doc)
    if owner is not None:
        return owner

    # 2. Check active object in active view (standard FreeCAD PartDesign active body)
    active_view = getattr(getattr(gui, "ActiveDocument", None), "ActiveView", None) if gui else None
    if active_view and hasattr(active_view, "getActiveObject"):
        try:
            pd_body = active_view.getActiveObject("pdbody")
            if pd_body is not None:
                return pd_body
        except Exception:
            pass

    # 3. Check doc.ActiveObject
    body = getattr(doc, "ActiveObject", None)
    if body and getattr(body, "TypeId", "") == "PartDesign::Body":
        return body

    # 4. Check doc.Objects
    for obj in getattr(doc, "Objects", []):
        if getattr(obj, "TypeId", "") == "PartDesign::Body":
            return obj
    return None


def _normalize_profile_subs(profile_obj: Any, sub_elements: list[str] | None) -> list[str]:
    """Normalize sketch sub-element list, upgrading open/multi-wire sketches to InternalFace1."""
    subs = [str(s) for s in (sub_elements or []) if s is not None]
    non_empty = [s for s in subs if s != ""]
    if non_empty:
        return non_empty

    if profile_obj is not None and (
        getattr(profile_obj, "TypeId", "").startswith("Sketcher::")
        or hasattr(profile_obj, "Geometry")
    ):
        shape = getattr(profile_obj, "Shape", None)
        internal = getattr(profile_obj, "InternalShape", None)
        if shape is not None and internal is not None:
            wires = getattr(shape, "Wires", []) or []
            faces = getattr(shape, "Faces", []) or []
            internal_faces = getattr(internal, "Faces", []) or []
            has_open_or_multi_wires = len(wires) > 1 or any(
                not getattr(w, "isClosed", lambda: True)() for w in wires
            )
            if len(faces) == 0 and len(internal_faces) > 0 and has_open_or_multi_wires:
                return ["InternalFace1"]
    return [""]


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
            face_subs = [s for s in subs if s.startswith("InternalFace") or s.startswith("Face")]
            if face_subs:
                return obj, face_subs
            return obj, _normalize_profile_subs(obj, subs)

        # Case B: Face of a solid
        face_subs = [s for s in subs if s.startswith("Face")]
        if face_subs:
            return obj, face_subs

    # Fallback to first selected object
    first = getattr(selection_ex[0], "Object", None)
    return first, _normalize_profile_subs(first, [""])


def _extract_test_face(
    profile_obj: Any,
    sub_elements: list[str] | None,
) -> tuple[Any | None, bool]:
    """Extract a planar test face and whether it requires local-to-global Placement."""
    sub_list = _normalize_profile_subs(profile_obj, sub_elements)
    internal = getattr(profile_obj, "InternalShape", None)
    if internal is not None and any(s.startswith("InternalFace") for s in sub_list):
        int_faces = getattr(internal, "Faces", []) or []
        if int_faces:
            idx = 0
            for s in sub_list:
                if s.startswith("InternalFace"):
                    suffix = s[len("InternalFace") :]
                    if suffix.isdigit():
                        idx = max(0, min(int(suffix) - 1, len(int_faces) - 1))
                        break
            target = int_faces[idx]
            return (target.copy() if hasattr(target, "copy") else target), True

    if hasattr(profile_obj, "Shape") and profile_obj.Shape is not None:
        prof_shape = profile_obj.Shape
        prof_faces = getattr(prof_shape, "Faces", []) or []
        if prof_faces:
            idx = 0
            for s in sub_list:
                if s.startswith("Face"):
                    suffix = s[len("Face") :]
                    if suffix.isdigit():
                        idx = max(0, min(int(suffix) - 1, len(prof_faces) - 1))
                        break
            target = prof_faces[idx]
            return (target.copy() if hasattr(target, "copy") else target), False

        # Standard FreeCAD SketchObject has 0 Shape.Faces and 1+ closed Shape.Wires
        prof_wires = getattr(prof_shape, "Wires", []) or []
        closed_wires = [w for w in prof_wires if getattr(w, "isClosed", lambda: False)()]
        if closed_wires:
            try:
                import Part

                made = Part.makeFace(closed_wires, "Part::FaceMakerBullseye")
                made_faces = getattr(made, "Faces", []) or []
                if made_faces:
                    return made_faces[0], False
            except Exception:
                pass

        # Fallback to InternalShape.Faces[0] if present
        if internal is not None:
            int_faces = getattr(internal, "Faces", []) or []
            if int_faces:
                target = int_faces[0]
                return (target.copy() if hasattr(target, "copy") else target), True

    return None, False


def _candidate_bodies(document: Any, preferred_body: Any = None) -> list[Any]:
    """Return candidate PartDesign::Body objects with existing solids, preferred first."""
    bodies: list[Any] = []
    if preferred_body is not None:
        bodies.append(preferred_body)
    if document is not None:
        for obj in getattr(document, "Objects", ()) or ():
            if (
                getattr(obj, "TypeId", "") == "PartDesign::Body"
                and obj not in bodies
                and getattr(obj, "Visibility", True) is not False
            ):
                bodies.append(obj)
    return bodies


def _body_has_solids(body: Any) -> bool:
    shape = getattr(body, "Shape", None) if body is not None else None
    return (
        shape is not None
        and not getattr(shape, "isNull", lambda: True)()
        and len(getattr(shape, "Solids", ())) > 0
    )


def classify_operation(
    profile_obj: Any,
    sub_elements: list[str] | None = None,
    length: float = 10.0,
    reversed_dir: bool = False,
    target_body: Any = None,
    allow_auto_reverse: bool = True,
    document: Any = None,
    prepared_face: Any = None,
) -> dict[str, Any]:
    """Classify the extrusion as join, cut, or new_body based on geometry."""
    app = _get_app()
    if length < 0.0:
        reversed_dir = not reversed_dir
        length = abs(length)

    candidates = [b for b in _candidate_bodies(document, target_body) if _body_has_solids(b)]

    if not candidates:
        return {
            "operation": "new_body" if target_body is None else "join",
            "auto_reverse": False,
            "target_body": target_body,
            "reason": "Target body has no existing solid",
            "confidence": 1.0,
        }

    primary_body = candidates[0]
    body_shape = getattr(primary_body, "Shape", None)

    # Extract face for test extrusion
    if prepared_face is None:
        face, needs_placement_transform = _extract_test_face(profile_obj, sub_elements)
    else:
        face, needs_placement_transform = prepared_face, False

    if face is None:
        return {
            "operation": "join",
            "auto_reverse": False,
            "target_body": primary_body,
            "reason": "Could not extract test face; defaulting to join",
            "confidence": 0.5,
        }

    try:
        # Placement alignment (only apply when face is in sketch-local InternalShape coordinates)
        pl = getattr(profile_obj, "Placement", None)
        if needs_placement_transform and pl is not None and hasattr(face, "Placement"):
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
                "target_body": primary_body,
                "reason": "Normal calculation unavailable",
                "confidence": 0.5,
            }

        eff_len = max(abs(length), 1e-3)
        sign = -1.0 if reversed_dir else 1.0
        dir_vec = normal * (sign * eff_len)
        rev_vec = normal * (-sign * eff_len)

        prism = face.extrude(dir_vec)
        prism_vol = (
            getattr(prism, "Volume", 0.0) if not getattr(prism, "isNull", lambda: True)() else 0.0
        )

        # 1. Volumetric penetration test across candidate bodies (Cut)
        for cand in candidates:
            c_shape = getattr(cand, "Shape", None)
            if c_shape is None or not hasattr(c_shape, "common"):
                continue
            common_shape = c_shape.common(prism)
            common_vol = (
                getattr(common_shape, "Volume", 0.0)
                if not getattr(common_shape, "isNull", lambda: True)()
                else 0.0
            )
            if common_vol > 1e-4 and (prism_vol <= 0.0 or common_vol > 0.01 * prism_vol):
                label = getattr(cand, "Label", getattr(cand, "Name", "Body"))
                return {
                    "operation": "cut",
                    "auto_reverse": False,
                    "target_body": cand,
                    "reason": f"Profile penetrates {label} (overlap volume: {common_vol:.2f})",
                    "confidence": 0.95,
                }

        # 2. Abutment / single-solid fuse test across candidate bodies (Join)
        for cand in candidates:
            c_shape = getattr(cand, "Shape", None)
            if c_shape is None:
                continue
            dist_fn = getattr(c_shape, "distToShape", None)
            dist = dist_fn(prism)[0] if callable(dist_fn) else 0.0
            if dist <= 1e-4:
                fuse_fn = getattr(c_shape, "fuse", None)
                fused = fuse_fn(prism) if callable(fuse_fn) else None
                fused_solids = len(getattr(fused, "Solids", [])) if fused else 1
                if fused_solids == 1:
                    label = getattr(cand, "Label", getattr(cand, "Name", "Body"))
                    return {
                        "operation": "join",
                        "auto_reverse": False,
                        "target_body": cand,
                        "reason": f"Profile abuts {label} and fuses into one solid",
                        "confidence": 0.95,
                    }

        # When dragging or evaluating an explicit signed direction (allow_auto_reverse=False),
        # if the prism neither penetrates a body nor merges into a single solid with a body,
        # it creates a New Body in this direction (Fusion 360 behavior).
        if not allow_auto_reverse:
            return {
                "operation": "new_body",
                "auto_reverse": False,
                "target_body": None,
                "reason": "Extrusion does not intersect any body in this direction",
                "confidence": 0.90,
            }

        # 3. Auto-reverse recovery (used for initial direction selection)
        rev_prism = face.extrude(rev_vec)
        dist_fn = getattr(body_shape, "distToShape", None)
        dist = dist_fn(prism)[0] if callable(dist_fn) else 0.0
        fuse_fn = getattr(body_shape, "fuse", None)

        if dist <= 1e-4:
            rev_fused = fuse_fn(rev_prism) if callable(fuse_fn) else None
            rev_fused_solids = len(getattr(rev_fused, "Solids", [])) if rev_fused else 0
            rev_common_vol = getattr(body_shape.common(rev_prism), "Volume", 0.0)
            if rev_common_vol > 1e-4:
                return {
                    "operation": "cut",
                    "auto_reverse": True,
                    "target_body": primary_body,
                    "reason": "Opposite direction penetrates body interior",
                    "confidence": 0.9,
                }
            elif rev_fused_solids == 1:
                return {
                    "operation": "join",
                    "auto_reverse": True,
                    "target_body": primary_body,
                    "reason": "Opposite direction fuses cleanly into body solid",
                    "confidence": 0.95,
                }
            return {
                "operation": "join",
                "auto_reverse": False,
                "target_body": primary_body,
                "reason": "Abutting profile",
                "confidence": 0.7,
            }

        rev_dist = dist_fn(rev_prism)[0] if callable(dist_fn) else 999.0
        if rev_dist <= 1e-4:
            rev_common_vol = getattr(body_shape.common(rev_prism), "Volume", 0.0)
            if rev_common_vol > 1e-4:
                return {
                    "operation": "cut",
                    "auto_reverse": True,
                    "target_body": primary_body,
                    "reason": "Current direction disconnected; opposite penetrates body",
                    "confidence": 0.9,
                }
            return {
                "operation": "join",
                "auto_reverse": True,
                "target_body": primary_body,
                "reason": "Current direction disconnected; opposite abuts body",
                "confidence": 0.9,
            }

        # 4. Disjoint in both directions -> New Body
        return {
            "operation": "new_body",
            "auto_reverse": False,
            "target_body": None,
            "reason": "Profile does not contact active body in either direction",
            "confidence": 0.85,
        }

    except Exception as exc:
        return {
            "operation": "join",
            "auto_reverse": False,
            "target_body": primary_body,
            "reason": f"Geometric classification failed ({exc}); defaulting to join",
            "confidence": 0.5,
        }


def _apply_extrude_common_props(
    feat: Any,
    length: float,
    reversed_dir: bool,
    symmetric: bool = False,
    taper_angle: float = 0.0,
) -> None:
    """Set common Pad/Pocket properties across FreeCAD 1.0/1.1."""
    feat.Length = abs(length)
    feat.Reversed = bool(reversed_dir)
    if symmetric:
        if hasattr(feat, "SideType"):
            try:
                feat.SideType = "Symmetric"
            except Exception:
                pass
        if hasattr(feat, "Midplane"):
            try:
                feat.Midplane = True
            except Exception:
                pass
    if abs(taper_angle) > 1e-6 and hasattr(feat, "TaperAngle"):
        try:
            feat.TaperAngle = float(taper_angle)
        except Exception:
            pass


def _bind_cross_body_profile_if_needed(
    target_body: Any,
    feat: Any,
    profile_obj: Any,
    sub_elements: list[str],
    doc: Any,
) -> None:
    """If profile_obj is owned by another Body and yields 0 solids, bind via SubShapeBinder."""
    shape = getattr(feat, "Shape", None)
    has_solids = (
        shape is not None
        and not getattr(shape, "isNull", lambda: False)()
        and len(getattr(shape, "Solids", ())) > 0
    )
    owning_body = _owning_body(profile_obj, doc)
    if (
        (shape is None or not has_solids)
        and owning_body is not None
        and owning_body != target_body
        and hasattr(target_body, "newObject")
    ):
        try:
            binder = target_body.newObject("PartDesign::SubShapeBinder", "Binder")
            clean_subs = tuple(s for s in sub_elements if s)
            binder.Support = [(profile_obj, clean_subs if clean_subs else ("Face1",))]
            if hasattr(binder, "recompute"):
                binder.recompute()
            feat.Profile = binder
            if hasattr(feat, "recompute"):
                feat.recompute()
            doc.recompute()
        except Exception:
            pass


def smart_extrude(
    operation: str = "auto",
    length: float = 10.0,
    reversed_dir: bool = False,
    profile: tuple[Any, list[str]] | None = None,
    document: Any = None,
    target_body: Any = None,
    symmetric: bool = False,
    taper_angle: float = 0.0,
    allow_auto_reverse: bool = True,
) -> dict[str, Any]:
    """Execute smart extrusion with automatic classification and fail-safe recovery."""
    app = _get_app()
    doc = document or (getattr(app, "ActiveDocument", None) if app else None)
    if doc is None:
        notify("Extrude", "No active document.", error=True)
        return {"status": "no-document"}

    if length < 0.0:
        reversed_dir = not reversed_dir
        length = abs(length)

    if profile is None:
        profile_obj, sub_elements = resolve_profile(document=doc)
    else:
        profile_obj, raw_subs = profile
        sub_elements = _normalize_profile_subs(profile_obj, raw_subs)

    if profile_obj is None:
        notify("Extrude", "Select a sketch or face to extrude.", error=True)
        return {"status": "no-selection"}

    if getattr(profile_obj, "TypeId", "").startswith("Sketcher::") or hasattr(
        profile_obj, "Geometry"
    ):
        test_face, _ = _extract_test_face(profile_obj, sub_elements)
        if test_face is None and getattr(profile_obj, "Geometry", None):
            try:
                import fmf_sketch_tools

                diagnosis = fmf_sketch_tools.diagnose_open_wires(profile_obj, tolerance=0.5)
                if not diagnosis["is_closed"]:
                    notify("Extrude", diagnosis["summary"], error=True)
                    return {
                        "status": "repair-available" if diagnosis["closable_gaps"] else "open-wire",
                        "diagnosis": diagnosis,
                    }
            except Exception:
                pass

    if target_body is None:
        target_body = _active_body(doc, profile_obj=profile_obj)

    effective_op = operation.lower()
    if effective_op not in {"auto", "join", "cut", "new_body"}:
        notify("Extrude", f"Unsupported operation: {operation}", error=True)
        return {"status": "unsupported-operation", "operation": effective_op}
    auto_reversed = False
    was_auto = effective_op == "auto"

    if was_auto:
        cls_result = classify_operation(
            profile_obj=profile_obj,
            sub_elements=sub_elements,
            length=length,
            reversed_dir=reversed_dir,
            target_body=target_body,
            allow_auto_reverse=allow_auto_reverse,
            document=doc,
        )
        effective_op = cls_result["operation"]
        if cls_result.get("target_body") is not None:
            target_body = cls_result["target_body"]
        if allow_auto_reverse and cls_result.get("auto_reverse", False):
            reversed_dir = not reversed_dir
            auto_reversed = True
        # FreeCAD's PartDesign::Pocket uses an inverted profile normal (-normal when Reversed=False,
        # +normal when Reversed=True), opposite to PartDesign::Pad.
        if effective_op == "cut" and cls_result.get("confidence", 0.0) >= 0.8:
            reversed_dir = not reversed_dir

    try:
        with transaction(doc, f"Smart Extrude ({effective_op.title()})"):
            if effective_op == "new_body" or target_body is None:
                # Create a new PartDesign::Body
                new_body = doc.addObject("PartDesign::Body", "Body")
                new_body.Label = "Body"
                owning_body = _owning_body(profile_obj, doc)
                profile_for_pad: Any = (profile_obj, sub_elements)

                if (
                    owning_body is None
                    and hasattr(profile_obj, "isDerivedFrom")
                    and profile_obj.isDerivedFrom("Sketcher::SketchObject")
                ):
                    # Move freestanding sketch into new_body
                    if hasattr(new_body, "addObject"):
                        try:
                            new_body.addObject(profile_obj)
                        except Exception:
                            pass
                elif (
                    owning_body is not None
                    and owning_body != new_body
                    and hasattr(new_body, "newObject")
                ):
                    # Profile is owned by another Body: link via SubShapeBinder for independence
                    try:
                        binder = new_body.newObject("PartDesign::SubShapeBinder", "Binder")
                        clean_subs = tuple(s for s in sub_elements if s)
                        binder.Support = [(profile_obj, clean_subs if clean_subs else ("Face1",))]
                        if hasattr(binder, "recompute"):
                            binder.recompute()
                        profile_for_pad = binder
                    except Exception:
                        profile_for_pad = (profile_obj, sub_elements)

                if hasattr(new_body, "newObject"):
                    feat = new_body.newObject("PartDesign::Pad", "Pad")
                else:
                    feat = doc.addObject("PartDesign::Pad", "Pad")
                    if hasattr(new_body, "addObject"):
                        new_body.addObject(feat)

                feat.Profile = profile_for_pad
                _apply_extrude_common_props(
                    feat, length, reversed_dir, symmetric=symmetric, taper_angle=taper_angle
                )
                if hasattr(feat, "recompute"):
                    feat.recompute()
                doc.recompute()

                _bind_cross_body_profile_if_needed(new_body, feat, profile_obj, sub_elements, doc)
                _activate_body_tip_visibility(new_body, feat, profile_obj)
                notify("Extrude", f"Created new Body with Pad ({abs(length):.1f} mm).")
                return {
                    "status": "ok",
                    "operation": "new_body",
                    "body": new_body,
                    "feature": feat,
                    "auto_reversed": auto_reversed,
                }

            elif effective_op == "cut":
                prev_body_shape = getattr(target_body, "Shape", None)
                prev_vol = (
                    getattr(prev_body_shape, "Volume", 0.0)
                    if prev_body_shape is not None
                    and not getattr(prev_body_shape, "isNull", lambda: True)()
                    else 0.0
                )

                feat_label = "Pocket"
                if hasattr(target_body, "newObject"):
                    feat = target_body.newObject("PartDesign::Pocket", feat_label)
                else:
                    feat = doc.addObject("PartDesign::Pocket", feat_label)
                    if hasattr(target_body, "addObject"):
                        target_body.addObject(feat)

                feat.Profile = (profile_obj, sub_elements)
                _apply_extrude_common_props(
                    feat, length, reversed_dir, symmetric=symmetric, taper_angle=taper_angle
                )
                if hasattr(feat, "recompute"):
                    feat.recompute()
                doc.recompute()

                _bind_cross_body_profile_if_needed(
                    target_body, feat, profile_obj, sub_elements, doc
                )

                # Verify that the Pocket/Intersect produced a valid solid and reduced volume
                shape = getattr(feat, "Shape", None)
                if shape is not None and hasattr(feat, "Reversed"):
                    solids = getattr(shape, "Solids", ())
                    new_vol = getattr(shape, "Volume", 0.0) if len(solids) > 0 else 0.0
                    did_cut = len(solids) > 0 and (prev_vol <= 0.0 or new_vol < prev_vol - 1e-4)
                    if not did_cut:
                        feat.Reversed = not reversed_dir
                        if hasattr(feat, "recompute"):
                            feat.recompute()
                        doc.recompute()
                        flipped_shape = getattr(feat, "Shape", None)
                        flipped_solids = (
                            getattr(flipped_shape, "Solids", ())
                            if flipped_shape is not None
                            else ()
                        )
                        flipped_vol = (
                            getattr(flipped_shape, "Volume", 0.0)
                            if len(flipped_solids) > 0
                            else 0.0
                        )
                        flipped_cut = len(flipped_solids) > 0 and (
                            prev_vol <= 0.0 or flipped_vol < prev_vol - 1e-4
                        )
                        if flipped_cut:
                            auto_reversed = True
                            event("info", "extrude", "auto_reverse", "recovered_pocket_direction")
                        else:
                            feat.Reversed = reversed_dir
                            if hasattr(feat, "recompute"):
                                feat.recompute()
                            doc.recompute()

                _activate_body_tip_visibility(target_body, feat, profile_obj)
                notify("Extrude", f"Created {feat_label} ({abs(length):.1f} mm).")
                return {
                    "status": "ok",
                    "operation": effective_op,
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
                _apply_extrude_common_props(
                    feat, length, reversed_dir, symmetric=symmetric, taper_angle=taper_angle
                )
                if hasattr(feat, "recompute"):
                    feat.recompute()
                doc.recompute()

                _bind_cross_body_profile_if_needed(
                    target_body, feat, profile_obj, sub_elements, doc
                )

                # Guard against empty solid or disconnected multi-solid failure
                shape = getattr(feat, "Shape", None)
                if allow_auto_reverse and shape is not None and hasattr(feat, "Reversed"):
                    solids = (
                        getattr(shape, "Solids", ())
                        if not getattr(shape, "isNull", lambda: False)()
                        else ()
                    )
                    needs_recovery = len(solids) == 0 or len(solids) > 1
                    if needs_recovery:
                        feat.Reversed = not reversed_dir
                        if hasattr(feat, "recompute"):
                            feat.recompute()
                        doc.recompute()
                        flipped_shape = getattr(feat, "Shape", None)
                        flipped_solids = (
                            getattr(flipped_shape, "Solids", ())
                            if flipped_shape is not None
                            and not getattr(flipped_shape, "isNull", lambda: True)()
                            else ()
                        )
                        if len(flipped_solids) == 1 or (
                            len(solids) == 0 and len(flipped_solids) > 0
                        ):
                            auto_reversed = True
                            event("info", "extrude", "auto_reverse", "recovered_empty_solid")
                        else:
                            # Revert if flipping didn't improve solid continuity
                            feat.Reversed = reversed_dir
                            if hasattr(feat, "recompute"):
                                feat.recompute()
                            doc.recompute()

                _activate_body_tip_visibility(target_body, feat, profile_obj)
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


class SmartExtrudeDragger:
    """Coin3D signed 3D arrow dragger and real-time boolean preview in the 3D viewport."""

    OPERATION_COLORS: ClassVar[dict[str, tuple[float, float, float]]] = {
        "join": (0.18, 0.62, 0.98),
        "cut": (0.94, 0.24, 0.24),
        "new_body": (0.18, 0.80, 0.52),
    }

    def __init__(self, on_drag_distance: Any = None) -> None:
        self.on_drag_distance = on_drag_distance
        self.scene_graph: Any = None
        self.root_sep: Any = None
        self.preview_sep: Any = None
        self.dragger_sep: Any = None
        self.origin_trans: Any = None
        self.axis_rot: Any = None
        self.dragger: Any = None
        self._updating_dragger = False
        self._last_flip: bool | None = None
        self._last_op: str | None = None
        self._hidden_body: Any = None

    def _get_coin(self) -> Any | None:
        try:
            import pivy.coin as coin

            return coin
        except ImportError:
            return None

    def attach(
        self,
        center: tuple[float, float, float],
        normal: tuple[float, float, float],
        signed_distance: float,
        operation: str = "join",
    ) -> bool:
        """Attach the signed 3D arrow dragger and preview root to the active 3D view."""
        self.detach()
        gui = _get_gui()
        coin = self._get_coin()
        if gui is None or coin is None:
            return False
        active_doc = getattr(gui, "ActiveDocument", None)
        active_view = getattr(active_doc, "ActiveView", None) if active_doc else None
        if active_view is None or not hasattr(active_view, "getSceneGraph"):
            return False
        try:
            sg = active_view.getSceneGraph()
            if sg is None:
                return False

            self.scene_graph = sg
            self.root_sep = coin.SoSeparator()
            self.preview_sep = coin.SoSeparator()
            self.dragger_sep = coin.SoSeparator()
            self.root_sep.addChild(self.preview_sep)
            self.root_sep.addChild(self.dragger_sep)

            self.origin_trans = coin.SoTranslation()
            self.origin_trans.translation.setValue(
                float(center[0]), float(center[1]), float(center[2])
            )
            self.dragger_sep.addChild(self.origin_trans)

            self.axis_rot = coin.SoRotation()
            nx, ny, nz = float(normal[0]), float(normal[1]), float(normal[2])
            self.axis_rot.rotation.setValue(
                coin.SbRotation(coin.SbVec3f(1.0, 0.0, 0.0), coin.SbVec3f(nx, ny, nz))
            )
            self.dragger_sep.addChild(self.axis_rot)

            self.dragger = coin.SoTranslate1Dragger()
            self._rebuild_arrow_parts(signed_distance < 0.0, operation)
            self._updating_dragger = True
            try:
                self.dragger.translation.setValue(float(signed_distance), 0.0, 0.0)
            finally:
                self._updating_dragger = False

            self.dragger.addMotionCallback(self._on_motion_cb)
            self.dragger_sep.addChild(self.dragger)
            sg.addChild(self.root_sep)
            return True
        except Exception:
            self.detach()
            return False

    def _build_arrow_geometry(self, active: bool, flip_head: bool, operation: str) -> Any:
        coin = self._get_coin()
        sep = coin.SoSeparator()
        mat = coin.SoMaterial()
        if active:
            mat.diffuseColor.setValue(1.0, 0.85, 0.15)
            mat.emissiveColor.setValue(0.35, 0.28, 0.0)
        else:
            rgb = self.OPERATION_COLORS.get(operation, (0.18, 0.62, 0.98))
            mat.diffuseColor.setValue(*rgb)
            mat.emissiveColor.setValue(rgb[0] * 0.25, rgb[1] * 0.25, rgb[2] * 0.25)
        sep.addChild(mat)

        # Base sphere at the arrow anchor
        base_sphere = coin.SoSphere()
        base_sphere.radius = 1.6
        sep.addChild(base_sphere)

        # Rotate local +Y (SoCylinder/SoCone axis) to +X (or -X when flipped past zero)
        target_dir = coin.SbVec3f(-1.0, 0.0, 0.0) if flip_head else coin.SbVec3f(1.0, 0.0, 0.0)
        rot = coin.SoRotation()
        rot.rotation.setValue(coin.SbRotation(coin.SbVec3f(0.0, 1.0, 0.0), target_dir))
        sep.addChild(rot)

        shaft_trans = coin.SoTranslation()
        shaft_trans.translation.setValue(0.0, 4.5, 0.0)
        sep.addChild(shaft_trans)

        cyl = coin.SoCylinder()
        cyl.radius = 0.9
        cyl.height = 9.0
        sep.addChild(cyl)

        tip_trans = coin.SoTranslation()
        tip_trans.translation.setValue(0.0, 6.5, 0.0)
        sep.addChild(tip_trans)

        cone = coin.SoCone()
        cone.bottomRadius = 2.6
        cone.height = 5.5
        sep.addChild(cone)
        return sep

    def _rebuild_arrow_parts(self, flip_head: bool, operation: str) -> None:
        if self.dragger is None:
            return
        if self._last_flip == flip_head and self._last_op == operation:
            return
        self._last_flip = flip_head
        self._last_op = operation
        try:
            self.dragger.setPart(
                "translator", self._build_arrow_geometry(False, flip_head, operation)
            )
            self.dragger.setPart(
                "translatorActive",
                self._build_arrow_geometry(True, flip_head, operation),
            )
        except Exception:
            pass

    def _on_motion_cb(self, *_args: Any) -> None:
        if self._updating_dragger or self.dragger is None:
            return
        try:
            val = self.dragger.translation.getValue()
            signed_x = float(val[0])
            # Snap very small values near zero only if not actively crossing
            if callable(self.on_drag_distance):
                self.on_drag_distance(signed_x)
        except Exception:
            pass

    def sync_position(self, signed_distance: float, operation: str) -> None:
        """Update the 3D arrow position and orientation without triggering motion feedback."""
        self._rebuild_arrow_parts(signed_distance < 0.0, operation)
        if self.dragger is None:
            return
        self._updating_dragger = True
        try:
            curr = self.dragger.translation.getValue()
            if abs(float(curr[0]) - float(signed_distance)) > 1e-4:
                self.dragger.translation.setValue(float(signed_distance), 0.0, 0.0)
        except Exception:
            pass
        finally:
            self._updating_dragger = False

    def _restore_hidden_body(self) -> None:
        if self._hidden_body is not None:
            try:
                self._hidden_body.Visibility = True
            except Exception:
                pass
            self._hidden_body = None

    def update_preview(
        self,
        prism_shape: Any,
        result_shape: Any,
        operation: str,
        target_body: Any = None,
    ) -> None:
        """Render the live 3D boolean preview and colored tool prism in the viewport."""
        coin = self._get_coin()
        if coin is None or self.preview_sep is None:
            return
        try:
            self.preview_sep.removeAllChildren()
            if target_body is not self._hidden_body:
                self._restore_hidden_body()

            # For Cut / Intersect, temporarily hide target_body and render result_shape live
            if (
                operation == "cut"
                and target_body is not None
                and result_shape is not None
                and hasattr(result_shape, "writeInventor")
            ):
                if self._hidden_body is None and getattr(target_body, "Visibility", True):
                    try:
                        target_body.Visibility = False
                        self._hidden_body = target_body
                    except Exception:
                        pass
                res_sep = coin.SoSeparator()
                res_mat = coin.SoMaterial()
                res_mat.diffuseColor.setValue(0.78, 0.80, 0.84)
                res_mat.specularColor.setValue(0.3, 0.3, 0.3)
                res_mat.shininess = 0.4
                res_sep.addChild(res_mat)
                inp = coin.SoInput()
                inp.setBuffer(result_shape.writeInventor())
                node = coin.SoDB.readAll(inp)
                if node is not None:
                    res_sep.addChild(node)
                    self.preview_sep.addChild(res_sep)
            else:
                self._restore_hidden_body()

            # Render the translucent colored tool prism
            if prism_shape is not None and hasattr(prism_shape, "writeInventor"):
                tool_sep = coin.SoSeparator()
                tool_mat = coin.SoMaterial()
                rgb = self.OPERATION_COLORS.get(operation, (0.18, 0.62, 0.98))
                tool_mat.diffuseColor.setValue(*rgb)
                tool_mat.transparency.setValue(0.50 if operation == "cut" else 0.32)
                tool_sep.addChild(tool_mat)
                inp = coin.SoInput()
                inp.setBuffer(prism_shape.writeInventor())
                node = coin.SoDB.readAll(inp)
                if node is not None:
                    tool_sep.addChild(node)
                    self.preview_sep.addChild(tool_sep)
        except Exception:
            pass

    def detach(self) -> None:
        """Remove Coin3D preview and dragger nodes and restore body visibility."""
        self._restore_hidden_body()
        if self.scene_graph is not None and self.root_sep is not None:
            try:
                self.scene_graph.removeChild(self.root_sep)
            except Exception:
                pass
        self.scene_graph = None
        self.root_sep = None
        self.preview_sep = None
        self.dragger_sep = None
        self.dragger = None
        self._last_flip = None
        self._last_op = None


class SmartExtrudeSession:
    """Interactive Fusion 360-style Smart Extrude session state and live preview coordinator."""

    OPERATIONS: ClassVar[tuple[str, ...]] = (
        "auto",
        "join",
        "cut",
        "new_body",
    )

    def __init__(
        self,
        document: Any = None,
        profile: tuple[Any, list[str]] | None = None,
        initial_distance: float = 10.0,
        operation_mode: str = "auto",
    ) -> None:
        app = _get_app()
        self.document = document or (getattr(app, "ActiveDocument", None) if app else None)
        self.profile_obj: Any = None
        self.sub_elements: list[str] = []
        self.signed_distance: float = float(initial_distance)
        self.symmetric: bool = False
        self.taper_angle: float = 0.0
        self.operation_mode: str = (operation_mode or "auto").lower()
        if self.operation_mode not in self.OPERATIONS:
            self.operation_mode = "auto"

        self.resolved_operation: str = "join"
        self.target_body: Any = None
        self.reason: str = "Select a sketch or face to extrude."
        self.prism_shape: Any = None
        self.result_shape: Any = None
        self.dragger = SmartExtrudeDragger(on_drag_distance=self._on_dragger_moved)
        self._listeners: list[Any] = []
        self._committed = False
        self._target_body_explicit = False
        self._cached_face_frame: (
            tuple[
                Any | None,
                tuple[float, float, float],
                tuple[float, float, float],
            ]
            | None
        ) = None
        self._drag_update_scheduled = False
        self._closed = False

        if profile is not None and profile[0] is not None:
            self.set_profile(profile[0], profile[1], pick_initial_direction=True)
        elif self.document is not None:
            prof_obj, subs = resolve_profile(document=self.document)
            if prof_obj is not None:
                self.set_profile(prof_obj, subs, pick_initial_direction=True)

    def add_listener(self, callback: Any) -> None:
        if callable(callback) and callback not in self._listeners:
            self._listeners.append(callback)

    def _notify_listeners(self) -> None:
        for cb in list(self._listeners):
            try:
                cb(self)
            except Exception:
                pass

    def _extract_world_face_and_frame(
        self,
    ) -> tuple[Any | None, tuple[float, float, float], tuple[float, float, float]]:
        """Return (world_face, center_xyz, normal_xyz)."""
        if self._cached_face_frame is not None:
            return self._cached_face_frame
        if self.profile_obj is None:
            return None, (0.0, 0.0, 0.0), (0.0, 0.0, 1.0)
        face, needs_pl = _extract_test_face(self.profile_obj, self.sub_elements)
        if face is None:
            return None, (0.0, 0.0, 0.0), (0.0, 0.0, 1.0)
        try:
            pl = getattr(self.profile_obj, "Placement", None)
            if needs_pl and pl is not None and hasattr(face, "Placement"):
                face.Placement = pl.multiply(face.Placement)
        except Exception:
            pass

        normal_xyz = (0.0, 0.0, 1.0)
        try:
            if hasattr(face, "normalAt"):
                n = face.normalAt(0, 0)
                if n is not None:
                    normal_xyz = (float(n.x), float(n.y), float(n.z))
        except Exception:
            pass

        center_xyz = (0.0, 0.0, 0.0)
        try:
            com = getattr(face, "CenterOfMass", None) or getattr(
                getattr(face, "BoundBox", None), "Center", None
            )
            if com is not None:
                center_xyz = (float(com.x), float(com.y), float(com.z))
        except Exception:
            pass

        self._cached_face_frame = (face, center_xyz, normal_xyz)
        return self._cached_face_frame

    def set_profile(
        self,
        profile_obj: Any,
        sub_elements: list[str] | None = None,
        pick_initial_direction: bool = True,
    ) -> None:
        """Set or switch the active extrusion profile and attach the 3D arrow dragger."""
        self.profile_obj = profile_obj
        self.sub_elements = _normalize_profile_subs(profile_obj, sub_elements)
        self._cached_face_frame = None
        default_body = _active_body(self.document, profile_obj=profile_obj)
        self.target_body = default_body
        self._target_body_explicit = False

        if pick_initial_direction and profile_obj is not None:
            init_cls = classify_operation(
                profile_obj=profile_obj,
                sub_elements=self.sub_elements,
                length=abs(self.signed_distance) or 10.0,
                reversed_dir=(self.signed_distance < 0.0),
                target_body=default_body,
                allow_auto_reverse=True,
                document=self.document,
            )
            if init_cls.get("auto_reverse", False):
                self.signed_distance = -self.signed_distance

        face, center_xyz, normal_xyz = self._extract_world_face_and_frame()
        if face is not None:
            self.dragger.attach(
                center=center_xyz,
                normal=normal_xyz,
                signed_distance=self.signed_distance,
                operation=self.resolved_operation,
            )
        self.evaluate()

    def _on_dragger_moved(self, new_signed_distance: float) -> None:
        self.signed_distance = float(new_signed_distance)
        if self._drag_update_scheduled or self._closed:
            return
        qt_core, _qt_gui, _qt_widgets = _get_qt()
        timer = getattr(qt_core, "QTimer", None) if qt_core is not None else None
        if timer is not None and hasattr(timer, "singleShot"):
            self._drag_update_scheduled = True
            timer.singleShot(16, self._flush_drag_update)
        else:
            self.evaluate(sync_dragger=False)

    def _flush_drag_update(self) -> None:
        self._drag_update_scheduled = False
        if not self._closed:
            self.evaluate(sync_dragger=False)

    def set_signed_distance(self, value: float, from_dragger: bool = False) -> None:
        """Set signed extrusion distance (+ forward, - reversed) and re-evaluate live operation."""
        self.signed_distance = float(value)
        self.evaluate(sync_dragger=not from_dragger)

    def flip_direction(self) -> None:
        """Flip the extrusion direction across the profile plane."""
        self.set_signed_distance(-self.signed_distance)

    def set_operation_mode(self, mode: str) -> None:
        norm = (mode or "auto").strip().lower().replace(" ", "_")
        if norm not in self.OPERATIONS:
            raise ValueError(f"Unsupported operation mode: {mode}")
        self.operation_mode = norm
        self.evaluate()

    def set_symmetric(self, symmetric: bool) -> None:
        self.symmetric = bool(symmetric)
        self.evaluate()

    def set_taper_angle(self, angle: float) -> None:
        self.taper_angle = float(angle)
        self.evaluate()

    def set_target_body(self, body: Any) -> None:
        self.target_body = body
        self._target_body_explicit = body is not None
        self.evaluate()

    def evaluate(self, sync_dragger: bool = True) -> dict[str, Any]:
        """Re-evaluate operation classification and update the 3D viewport preview."""
        if self.profile_obj is None:
            self.reason = "Select a sketch or face in the viewport."
            self.prism_shape = None
            self.result_shape = None
            self.dragger.detach()
            self._notify_listeners()
            return {"status": "no-profile"}

        default_body = self.target_body or _active_body(self.document, profile_obj=self.profile_obj)
        abs_len = abs(self.signed_distance)
        is_rev = self.signed_distance < 0.0

        if self.operation_mode == "auto":
            cls = classify_operation(
                profile_obj=self.profile_obj,
                sub_elements=self.sub_elements,
                length=max(abs_len, 0.1),
                reversed_dir=is_rev,
                target_body=default_body,
                allow_auto_reverse=False,
                document=None if self._target_body_explicit else self.document,
                prepared_face=self._extract_world_face_and_frame()[0],
            )
            self.resolved_operation = cls["operation"]
            if cls.get("target_body") is not None or self.resolved_operation == "new_body":
                self.target_body = cls.get("target_body")
            else:
                self.target_body = default_body
            self.reason = cls.get("reason", "")
        else:
            self.resolved_operation = self.operation_mode
            if self.resolved_operation == "new_body":
                self.target_body = None
                self.reason = "Creates an independent new Body"
            else:
                if self.target_body is None:
                    self.target_body = default_body
                target_lbl = getattr(
                    self.target_body,
                    "Label",
                    getattr(self.target_body, "Name", "Body"),
                )
                self.reason = f"{self.resolved_operation.replace('_', ' ').title()} on {target_lbl}"

        # Build live 3D preview shapes
        face, _center_xyz, normal_xyz = self._extract_world_face_and_frame()
        self.prism_shape = None
        self.result_shape = None
        app = _get_app()
        if face is not None and abs_len > 1e-3 and hasattr(face, "extrude"):
            try:
                if app is not None and hasattr(app, "Vector"):
                    n_vec = app.Vector(*normal_xyz)
                else:
                    n_vec = face.normalAt(0, 0)
                if self.symmetric:
                    work_face = face.copy() if hasattr(face, "copy") else face
                    if hasattr(work_face, "translate"):
                        work_face.translate(n_vec * (-0.5 * abs_len))
                    self.prism_shape = work_face.extrude(n_vec * abs_len)
                else:
                    sign = -1.0 if is_rev else 1.0
                    self.prism_shape = face.extrude(n_vec * (sign * abs_len))

                body_shape = (
                    getattr(self.target_body, "Shape", None)
                    if self.target_body is not None
                    else None
                )
                if (
                    body_shape is not None
                    and self.prism_shape is not None
                    and not getattr(body_shape, "isNull", lambda: True)()
                ):
                    if self.resolved_operation == "cut" and hasattr(body_shape, "cut"):
                        self.result_shape = body_shape.cut(self.prism_shape)
                    elif self.resolved_operation == "join" and hasattr(body_shape, "fuse"):
                        self.result_shape = body_shape.fuse(self.prism_shape)
            except Exception:
                pass

        self.dragger.sync_position(self.signed_distance, self.resolved_operation)
        self.dragger.update_preview(
            self.prism_shape,
            self.result_shape,
            self.resolved_operation,
            self.target_body,
        )
        self._notify_listeners()
        return {
            "status": "ok",
            "operation": self.resolved_operation,
            "signed_distance": self.signed_distance,
            "target_body": self.target_body,
            "reason": self.reason,
        }

    def commit(self) -> dict[str, Any]:
        """Commit the previewed extrusion as a native FreeCAD feature."""
        if self._committed:
            return {"status": "already-committed"}
        self.dragger.detach()
        if self.profile_obj is None:
            notify("Extrude", "Select a sketch or face to extrude.", error=True)
            return {"status": "no-selection"}

        op = self.resolved_operation
        abs_len = max(abs(self.signed_distance), 0.01)
        world_rev = self.signed_distance < 0.0
        # PartDesign::Pocket extrudes along -normal when Reversed=False, opposite to Pad
        feat_rev = (not world_rev) if op == "cut" else world_rev

        result = smart_extrude(
            operation=op,
            length=abs_len,
            reversed_dir=feat_rev,
            profile=(self.profile_obj, self.sub_elements),
            document=self.document,
            target_body=self.target_body,
            symmetric=self.symmetric,
            taper_angle=self.taper_angle,
            allow_auto_reverse=False,
        )
        if result.get("status") == "ok":
            self._committed = True
            self._closed = True
        return result

    def cancel(self) -> None:
        """Cancel the interactive session and remove all temporary preview geometry."""
        self._closed = True
        self.dragger.detach()


_active_extrude_session: SmartExtrudeSession | None = None


def get_active_extrude_session() -> SmartExtrudeSession | None:
    """Return the currently active interactive SmartExtrudeSession, if any."""
    return _active_extrude_session


class _ProfileSelectionObserver:
    """Selection observer that feeds newly clicked sketches/faces into SmartExtrudeTaskPanel."""

    def __init__(self, on_selection_changed: Any) -> None:
        self._callback = on_selection_changed

    def addSelection(self, doc: str, obj: str, sub: str, _pnt: Any = None) -> None:
        if callable(self._callback):
            self._callback(doc, obj, sub)


class SmartExtrudeTaskPanel:
    """Fusion 360-style Smart Extrude Task Panel for FreeCAD Gui.Control.showDialog."""

    OPERATION_ITEMS: ClassVar[tuple[tuple[str, str], ...]] = (
        ("auto", "Auto (Join / Cut / New Body)"),
        ("join", "Join"),
        ("cut", "Cut"),
        ("new_body", "New Body"),
    )

    BADGE_STYLES: ClassVar[dict[str, str]] = {
        "join": "background-color: #1d4ed8; color: #ffffff; border: 1px solid #60a5fa;",
        "cut": "background-color: #b91c1c; color: #ffffff; border: 1px solid #f87171;",
        "new_body": "background-color: #047857; color: #ffffff; border: 1px solid #34d399;",
    }

    def __init__(self, session: SmartExtrudeSession) -> None:
        global _active_extrude_session
        self.session = session
        _active_extrude_session = session
        self._syncing_ui = False
        self._selecting_profile = session.profile_obj is None
        self._observer: _ProfileSelectionObserver | None = None

        self.form: Any = None
        self.badge_label: Any = None
        self.profile_label: Any = None
        self.select_profile_btn: Any = None
        self.direction_combo: Any = None
        self.flip_btn: Any = None
        self.distance_spin: Any = None
        self.taper_spin: Any = None
        self.operation_combo: Any = None
        self.body_combo: Any = None
        self.reason_label: Any = None
        self.reversed_check: Any = None

        self._build_ui()
        self._install_selection_observer()
        self.session.add_listener(self._sync_from_session)
        self._sync_from_session(self.session)

    def _build_ui(self) -> None:
        _qt_core, _qt_gui, qt_widgets = _get_qt()
        if qt_widgets is None or not hasattr(qt_widgets, "QWidget"):
            return
        try:
            root = qt_widgets.QWidget()
            root.setObjectName("FMF_SmartExtrudeTaskPanel")
            if hasattr(root, "setWindowTitle"):
                root.setWindowTitle("Smart Extrude")
            root.setStyleSheet(
                "QWidget#FMF_SmartExtrudeTaskPanel {"
                "  background-color: #1e222a; color: #e2e8f0; font-size: 12px;"
                "}"
                "QLabel { color: #cbd5e1; }"
                "QDoubleSpinBox, QComboBox, QPushButton {"
                "  background-color: #0f172a; color: #f8fafc;"
                "  border: 1px solid #334155; border-radius: 4px; padding: 4px 6px;"
                "}"
                "QPushButton:hover { border-color: #3b82f6; background-color: #1e293b; }"
            )

            outer = qt_widgets.QVBoxLayout(root)
            outer.setContentsMargins(10, 10, 10, 10)
            outer.setSpacing(8)

            # 1. Header + Live Operation Badge
            header_row = qt_widgets.QHBoxLayout()
            title_lbl = qt_widgets.QLabel("<b>SMART EXTRUDE</b>", root)
            header_row.addWidget(title_lbl)
            self.badge_label = qt_widgets.QLabel("AUTO: JOIN", root)
            self.badge_label.setObjectName("FMF_ExtrudeOperationBadge")
            header_row.addWidget(self.badge_label)
            outer.addLayout(header_row)

            # 2. Profile selector row
            prof_row = qt_widgets.QHBoxLayout()
            prof_row.addWidget(qt_widgets.QLabel("Profile:", root))
            self.profile_label = qt_widgets.QLabel("None", root)
            self.profile_label.setObjectName("FMF_ExtrudeProfileLabel")
            prof_row.addWidget(self.profile_label)
            self.select_profile_btn = qt_widgets.QPushButton("Select", root)
            self.select_profile_btn.setObjectName("FMF_ExtrudeSelectProfileBtn")
            if hasattr(self.select_profile_btn, "clicked"):
                self.select_profile_btn.clicked.connect(self._on_toggle_select_profile)
            prof_row.addWidget(self.select_profile_btn)
            outer.addLayout(prof_row)

            # 3. Direction row (One Side / Symmetric + Flip button)
            dir_row = qt_widgets.QHBoxLayout()
            dir_row.addWidget(qt_widgets.QLabel("Direction:", root))
            self.direction_combo = qt_widgets.QComboBox(root)
            self.direction_combo.setObjectName("FMF_ExtrudeDirectionCombo")
            self.direction_combo.addItem("One Side", "one_side")
            self.direction_combo.addItem("Symmetric", "symmetric")
            if hasattr(self.direction_combo, "currentIndexChanged"):
                self.direction_combo.currentIndexChanged.connect(self._on_direction_mode_changed)
            dir_row.addWidget(self.direction_combo)

            self.flip_btn = qt_widgets.QPushButton("Flip ⇄", root)
            self.flip_btn.setObjectName("FMF_ExtrudeFlipBtn")
            self.flip_btn.setToolTip("Reverse extrusion direction (or drag arrow past 0)")
            if hasattr(self.flip_btn, "clicked"):
                self.flip_btn.clicked.connect(self._on_flip_clicked)
            dir_row.addWidget(self.flip_btn)
            outer.addLayout(dir_row)

            # 4. Signed Distance row
            dist_row = qt_widgets.QHBoxLayout()
            dist_row.addWidget(qt_widgets.QLabel("Distance:", root))
            self.distance_spin = qt_widgets.QDoubleSpinBox(root)
            self.distance_spin.setObjectName("lengthEdit")
            self.distance_spin.setMinimum(-100000.0)
            self.distance_spin.setMaximum(100000.0)
            self.distance_spin.setDecimals(2)
            self.distance_spin.setSuffix(" mm")
            self.distance_spin.setValue(self.session.signed_distance)
            if hasattr(self.distance_spin, "valueChanged"):
                self.distance_spin.valueChanged.connect(self._on_distance_changed)
            dist_row.addWidget(self.distance_spin)
            outer.addLayout(dist_row)

            # 5. Taper Angle row
            taper_row = qt_widgets.QHBoxLayout()
            taper_row.addWidget(qt_widgets.QLabel("Taper Angle:", root))
            self.taper_spin = qt_widgets.QDoubleSpinBox(root)
            self.taper_spin.setObjectName("FMF_ExtrudeTaperSpin")
            self.taper_spin.setMinimum(-89.0)
            self.taper_spin.setMaximum(89.0)
            self.taper_spin.setDecimals(1)
            self.taper_spin.setSuffix(" °")
            self.taper_spin.setValue(self.session.taper_angle)
            if hasattr(self.taper_spin, "valueChanged"):
                self.taper_spin.valueChanged.connect(self._on_taper_changed)
            taper_row.addWidget(self.taper_spin)
            outer.addLayout(taper_row)

            # 6. Operation row (Auto / Join / Cut / Intersect / New Body)
            op_row = qt_widgets.QHBoxLayout()
            op_row.addWidget(qt_widgets.QLabel("Operation:", root))
            self.operation_combo = qt_widgets.QComboBox(root)
            self.operation_combo.setObjectName("FMF_ExtrudeOperationCombo")
            for op_key, op_label in self.OPERATION_ITEMS:
                self.operation_combo.addItem(op_label, op_key)
            if hasattr(self.operation_combo, "currentIndexChanged"):
                self.operation_combo.currentIndexChanged.connect(self._on_operation_changed)
            op_row.addWidget(self.operation_combo)
            outer.addLayout(op_row)

            # 7. Target Body row
            body_row = qt_widgets.QHBoxLayout()
            body_row.addWidget(qt_widgets.QLabel("Target Body:", root))
            self.body_combo = qt_widgets.QComboBox(root)
            self.body_combo.setObjectName("FMF_ExtrudeTargetBodyCombo")
            self._populate_body_combo()
            if hasattr(self.body_combo, "currentIndexChanged"):
                self.body_combo.currentIndexChanged.connect(self._on_body_changed)
            body_row.addWidget(self.body_combo)
            outer.addLayout(body_row)

            # 8. Status / diagnostic explanation
            self.reason_label = qt_widgets.QLabel(self.session.reason, root)
            self.reason_label.setObjectName("FMF_ExtrudeReasonLabel")
            if hasattr(self.reason_label, "setWordWrap"):
                self.reason_label.setWordWrap(True)
            outer.addWidget(self.reason_label)

            self.form = root
        except Exception:
            self.form = None

    def _populate_body_combo(self) -> None:
        if self.body_combo is None:
            return
        try:
            self.body_combo.clear()
            self.body_combo.addItem("<Auto / New Body>", "")
            if self.session.document is not None:
                for obj in getattr(self.session.document, "Objects", ()) or ():
                    if getattr(obj, "TypeId", "") == "PartDesign::Body":
                        lbl = getattr(obj, "Label", getattr(obj, "Name", "Body"))
                        self.body_combo.addItem(lbl, getattr(obj, "Name", ""))
        except Exception:
            pass

    def _install_selection_observer(self) -> None:
        gui = _get_gui()
        sel = getattr(gui, "Selection", None) if gui else None
        if sel is not None and hasattr(sel, "addObserver"):
            try:
                self._observer = _ProfileSelectionObserver(self._on_viewport_selection)
                sel.addObserver(self._observer)
            except Exception:
                self._observer = None

    def _remove_selection_observer(self) -> None:
        gui = _get_gui()
        sel = getattr(gui, "Selection", None) if gui else None
        if self._observer is not None and sel is not None and hasattr(sel, "removeObserver"):
            try:
                sel.removeObserver(self._observer)
            except Exception:
                pass
        self._observer = None

    def _on_viewport_selection(self, _doc_name: str, obj_name: str, sub_name: str) -> None:
        if not self._selecting_profile and self.session.profile_obj is not None:
            return
        if self.session.document is None:
            return
        obj = None
        if hasattr(self.session.document, "getObject"):
            obj = self.session.document.getObject(obj_name)
        if obj is None:
            for cand in getattr(self.session.document, "Objects", ()) or ():
                if getattr(cand, "Name", "") == obj_name:
                    obj = cand
                    break
        if obj is None:
            return
        is_sketch = getattr(obj, "TypeId", "").startswith("Sketcher::") or hasattr(obj, "Geometry")
        is_face = bool(
            sub_name and (sub_name.startswith("Face") or sub_name.startswith("InternalFace"))
        )
        if is_sketch or is_face:
            self._selecting_profile = False
            subs = [sub_name] if sub_name else []
            self.session.set_profile(obj, subs, pick_initial_direction=True)

    def _on_toggle_select_profile(self) -> None:
        self._selecting_profile = True
        if self.profile_label is not None and hasattr(self.profile_label, "setText"):
            self.profile_label.setText("Click a sketch or face...")

    def _on_direction_mode_changed(self, index: int) -> None:
        if self._syncing_ui:
            return
        self.session.set_symmetric(index == 1)

    def _on_flip_clicked(self) -> None:
        self.session.flip_direction()

    def _on_distance_changed(self, val: float) -> None:
        if self._syncing_ui:
            return
        self.session.set_signed_distance(float(val))

    def _on_taper_changed(self, val: float) -> None:
        if self._syncing_ui:
            return
        self.session.set_taper_angle(float(val))

    def _on_operation_changed(self, index: int) -> None:
        if self._syncing_ui:
            return
        if 0 <= index < len(self.OPERATION_ITEMS):
            op_key = self.OPERATION_ITEMS[index][0]
            self.session.set_operation_mode(op_key)

    def _on_body_changed(self, index: int) -> None:
        if self._syncing_ui or self.body_combo is None:
            return
        if index <= 0:
            self.session.set_target_body(None)
            return
        if self.session.document is not None:
            bodies = [
                o
                for o in getattr(self.session.document, "Objects", ()) or ()
                if getattr(o, "TypeId", "") == "PartDesign::Body"
            ]
            if 0 <= index - 1 < len(bodies):
                self.session.set_target_body(bodies[index - 1])

    def _sync_from_session(self, session: SmartExtrudeSession) -> None:
        if self._syncing_ui:
            return
        self._syncing_ui = True
        try:
            op = session.resolved_operation
            op_upper = op.replace("_", " ").upper()
            badge_text = f"AUTO → {op_upper}" if session.operation_mode == "auto" else op_upper
            if self.badge_label is not None:
                if hasattr(self.badge_label, "setText"):
                    self.badge_label.setText(badge_text)
                if hasattr(self.badge_label, "setStyleSheet"):
                    style = self.BADGE_STYLES.get(op, self.BADGE_STYLES["join"])
                    self.badge_label.setStyleSheet(
                        f"padding: 2px 8px; border-radius: 4px; font-weight: bold; {style}"
                    )

            if self.profile_label is not None and hasattr(self.profile_label, "setText"):
                if session.profile_obj is not None:
                    lbl = getattr(
                        session.profile_obj,
                        "Label",
                        getattr(session.profile_obj, "Name", "Profile"),
                    )
                    sub_str = (
                        f" ({session.sub_elements[0]})"
                        if session.sub_elements and session.sub_elements[0]
                        else ""
                    )
                    self.profile_label.setText(f"{lbl}{sub_str}")
                else:
                    self.profile_label.setText("Click a sketch or face...")

            if self.distance_spin is not None and hasattr(self.distance_spin, "setValue"):
                self.distance_spin.setValue(session.signed_distance)

            if self.operation_combo is not None and hasattr(
                self.operation_combo, "setCurrentIndex"
            ):
                keys = [k for k, _ in self.OPERATION_ITEMS]
                if session.operation_mode in keys:
                    self.operation_combo.setCurrentIndex(keys.index(session.operation_mode))

            if self.reason_label is not None and hasattr(self.reason_label, "setText"):
                self.reason_label.setText(session.reason)

            if _active_extrude_hud is not None:
                _active_extrude_hud.sync_from_task()
        finally:
            self._syncing_ui = False

    def accept(self) -> bool:
        """Called by FreeCAD when the user clicks OK or presses Enter."""
        global _active_extrude_session
        self._remove_selection_observer()
        close_extrude_hud()
        res = self.session.commit()
        _active_extrude_session = None
        return res.get("status") == "ok"

    def reject(self) -> bool:
        """Called by FreeCAD when the user clicks Cancel or presses Escape."""
        global _active_extrude_session
        self._remove_selection_observer()
        close_extrude_hud()
        self.session.cancel()
        _active_extrude_session = None
        return True


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
        if doc is None:
            notify("Extrude", "No active document.", error=True)
            return

        # If the user is currently inside Sketcher edit mode, automatically finish the
        # sketch and use it as the profile (Fusion 360 behavior).
        gui_doc = getattr(gui, "ActiveDocument", None) if gui else None
        in_edit_sketch = None
        if gui_doc is not None and hasattr(gui_doc, "getInEdit"):
            try:
                edit_vp = gui_doc.getInEdit()
                edit_obj = getattr(edit_vp, "Object", edit_vp)
                if edit_obj is not None and (
                    getattr(edit_obj, "TypeId", "").startswith("Sketcher::")
                    or hasattr(edit_obj, "Geometry")
                ):
                    in_edit_sketch = edit_obj
                    if hasattr(gui_doc, "resetEdit"):
                        gui_doc.resetEdit()
            except Exception:
                pass

        profile_obj, sub_elements = resolve_profile(document=doc)
        if profile_obj is None and in_edit_sketch is not None:
            profile_obj = in_edit_sketch
            sub_elements = _normalize_profile_subs(profile_obj, [])

        control = getattr(gui, "Control", None) if gui else None
        if control is not None and hasattr(control, "showDialog"):
            if hasattr(control, "activeDialog"):
                try:
                    if control.activeDialog():
                        notify(
                            "Extrude",
                            "Finish or cancel the current task before starting Smart Extrude.",
                            error=True,
                        )
                        return
                except Exception:
                    event("warning", "extrude", "task_dialog", "active_dialog_check_failed")
            session = SmartExtrudeSession(
                document=doc,
                profile=(profile_obj, sub_elements) if profile_obj is not None else None,
            )
            panel = SmartExtrudeTaskPanel(session)
            try:
                control.showDialog(panel)
            except Exception as exc:
                panel.reject()
                event("error", "extrude", "task_dialog", f"show_failed:{type(exc).__name__}")
                notify("Extrude", "Could not open the Smart Extrude task panel.", error=True)
                return
            if panel.distance_spin is not None:
                show_extrude_hud(
                    {"spinbox": panel.distance_spin, "checkbox_reversed": None},
                    operation=session.operation_mode,
                )
            return

        # Headless / non-TaskView fallback: execute directly
        if profile_obj is None:
            notify("Extrude", "Select a sketch or face to extrude.", error=True)
            return
        smart_extrude(
            operation="auto",
            profile=(profile_obj, sub_elements),
            document=doc,
        )


def register(add_command: Any = None) -> None:
    """Register FMF_SmartExtrude command."""
    gui = _get_gui()
    register_with = add_command or (getattr(gui, "addCommand", None) if gui else None)
    if callable(register_with):
        register_with("FMF_SmartExtrude", SmartExtrudeCommand())
