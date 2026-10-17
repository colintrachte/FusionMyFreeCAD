"""Reject personal machine paths, private emails, and likely secrets in tracked text."""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Rule:
    name: str
    pattern: re.Pattern[str]


RULES = (
    Rule(
        "absolute Windows user-profile path",
        re.compile(r"(?i)(?<![A-Z0-9_])[A-Z]:[\\/]+Users[\\/]+[^\\/\s\"'<>]+[\\/]"),
    ),
    Rule(
        "personal workspace path",
        re.compile(r"(?i)(?<![A-Z0-9_])[A-Z]:[\\/]+(?:AI Sandbox|Git)(?:[\\/]|$)"),
    ),
    Rule(
        "known private email",
        re.compile(r"(?i)(?:cgtrachte@" + r"gmail\.com|colin@" + r"colintrachte\.com)"),
    ),
    Rule("old personal workspace name", re.compile(r"(?i)FreeCAD " + "UI Study")),
    Rule("PEM private key", re.compile(r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----")),
    Rule("GitHub personal access token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    Rule("OpenAI API key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
)


def tracked_files(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        check=True,
        stdin=subprocess.DEVNULL,
        capture_output=True,
    )
    return [root / item.decode("utf-8") for item in result.stdout.split(b"\0") if item]


def scan_text(text: str) -> list[tuple[int, str]]:
    findings = []
    for line_number, line in enumerate(text.splitlines(), 1):
        for rule in RULES:
            if rule.pattern.search(line):
                findings.append((line_number, rule.name))
    return findings


def scan_repository(root: Path) -> list[tuple[Path, int, str]]:
    findings = []
    for path in tracked_files(root):
        if not path.is_file():
            continue
        data = path.read_bytes()
        if b"\0" in data:
            continue
        text = data.decode("utf-8", errors="replace")
        findings.extend((path.relative_to(root), line, name) for line, name in scan_text(text))
    return findings


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    findings = scan_repository(root)
    if not findings:
        print("Repository privacy check passed.")
        return 0

    print("Repository privacy check failed. Replace private values with portable placeholders:")
    for path, line, name in findings:
        # Do not echo a secret or private value into CI logs.
        print("{}:{}: {}".format(path.as_posix(), line, name))
    return 1


if __name__ == "__main__":
    sys.exit(main())
