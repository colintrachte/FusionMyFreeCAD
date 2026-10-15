"""Regression coverage for FMF terminology in the bundled SearchBar."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEARCH_BOX = ROOT / "bundled-addons" / "SearchBar" / "SearchBox.py"


def _search_helpers():
    tree = ast.parse(SEARCH_BOX.read_text(encoding="utf-8"))
    wanted = {"fmfSearchableText", "fmfResultText"}
    functions = [
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in wanted
    ]
    namespace = {}
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(SEARCH_BOX), "exec"), namespace)
    return namespace


def test_pad_is_searchable_by_native_and_fmf_names():
    helpers = _search_helpers()
    group = {
        "text": "Extrude",
        "toolTip": "<b>Pad</b><i>PartDesign_Pad</i>",
    }

    searchable = helpers["fmfSearchableText"](group).lower()
    assert "pad" in searchable
    assert "extrude" in searchable
    assert helpers["fmfResultText"](group) == "Pad / Extrude (Part Design)"


def test_part_extrude_remains_distinct_from_part_design_pad():
    helpers = _search_helpers()
    group = {
        "text": "Extrude",
        "toolTip": "<b>Extrude</b><i>Part_Extrude</i>",
    }

    assert helpers["fmfResultText"](group) == "Extrude (Part)"
