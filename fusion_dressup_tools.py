"""Zero-popup in-place workflow enhancements for FreeCAD Chamfer and Fillet tools.

Transforms FreeCAD's native PartDesign Chamfer and Fillet tools to match the
fluid Fusion 360 workflow ("click tool, click edge or surface, type dimension, hit enter")
with ZERO popups, zero floating overlays, and zero HUDs:

1. Live Preview: Automatically enables `keyboardTracking = True` on chamferSize,
   filletRadius, and secondary dimension spinboxes so typing digits instantly
   updates the 3D model in real time.
2. 10-Key Numpad Shield: Intercepts numpad digits and periods during active dressup
   tasks, routing them to the dimension spinbox and preventing FreeCAD's 3D viewport
   from interpreting them as camera viewpoint shortcuts (Std_ViewFront, Std_ViewTop, etc.).
3. Persistent Selection Mode: Automatically ensures selection mode is active
   (`buttonRefSel.setChecked(True)`) so edges and surfaces can be clicked immediately
   without requiring the user to find and click the "Select" button.
4. Auto-Focus on 3D Pick: Automatically focuses the dimension spinbox and selects
   all text whenever an edge or surface is clicked in the 3D viewport, allowing
   immediate dimension typing.
5. Safe Enter-to-Commit: Commits the typed spinbox text and triggers model recompute
   before accepting the task dialog, ensuring the exact typed dimension is saved.
"""

from __future__ import annotations

import sys
from typing import Any

from fusion_common import log_swallowed


def _get_app() -> Any:
    try:
        import FreeCAD

        return FreeCAD
    except ImportError:
        return None


def _get_gui() -> Any:
    try:
        import FreeCADGui

        return FreeCADGui
    except ImportError:
        return None


_qt_cache: tuple[Any, tuple[Any, Any, Any]] | None = None


def _get_qt() -> tuple[Any, Any, Any]:
    """The Qt modules, resolved once per binding.

    This is called from an application-wide event filter, so it runs for every
    event FreeCAD delivers -- thousands a second while dragging. Re-running the
    import machinery each time was pure overhead on the hottest path there is.

    Keyed on the binding module itself rather than cached outright, so a test
    harness that swaps the fake Qt between cases still gets the current one for
    a single dictionary lookup.
    """
    global _qt_cache
    binding = sys.modules.get("PySide") or sys.modules.get("PySide6")
    if _qt_cache is not None and _qt_cache[0] is binding:
        return _qt_cache[1]
    resolved = _resolve_qt()
    _qt_cache = (binding, resolved)
    return resolved


def _resolve_qt() -> tuple[Any, Any, Any]:
    try:
        from PySide import QtCore, QtGui, QtWidgets

        return QtCore, QtGui, QtWidgets
    except ImportError:
        try:
            from PySide6 import QtCore, QtGui, QtWidgets  # type: ignore[assignment]

            return QtCore, QtGui, QtWidgets
        except ImportError:
            try:
                from PySide2 import QtCore, QtGui, QtWidgets  # type: ignore[assignment]

                return QtCore, QtGui, QtWidgets
            except ImportError:
                return None, None, None


# Qt requires a real QObject for installEventFilter(); a plain Python class is
# rejected at runtime. Resolved once at import because a class statement cannot
# pick its base lazily. _get_qt() is fully guarded, so this degrades to object
# when Qt is unavailable (headless tests), where the filter is never installed.
_qt_core, _, _ = _get_qt()
_QObjectBase: Any = getattr(_qt_core, "QObject", object) if _qt_core is not None else object

_numpad_shield_filter: _DressUpNumpadShield | None = None
_selection_observer: _DressUpSelectionObserver | None = None


def find_child(parent: Any, widget_type: Any, name: str) -> Any:
    """Find a child widget by type and objectName across Qt implementations."""
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


