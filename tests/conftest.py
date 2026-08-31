"""Shared fixtures: a fresh fake FreeCAD session per test."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fake_freecad import ROOT, Environment, FakeTimer


@pytest.fixture
def env(tmp_path):
    environment = Environment(tmp_path / "FreeCAD").install()
    yield environment
    FakeTimer.reset()
    for name in (
        "FreeCAD",
        "FreeCADGui",
        "PySide",
        "PySide.QtCore",
        "PySide.QtGui",
        "PySide.QtWidgets",
        "fusion_bootstrap",
        "_fusion_my_freecad_runtime",
    ):
        sys.modules.pop(name, None)


@pytest.fixture
def bootstrap(env):
    return env.load_bootstrap()


@pytest.fixture
def installed(env, bootstrap):
    """A completed first installation."""
    bootstrap.prepare()
    return bootstrap


@pytest.fixture
def runtime(env, bootstrap):
    return env.load_runtime()


@pytest.fixture(scope="session")
def layout():
    return json.loads(
        (ROOT / "Resources" / "FusionMyFreeCAD" / "layout-v3.json").read_text("utf-8")
    )


@pytest.fixture(scope="session")
def manifest():
    return json.loads(
        (ROOT / "Resources" / "FusionMyFreeCAD" / "layout-manifest.json").read_text("utf-8")
    )


@pytest.fixture(scope="session")
def repo_root():
    return ROOT
