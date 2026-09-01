"""The human release helper updates metadata without rewriting historical release text."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_helper():
    spec = importlib.util.spec_from_file_location(
        "prepare_release", ROOT / "tools" / "prepare_release.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def release_tree(tmp_path: Path) -> Path:
    (tmp_path / "Resources/FusionMyFreeCAD").mkdir(parents=True)
    (tmp_path / "docs").mkdir()
    (tmp_path / "package.xml").write_text(
        "<package>\n  <version>1.2.0</version>\n  <date>2026-08-31</date>\n</package>\n",
        encoding="utf-8",
    )
    for name in ("layout-v3.json", "layout-manifest.json"):
        (tmp_path / "Resources/FusionMyFreeCAD" / name).write_text(
            '{\n  "layoutVersion": "1.2.0",\n  "other": true\n}\n', encoding="utf-8"
        )
    (tmp_path / "README.md").write_text(
        "Version **1.2.0**\n"
        "`FusionMyFreeCAD-1.2.0.zip` [1.2.0 release](repo/releases/tag/v1.2.0)\n",
        encoding="utf-8",
    )
    (tmp_path / "docs/INSTALL-FREECAD-ADDON.md").write_text(
        "`FusionMyFreeCAD-1.2.0.zip` [1.2.0 release](repo/releases/tag/v1.2.0)\n"
        "Version 1.2.0 replaced the retired installer.\n",
        encoding="utf-8",
    )
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n"
        "All notable user-visible changes to FusionMyFreeCAD are recorded here.\n\n"
        "## 1.2.0 — 2026-08-31\n\nOld changes.\n",
        encoding="utf-8",
    )
    return tmp_path


def test_prepare_updates_current_metadata_and_creates_editable_notes(tmp_path):
    helper = load_helper()
    root = release_tree(tmp_path)

    changed = helper.prepare(root, "1.3.0", "2026-09-01")

    assert changed
    assert "<version>1.3.0</version>" in (root / "package.xml").read_text(encoding="utf-8")
    assert "<date>2026-09-01</date>" in (root / "package.xml").read_text(encoding="utf-8")
    for name in ("layout-v3.json", "layout-manifest.json"):
        assert '"layoutVersion": "1.3.0"' in (root / "Resources/FusionMyFreeCAD" / name).read_text(
            encoding="utf-8"
        )
    assert "Version **1.3.0**" in (root / "README.md").read_text(encoding="utf-8")
    install = (root / "docs/INSTALL-FREECAD-ADDON.md").read_text(encoding="utf-8")
    assert "FusionMyFreeCAD-1.3.0.zip" in install
    assert "Version 1.2.0 replaced the retired installer." in install
    assert "## 1.3.0 — 2026-09-01" in (root / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "TODO" in (root / "docs/RELEASE-NOTES-1.3.0.md").read_text(encoding="utf-8")

    assert helper.prepare(root, "1.3.0", "2026-09-01") == []


@pytest.mark.parametrize("version", ["v1.3.0", "1.3", "next"])
def test_prepare_rejects_ambiguous_versions(tmp_path, version):
    helper = load_helper()
    root = release_tree(tmp_path)

    with pytest.raises(ValueError, match=r"X\.Y\.Z"):
        helper.prepare(root, version, "2026-09-01")
