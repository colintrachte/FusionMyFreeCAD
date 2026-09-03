# Handoff: "Mirror + Constraints" and the 1.3.2 → 1.3.3 recovery

**Status:** Work in progress. One feature is not finished; a crash regression is fixed.
**Date:** 2026-09-03
**Author:** Claude (Sonnet 5), from a long pairing session with the maintainer (Colin).
**Scope:** `fusion_sketch_tools.py`, `fusion_bootstrap.py`, `Resources/FusionMyFreeCAD/runtime.py`,
the Sketcher ribbon layout, `tests/`, `tools/install-dev.ps1`, and the withdrawn v1.3.2 release.
**Repo state at handoff:** branch `main`, HEAD = `b0d86a5`, in sync with `origin/main`
(`git status`: `## main...origin/main`, nothing ahead/behind). GitHub release `v1.3.2` is a
**draft** (withdrawn); the `v1.3.2` git tag still points at `c32f982`. No `v1.3.3` release exists;
`package.xml` / `layout-v3.json` / `layout-manifest.json` already say `1.3.3`.
`python -m pytest tests -q` green (149), `ruff` clean, `validate_addon.py` VALID.

---

## 1. TL;DR for whoever picks this up

Two threads ran in parallel:

1. **v1.3.2 crashed FreeCAD 1.1.3 on startup / Sketcher-open** ("Access violation in
   `GUIApplication::notify`", intermittent). **Root-caused and fixed.** v1.3.2 was pulled to a
   draft. `main` now carries the fix as an unreleased 1.3.3.

2. **The "Mirror + Constraints" command still does not do what the user wants.** The user wants a
   mirrored sketch element that (a) is *live-linked* to its source (drag one, the other mirrors —
   "Fusion 360 can do it") **and** (b) leaves a profile whose enclosed regions can be selected and
   extruded. On **FreeCAD 1.1.3 these two goals conflict at the constraint-solver level** and I
   could not satisfy both. The command currently picks one per element (see §6). A targeted
   diagnostic is pending from the user that decides the next move (§8).

If you only read one more section, read **§5 (verified FreeCAD facts)** — those were expensive to
learn and are the constraints any solution must respect.

---

## 2. The v1.3.2 startup crash (RESOLVED)

**Symptom:** `Unhandled Base::Exception caught in GUIApplication::notify. ... Access violation`,
FreeCAD frozen, on FreeCAD 1.1.3, typically the first launch after installing 1.3.2, before the
user ran any command. Did not always reproduce on a plain restart.

**What 1.3.2 added:** `fusion_sketch_tools.py` (new module) + 3 Sketcher ribbon buttons
(`FusionMyFreeCAD_MirrorWithConstraints`, the `Sketcher_ConstrainCoincidentUnified` swap,
`Sketcher_ConstrainPointOnObject`).

**Root cause:** `MirrorWithConstraintsCommand.IsActive()` called `active_sketch()` →
`Gui.ActiveDocument.getInEdit()`. FreeCAD polls every visible command's `IsActive()` on a timer.
`_SketchEditWorkbenchObserver.slotInEdit` switched workbench **synchronously inside the observer
callback**, which rebuilds the ribbon and re-polls `IsActive()` *while FreeCAD is still inside
`setEdit`*. `getInEdit()` then returns a half-built view provider whose `.Object` / `.isDerivedFrom`
dereference faults in C++ — uncatchable by Python `try/except`. Intermittent because it depends on
ribbon-rebuild vs `setEdit` timing.

**Fix (commits `1b045b7`, `1a07294`):**
- `IsActive()` is now cheap and side-effect free: `App.ActiveDocument is not None` and
  `Gui.activeWorkbench().name() == "SketcherWorkbench"`. Nothing touches edit state. The real
  "is a sketch open?" check happens in `Activated()`, where FreeCAD is idle.
- `_SketchEditWorkbenchObserver.slotInEdit` defers the workbench switch with
  `QtCore.QTimer.singleShot(0, ...)` (same pattern as `_frame_origin_planes`), so it runs after
  `setEdit` returns.
- 1.3.2's Coincident/Point-on-Object ribbon changes were **reverted** (not part of 1.3.3). Only
  the mirror button is being pursued.

The user confirmed no crash across several restarts after this. Treat this as done unless it
recurs.

---

## 3. What the "Mirror + Constraints" feature is for

FreeCAD's native **Mirror** (`Sketcher_Symmetry`) makes a copy of selected geometry. On 1.1.3 it
does **not** reproduce constraints that tie a selected element to *unselected* geometry (e.g. a
divider line whose endpoints are `PointOnObject` on the rectangle's top/bottom edges). So a
mirrored divider comes back detached: the profile no longer closes cleanly.

The user's mental model is Fusion 360: mirror a divider inside a rectangle, get three enclosed
regions you can extrude independently, and dragging the source divider moves the mirror.

`FusionMyFreeCAD_MirrorWithConstraints` (`fusion_sketch_tools.py`) is the attempt to close that
gap on top of `SketchObject.addSymmetric`.

---

## 4. The core problem

To make a mirrored divider `geo6` behave, it needs to be fully constrained (0 DoF) by some mix of:

- endpoint attachments to the borders (`PointOnObject`/`Coincident`) — **required for FreeCAD to
  split the border edges and detect the enclosed regions**; and/or
- a `Symmetric` link to the source `geo5` — **required for the live drag coupling**.

A `Symmetric` *point* constraint is **two equations** (mirror both x and y of the point). When
`geo6`'s endpoints are already on the (axis-symmetric) borders via `PointOnObject`, the y half of
every `Symmetric` link duplicates what `PointOnObject` already pins. FreeCAD counts constraints,
not independent equations, so:

```
geo6 has 4 DoF.
PointOnObject(top) + PointOnObject(bottom) + Vertical  = 3 equations  -> DoF 1
+ Symmetric(start)                                      = +2 equations -> DoF -1  -> ORANGE
```

**Orange = over-constrained = blocks editing the sketch.** This is the wall. Every attempt to have
both attachments and links hit it.

---

## 5. Verified facts about FreeCAD 1.1.3 (from the user's Python console)

These were confirmed empirically on the user's machine. Trust them.

1. **`SketchObject.addSymmetric(geoIdList, refGeoId, refPosId)` has no constraint-adding option.**
   `help(s.addSymmetric)` → *"Add symmetric geometric objects to the sketch with respect to a
   reference point or line."* Geometry only. Adding the `Symmetric` constraints ourselves is the
   only route.

2. **`addSymmetric` reproduces single-element orientation constraints** (`Vertical` / `Horizontal`
   / `Block`) onto the mirrored copy. It does **not** reproduce boundary constraints
   (`PointOnObject` to an unselected edge) — that omission is the whole reason this feature exists.

3. **Line-to-line `Symmetric` is malformed.**
   `Sketcher.Constraint('Symmetric', g1, 0, g2, 0, refLineGeoId)` →
   `Sketcher constraint number N is malformed! ... The Sketch has malformed constraints!`
   Only the point-to-point forms work:
   `('Symmetric', g1, p1, g2, p2, gLine)` (about a line) and
   `('Symmetric', g1, p1, g2, p2, gPoint, pPoint)` (about a point).

4. **Axis GeoIds work as the `Symmetric` reference line:** `-1` = X axis, `-2` = Y axis. A mirror
   about the sketch Y axis uses `('Symmetric', g1, p1, g2, p2, -2)`. Confirmed in a dump:
   `Symmetric First 5 1 Second 6 1 Third -2`.

5. **Region detection needs a topological attachment on the element.** With `MakeInternals` on, a
   rectangle + one divider that has `PointOnObject` to top/bottom produced two selectable
   `Sketch.InternalFace1/2`. A *symmetry-only* mirrored divider (positioned exactly on the borders
   by `Symmetric` links, but with no `PointOnObject`/`Coincident`) produced **no third split** —
   still only two `InternalFace`s. **Geometric touch is not enough; FreeCAD needs the
   `PointOnObject`/`Coincident`.**

6. **`Sketch.Shape.Faces` is often `0`** for these profiles even when the sketch is fully
   constrained and green (DoF 0). The selectable regions come through `MakeInternals` as
   `Sketch.InternalFaceN` sub-shapes, not through `Shape.Faces`. Padding the *whole* sketch fails
   with `Pad: Wire is not closed` because the interior dividers are open wires; the Fusion-like
   path is to leave the sketch and select an `InternalFace` in the 3D view.

7. **FreeCAD's redundancy/conflict flags lag per-step `solve()` calls.** Adding a constraint,
   calling `sketch.solve()` / `sketch.recompute()`, and immediately reading
   `sketch.RedundantConstraints` can miss a redundancy that a later full
   `App.ActiveDocument.recompute()` (or the commit) then reports. Any "add, check, maybe remove"
   loop races this. Symptom: report said `linked 1 pair` but the Report view then showed
   `redundant [14, 15, 16]` and the sketch went orange after the fact.

8. **`Symmetric` + border attachments over-constrains (orange).** Directly observed:
   `redundant [14, 15, 16]`, `DoF -5`, sketch orange, middle region will not pad. Orange blocks
   all sketch editing until the user removes a constraint.

9. **A construction point coincident to the origin, or any constraint that touches only a sketch
   axis with nothing mirrored, must be left alone.** An earlier classifier bug routed
   `Coincident(constructionPoint, -1)` into the boundary planner and reported
   `skipped Coincident #9: could not identify the mirrored endpoint` as noise. Fixed in `59d4c44`
   (`classify_constraint`: `if not in_source: return "native"`).

10. **The user has FusionMyFreeCAD installed in two Mod dirs simultaneously:**
    `%APPDATA%\FreeCAD\Mod\FusionMyFreeCAD` and `%APPDATA%\FreeCAD\v1-1\Mod\FusionMyFreeCAD`.
    `App.getUserAppDataDir()` resolves to the `v1-1` one (that is where FMF writes its backups).
    Two copies sharing one `RibbonUI_Data` is the likely cause of the
    "replaced a ribbon layout that changed outside the add-on" line on every launch. Advise the
    user to delete the non-versioned copy.

---

## 6. Chronology of approaches (map to commits)

| Commit | Approach | Result |
|---|---|---|
| `1a07294` | Mirror + copy boundary `PointOnObject`/`Coincident` only. No symmetry link. | User: "the new button works, except it does not add the mirror constraint." Did **not** verify extrude at this point. |
| `0abe695` | Add a `Symmetric` link per shared named point of each pair; bulk-remove any the solver later flags. Distinct icon added (kept — user approves). | Intermittent: sometimes `linked 1 pair` cleanly, sometimes rolled back citing `redundant 14`. Non-deterministic (fact #7). "One end lost its constraint." |
| `37fd9d7` | Per-pair **all-or-nothing**: add both links, if bad-count rises roll the whole pair back. | Removed the half-linked state and the redundancy warning, but for the user's real sketch it just rolled back → back to "no link". |
| `86e8b20` | Before linking, **strip** the `Vertical` that `addSymmetric` reproduced onto the copy (fact #2), then add links. | User: "works much better!" `linked 1 pair symmetrically; copied 0 boundary constraints`, no orange, no warning. **But then:** middle region won't select/extrude (fact #5). |
| `6da75e8` | Keep the boundary `PointOnObject` copies on linked pairs too (`drop_redundant=False`), to get the topology for region detection. | **Over-constrained → orange** (`redundant [16,17]`, fact #8). Worse: orange blocks editing. |
| `464de60` | Revert `6da75e8`. Back to `86e8b20` behavior + startup-noise reduction. | Clean, linked, no orange — but middle still not extrudable. |
| `59d4c44` | Reorder: copy boundary attachments **first**, then add links **incrementally**, keeping "clean or partially redundant", dropping "fully redundant / conflicting". Split `_bad_constraint_indices` into conflicting / fully-redundant / partially-redundant. | Still went **orange** on the user's sketch (`redundant [14,15,16]`) — the incremental check kept a link that a later recompute flagged (fact #7). |
| `b0d86a5` (**current**) | Decide **per mirrored element**: if it got a border attachment (a divider) → reattach only, **no link** (never orange, profile fillable); if it is free-floating geometry → add the symmetry links (nothing to conflict). | No orange, no redundancy: `mirrored 1 element; reattached 1 to border; copied 2 boundary constraints`. **But** user reports the middle *still* won't pad, and (as designed) no live link on the divider. |

Non-mirror commits in the same range: `392da30` + `1cee5f1` add `tools/install-dev.ps1`
(build + drop into a chosen Mod dir; autodetects candidates, remembers the choice in git-ignored
`.install-dev.local.json`). Startup-noise reduction is in `6da75e8` (20 "moved the X shortcut"
lines → one `reassigned N keyboard shortcuts` summary; `updated FREQUENT` and the ribbon-layout
line downgraded to `PrintLog`).

---

## 7. Current implementation (`b0d86a5`)

`fusion_sketch_tools.mirror_sketch_geometry`:

1. `sketch.addSymmetric(source_indices, reference_geoid, reference_pos)` → mirror geometry +
   `mapping` {source geoid → mirror geoid}.
2. `plan_constraint_copies` + `apply_constraint_copies` → copy the boundary
   `PointOnObject`/`Coincident` attachments onto **every** mirrored element. `apply_constraint_copies`
   removes any copy the solver rejects.
3. `attached_mirror_ids` = mirror geoids that got a copied attachment.
4. `plan_symmetry_links` for pairs **not** in `attached_mirror_ids` only. `apply_symmetry_links`
   adds them one at a time; drops any flagged conflicting/malformed (reported in `link_dropped`)
   or fully redundant (dropped silently); keeps clean / partially-redundant.
5. Result dict: `mirrored`, `linked`, `link_dropped`, `linked_pairs`, `attached_pairs`, `copied`,
   `skipped`, `removed`, `unmatched`, `mapping`.

Report line: `mirrored N element(s); reattached K to border(s); linked M pair(s) symmetrically;
copied P boundary constraint(s)` (parts omitted when zero).

Net effect for a divider: it is reattached (`PointOnObject` to top/bottom + reproduced `Vertical`
→ 1 free DoF, white sketch, **not** orange) and **not** symmetry-linked. For free-floating
geometry: two `Symmetric` links, fully constrained, live.

**Known gaps at this commit:**
- The user says the middle region *still* won't pad even with both dividers carrying
  `PointOnObject`. Not yet explained — could be a stale `Shape`/`MakeInternals` refresh issue, a
  divider that projects past the border segment, or `PointOnObject` genuinely not triggering a
  split in their FreeCAD build/prefs. **Needs `len(s.Shape.Faces)` and an "what does the middle
  highlight as" check from the user.**
- No live link on a bordered divider (by design of this commit). The user explicitly still wants
  it.

---

## 8. Pending diagnostic (blocks the next decision)

The user was asked to run, on a sketch immediately after **Mirror + Constraints**
(geo 5 = source divider, geo 6 = its mirror — adjust ids to their sketch):

```python
s = App.ActiveDocument.getObject('Sketch')
print("faces before:", len(s.Shape.Faces))
i = s.addConstraint(Sketcher.Constraint('Symmetric', 5, 1, 6, 1, -2))
s.recompute()
print("DoF:", s.solve())
print("redundant:", list(s.RedundantConstraints))
print("partial:", list(getattr(s, 'PartiallyRedundantConstraints', [])))
print("conflicting:", list(s.ConflictingConstraints))
print("faces after:", len(s.Shape.Faces))
```

plus: leave the sketch, hover the middle region in 3D, report what it highlights as
(`Sketch.InternalFaceN` or nothing).

**Decision tree from the result:**

- **DoF 0, `conflicting []`, `redundant []`, only `partial [i]`, sketch stays green** →
  the "reattach + exactly one `Symmetric` link" configuration is viable. Implement that: for a
  bordered pair, after the border copies, add a **single** `Symmetric` link on one endpoint
  (couples the sideways position; its y half is the partial redundancy). One informational yellow
  note per mirrored element; live + extrudable. This is the best outcome.
- **`redundant`/`conflicting` non-empty, or it goes orange** → the solver genuinely cannot do
  both. Two honest options, pick with the user:
  1. **Split the border edges** at each divider crossing (source and mirror) so the profile is
     real topology: `Sketcher_Split` / trim the top and bottom edges at the crossing x, add
     `Coincident` to the new vertices. Guarantees the middle pads. The live link then stays a
     manual `Symmetric` the user adds (with its redundancy note).
  2. Ship "reattach only" (current `b0d86a5`) and document that a live link on a divider is a
     manual step. Least effort, least satisfying.
- **`faces` jumps to 3 and the middle highlights as an `InternalFace` after adding the one link**
  → the earlier "won't pad" was a stale-shape artifact. The real fix is small: force a
  `sketch.recompute()` + `App.ActiveDocument.recompute()` (or touch `MakeInternals`) at the end
  of the command, and verify `MakeInternals` is actually set on the sketch object
  (`Preferences/Mod/Sketcher` → `MakeInternals`, set by `runtime.py` — confirm it took).

---

## 9. Process lessons (please internalise before continuing)

1. **Get the user's real sketch data early.** I burned ~8 iterations guessing at FreeCAD solver
   behaviour and shipped a regression almost every round. The one console dump that actually
   showed the constraint list and `help(addSymmetric)` collapsed the search space immediately.
   Ask for `for i,c in enumerate(s.Constraints): print(i, c.Type, c.First, c.FirstPos, c.Second,
   c.SecondPos, c.Third, c.ThirdPos)` and `s.solve()` / `len(s.Shape.Faces)` up front.
2. **The test fake cannot model the solver.** `tests/fake_freecad.py` never produces genuine
   redundancy/DoF results. Tests pass while the real behaviour is wrong. `FakeSketch` now has
   `_reject` / `_partial` / `_conflict` predicates so a test can *simulate* the solver marking a
   constraint, but that only checks your bookkeeping, not FreeCAD's actual verdict. Every solver
   assumption must be checked against real FreeCAD.
3. **Multi-line paste into FreeCAD's Python console gets mangled** (indentation, blank lines,
   `for` loops). Give the user single-line statements, or a `.FCMacro` file.
4. **Version confusion cost two rounds.** Every build is "1.3.3", so the user twice tested a stale
   zip and I mis-read the results. Options: bump a patch/build number per iteration, or print a
   short build hash in the startup message, or have `install-dev.ps1` echo the zip's SHA.
5. **Orange (over-constrained) is a hard fail** — it blocks the user from working. A yellow
   "partially redundant" note is acceptable (sketch still functions). Never ship something that
   can go orange on a normal input.
6. **Don't keep a deliberately-redundant constraint to force topology.** `drop_redundant=False`
   (commit `6da75e8`) seemed clever and went straight to orange.

---

## 10. Repo / workflow reference

- **Build a testable zip:** `python tools/build_addon_package.py` → `dist/FusionMyFreeCAD-<ver>.zip`
  (single top-level `FusionMyFreeCAD/` folder — correct FreeCAD add-on layout).
- **Install into FreeCAD for testing:** `.\tools\install-dev.ps1` (PowerShell, from repo root).
  First run lists detected Mod dirs and asks; the choice is saved to `.install-dev.local.json`
  (git-ignored). `-NoBuild` reinstalls the last zip; `-List` shows candidates; `-Reset` forgets.
- **Checks (all must pass; CI runs the first):**
  `python -m pytest tests -q` · `python -m ruff check .` · `python -m ruff format --check .` ·
  `python validate_addon.py`
- **Deliver to the user:** they follow from another device — send builds with `SendUserFile`
  and quote the SHA-256 from `dist/FusionMyFreeCAD-<ver>.zip.sha256`.
- **Key files:**
  - `fusion_sketch_tools.py` — the whole mirror feature. Pure helpers + FreeCAD-touching
    `mirror_sketch_geometry` / `mirror_with_constraints` + `MirrorWithConstraintsCommand`.
  - `fusion_bootstrap.py` — `register_commands` wires in `fusion_sketch_tools.register()`;
    `_SketchEditWorkbenchObserver` (the deferred workbench switch); `prepare()` / `_verify_layout`
    (ribbon regen + the "changed outside the add-on" logic, §5.10).
  - `Resources/FusionMyFreeCAD/runtime.py` — `reconcile_actions` (shortcut reassignment + the
    summary line), `refresh_adaptive_panel` (FREQUENT), `MakeInternals` preference is set here.
  - `Resources/FusionMyFreeCAD/layout-v3.json` — `FusionMyFreeCAD_MirrorWithConstraints` is a
    small button in the Sketcher `Fusion Sketch Modify_newPanel`, in front of the large native
    `Sketcher_Symmetry`. `layout-manifest.json` has `authoredIcons`
    (`["FusionMyFreeCAD_MirrorWithConstraints"]`) so the icon-provenance tests accept the
    add-on-drawn SVG at
    `bundled-addons/FreeCAD-Ribbon/Resources/FreeCAD Icons/FusionMyFreeCAD_MirrorWithConstraints.svg`
    (native Mirror glyph + green "+" badge — user approved).
  - `tests/fake_freecad.py` — `FakeSketch` (`addSymmetric`, `mirror_selected` which now also
    reproduces `Vertical`/`Horizontal`/`Block` onto copies), `_refresh_rejections` +
    `_reject`/`_partial`/`_conflict`. `FakeConstraint` parses `Symmetric` (incl. the 6th
    `Third` arg) and `Equal`.
  - `tests/test_sketch_tools.py` — mirror feature tests. `_card_box` (dividers with
    `PointOnObject` to borders) and `_floating_line_box` (a free interior line).
- **CHANGELOG.md** 1.3.3 section describes: the 1.3.2 withdrawal + crash fix, the mirror behaviour
  as of `b0d86a5`, the icon, the quieter startup, and that the 1.3.2 Coincident/Point-on-Object
  changes are not included. `docs/RELEASE-NOTES-1.3.3.md` mirrors it. Update both when the mirror
  behaviour changes again.

---

## 11. Release / git state to be careful with

- `v1.3.2` GitHub release is a **draft** (via `gh release edit v1.3.2 --draft`). `v1.3.1` is the
  live "Latest". Do **not** re-publish `v1.3.2`. The `v1.3.2` git tag still points at `c32f982`.
- `main` == `origin/main` at `b0d86a5` (session commits are pushed). Nothing is released as 1.3.3
  yet. `package.xml`, `layout-v3.json`, `layout-manifest.json` all say `1.3.3`; the CHANGELOG
  1.3.3 section and `docs/RELEASE-NOTES-1.3.3.md` exist and must be kept current as the mirror
  behaviour changes. When the feature is actually right, follow `RELEASING.md` (there is a
  dispatchable GitHub Actions release workflow) to cut `v1.3.3`.
- Commit-message convention in this repo ends with
  `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.

---

## 12. If you want to change tack entirely

Ideas not yet tried, roughly in order of promise:

1. **Reattach + one `Symmetric` link** (pending the §8 diagnostic). Cleanest if the solver allows
   green-with-a-note.
2. **Edge splitting.** After mirroring, split the top/bottom border edges at every divider
   crossing and `Coincident` the divider endpoints to the new vertices. Real topology → the
   middle definitely pads and even a whole-sketch pad closes. Investigate the Python API for
   `Sketcher_Split` / `SketchObject.split` on 1.1.3 (was not checked). Live link stays manual.
3. **Construction-geometry "rails".** Instead of `Symmetric` on endpoints, mirror the divider as
   construction geometry that carries the link, and put the real (extrudable) divider on top with
   `PointOnObject` to both the rail and the borders. Speculative; may just move the redundancy.
4. **Accept native `Sketcher_Symmetry` semantics** and make the FMF button only do the
   boundary-constraint copy (its original 1a07294 job), documenting that a live link is a manual
   `Symmetric`. This is the low-risk fallback the user will probably reject but should be offered
   explicitly.

The user is patient but has iterated a lot. Lead with the §8 diagnostic result, propose **one**
concrete plan, and confirm the trade-off (live vs. zero notes vs. extrudable) before building
again.
