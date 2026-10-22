# Research brief: Native recent documents at FMF startup

**Status:** Independent research pass for implementation planning  
**Date:** 2026-10-21  
**Question:** Should FMF build a recent-document picker, or expose FreeCAD's existing UI?  
**Method:** Inspected FMF startup/action architecture and FreeCAD's official source and documentation.

## Executive finding

FreeCAD already owns both pieces FMF needs. Its Qt Start page displays recent files and can be
opened with the native `Start_Start` command, while `Std_OpenGroup` is a native dropdown action
backed by FreeCAD's recent-file implementation. FMF should not create or persist another history.
It should show the native Start page after FMF startup when no document was supplied or opened,
and provide a durable native-command route back to that page.

## What already exists / key findings

- FreeCAD 1.0 replaced the old Start workbench with a QtWidgets Start page, available through
  **Help -> Start**. The page includes recent files and new-file shortcuts.[1]
- FreeCAD's `Std_OpenGroup` action is a `RecentFilesAction`. Its first item runs the ordinary Open
  command and its remaining items activate FreeCAD's recent files directly.[2]
- FreeCAD's main window owns the MRU list. Normal file open/import and Save As operations append to
  that same list, so reusing it preserves FreeCAD's behavior and preferences.[3][4]
- FMF currently hides the menu bar while enabled and does not expose `Start_Start` or
  `Std_OpenGroup` in its declarative layout. That explains why native recent documents feel buried
  even though the host already provides them (`fmf_bootstrap.py:1203`,
  `Resources/FMF/layout-v3.json:52`).

## Ideas or implications

1. Defer `Gui.runCommand("Start_Start")` until FMF and the Ribbon have completed startup, but only
   when `App.listDocuments()` is empty. This avoids replacing a file explicitly opened from the OS
   or command line.
2. Add a visible **Start / Recent** native command entry to the FMF Design startup surface so the
   user can reopen the same page later.
3. Keep FreeCAD's MRU model authoritative. Do not parse preferences, duplicate paths, generate
   thumbnails, or implement separate missing-file cleanup.
4. Treat `Start_Start` availability as a runtime capability and fail quietly on unsupported host
   builds; FMF supports FreeCAD 1.1+, where the page is expected, but command presence should still
   be tested.

## Contradictions and uncertainty

- The Start page is clearly documented and its command is observed in official FreeCAD project
  output, but the available environment has no discoverable FreeCAD installation for live probing.
- It remains to be verified whether the bundled Ribbon preserves the native submenu of
  `Std_OpenGroup`. The Start page route is therefore the lower-risk primary implementation; a
  Ribbon dropdown should only be added after a live QAction probe.

## Gaps and open questions

- Exact startup timing must be validated in a real FreeCAD 1.1 GUI to ensure the Start page is not
  immediately covered or closed by Ribbon initialization.
- The expected behavior after the last document closes should be decided separately; the present
  request only requires startup exposure.

## Suggested decision or next experiment

Implement native Start-page exposure first: schedule it after UI initialization, gate it on zero
open documents, add a visible command to return to it, and verify it against a clean startup plus a
startup where an `.FCStd` file was supplied. Probe `Std_OpenGroup` live before deciding whether to
surface its dropdown as an additional ribbon control.

## Sources

1. FreeCAD release notes 1.0, Start page: https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Release_notes_1.0.md
2. FreeCAD `Std_OpenGroup` / `RecentFilesAction`: https://github.com/FreeCAD/FreeCAD/blob/main/src/Gui/CommandDoc.cpp
3. FreeCAD `Gui::MainWindow` recent-file API: https://freecad.github.io/SourceDoc/d5/d2f/classGui_1_1MainWindow.html
4. FreeCAD GUI application file-open/MRU path: https://github.com/FreeCAD/FreeCAD/blob/main/src/Gui/Application.cpp
