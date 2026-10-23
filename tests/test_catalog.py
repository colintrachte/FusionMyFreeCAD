import json
from pathlib import Path

import fmf_catalog


def test_layout_commands_have_one_canonical_catalog_entry():
    entries = fmf_catalog.load_catalog()
    ids = [entry.id for entry in entries]
    assert len(ids) == len(set(ids))
    assert "PartDesign_Pad" in ids
    assert "Part_Extrude" in ids


def test_product_alias_is_discovery_only_and_ranks_the_canonical_command():
    entries = fmf_catalog.load_catalog()
    ranked = fmf_catalog.rank("extrude join", entries, "FMFDesignWorkbench")
    assert ranked[0].id == "PartDesign_Pad"
    assert ranked[0].name == "Pad"


def test_typo_and_abbreviation_ranking_is_deterministic():
    entries = fmf_catalog.load_catalog()
    first = [entry.id for entry in fmf_catalog.rank("revolv", entries)]
    second = [entry.id for entry in fmf_catalog.rank("revolv", entries)]
    assert first == second
    assert {"PartDesign_Revolution", "Part_Revolve"} >= {first[0]}
    assert fmf_catalog.rank("lne", entries)[0].id == "Sketcher_CreateLine"


def test_catalog_covers_non_command_targets():
    kinds = {entry.kind for entry in fmf_catalog.load_catalog()}
    assert {"command", "object", "preference", "help"} <= kinds


def test_shortcut_plan_is_non_mutating_and_captures_exact_prior_state():
    actions = [
        {"id": "PartDesign_Pad", "name": "Pad", "shortcut": ""},
        {"id": "Assembly_View", "name": "Assembly View", "shortcut": "E"},
        {"id": "Std_Copy", "name": "Copy", "shortcut": "Ctrl+C"},
    ]
    before = json.loads(json.dumps(actions))
    plan = fmf_catalog.plan_shortcuts({"PartDesign_Pad": "E"}, actions)
    assert actions == before
    assert plan.prior == {"PartDesign_Pad": "", "Assembly_View": "E"}
    assert plan.conflicts[0].owner_id == "Assembly_View"
    assert plan.conflicts[0].target_id == "PartDesign_Pad"


def test_search_corpus_is_versioned_and_has_at_least_thirty_queries():
    path = Path(__file__).parent / "fixtures" / "search-corpus.json"
    corpus = json.loads(path.read_text(encoding="utf-8"))
    assert corpus["schemaVersion"] == 1
    assert len(corpus["queries"]) >= 30
    assert {item["category"] for item in corpus["queries"]} >= {
        "exact",
        "fusion-alias",
        "abbreviation",
        "typo",
        "cross-workbench",
        "object",
        "preference",
        "help",
    }
