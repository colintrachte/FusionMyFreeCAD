"""Tests for fmf_dressup_tools: Zero-popup Chamfer & Fillet workflow enhancers."""

from __future__ import annotations

import types
from pathlib import Path

from fake_freecad import FakeQtWidget, FakeTimer

import fmf_dressup_tools as dressup

ROOT = Path(__file__).resolve().parents[1]


class FakeEvent:
    def __init__(self, event_type, key=None, text=""):
        self._type = event_type
        self._key = key
        self._text = text
        self.accepted = False

    def type(self):
        return self._type

    def key(self):
        return self._key

    def text(self):
        return self._text

    def accept(self):
        self.accepted = True


def _setup_chamfer_dialog(env):
    """Set up fake Qt widgets mimicking TaskChamferParameters."""
    main_window = env.main_window

    chamfer_size = env.qtwidgets.QWidget()
    chamfer_size.setObjectName("chamferSize")
    chamfer_size._visible = True
    chamfer_size.setKeyboardTracking(False)
    chamfer_size.setText("1.00 mm")

    button_ref_sel = env.qtwidgets.QToolButton()
    button_ref_sel.setObjectName("buttonRefSel")
    button_ref_sel._visible = True
    button_ref_sel.setChecked(False)

    list_refs = env.qtwidgets.QWidget()
    list_refs.setObjectName("listWidgetReferences")
    list_refs._visible = True

    button_box = env.qtwidgets.QDialogButtonBox()

    main_window.widgets.extend([chamfer_size, button_ref_sel, list_refs])
    main_window.button_boxes.append(button_box)

    doc = env.app.newDocument("TestDoc")
    pad = types.SimpleNamespace(
        Name="Pad",
        isDerivedFrom=lambda t: t == "PartDesign::Pad",
    )
    chamfer_obj = types.SimpleNamespace(
        Name="Chamfer",
        Base=(pad, ["Edge1"]),
        isDerivedFrom=lambda t: t == "PartDesign::Chamfer",
    )
    doc.Objects = [pad, chamfer_obj]

    return {
        "chamfer_size": chamfer_size,
        "button_ref_sel": button_ref_sel,
        "list_refs": list_refs,
        "button_box": button_box,
        "pad": pad,
        "chamfer_obj": chamfer_obj,
        "doc": doc,
    }


def _setup_fillet_dialog(env):
    """Set up fake Qt widgets mimicking TaskFilletParameters."""
    main_window = env.main_window

    fillet_radius = env.qtwidgets.QWidget()
    fillet_radius.setObjectName("filletRadius")
    fillet_radius._visible = True
    fillet_radius.setKeyboardTracking(False)
    fillet_radius.setText("2.00 mm")

    button_ref_sel = env.qtwidgets.QToolButton()
    button_ref_sel.setObjectName("buttonRefSel")
    button_ref_sel._visible = True
    button_ref_sel.setChecked(False)

    list_refs = env.qtwidgets.QWidget()
    list_refs.setObjectName("listWidgetReferences")
    list_refs._visible = True

    button_box = env.qtwidgets.QDialogButtonBox()

    main_window.widgets.extend([fillet_radius, button_ref_sel, list_refs])
    main_window.button_boxes.append(button_box)

    doc = env.app.newDocument("FilletDoc")
    pad = types.SimpleNamespace(
        Name="Pad",
        isDerivedFrom=lambda t: t == "PartDesign::Pad",
    )
    fillet_obj = types.SimpleNamespace(
        Name="Fillet",
        Base=(pad, ["Edge2"]),
        isDerivedFrom=lambda t: t == "PartDesign::Fillet",
    )
    doc.Objects = [pad, fillet_obj]

    return {
        "fillet_radius": fillet_radius,
        "button_ref_sel": button_ref_sel,
        "list_refs": list_refs,
        "button_box": button_box,
        "pad": pad,
        "fillet_obj": fillet_obj,
        "doc": doc,
    }


def test_enhance_active_dressup_enables_keyboard_tracking_and_selection(env):
    """Enhance actively sets keyboardTracking=True and buttonRefSel.setChecked(True)."""
    widgets = _setup_chamfer_dialog(env)
    chamfer_size = widgets["chamfer_size"]
    button_ref_sel = widgets["button_ref_sel"]

    assert chamfer_size.keyboardTracking() is False
    assert button_ref_sel.isChecked() is False

    info = dressup.get_active_dressup_info()
    assert info is not None
    assert info["type"] == "Chamfer"
    assert info["spinbox"] is chamfer_size

    dressup.enhance_active_dressup(info)

    assert chamfer_size.keyboardTracking() is True
    assert button_ref_sel.isChecked() is True


def test_enhance_fillet_dialog(env):
    """Fillet dialog spinbox and selection button are properly enhanced."""
    widgets = _setup_fillet_dialog(env)
    fillet_radius = widgets["fillet_radius"]
    button_ref_sel = widgets["button_ref_sel"]

    assert fillet_radius.keyboardTracking() is False
    assert button_ref_sel.isChecked() is False

    info = dressup.get_active_dressup_info()
    assert info is not None
    assert info["type"] == "Fillet"
    assert info["spinbox"] is fillet_radius

    dressup.enhance_active_dressup(info)

    assert fillet_radius.keyboardTracking() is True
    assert button_ref_sel.isChecked() is True


