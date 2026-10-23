- [x] **Score 5 🥇 · Class 1 — Instantiate FMF governance and PMT configuration**

  **ID:** task_a1010000000000000000000000000001
  **Status:** Shipped
  **Outcome:** Replace generic PMT placeholders with FMF identity, review tiers, routing constraints, and read-only external-reference definitions.
  **Work mode:** Steward
  **Execution size:** Medium
  **Uncertainty:** Low
  **Acceptance:** Governance files contain no `[FILL IN` markers and explicitly protect profile restoration, document mutation, workbench lifecycle, packaging, and version authority.
  **Expected evidence:** PMT doctor and route checks pass with no runtime-code changes.
  **Implement:** `CLAUDE.md` · `REVIEW_TIERS.md` · `docs/ai-harness.md` · `helper_scripts/PMT/external_refs.json` · `helper_scripts/PMT/system_prompt.txt`
  **Context:** `AGENTS.md` · `FORGE_AND_STEWARD.md` · `docs/dev-guide/CURRENT-FEATURE-INVENTORY.md`

- [x] **Score 5 🥇 · Class 2 — Build stock-to-FMF parity matrices**

  **ID:** task_a1030000000000000000000000000003
  **Status:** Shipped
  **Outcome:** Map every Design/Part/Sketch/Surface stock command and workflow to prominent, dropdown, searchable, intentionally omitted, or superior FMF paths.
  **Work mode:** Forge + Steward
  **Execution size:** Large
  **Uncertainty:** Medium
  **Protected behavior:** Curated Create/Modify/Construct/Inspect organization is not replaced by toolbar discovery.
  **Acceptance:** Every current stock and FMF command ID has a verified disposition; omissions have rationale and an alternate path.
  **Expected evidence:** Four reviewed matrices and an automated completeness check.
  **Implement:** `docs/dev-guide/workbench-parity.md` · `tools/check_workbench_parity.py`
  **Context:** `Resources/FMF/layout-v3.json` · `command-map.md` · `docs/dev-guide/CURRENT-FEATURE-INVENTORY.md`
  **Read:** `<freecad>/src/Mod/PartDesign/Gui/Workbench.cpp` · `<freecad>/src/Mod/Part/Gui/Workbench.cpp` · `<freecad>/src/Mod/Sketcher/Gui/Workbench.cpp` · `<freecad>/src/Mod/Surface/Gui/Workbench.cpp`

- [x] **Score 5 🥇 · Class 2 — Specify the activation and restoration state machine**

  **ID:** task_a1040000000000000000000000000004
  **Status:** Shipped
  **Outcome:** Define canonical lifecycle behavior for install, activate, decline, disable, upgrade, failure, shutdown, restore, uninstall, reinstall, and optional stock-workbench hiding.
  **Work mode:** Forge + Steward
  **Execution size:** Large
  **Uncertainty:** High
  **Protected behavior:** Baseline is write-once; recovery remains reachable after partial failure; declining activation leaves FreeCAD unchanged.
  **Acceptance:** Transitions are idempotent, partial failure yields usable classic UI, native toolbars remain discoverable, and prior workbench visibility restores exactly.
  **Expected evidence:** State diagram, transition table, failure-injection tests, and GUI checklist.
  **Implement:** `docs/dev-guide/ACTIVATION-AND-RESTORATION.md` · `tests/test_lifecycle.py`
  **Context:** `fmf_bootstrap.py` · `Resources/FMF/runtime.py` · `tests/test_install.py`
  **Read:** `<fmf-study>/ANALYTICAL_FOUNDATIONS_AND_BENCHMARKS.md` · `<fmf-study>/upstream_repos/NeoRibbon/InitGui.py`
  **Prefer after:** task_a1020000000000000000000000000002

- [x] **Score 5 🥇 · Class 2 — Introduce a native action adapter**

  **ID:** task_a1050000000000000000000000000005
  **Status:** Shipped — adapter foundation; renderer integration is tracked separately
  **Outcome:** Resolve and invoke native actions and expose enabled/checkable/checked state with safe subscription disposal and no layout policy.
  **Work mode:** Forge + Steward
  **Execution size:** Medium
  **Uncertainty:** Medium
  **Protected behavior:** Existing command invocation, usage tracking, and layout declarations retain their semantics.
  **Acceptance:** A checkable action synchronizes through ribbon, menu, shortcut, and native code; missing/destroyed actions degrade safely.
  **Expected evidence:** Unit fixtures and a real-FreeCAD demonstration.
  **Implement:** `fmf_actions.py` · `Resources/FMF/runtime.py`
  **Context:** `fmf_common.py` · `fmf_bootstrap.py`
  **Read:** `<fmf-study>/THE_IDEAL_ARCHITECTURE.md` · `<fmf-study>/research/NEORIBBON_TECHNICAL_REVIEW.md`
  **Blocked by:** task_a1020000000000000000000000000002 · task_a1030000000000000000000000000003