def get_active_dressup_info() -> dict[str, Any] | None:
    """Detect whether a PartDesign Chamfer or Fillet task panel is currently active."""
    gui = _get_gui()
    _qt_core, _qt_gui, qt_widgets = _get_qt()
    app = _get_app()

    if gui is None or qt_widgets is None:
        return None

    main_window = gui.getMainWindow() if hasattr(gui, "getMainWindow") else None
    if main_window is None:
        return None

    chamfer_size = find_child(main_window, qt_widgets.QWidget, "chamferSize")
    fillet_radius = find_child(main_window, qt_widgets.QWidget, "filletRadius")

    active_type: str | None = None
    spinbox = None

    if chamfer_size is not None and getattr(chamfer_size, "isVisible", lambda: False)():
        active_type = "Chamfer"
        spinbox = chamfer_size
    elif fillet_radius is not None and getattr(fillet_radius, "isVisible", lambda: False)():
        active_type = "Fillet"
        spinbox = fillet_radius

    if not active_type or spinbox is None:
        return None

    button_ref_sel = find_child(main_window, qt_widgets.QToolButton, "buttonRefSel")
    list_references = find_child(main_window, qt_widgets.QWidget, "listWidgetReferences")

    # Resolve active dressup document object and base feature
    dressup_obj = None
    base_obj = None
    doc = getattr(app, "ActiveDocument", None) if app is not None else None

    if doc is not None:
        gui_doc = gui.getDocument(doc.Name) if hasattr(gui, "getDocument") else None
        in_edit = getattr(gui_doc, "InEdit", None) if gui_doc else None
        if (
            in_edit
            and hasattr(in_edit, "isDerivedFrom")
            and in_edit.isDerivedFrom(f"PartDesign::{active_type}")
        ):
            dressup_obj = in_edit
        else:
            candidates = [
                o
                for o in getattr(doc, "Objects", [])
                if hasattr(o, "isDerivedFrom") and o.isDerivedFrom(f"PartDesign::{active_type}")
            ]
            if candidates:
                dressup_obj = candidates[-1]

        if dressup_obj is not None:
            base_val = getattr(dressup_obj, "Base", None)
            if isinstance(base_val, tuple) and len(base_val) > 0:
                base_obj = base_val[0]
            elif hasattr(dressup_obj, "getBaseObject"):
                try:
                    base_obj = dressup_obj.getBaseObject()
                except Exception:
                    pass

        if base_obj is None:
            body = getattr(doc, "ActiveBody", None) or getattr(doc, "Body", None)
            if not body:
                bodies = [
                    o
                    for o in getattr(doc, "Objects", [])
                    if hasattr(o, "isDerivedFrom") and o.isDerivedFrom("PartDesign::Body")
                ]
                if bodies:
                    body = bodies[-1]
            if body and hasattr(body, "Tip"):
                base_obj = body.Tip

    return {
        "type": active_type,
        "spinbox": spinbox,
        "button_ref_sel": button_ref_sel,
        "list_references": list_references,
        "dressup_obj": dressup_obj,
        "base_obj": base_obj,
        "doc": doc,
    }


def enhance_active_dressup(info: dict[str, Any] | None = None) -> None:
    """Apply in-place enhancements to the active dressup task panel."""
    if info is None:
        info = get_active_dressup_info()
    if not info:
        return

    spinbox = info.get("spinbox")
    if spinbox and hasattr(spinbox, "setKeyboardTracking"):
        tracking = spinbox.keyboardTracking() if hasattr(spinbox, "keyboardTracking") else False
        if not tracking:
            spinbox.setKeyboardTracking(True)

    gui = _get_gui()
    _qt_core, _qt_gui, qt_widgets = _get_qt()
    main_window = gui.getMainWindow() if (gui and hasattr(gui, "getMainWindow")) else None
    if main_window and qt_widgets is not None:
        for name in ("chamferSize2", "chamferAngle"):
            extra = find_child(main_window, qt_widgets.QWidget, name)
            if extra and hasattr(extra, "setKeyboardTracking"):
                extra_tracking = (
                    extra.keyboardTracking() if hasattr(extra, "keyboardTracking") else False
                )
                if not extra_tracking:
                    extra.setKeyboardTracking(True)

    btn = info.get("button_ref_sel")
    if btn and hasattr(btn, "isChecked") and not btn.isChecked():
        if hasattr(btn, "setChecked"):
            btn.setChecked(True)


