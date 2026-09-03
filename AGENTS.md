# Agent Workspace Guidelines for FusionMyFreeCAD

## Internal Scratchpad & Snippet Cache: `ai_poop/`
- **Default / Project-Local:** All agent scratchpads, FreeCAD diagnostic snippets, and execution helpers belong in the project-local [`ai_poop/`](./ai_poop/README.md).
- **Check local first:** Before creating one-off diagnostic scripts, FreeCAD subprocess runners, or Coin3D calculations, check `ai_poop/`.
- **Global Poop Rule:** A portable global folder exists on the Desktop (`~/Desktop/AI_Poop`), but **NEVER** read from, write to, or modify the global folder unless the user explicitly requests it.
- **Strict Separation:** Never put project-specific logic, repository paths, or addon build scripts into the global folder.
- Do not commit `ai_poop/` to user-facing git releases; it is ignored in `.gitignore`.

## Local Environment Pointers
- **Python for tests:** `C:\Program Files\Python313\python.exe`
- **Pytest:** `& "C:\Program Files\Python313\python.exe" -m pytest`
- **FreeCAD 1.1 Executables:**
  - GUI: `C:\Program Files\FreeCAD 1.1\bin\freecad.exe`
  - Headless/CLI: `C:\Program Files\FreeCAD 1.1\bin\freecadcmd.exe`
- **Addon Mod Path:** `C:\Users\Colin\AppData\Roaming\FreeCAD\v1-1\Mod\FusionMyFreeCAD`
- **Local Dev Deploy:** `powershell -ExecutionPolicy Bypass -File .\tools\install-dev.ps1`
