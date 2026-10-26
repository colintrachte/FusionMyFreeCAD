"""Tests for fmf_persistence service."""

from __future__ import annotations

import pytest

import fmf_persistence as persistence


@pytest.fixture(autouse=True)
def clean_persistence():
    persistence.reset()
    yield
    persistence.reset()


def test_persistence_dirty_tracking(env):
    assert persistence.is_parameters_dirty() is False
    assert persistence.flush_parameters() is False
    assert env.saved_parameters == 0

    persistence.mark_parameters_dirty()
    assert persistence.is_parameters_dirty() is True

    success = persistence.flush_parameters()
    assert success is True
    assert persistence.is_parameters_dirty() is False
    assert env.saved_parameters == 1


def test_persistence_force_flush(env):
    assert persistence.is_parameters_dirty() is False
    success = persistence.flush_parameters(force=True)
    assert success is True
    assert env.saved_parameters == 1


def test_persistence_reset():
    persistence.mark_parameters_dirty()
    assert persistence.is_parameters_dirty() is True
    persistence.reset()
    assert persistence.is_parameters_dirty() is False