def _focus_and_select(spinbox: Any) -> None:
    """Direct focus to the spinbox and select its text for immediate overwriting."""
    if spinbox is None:
        return
    try:
        line_edit = getattr(spinbox, "lineEdit", lambda: None)()
        target = line_edit if line_edit is not None else spinbox

        if hasattr(target, "setFocus"):
            target.setFocus()
        if hasattr(target, "selectAll"):
            target.selectAll()
        elif hasattr(spinbox, "selectAll"):
            spinbox.selectAll()
    except Exception:
        pass


class _DressUpNumpadShield(_QObjectBase):
    """Application-level event filter active during Chamfer and Fillet tasks."""

    def __init__(self, parent: Any = None) -> None:
        if _QObjectBase is not object:
            super().__init__(parent)

    def eventFilter(self, watched: Any, event: Any) -> bool:
        qt_core, _qt_gui, qt_widgets = _get_qt()
        if event is None or qt_core is None:
            return False

        event_type = getattr(event, "type", lambda: None)()
        key_press_type = getattr(qt_core.QEvent, "KeyPress", None)

        # On dialog show / window activation, ensure live tracking & selection mode
        if event_type in (
            getattr(qt_core.QEvent, "Show", None),
            getattr(qt_core.QEvent, "FocusIn", None),
            getattr(qt_core.QEvent, "WindowActivate", None),
        ):
            info = get_active_dressup_info()
            if info:
                enhance_active_dressup(info)
            return False

        if event_type != key_press_type:
            return False

        info = get_active_dressup_info()
        if not info:
            return False

        spinbox = info.get("spinbox")
        if spinbox is None:
            return False

        key = getattr(event, "key", lambda: None)()

        # Handle Enter / Return
        return_keys = (
            getattr(qt_core.Qt, "Key_Return", None),
            getattr(qt_core.Qt, "Key_Enter", None),
        )
        if key in return_keys:
            return self._handle_enter(info)

        # Handle Escape
        if key == getattr(qt_core.Qt, "Key_Escape", None):
            return self._handle_escape(info)

        # Digits, decimal, backspace, operators
        numpad_keys = {getattr(qt_core.Qt, f"Key_{i}", -1) for i in range(10)} | {
            getattr(qt_core.Qt, "Key_Period", -1),
            getattr(qt_core.Qt, "Key_Comma", -1),
            getattr(qt_core.Qt, "Key_Minus", -1),
            getattr(qt_core.Qt, "Key_Plus", -1),
            getattr(qt_core.Qt, "Key_Backspace", -1),
            getattr(qt_core.Qt, "Key_Delete", -1),
        }
        numpad_keys.discard(-1)

        if key in numpad_keys:
            focus_widget = None
            if qt_widgets and hasattr(qt_widgets, "QApplication"):
                try:
                    focus_widget = qt_widgets.QApplication.focusWidget()
                except Exception:
                    pass

            line_edit = None
            if hasattr(spinbox, "lineEdit"):
                try:
                    line_edit = spinbox.lineEdit()
                except Exception:
                    pass

            # If spinbox or its inner line edit already has focus, let Qt handle typing
            if focus_widget is not None and (focus_widget is spinbox or focus_widget is line_edit):
                return False

            # Focus was in 3D viewport or elsewhere: route directly to spinbox
            return self._route_key_to_spinbox(spinbox, line_edit, event, key)

        return False

    def _route_key_to_spinbox(self, spinbox: Any, line_edit: Any, event: Any, key: Any) -> bool:
        _qt_core, _qt_gui, qt_widgets = _get_qt()
        target = line_edit if line_edit is not None else spinbox
        try:
            if hasattr(target, "setFocus"):
                target.setFocus()

            text = getattr(event, "text", lambda: "")()
            if text:
                if hasattr(target, "insert"):
                    target.insert(text)
                elif (
                    qt_widgets
                    and hasattr(qt_widgets, "QApplication")
                    and hasattr(qt_widgets.QApplication, "sendEvent")
                ):
                    qt_widgets.QApplication.sendEvent(target, event)
            elif key == getattr(_qt_core.Qt, "Key_Backspace", None):
                if hasattr(target, "backspace"):
                    target.backspace()
                elif (
                    qt_widgets
                    and hasattr(qt_widgets, "QApplication")
                    and hasattr(qt_widgets.QApplication, "sendEvent")
                ):
                    qt_widgets.QApplication.sendEvent(target, event)

            if hasattr(event, "accept"):
                event.accept()
            return True
        except Exception as exc:
            log_swallowed(exc, "routing numpad key to spinbox")
            return False

    def _handle_enter(self, info: dict[str, Any]) -> bool:
        gui = _get_gui()
        _qt_core, _qt_gui, qt_widgets = _get_qt()
        spinbox = info.get("spinbox")
        doc = info.get("doc")
        try:
            if spinbox and hasattr(spinbox, "interpretText"):
                spinbox.interpretText()

            if doc and hasattr(doc, "recompute"):
                doc.recompute()

            main_window = gui.getMainWindow() if (gui and hasattr(gui, "getMainWindow")) else None
            if main_window and qt_widgets is not None and hasattr(qt_widgets, "QDialogButtonBox"):
                button_boxes = main_window.findChildren(qt_widgets.QDialogButtonBox)
                for bb in button_boxes:
                    ok_btn = None
                    if hasattr(bb, "button"):
                        ok_btn = bb.button(qt_widgets.QDialogButtonBox.Ok)
                    if ok_btn and hasattr(ok_btn, "isVisible") and ok_btn.isVisible():
                        if hasattr(ok_btn, "animateClick"):
                            ok_btn.animateClick()
                        elif hasattr(ok_btn, "click"):
                            ok_btn.click()
                        return True

            if gui and hasattr(gui, "Control") and hasattr(gui.Control, "closeDialog"):
                gui.Control.closeDialog()
                return True

            return True
        except Exception as exc:
            log_swallowed(exc, "handling dressup Enter key")
            return False

    def _handle_escape(self, info: dict[str, Any]) -> bool:
        gui = _get_gui()
        _qt_core, _qt_gui, qt_widgets = _get_qt()
        try:
            main_window = gui.getMainWindow() if (gui and hasattr(gui, "getMainWindow")) else None
            if main_window and qt_widgets is not None and hasattr(qt_widgets, "QDialogButtonBox"):
                button_boxes = main_window.findChildren(qt_widgets.QDialogButtonBox)
                for bb in button_boxes:
                    cancel_btn = None
                    if hasattr(bb, "button"):
                        cancel_btn = bb.button(qt_widgets.QDialogButtonBox.Cancel)
                    if cancel_btn and hasattr(cancel_btn, "isVisible") and cancel_btn.isVisible():
                        if hasattr(cancel_btn, "animateClick"):
                            cancel_btn.animateClick()
                        elif hasattr(cancel_btn, "click"):
                            cancel_btn.click()
                        return True

            if gui and hasattr(gui, "Control") and hasattr(gui.Control, "closeDialog"):
                gui.Control.closeDialog()
                return True
            return True
        except Exception as exc:
            log_swallowed(exc, "handling dressup Escape key")
            return False


