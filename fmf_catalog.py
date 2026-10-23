"""Shared FMF discovery metadata, ranking, and shortcut planning.

This module deliberately has no FreeCAD or Qt imports.  Search, diagnostics,
and the runtime shortcut UI can therefore consume the same stable identities
without inventing private command maps.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LAYOUT_PATH = ROOT / "Resources" / "FMF" / "layout-v3.json"
METADATA_PATH = ROOT / "Resources" / "FMF" / "command-catalog.json"
_CAMEL_RE = re.compile(r"[A-Z]+(?=[A-Z][a-z]|\d|$)|[A-Z]?[a-z]+|\d+")


@dataclass(frozen=True)
class CatalogEntry:
    """One invokable or navigable item with a stable canonical identity."""

    id: str
    name: str
    kind: str = "command"
    aliases: tuple[str, ...] = ()
    workbenches: tuple[str, ...] = ()
    shortcut: str = ""
    target: str = ""
    explanation: str = ""
    available: bool = True

    @property
    def searchable_text(self):
        return " ".join((self.name, self.id, *self.aliases)).strip()


@dataclass(frozen=True)
class ShortcutConflict:
    """An occupied shortcut and the explicit reassignment FMF proposes."""

    sequence: str
    owner_id: str
    owner_name: str
    target_id: str


@dataclass
class ShortcutPlan:
    """A non-mutating plan; callers apply it only after user acceptance."""

    assignments: dict[str, str] = field(default_factory=dict)
    conflicts: list[ShortcutConflict] = field(default_factory=list)
    prior: dict[str, str] = field(default_factory=dict)


def _tokens(text):
    tokens = []
    for part in re.split(r"[^A-Za-z0-9]+", text or ""):
        tokens.extend(piece.casefold() for piece in _CAMEL_RE.findall(part))
    return tokens


def _distance(left, right, limit):
    if abs(len(left) - len(right)) > limit:
        return None
    previous = list(range(len(right) + 1))
    for row, char_left in enumerate(left, 1):
        current = [row]
        for column, char_right in enumerate(right, 1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[column] + 1,
                    previous[column - 1] + (char_left != char_right),
                )
            )
        previous = current
    result = previous[-1]
    return result if result <= limit else None


def _field_score(term, text, base=0):
    folded = text.casefold()
    if folded == term:
        return base
    if folded.startswith(term):
        return base + 5
    words = _tokens(text)
    if term in words:
        return base + 12
    for index, word in enumerate(words):
        if word.startswith(term):
            return base + 18 + min(index, 4)
    for word in words:
        position = word.find(term)
        if position > 0:
            return base + 95 + min(position, 10)
    limit = 1 if len(term) < 6 else 2
    fuzzy = [_distance(term, word, limit) for word in words]
    fuzzy = [value for value in fuzzy if value not in (None, 0)]
    if fuzzy:
        return base + 130 + min(fuzzy) * 15
    return None


def score(query, entry, active_workbench=""):
    """Return a deterministic relevance score (lower is better)."""
    terms = query.casefold().split()
    if not terms:
        return 0
    fields = [(entry.name, 0), *[(alias, 20) for alias in entry.aliases], (entry.id, 80)]
    total = 0
    for term in terms:
        matches = [_field_score(term, text, base) for text, base in fields]
        matches = [value for value in matches if value is not None]
        if not matches:
            return None
        total += min(matches)
    if active_workbench and active_workbench in entry.workbenches:
        total -= 10
    if not entry.available:
        total += 500
    return total


@lru_cache(maxsize=128)
def _rank_cached(query, entries, active_workbench):
    ranked = []
    for entry in entries:
        value = score(query, entry, active_workbench)
        if value is not None:
            ranked.append((value, entry.name.casefold(), entry.id.casefold(), entry))
    ranked.sort(key=lambda item: item[:3])
    return tuple(item[3] for item in ranked)


def rank(query, entries, active_workbench=""):
    """Return catalog entries ordered by relevance and stable identity."""
    return _rank_cached(query, tuple(entries), active_workbench)


@lru_cache(maxsize=1)
def load_catalog(layout_path=LAYOUT_PATH, metadata_path=METADATA_PATH):
    """Build the catalog from the authoritative layout plus small overrides."""
    layout = json.loads(Path(layout_path).read_text(encoding="utf-8"))
    metadata = json.loads(Path(metadata_path).read_text(encoding="utf-8"))
    found = {}
    for workbench, panels in layout["workbenches"].items():
        for panel in panels:
            for area in ("commands", "overflow"):
                for command in panel.get(area, []):
                    command_id, _source, _size, label, _icon = command
                    record = found.setdefault(command_id, {"names": [], "workbenches": []})
                    if label and label not in record["names"]:
                        record["names"].append(label)
                    if workbench not in record["workbenches"]:
                        record["workbenches"].append(workbench)
    overrides = metadata.get("entries", {})
    entries = []
    for command_id, record in found.items():
        override = overrides.get(command_id, {})
        entries.append(
            CatalogEntry(
                id=command_id,
                name=override.get("name") or record["names"][0] or command_id,
                aliases=tuple(override.get("aliases", ())),
                workbenches=tuple(record["workbenches"]),
                shortcut=override.get("shortcut", ""),
                explanation=override.get("explanation", ""),
            )
        )
    for item_id, override in overrides.items():
        if item_id in found:
            continue
        entries.append(
            CatalogEntry(
                id=item_id,
                name=override["name"],
                kind=override.get("kind", "command"),
                aliases=tuple(override.get("aliases", ())),
                workbenches=tuple(override.get("workbenches", ())),
                shortcut=override.get("shortcut", ""),
                target=override.get("target", ""),
                explanation=override.get("explanation", ""),
            )
        )
    return tuple(sorted(entries, key=lambda item: item.id.casefold()))


@lru_cache(maxsize=1)
def entry_map():
    return {entry.id: entry for entry in load_catalog()}


def plan_shortcuts(desired, actions):
    """Inspect action records without changing them.

    ``actions`` contains dictionaries with ``id``, ``name``, and ``shortcut``.
    The returned ``prior`` map is sufficient to restore every affected action.
    """
    plan = ShortcutPlan(assignments=dict(desired))
    normalized = {sequence.casefold(): command for command, sequence in desired.items()}
    for action in actions:
        action_id = action.get("id", "")
        sequence = action.get("shortcut", "")
        if action_id in desired or sequence.casefold() in normalized:
            plan.prior[action_id] = sequence
        target = normalized.get(sequence.casefold())
        if sequence and target and action_id != target:
            plan.conflicts.append(
                ShortcutConflict(sequence, action_id, action.get("name") or action_id, target)
            )
    return plan
