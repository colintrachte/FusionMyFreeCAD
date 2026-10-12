# FMF 1.8.0 baseline journeys

Run these journeys before and after each owned-workbench migration slice. Record FreeCAD build,
OS, display scale, clean/custom profile, elapsed time, errors, assistance, and recovery result.

1. Install, restart, verify four layouts, and run **Verify FusionMyFreeCAD**.
2. Create a document/body/sketch from Part Design, select an origin plane, finish, and return.
3. Create constrained geometry using Coincident, Smart Dimension, Midpoint, and Smart Slot.
4. Mirror attached and free geometry with **Mirror + Constraints** and Pad multiple regions.
5. Create Pad/Pocket, then Fillet/Chamfer by 3D pick, numpad dimension, preview, and Enter.
6. Create a datum midplane and edit parameters through the dock.
7. Break a supported attachment, run Repair References, Update Model, Undo, and recompute.
8. Export representative STEP, STL/3MF, and DXF selections.
9. Reorder/reset one panel, exercise FREQUENT promotion, restart, and verify persistence.
10. Search commands, objects, and preferences using Fusion and native terminology.
11. Reapply FMF, then restore the original customized profile and compare managed state.
12. Simulate interrupted startup and missing state with the baseline intact; verify recovery.

`tools/benchmark_fmf.py` records the static layout baseline. Run it with `--live` inside FreeCAD to
capture the build and workbench probe. GUI timing, screenshots, and interaction results remain
manual evidence and must not be inferred from the static output.

## Running against the FreeCAD source build

An installed FreeCAD executable is not required. The upstream reference checkout may provide a
built Pixi environment at `.pixi/envs/default/Library/bin/FreeCAD.exe` on Windows. Treat that
checkout as read-only: run its executable, but put scripts, logs, configuration, temporary data,
and output under this repository's ignored `ai_poop/` directory.

Set `FREECAD_USER_HOME`, `FREECAD_USER_DATA`, and `FREECAD_USER_TEMP` to an isolated directory and
also pass isolated `--user-cfg` and `--system-cfg` paths. Add this repository with `-M` only when
the test intentionally loads FMF. For native-FreeCAD control measurements, pass
`--disable-addon FusionMyFreeCAD`. On the checked source build, prepend the Pixi environment,
`Library/bin`, and `Scripts` to `PATH` and set `QT_PLUGIN_PATH` to
`Library/lib/qt6/plugins` before launching.

The checked-in live evidence was captured from source build `26.3.0devR47870` at revision
`a61ee58c265ca735e1ddbd2df0a9ca78574b5284`. The isolated native-action probe toggled
`Std_ViewStatusBar`, observed five state notifications, restored the original state, and degraded
safely for a missing action; see `tests/fixtures/freecad-native-action.json`.

The Coincident backend regression probe created two disconnected sketch lines, selected `Vertex2`
and `Vertex3`, and ran the exact command declared by FMF:
`Sketcher_ConstrainCoincidentUnified`. The source build added one `Coincident` constraint. The
machine-readable result is `tests/fixtures/freecad-coincident-command.json`. A human click check of
the rendered FMF button remains required because a hidden startup script cannot establish whether
the visible ribbon button is wired to the same native command after the UI settles.

Fresh-profile FMF startup also exposed a benchmark risk: FreeCAD Ribbon's first-run command-cache
generation stalled while switching to `CAMWorkbench` in a hidden run. Do not count that launch as
a successful startup measurement. Repeat it visibly or pre-seed the cache before recording startup
timings, and retain the log as diagnostic evidence rather than silently timing out.

## Manual sign-off record

The remaining evidence must be gathered in a visible FreeCAD session. Record `PASS` or `FAIL` and a
short note for each item; attach screenshots for items 1, 3, 5, and 9.

1. Four layouts: Part Design, Part, Sketcher, and Surface render without blank or overlapping panels.
2. Sketch transition: create a Body and plane-attached sketch, Finish Sketch, reopen it, and finish
   again; the expected workbench and tree selection return each time.
3. Coincident button: draw two disconnected lines, Ctrl-select their nearest endpoints, click FMF's
   Coincident button, and confirm one Coincident constraint appears and the endpoints join.
4. Mirror + Constraints: mirror attached and free sketch geometry; confirm geometry and constraints
   survive Finish Sketch and reopen.
5. Multi-region Pad: make two closed non-overlapping profiles and Pad both in one operation.
6. Dress-up input: create Fillet or Chamfer from a selected 3D edge, type a value, preview, accept,
   and Undo once.
7. Export: export representative objects through FMF to STEP and STL or 3MF, plus a sketch to DXF;
   confirm each file is created and non-empty.
8. Search and adaptation: find one command using Fusion terminology and one using its FreeCAD name;
   invoke a FREQUENT candidate repeatedly, restart, and confirm only FREQUENT changes.
9. Lifecycle: run Verify FusionMyFreeCAD, note the result, run Reset FusionMyFreeCAD and restart, then disable
   FusionMyFreeCAD. Restart again and confirm native menus/toolbars and the pre-FMF workbench
   appearance remain active. Re-enable FMF in Preferences and restart to confirm it returns.

Report the FreeCAD version, Windows display scale, whether the profile was already customized, and
rough cold-start time. Any failure keeps this gate open; do not work around it merely to obtain a
passing record.
