"""Reject Ribbon changes that corrupt Sketcher-exit workbench transitions."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FCBINDING = ROOT / "bundled-addons" / "FreeCAD-Ribbon" / "FCBinding.py"


def _method_source(source: str, name: str) -> str:
    tree = ast.parse(source)
    method = next(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
        ),
        None,
    )
    if method is None:
        raise RuntimeError(f"Ribbon transition contract: {name}() is missing")
    return ast.get_source_segment(source, method) or ""


def validate(source: str | None = None) -> None:
    """Validate the synchronization and panel-identity invariants."""
    source = FCBINDING.read_text(encoding="utf-8") if source is None else source
    transition = _method_source(source, "onUserChangedWorkbench")
    if transition.count("self.onWbActivated()") != 2:
        raise RuntimeError(
            "Ribbon transition contract: onUserChangedWorkbench() must retain both "
            "onWbActivated() synchronization passes"
        )
    if transition.count("self.ApplicationMenus()") != 2:
        raise RuntimeError(
            "Ribbon transition contract: onUserChangedWorkbench() must retain both "
            "ApplicationMenus() synchronization passes"
        )
    second_sync = transition.rindex("self.onWbActivated()")
    for required_after in ("self.hideClassicToolbars()", "self.on_Customize_Clicked()"):
        if required_after not in transition or second_sync > transition.index(required_after):
            raise RuntimeError(
                "Ribbon transition contract: the second synchronization pass must run "
                f"before {required_after}"
            )

    replacement = _method_source(source, "_fmfReplacePanel")
    required_replacement_fragments = (
        "category.replaceWidget(panel, replacement)",
        "if candidate is panel:",
        "category._panels.pop(key, None)",
        "category._panels[replacement.objectName()] = replacement",
        "panel.deleteLater()",
    )
    missing = [
        fragment for fragment in required_replacement_fragments if fragment not in replacement
    ]
    if missing:
        raise RuntimeError(
            "Ribbon transition contract: panel replacement can retain stale aliases; "
            f"missing {missing}"
        )

    responsive = _method_source(source, "_rebuildResponsivePanels")
    reset = _method_source(source, "_resetOnePanel")
    if "self._fmfReplacePanel(category, panel, replacement)" not in responsive:
        raise RuntimeError(
            "Ribbon transition contract: responsive rebuild bypasses safe panel replacement"
        )
    if "self._fmfReplacePanel(self.currentCategory(), panel, replacement)" not in reset:
        raise RuntimeError(
            "Ribbon transition contract: panel reset bypasses safe panel replacement"
        )
    if "category._panels[replacement.title()]" in source:
        raise RuntimeError("Ribbon transition contract: display-title panel aliases are forbidden")


def main() -> None:
    validate()
    print("Ribbon transition contract passed.")


if __name__ == "__main__":
    main()
