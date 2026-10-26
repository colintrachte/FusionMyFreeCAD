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