def test_numpad_shield_routes_digits_and_blocks_camera(env):
    """Numpad keys typed while 3D viewport has focus route into spinbox and block camera."""
    widgets = _setup_chamfer_dialog(env)
    chamfer_size = widgets["chamfer_size"]
    chamfer_size.setText("")

    shield = dressup._DressUpNumpadShield()

    # Emulate typing '2' on the numpad while focus is outside the spinbox
    key_event = FakeEvent(env.qtcore.QEvent.KeyPress, env.qtcore.Qt.Key_2, "2")
    handled = shield.eventFilter(None, key_event)

    assert handled is True
    assert key_event.accepted is True
    assert getattr(chamfer_size, "_focused", False) is True
    assert chamfer_size.text() == "2"


def test_numpad_shield_passes_through_when_spinbox_already_focused(env):
    """When the spinbox already has focus, numpad digits pass through to native Qt handling."""
    widgets = _setup_chamfer_dialog(env)
    chamfer_size = widgets["chamfer_size"]

    shield = dressup._DressUpNumpadShield()

    # Set focus widget to chamfer_size
    env.pyside.QtWidgets.QApplication.instance().focus_widget = chamfer_size

    key_event = FakeEvent(env.qtcore.QEvent.KeyPress, env.qtcore.Qt.Key_5, "5")
    handled = shield.eventFilter(None, key_event)

    # Handled should be False so Qt handles typing normally
    assert handled is False


def test_numpad_shield_ignores_events_when_no_dressup_active(env):
    """When no Chamfer or Fillet dialog is open, all events pass through unmodified."""
    shield = dressup._DressUpNumpadShield()
    key_event = FakeEvent(env.qtcore.QEvent.KeyPress, env.qtcore.Qt.Key_1, "1")

    handled = shield.eventFilter(None, key_event)
    assert handled is False


def test_numpad_shield_enter_commits_spinbox_and_triggers_ok(env):
    """Pressing Return/Enter commits spinbox text and activates the dialog's OK button."""
    widgets = _setup_chamfer_dialog(env)
    chamfer_size = widgets["chamfer_size"]
    button_box = widgets["button_box"]

    ok_btn = button_box.button(env.qtwidgets.QDialogButtonBox.Ok)
    assert ok_btn.clicks == 0

    shield = dressup._DressUpNumpadShield()
    enter_event = FakeEvent(env.qtcore.QEvent.KeyPress, env.qtcore.Qt.Key_Return, "\r")

    handled = shield.eventFilter(None, enter_event)
    assert handled is True
    assert getattr(chamfer_size, "_text_interpreted", False) is True
    assert ok_btn.clicks == 1


def test_numpad_shield_escape_triggers_cancel(env):
    """Pressing Escape activates the dialog's Cancel button."""
    widgets = _setup_chamfer_dialog(env)
    button_box = widgets["button_box"]

    cancel_btn = button_box.button(env.qtwidgets.QDialogButtonBox.Cancel)
    assert cancel_btn.clicks == 0

    shield = dressup._DressUpNumpadShield()
    esc_event = FakeEvent(env.qtcore.QEvent.KeyPress, env.qtcore.Qt.Key_Escape)

    handled = shield.eventFilter(None, esc_event)
    assert handled is True
    assert cancel_btn.clicks == 1


def test_selection_observer_auto_focuses_spinbox_and_sets_selection_mode(env):
    """Adding a 3D selection auto-focuses the spinbox and keeps buttonRefSel checked."""
    widgets = _setup_chamfer_dialog(env)
    chamfer_size = widgets["chamfer_size"]
    button_ref_sel = widgets["button_ref_sel"]

    observer = dressup._DressUpSelectionObserver()
    observer.addSelection("TestDoc", "Pad", "Edge1")
    FakeTimer.pump()

    assert button_ref_sel.isChecked() is True
    assert getattr(chamfer_size, "_focused", False) is True
    assert getattr(chamfer_size, "_all_selected", False) is True


def test_selection_observer_normalizes_body_subelement(env):
    """Picks on Body are normalized to the base feature so referenceSelected accepts them."""
    _widgets = _setup_chamfer_dialog(env)

    observer = dressup._DressUpSelectionObserver()
    env.gui_events.clear()

    # Emulate selection on Body.Edge3
    observer.addSelection("TestDoc", "Body", "Pad.Edge3")

    # Observer should normalize and forward Pad selection
    forwarded = [evt for evt in env.gui_events if evt[0] == "selection"]
    assert len(forwarded) >= 1
    assert ("selection", "Pad") in forwarded


def test_install_and_uninstall_enhancers(env):
    """Enhancers install and uninstall idempotently without leaking filters or observers."""
    dressup.uninstall_dressup_enhancers()

    task_surface = FakeQtWidget()
    task_surface.setObjectName("Tasks")
    task_child = FakeQtWidget()
    task_surface.children = [task_child]
    env.main_window.widgets.append(task_surface)

    dressup.install_dressup_enhancers()
    app = env.pyside.QtWidgets.QApplication.instance()
    assert app.filters == []
    assert dressup._numpad_shield_targets
    assert task_surface._installed_filters == [dressup._numpad_shield_filter]
    assert task_child._installed_filters == [dressup._numpad_shield_filter]
    assert len(env.selection_observers) >= 1

    dressup.uninstall_dressup_enhancers()
    assert len(app.filters) == 0
    assert task_surface._installed_filters == []
    assert task_child._installed_filters == []
    assert len(env.selection_observers) == 0
