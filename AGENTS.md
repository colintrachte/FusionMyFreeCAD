# Agent Workspace Guidelines for FMF

## Version Authority
- **Never increment or otherwise change FMF's main project/release version without the
  user's explicit prior approval.** The current 1.9.0 version is accepted and must not be rolled
  back merely because it was previously incremented without consultation.
- Do not infer permission for a future project-version bump from a feature request, bug fix,
  documentation update, package build, deployment, or release-preparation request. Ask first.
- This rule does not prohibit ordinary changes to unrelated versioned schemas, formats,
  dependencies, compatibility declarations, or internal data when the task requires them.

## Internal Scratchpad & Snippet Cache: `ai_poop/`
- **Default / Project-Local:** All agent scratchpads, FreeCAD diagnostic snippets, and execution helpers belong in the project-local [`ai_poop/`](./ai_poop/README.md).
- **Check local first:** Before creating one-off diagnostic scripts, FreeCAD subprocess runners, or Coin3D calculations, check `ai_poop/`.
- **Global Poop Rule:** A portable global folder exists on the Desktop (`~/Desktop/AI_Poop`), but **NEVER** read from, write to, or modify the global folder unless the user explicitly requests it.
- **Strict Separation:** Never put project-specific logic, repository paths, or addon build scripts into the global folder.
- Do not commit `ai_poop/` to user-facing git releases; it is ignored in `.gitignore`.

## Local Environment Pointers
- **Python for tests:** `C:\Program Files\Python313\python.exe`
- **Pytest:** `& "C:\Program Files\Python313\python.exe" -m pytest`
- **FreeCAD 1.1 Executables:** Locate the active installation with `Get-Command freecad.exe,
  freecadcmd.exe` or use its actual install directory. Do not assume `C:\Program Files\FreeCAD 1.1`;
  that path is not present on every development machine.
- **Addon Mod Path:** `%APPDATA%\FreeCAD\v1-1\Mod\FMF` (PowerShell: `$env:APPDATA\FreeCAD\v1-1\Mod\FMF`, Linux: `~/.local/share/FreeCAD/Mod/FMF`)
- **Local Dev Deploy:** `powershell -ExecutionPolicy Bypass -File .\tools\install-dev.ps1`

## Ribbon Workbench-Transition Guardrail
- In `FreeCAD-Ribbon/FCBinding.py`, the repeated `onWbActivated()`, `ApplicationMenus()`,
  `hideClassicToolbars()`, and customization synchronization inside
  `onUserChangedWorkbench()` are intentional. Do not remove or skip them as a performance
  optimization. FreeCAD may emit its Sketcher-exit workbench signal before Ribbon finishes
  selecting the destination category; suppressing the second synchronization pass can merge
  Sketch and Design panels into one corrupted ribbon tab.
- Performance work may cache idempotent data used by those calls, but must preserve the full
  transition sequence and the regression contract in `tests/test_package.py`.
- Responsive and reset-driven panel replacement must remove every dictionary entry that still
  points to the old panel, then register the replacement by `objectName()`. Do not combine
  `replacePanel()` with a second `_panels[...]` assignment: FMF panel display titles and object
  names differ, so that pattern accumulates stale aliases and eventually renders duplicate panels.

## Focus and Event-Filter Performance Guardrail
- Ribbon focus handlers must not call `setWindowState()`, replace a dock title-bar widget, rebuild
  panels, or otherwise mutate window structure on `ApplicationActivated`, `WindowActivate`, or
  `WindowDeactivate`. Update window-state-dependent icons only from actual `WindowStateChange`.
- SearchBar must retain one shared `EventInspector_SB`, install it at most once per watched object,
  connect `workbenchActivated` once, and provide teardown for disable and shutdown. Never construct
  an event filter inline inside a workbench-activation callback.
- Preserve the structural contracts in `tests/test_package.py`. After changing Ribbon focus or
  SearchBar lifecycle code, also run `tools/probe_focus_performance.py` in the built FreeCAD source
  environment. The accepted baseline is one SearchBar filter, zero filters added by repeated
  installation, zero focus-time title-bar replacements, and sub-2 ms p95 handler time.

## FreeCAD Host-Isolation Guardrail
- FMF startup and Ribbon cache generation must not activate native workbenches to discover
  commands, perform network requests, or install event filters on `QApplication`. Keep task-panel
  Enter handling scoped to the Tasks widget subtree.
- Ribbon construction must suppress tab-change callbacks until all categories exist. Programmatic
  tab insertion is not a user workbench choice and must never activate the tab's workbench.
- Python-defined FMF workbenches do not expose FreeCAD's private `__Workbench__` field. Cache code
  must reuse public data already collected and tolerate unavailable toolbar APIs.
- Every FMF command `Pixmap` must name a real Qt/FreeCAD icon or an existing file. Preserve
  authored icons during vendor sync and run `tools/probe_host_isolation.py` after changes to
  startup, workbench discovery, Ribbon construction, event filters, or command icons.

## Repository Privacy
- Never commit personal absolute paths, user-profile names, private email addresses, credentials,
  conversation exports, or machine-specific workspace names. Use portable environment variables or
  placeholders such as `<fmf-repo>`, `<upstream-reference>`, and `<user-home>`.
- Run `python tools/check_repository_privacy.py` before committing. CI and the release workflow run
  the same check and report only the finding category and location, never the matched value.