class _DressUpSelectionObserver:
    """Selection observer that manages edge/face auto-focus and subelement resolution."""

    def __init__(self) -> None:
        self._busy = False

    def addSelection(
        self, doc_name: str, obj_name: str, sub_name: str, mouse_pos: Any = None
    ) -> None:
        if self._busy:
            return
        gui = _get_gui()
        qt_core, _qt_gui, _qt_widgets = _get_qt()
        try:
            info = get_active_dressup_info()
            if not info:
                return

            spinbox = info.get("spinbox")
            button_ref_sel = info.get("button_ref_sel")
            base_obj = info.get("base_obj")

            # 1. Ensure selection mode button is checked so subsequent clicks work
            if (
                button_ref_sel
                and hasattr(button_ref_sel, "isChecked")
                and not button_ref_sel.isChecked()
            ):
                if hasattr(button_ref_sel, "setChecked"):
                    button_ref_sel.setChecked(True)

            # 2. Subelement normalization: If selection came in through Body
            if base_obj and hasattr(base_obj, "Name"):
                base_name = base_obj.Name
                if (
                    obj_name != base_name
                    and gui is not None
                    and hasattr(gui, "Selection")
                    and hasattr(gui.Selection, "addSelection")
                ):
                    sub_part = sub_name.split(".")[-1] if sub_name and "." in sub_name else sub_name
                    if sub_part and (sub_part.startswith("Edge") or sub_part.startswith("Face")):
                        self._busy = True
                        try:
                            gui.Selection.addSelection(doc_name, base_name, sub_part)
                        finally:
                            self._busy = False

            # 3. Auto-focus and select spinbox so user can type dimension immediately
            if spinbox:
                if qt_core and hasattr(qt_core, "QTimer") and hasattr(qt_core.QTimer, "singleShot"):
                    qt_core.QTimer.singleShot(0, lambda: _focus_and_select(spinbox))
                else:
                    _focus_and_select(spinbox)
        except Exception as exc:
            log_swallowed(exc, "handling dressup addSelection")

    def removeSelection(
        self, doc_name: str, obj_name: str, sub_name: str, mouse_pos: Any = None
    ) -> None:
        pass

    def clearSelection(self, doc_name: str) -> None:
        pass

    def setSelection(self, doc_name: str) -> None:
        pass


