"""Tests for fmf_chrome controller."""

from __future__ import annotations

import pytest

from fmf_chrome import ChromeController, ChromeState


@pytest.fixture
def controller(env):
    ctrl = ChromeController(env.gui)
    ctrl.reset()
    return ctrl


def test_chrome_skips_mutation_when_state_unchanged(controller, env):
    desired = ChromeState(
        toolbars_hidden=True,
        menubar_hidden=True,
        ribbon_visible=True,
        family_enabled=True,
    )
    # First application mutates chrome
    applied_first = controller.apply(desired)
    assert applied_first is True
    assert controller.current_state == desired

    # Second application with same desired state is a no-op
    applied_second = controller.apply(desired)
    assert applied_second is False
    assert controller.current_state == desired


def test_chrome_restore_resets_state(controller, env):
    desired = ChromeState(
        toolbars_hidden=True,
        menubar_hidden=True,
        ribbon_visible=True,
        family_enabled=True,
    )
    controller.apply(desired)
    assert controller.current_state == desired

    restored = controller.restore()
    assert restored is True
    assert controller.current_state is None


def test_chrome_keeps_menubar_visible_when_ribbon_is_missing(controller, env):
    # When ribbon dock does not exist, menubar must not be hidden
    desired = ChromeState(
        toolbars_hidden=True,
        menubar_hidden=True,
        ribbon_visible=True,
        family_enabled=True,
    )
    env.main_window.menuBar().show()
    assert env.main_window.menuBar().isVisible() is True

    controller.apply(desired)
    assert env.main_window.menuBar().isVisible() is True


def test_chrome_hides_menubar_when_ribbon_is_present_and_visible(controller, env):
    ribbon = env.pyside.QtWidgets.QDockWidget(object_name="Ribbon")
    ribbon.show()
    env.main_window.docks.append(ribbon)

    desired = ChromeState(
        toolbars_hidden=True,
        menubar_hidden=True,
        ribbon_visible=True,
        family_enabled=True,
    )
    controller.apply(desired)
    assert env.main_window.menuBar().isVisible() is False


def test_chrome_keeps_menubar_visible_while_ribbon_dock_is_settling(controller, env):
    class SettlingDock(env.pyside.QtWidgets.QDockWidget):
        def show(self):
            pass

        def isHidden(self):
            return False

    ribbon = SettlingDock(object_name="Ribbon")
    env.main_window.docks.append(ribbon)
    desired = ChromeState(
        toolbars_hidden=True,
        menubar_hidden=True,
        ribbon_visible=True,
        family_enabled=True,
    )

    controller.apply(desired)

    assert ribbon.isVisible() is False
    assert env.main_window.menuBar().isVisible() is True


def test_chrome_reapplies_cached_state_after_ribbon_appears(controller, env):
    desired = ChromeState(
        toolbars_hidden=True,
        menubar_hidden=True,
        ribbon_visible=True,
        family_enabled=True,
    )
    controller.apply(desired)
    assert env.main_window.menuBar().isVisible() is True

    ribbon = env.pyside.QtWidgets.QDockWidget(object_name="Ribbon")
    ribbon.show()
    env.main_window.docks.append(ribbon)

    assert controller.apply(desired) is True
    assert env.main_window.menuBar().isVisible() is False
