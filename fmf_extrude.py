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
        if self.checkbox_reversed is not None and hasattr(
            self.checkbox_reversed, "isChecked"
        ):
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
                tool_flag = getattr(flags, "ToolTip", None) or getattr(
                    flags, "SubWindow", None
                )
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
            if hasattr(dist_spin, "valueChanged") and hasattr(
                dist_spin.valueChanged, "connect"
            ):
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
            if self.checkbox_reversed is not None and hasattr(
                self.checkbox_reversed, "setChecked"
            ):
                self.checkbox_reversed.setChecked(want_reversed)
            if self.spinbox is not None and hasattr(self.spinbox, "setValue"):
                self.spinbox.setValue(abs_val)
            if self.distance_input is not None and hasattr(
                self.distance_input, "setValue"
            ):
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
            if self.distance_input is not None and hasattr(
                self.distance_input, "setValue"
            ):
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
        if self.operation_combo is not None and hasattr(
            self.operation_combo, "setCurrentIndex"
        ):
            try:
                self.operation_combo.setCurrentIndex(
                    self.OPERATIONS.index(self._operation)
                )
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
    main_window = (
        gui.getMainWindow() if gui is not None and hasattr(gui, "getMainWindow") else None
    )
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


def enhance_active_extrude(
    info: dict[str, Any] | None = None, operation: str = "auto"
) -> bool:
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


def _activate_body_tip_visibility(
    body: Any, feat: Any, profile_obj: Any = None
) -> None:
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
        closed_wires = [
            w for w in prof_wires if getattr(w, "isClosed", lambda: False)()
        ]
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


def classify_operation(
    profile_obj: Any,
    sub_elements: list[str] | None = None,
    length: float = 10.0,
    reversed_dir: bool = False,
    target_body: Any = None,
) -> dict[str, Any]:
    """Classify the extrusion as join, cut, or new_body based on geometry."""
    app = _get_app()
    if length < 0.0:
        reversed_dir = not reversed_dir
        length = abs(length)

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
    face, needs_placement_transform = _extract_test_face(profile_obj, sub_elements)

    if face is None:
        return {
            "operation": "join",
            "auto_reverse": False,
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

    closed_wire_gaps = 0
    if (
        getattr(profile_obj, "TypeId", "").startswith("Sketcher::")
        or hasattr(profile_obj, "Geometry")
    ):
        test_face, _ = _extract_test_face(profile_obj, sub_elements)
        if test_face is None and getattr(profile_obj, "Geometry", None):
            try:
                import fmf_sketch_tools

                diagnosis = fmf_sketch_tools.diagnose_open_wires(
                    profile_obj, tolerance=0.5
                )
                if not diagnosis["is_closed"]:
                    if diagnosis["closable_gaps"]:
                        repair = fmf_sketch_tools.close_open_wire_gaps(
                            profile_obj, tolerance=0.5
                        )
                        closed_wire_gaps = int(repair.get("closed_count", 0))
                        sub_elements = _normalize_profile_subs(
                            profile_obj, sub_elements
                        )
                    else:
                        notify("Extrude", diagnosis["summary"], error=True)
                        return {
                            "status": "open-wire",
                            "diagnosis": diagnosis,
                        }
            except Exception:
                pass

    target_body = _active_body(doc, profile_obj=profile_obj)

    effective_op = operation.lower()
    auto_reversed = False
    was_auto = effective_op == "auto"

    if was_auto:
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
                if (
                    owning_body is None
                    and hasattr(profile_obj, "isDerivedFrom")
                    and profile_obj.isDerivedFrom("Sketcher::SketchObject")
                ):
                    # Only move sketch into new_body if it is not already owned by another Body
                    if hasattr(new_body, "addObject"):
                        try:
                            new_body.addObject(profile_obj)
                        except Exception:
                            pass

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

                # If profile_obj belongs to another Body in real FreeCAD, direct cross-body
                # Pad reference yields 0 solids; bind via PartDesign::SubShapeBinder.
                shape = getattr(feat, "Shape", None)
                has_solids = (
                    shape is not None
                    and not getattr(shape, "isNull", lambda: False)()
                    and len(getattr(shape, "Solids", ())) > 0
                )
                if (
                    shape is not None
                    and not has_solids
                    and owning_body is not None
                    and owning_body != new_body
                    and hasattr(new_body, "newObject")
                ):
                    try:
                        binder = new_body.newObject("PartDesign::SubShapeBinder", "Binder")
                        clean_subs = tuple(s for s in sub_elements if s)
                        binder.Support = [(profile_obj, clean_subs)]
                        if hasattr(binder, "recompute"):
                            binder.recompute()
                        feat.Profile = (binder, ["Face1"])
                        if hasattr(feat, "recompute"):
                            feat.recompute()
                        doc.recompute()
                    except Exception:
                        pass

                _activate_body_tip_visibility(new_body, feat, profile_obj)
                notify("Extrude", f"Created new Body with Pad ({abs(length):.1f} mm).")
                return {
                    "status": "ok",
                    "operation": "new_body",
                    "body": new_body,
                    "feature": feat,
                    "auto_reversed": auto_reversed,
                    "closed_wire_gaps": closed_wire_gaps,
                }

            elif effective_op == "cut":
                prev_body_shape = getattr(target_body, "Shape", None)
                prev_vol = (
                    getattr(prev_body_shape, "Volume", 0.0)
                    if prev_body_shape is not None
                    and not getattr(prev_body_shape, "isNull", lambda: True)()
                    else 0.0
                )

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

                # Verify that the Pocket produced a valid solid and reduced volume when prev_vol > 0
                shape = getattr(feat, "Shape", None)
                if shape is not None and hasattr(feat, "Reversed"):
                    solids = getattr(shape, "Solids", ())
                    new_vol = getattr(shape, "Volume", 0.0) if len(solids) > 0 else 0.0
                    did_cut = len(solids) > 0 and (
                        prev_vol <= 0.0 or new_vol < prev_vol - 1e-4
                    )
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
                notify("Extrude", f"Created Pocket cut ({abs(length):.1f} mm).")
                return {
                    "status": "ok",
                    "operation": "cut",
                    "body": target_body,
                    "feature": feat,
                    "auto_reversed": auto_reversed,
                    "closed_wire_gaps": closed_wire_gaps,
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

                # Guard against empty solid or disconnected multi-solid failure
                shape = getattr(feat, "Shape", None)
                if shape is not None and hasattr(feat, "Reversed"):
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
                    "closed_wire_gaps": closed_wire_gaps,
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

        res = smart_extrude(operation="auto", document=doc)
        if res.get("status") == "ok" and res.get("feature") is not None:
            feat = res["feature"]
            op_used = res.get("operation", "auto")
            gui_doc = getattr(gui, "ActiveDocument", None) if gui else None
            if gui_doc is not None and hasattr(gui_doc, "setEdit"):
                try:
                    gui_doc.setEdit(getattr(feat, "Name", feat))
                except Exception:
                    pass
            enhance_active_extrude(operation=op_used)


def register(add_command: Any = None) -> None:
    """Register FMF_SmartExtrude command."""
    gui = _get_gui()
    register_with = add_command or (getattr(gui, "addCommand", None) if gui else None)
    if callable(register_with):
        register_with("FMF_SmartExtrude", SmartExtrudeCommand())