def install_dressup_enhancers() -> None:
    """Install the application numpad shield and selection observer."""
    global _numpad_shield_filter, _selection_observer

    gui = _get_gui()
    _qt_core, _qt_gui, qt_widgets = _get_qt()

    if (
        _numpad_shield_filter is None
        and qt_widgets is not None
        and hasattr(qt_widgets, "QApplication")
    ):
        app = qt_widgets.QApplication.instance()
        if app and hasattr(app, "installEventFilter"):
            _numpad_shield_filter = _DressUpNumpadShield()
            app.installEventFilter(_numpad_shield_filter)

    if (
        _selection_observer is None
        and gui is not None
        and hasattr(gui, "Selection")
        and hasattr(gui.Selection, "addObserver")
    ):
        _selection_observer = _DressUpSelectionObserver()
        gui.Selection.addObserver(_selection_observer)


def uninstall_dressup_enhancers() -> None:
    """Uninstall the event filter and selection observer (useful for teardown and tests)."""
    global _numpad_shield_filter, _selection_observer

    gui = _get_gui()
    _qt_core, _qt_gui, qt_widgets = _get_qt()

    if (
        _numpad_shield_filter is not None
        and qt_widgets is not None
        and hasattr(qt_widgets, "QApplication")
    ):
        app = qt_widgets.QApplication.instance()
        if app and hasattr(app, "removeEventFilter"):
            try:
                app.removeEventFilter(_numpad_shield_filter)
            except Exception:
                pass
        _numpad_shield_filter = None

    if (
        _selection_observer is not None
        and gui is not None
        and hasattr(gui, "Selection")
        and hasattr(gui.Selection, "removeObserver")
    ):
        try:
            gui.Selection.removeObserver(_selection_observer)
        except Exception:
            pass
        _selection_observer = None


def register(add_command: Any = None) -> None:
    """Register dressup enhancers during add-on startup."""
    install_dressup_enhancers()
