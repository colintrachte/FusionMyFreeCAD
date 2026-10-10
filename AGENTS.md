# Agent Workspace Guidelines for FusionMyFreeCAD

## Version Authority
- **Never increment or otherwise change FusionMyFreeCAD's main project/release version without the
  user's explicit prior approval.** The current 1.8.0 version is accepted and must not be rolled
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
- **Addon Mod Path:** `%APPDATA%\FreeCAD\v1-1\Mod\FusionMyFreeCAD` (PowerShell: `$env:APPDATA\FreeCAD\v1-1\Mod\FusionMyFreeCAD`, Linux: `~/.local/share/FreeCAD/Mod/FusionMyFreeCAD`)
- **Local Dev Deploy:** `powershell -ExecutionPolicy Bypass -File .\tools\install-dev.ps1`
