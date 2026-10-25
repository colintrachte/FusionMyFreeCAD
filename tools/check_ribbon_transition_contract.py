"""Reject Ribbon changes that corrupt Sketcher-exit workbench transitions."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FCBINDING = ROOT / "bundled-addons" / "FreeCAD-Ribbon" / "FCBinding.py"
BOOTSTRAP = ROOT / "fmf_bootstrap.py"


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


def validate(source: str | None = None, bootstrap_source: str | None = None) -> None:
    """Validate passive transition and stable panel-identity invariants."""
    source = FCBINDING.read_text(encoding="utf-8") if source is None else source
    bootstrap_source = (
        BOOTSTRAP.read_text(encoding="utf-8") if bootstrap_source is None else bootstrap_source
    )
    transition = _method_source(source, "onUserChangedWorkbench")
    forbidden_transition_work = (
        "self.onWbActivated(",
        "self.ApplicationMenus(",
        "self.buildPanels(",
        "self.on_Customize_Clicked(",
    )
    present = [fragment for fragment in forbidden_transition_work if fragment in transition]
    if present:
        raise RuntimeError(
            "Ribbon transition contract: a user tab handler performs transition rebuild work; "
            f"found {present}"
        )
    if transition.count("Gui.activateWorkbench(") != 1:
        raise RuntimeError(
            "Ribbon transition contract: only a user tab choice may request one workbench change"
        )
    if "self._fmfProgrammaticTabChange" not in transition:
        raise RuntimeError("Ribbon transition contract: programmatic tab changes are not guarded")

    selector = _method_source(source, "selectFmfWorkbenchContext")
    for fragment in (
        "self._fmfProgrammaticTabChange = True",
        "finally:",
        "self._fmfProgrammaticTabChange = False",
        "workbenchName not in self._fmfBuiltWorkbenches",
    ):
        if fragment not in selector:
            raise RuntimeError(
                "Ribbon transition contract: passive context selection is incomplete; "
                f"missing {fragment}"
            )

    activation = _method_source(source, "onWbActivated")
    for fragment in ("Gui.activateWorkbench(", "self.buildPanels("):
        if fragment in activation:
            raise RuntimeError(
                "Ribbon transition contract: host activation callback performs forbidden work; "
                f"found {fragment}"
            )
    if "self.selectFmfWorkbenchContext(workbenchName)" not in activation:
        raise RuntimeError("Ribbon transition contract: host activation is not presentation-only")

    resize = _method_source(source, "resizeEvent")
    if "_rebuildResponsivePanels" in source or "QTimer.singleShot" in resize:
        raise RuntimeError("Ribbon transition contract: resize may replace live panel widgets")

    bootstrap_tree = ast.parse(bootstrap_source)
    observer = next(
        node
        for node in bootstrap_tree.body
        if isinstance(node, ast.ClassDef) and node.name == "_SketchEditWorkbenchObserver"
    )
    observer_source = ast.get_source_segment(bootstrap_source, observer) or ""
    if "Gui.activateWorkbench(" in observer_source:
        raise RuntimeError(
            "Ribbon transition contract: sketch edit observers must not activate workbenches"
        )
    if "show_ribbon_context(" not in observer_source:
        raise RuntimeError("Ribbon transition contract: sketch edit presentation is not passive")

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

    reset = _method_source(source, "_resetOnePanel")
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
