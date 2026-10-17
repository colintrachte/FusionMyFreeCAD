"""Regression tests for the tracked-file privacy gate."""

from __future__ import annotations

import sys

from fake_freecad import ROOT

sys.path.insert(0, str(ROOT / "tools"))
from check_repository_privacy import scan_repository, scan_text


def test_tracked_repository_has_no_private_machine_details_or_secrets():
    assert scan_repository(ROOT) == []


def test_privacy_scanner_identifies_values_without_returning_them():
    slash = chr(92)
    samples = [
        slash.join(("C:", "Users", "someone", "Desktop", "private.txt")),
        slash.join(("D:", "Git", "SomeProject", "file.py")),
        "-----BEGIN " + "PRIVATE KEY-----",
        "ghp_" + "abcdefghijklmnopqrstuvwxyz123456",
    ]
    findings = scan_text("\n".join(samples))
    assert findings == [
        (1, "absolute Windows user-profile path"),
        (2, "personal workspace path"),
        (3, "PEM private key"),
        (4, "GitHub personal access token"),
    ]


def test_privacy_scanner_allows_portable_paths_and_public_noreply_email():
    text = "\n".join(
        [
            r"%APPDATA%\FreeCAD\Mod\FMF",
            "~/projects/FMF",
            "<fmf-repo>/tools/install-dev.ps1",
            "colintrachte@users.noreply.github.com",
        ]
    )
    assert scan_text(text) == []
