# Implementation review: recommended improvements

**Status:** Independent code review of the current add-on (Codex-authored)
**Date:** 2026-08-25
**Reviewer:** Claude (Opus 5)
**Scope:** `InitGui.py`, `fusion_bootstrap.py`, `Resources/FusionMyFreeCAD/`, `validate_addon.py`, `tools/`, packaging, docs, and repository hygiene.
**Baseline:** `git HEAD = b23e834 "Release 0.1"`, corrected package version 1.0.0, working tree clean. `python validate_addon.py` passes (`VALID: self-contained add-on 1.0.0; 3.6 MiB unpacked`).

## Overall assessment

This is genuinely good work for its size. The reversibility design is the standout: capture-then-restore of a declared `PREFERENCE_KEYS` set, timestamped backups, atomic JSON writes, a self-check command, and a documented restore path. That is more care than most FreeCAD UI add-ons take, and `MAINTAINING.md` is unusually honest about what validation does and does not prove.

The weaknesses cluster in three places:

1. **The add-on is more aggressive toward the user's profile than its own docs imply.** Most managed preferences are re-applied unconditionally at every launch, and the runtime strips conflicting Qt shortcuts application-wide.
2. **Startup is orchestrated by a ladder of hard-coded `QTimer` delays** rather than by events, and a single exception in `prepare()` takes down the recovery commands with it.
3. **Truth is duplicated** — version in 5 places, layout in 3, manifest in 2, runtime code in 2 — and the tests are largely source-text string matching, so they pin the duplication in place instead of eliminating it.

Recommendations below are ordered by expected value, not by effort.

---

## Priority 1 — Correctness and user trust

### 1. Do not let `prepare()` failure disable Verify and Restore

`InitGui.py:9-13` calls `prepare()`, `register_commands()`, `run_runtime()`, then the two vendor loads, with no error handling. `prepare()` raises on an old FreeCAD (`fusion_bootstrap.py:219`), a missing payload file (`:222`), an invalid generated ribbon (`:256`), and — unguarded — on a corrupt or schema-drifted state file (`:224` `_load_json`, `:247` `state["backupRoot"]`).

Any of those aborts the module, so the user is left with whatever half-applied state exists **and no Verify UI or Restore UI commands to get out of it**. That inverts the product's core promise.

**Fix:** register commands first, then run `prepare()` inside `try/except`, report failure via `App.Console.PrintError` plus a non-modal notification, and record the failure in the state/status file. Treat a corrupt `STATE_PATH` as a recoverable condition: rename it aside rather than crashing.

### 2. Never re-capture a baseline over your own settings

`prepare()` captures the pre-install preference baseline only when `state is None` (`fusion_bootstrap.py:236-245`). If `FusionMyFreeCAD-addon-state.json` is deleted, corrupted, or lost with a profile copy while the add-on is still installed, the next launch captures **FusionMyFreeCAD's own applied values** as the "previous UI." Restore then restores Fusion settings and the user's original configuration is permanently gone.

**Fix:** write a second, never-overwritten `baseline.json` inside `FusionMyFreeCAD-Backups/` on true first install and treat its presence as proof a baseline already exists. Refuse to re-capture when a backup root exists but state does not; surface that as a Verify failure instead.

### 3. Stop overwriting user customization at every launch

`apply_preferences()` (`runtime.py:59-119`) runs on every start and writes unconditionally. Only three groups are opt-out-able (`SetStartWorkbench`, `SetNavigation`, `SetShortcuts`); ComboView docking, all Ribbon icon sizes, the four Sketcher dimensioning flags, and the SearchBar dialog suppression are forced every time. A user who changes any of them in FreeCAD's own preferences dialog silently loses the change on the next restart, with no message explaining why.

**Fix:** apply managed preferences once (keyed on `packageVersion` + `layoutVersion` in the state file), then only on explicit user request via a "Reapply FusionMyFreeCAD defaults" command. If a value must be enforced every launch, say so in `README.md` and list it in Verify's output.

### 4. Make the shortcut hijack visible and reversible

`reconcile_actions()` (`runtime.py:403-434`) walks every `QAction` under the main window and, for each of the 13 Fusion shortcuts, clears the shortcut of **any other action** holding the same sequence (`:429`), then rebinds with `ApplicationShortcut` context. This runs on startup and again on every workbench activation.

Two problems: the user is never told which native or custom bindings were taken away, and the removals live only in Qt — `restore()` restores the `Preferences/Shortcut` parameter group but nothing records what was stripped at runtime.

**Fix:** collect the displaced `(objectName, sequence)` pairs, log them once via `App.Console.PrintMessage`, include the list in `FusionMyFreeCAD-runtime-status.json`, and show it in Verify UI. Skip the steal entirely when `SetShortcuts` is off.

### 5. Default `CreateStarterDesign` to off

`ensure_starter_design()` (`runtime.py:164-178`) creates an unsaved document plus a `PartDesign::Body` on **every** launch that has no active document, defaulting to `True`. The user gets a phantom "Part" document they did not ask for and a save prompt on exit. Fusion's start experience is a data panel, not a pre-made body.

**Fix:** default to `False`, or scope it to genuine first run only (state file records `starterDesignCreated`).

### 6. Preserve, or explicitly warn about, ribbon edits on upgrade

On a version bump `prepare()` regenerates `RibbonStructure.json` wholesale. Anything the user built with FreeCAD-Ribbon's own layout designer is replaced. It is copied to `<backupRoot>/updates/<timestamp>-RibbonStructure.json` (`:246-250`), which is correct but undiscoverable.

**Fix:** on upgrade, detect that the on-disk ribbon differs from the previously generated one (the state file already stores `ribbonSha256` at `:262` — currently written and never read) and prompt, or at minimum print the backup path to the report view and expose it in Verify.

---

## Priority 2 — Architecture

### 7. Replace the `QTimer` ladder with event-driven setup

`runtime.py:437-453` schedules work at 100/250/400/500/750/900/1500/1750/1800/2000 ms, some of it repeatedly per workbench switch. These constants encode one machine's startup timing. On a slow disk, a large document, or a machine loading many other add-ons, `ensure_model_tree` and `reconcile_actions` will fire before the widgets they look for exist — and both swallow the failure silently (`runtime.py:127`, `:157`).

**Fix:** hang the work off signals that mean the thing is ready (`mainWindowClosed`/`workbenchActivated` already exists; use `QTimer(0)` posted-event ordering or a bounded retry with backoff and a final warning) rather than wall-clock guesses. If a retry loop is genuinely needed, make it explicit — `retry(fn, attempts=5, interval=200)` — so the intent is legible and a permanent failure is reported instead of hidden.

### 8. Reconsider bundling forks of FreeCAD-Ribbon and SearchBar

Bundling gets one-step install, and the dependency-stripping patches (lxml, NumPy, Matplotlib → stdlib) are real value. But the cost compounds: users with the standalone add-ons get a fragile duplicate-detection heuristic (`load_vendor` checks `"FCBinding" in sys.modules`, `fusion_bootstrap.py:437-457` — a guess about another package's import side effects); upstream bug fixes and security fixes never reach users; and `tools/sync_bundled_addons.py` must re-apply local patches forever, by hand, against an ignored `vendor/` tree that no one else can reproduce.

**Fix, in order:**
1. Upstream the dependency-removal patches to FreeCAD-Ribbon and SearchBar. They are strictly beneficial to those projects and would delete most of the maintenance burden here.
2. Declare `<depend type="addon">FreeCAD Ribbon</depend>` / `SearchBar` in `package.xml` and let Addon Manager handle installation, keeping the bundled copies as a documented offline fallback behind a preference.
3. Whatever is kept bundled: record the upstream commit SHA per snapshot in `THIRD_PARTY_NOTICES.md`, and keep a `patches/` directory of actual diffs so `sync_bundled_addons.py` can apply them mechanically and fail loudly when one no longer applies.

### 9. Collapse the duplicate sources of truth

| Duplicated thing | Copies |
|---|---|
| Version `1.0.0` | `package.xml`, `fusion_bootstrap.py:17`, `layout-v3.json`, `layout-manifest.json`, `validate_addon.py` — synchronization is a manual `rg` per `MAINTAINING.md` |
| Layout spec | A second Windows-only copy had already diverged from `Resources/FusionMyFreeCAD/layout-v3.json` |
| Manifest | A second Windows-only copy had already diverged from `Resources/FusionMyFreeCAD/layout-manifest.json` |
| Panel order | `layout-v3.json` panel list vs `layout-manifest.json["workbenchPanelOrder"]` |
| Runtime code | A second Windows-only runtime copy had diverged from `Resources/FusionMyFreeCAD/runtime.py` |

**Fix:** read the version from `package.xml` at runtime (or generate a one-line `_version.py`), derive `workbenchPanelOrder` from the layout at load time instead of storing it, and remove the duplicate Windows-only payload.

### 10. Derive `_verify_layout` from the layout spec

`fusion_bootstrap.py:166-214` hard-codes fourteen checks against literal panel names (`"Fusion Sketch Entry_newPanel"`, `"Fusion Parameters_newPanel"`, …) and one literal label (`"Smart Dimension"`). Renaming a panel in `layout-v3.json` silently breaks verification — or, worse, passes while checking nothing meaningful.

**Fix:** generate the structural checks from `layout-v3.json` (every declared panel exists, order matches, every declared command is present, no native toolbar leaked into `order`) and keep only genuinely invariant assertions as literals.

### 11. Remove the duplicate Windows setup path

At review time, a retired Windows-only setup tree duplicated the layout, manifest, runtime, and validation logic. Every runtime change therefore had to be mirrored into a path the user documentation no longer supported, and its generator depended on a source path outside the repository.

**Resolution (2026-08-30):** the duplicate setup source and generated launcher artifacts were removed from `main`. The self-contained FreeCAD add-on is now the only release path.

### 12. Rethink adaptive reordering of primary panels

> **Correction after implementing this.** My first reading overstated the problem. `_rewrite_panels` permutes candidates *only within the slot positions they already occupy*, so the Sketcher pins swap which of two commands (Polyline/Spline, Move/Rotate) holds one fixed slot. Non-candidate buttons never move. That is contained and genuinely Fusion-like, not the panel-wide reshuffle I described, so the "restrict adaptation to FREQUENT panels" recommendation is withdrawn.
>
> The scoring complaint stands and was the real defect.

The scoring is twitchy: defaults get a baseline of `0.75` (`runtime.py:285`) while a single click scores `1.0`, so one accidental use promotes a command above every default for roughly a month of decay.

The payoff is also deferred: `refresh_adaptive_panel` rewrites the 193 KB `RibbonStructure.json` and then tells the user it "appears on the next ribbon reload" (`runtime.py:355-357`), so the adaptation is invisible in the session that earned it.

**Fix:** raise the promotion threshold so displacing a default takes sustained use; keep the slot-swap behaviour; and either refresh the panel live or accept the deferred payoff as a documented limitation.

---

## Priority 3 — Testing and CI

### 13. Convert `validate_addon.py` into a real test suite

It is one 190-line `main()` of bare `assert`s that stops at the first failure, and a large share of the assertions are **source-text substring matches**:

```python
assert 'search.SetBool("ShowChangeDialog", False)' in runtime_source
assert 'names = ("Combo View", "ComboView", "Model", "Tree view")' in runtime_source
```

These break on reformatting, pass on code that is present but unreachable, and actively discourage refactoring — which is why the duplication in item 9 has survived.

**Fix:** move to `pytest` with one test per concern; extract the fake FreeCAD/Gui harness (`load_bootstrap`, `ParameterGroup`, `FakeDocument`) into a reusable `tests/fake_freecad.py` fixture — it is the best part of the file and deserves to be used more widely; and replace the string matches with behavioral assertions against that fake (call `apply_preferences()` and assert the resulting parameter values; call `reconcile_actions()` against fake actions and assert the resulting shortcut map). Keep AST-level checks (like the existing `CheckDataFileVersion` modal-dialog check, `validate_addon.py:141-149`) where behavior cannot be simulated — that one is well done.

**Untested behavior worth covering first:** upgrade path (state exists, version differs), corrupt state file, `restore()` when the backup directory is missing, `refresh_adaptive_panel` reordering math, and `_restore_preferences` for keys that did not previously exist.

### 14. Add CI and lint config

There is no `pyproject.toml`, no `ruff`/`black` config, no workflow file, and no `conftest.py`. Everything is run by hand from PowerShell, so the cross-platform claim in `README.md` is never exercised. `D:\Git\dev-setup-kit` already has the canonical preset kit for this — apply it here.

Minimum: a GitHub Actions matrix on `ubuntu-latest` / `macos-latest` / `windows-latest` × Python 3.11+ running `ruff check`, `pytest`, `python tools/build_addon_package.py`, and an archive-content diff. That alone would substantiate the cross-platform claim and catch path-separator and case-sensitivity bugs that Windows-only testing cannot.

---

## Priority 4 — Packaging, docs, hygiene

### 15. Shrink the repository before submitting to the add-on index

`.git` is **138 MB** for a 3.6 MiB add-on, and Addon Manager clones the repository. History holds `docs/a-freecad-manual.pdf` (15 MB, tracked, and a third-party document), `vendor/SearchBar/Resources.py` (4.8 MB), and several ~1 MB `vendor/FreeCAD-Ribbon` blobs from before `vendor/` was ignored.

**Fix:** drop the bundled manual in favor of a link to the official FreeCAD documentation, then either rewrite history (`git filter-repo`) or publish from a clean repository. Do this before index submission, not after.

### 16. Fix the README

The current `README.md` is two documents fused together: install/status text, then a stray orphan `>` blockquote marker mid-file, then the original 2026-07-30 research brief (Fusion↔FreeCAD tables, "Recommended level of customization", "Files in this folder"). Anyone landing on the repository reads install instructions that dissolve into research notes recommending *against* ribbon replacements.

**Fix:** README = what it is, a screenshot, install, verify, restore, uninstall, compatibility, license. Move the research prose to `research/` where the rest of it already lives.

### 17. Reconcile the license story

`package.xml` declares `GPL-3.0-or-later`, `LICENSE` is GPL-3, `LICENSES/FusionMyFreeCAD-MIT.txt` retains MIT for the original code, and no file states which source files each covers. Separately, `THIRD_PARTY_NOTICES.md` records SearchBar as LGPL-2.1 (matching its `LICENSE` file) while the bundled `SearchBar/package.xml` declares `CCOv1` — an upstream inconsistency inherited without comment.

**Fix:** add SPDX headers to first-party files, state plainly in `README.md` that the distributed combined work is GPL-3.0-or-later because it bundles FreeCAD-Ribbon, and note the SearchBar license discrepancy in `THIRD_PARTY_NOTICES.md` (ideally after asking upstream which is authoritative).

### 18. Clean stale metadata and outputs

- `bundled-addons/SearchBar/package.xml` still declares `<depend type="python">lxml</depend>` even though the patch removed that requirement — the whole point of the change.
- `dist/` held stale and mismatched release artifacts.
- `Resources/FusionMyFreeCAD/__pycache__/runtime.cpython-311.pyc` exists in the working tree (ignored, but it will be picked up by anything that walks the tree).
- 13 of the 78 icons referenced by `layout-v3.json` have no bundled file. **Checked while implementing: these are all FreeCAD built-in command icons and resolve from FreeCAD's own registry at runtime, so nothing is broken.** The real defect is that `sync_bundled_addons.py` selects icons by stem match and silently skips anything it cannot find, so a genuine typo would render a blank button with no warning.
- `package.xml` declares `<content><workbench>` but `InitGui.py` never calls `Gui.addWorkbench`. Verify how Addon Manager presents an add-on that declares a workbench and registers none before submission.

### 19. Add a preferences page

Four documented opt-outs (`SetStartWorkbench`, `SetNavigation`, `SetShortcuts`, `CreateStarterDesign`) exist only as raw parameters under `Mod/FusionMyFreeCAD`, reachable through the parameter editor. Given items 3–5, these are exactly the switches an unhappy user needs.

**Fix:** ship a small `.ui` preferences page (the bundled SearchBar already demonstrates the pattern in `Resources/ui/PreferencesUI_SearchBar.ui`) and link it from Verify UI's output.

### 20. Handle orphaned state after removal

Removing the add-on through Addon Manager deletes `Mod/FusionMyFreeCAD` but leaves `RibbonUI_Data/`, `FusionMyFreeCAD-addon-state.json`, `FusionMyFreeCAD-usage.json`, `FusionMyFreeCAD-runtime-status.json`, and every applied preference. The docs say to click Restore UI first; users will not.

**Fix:** publish a standalone one-file recovery macro in `tools/` that performs a restore from the state file without the add-on installed, and link it from `docs/INSTALL-FREECAD-ADDON.md`.

---

## Smaller notes

- `fusion_bootstrap.py:262` writes `ribbonSha256` that nothing ever reads; `verify()` should compare it (see item 6) or it should be dropped.
- `restore()` (`:281-303`) is not transactional: a throw inside `_restore_preferences` leaves the ribbon restored and the state file still present. Make it idempotent and safe to re-run.
- `run_runtime`/`load_vendor` stash load flags as attributes on the `FreeCAD` module (`App._fusion_my_freecad_runtime_loaded`). A module-level guard in a small `fusion_state.py` is equivalent and does not mutate another package's namespace.
- `reconcile_actions()` does `main_window.findChildren(QAction)` — thousands of objects — then an inner scan per shortcut, on every workbench activation. Cache the name→action map and invalidate on workbench change.
- `write_runtime_status()` re-reads `layout-manifest.json` from disk instead of using `load_manifest()`'s cache, and rewrites the status JSON on every activation.
- `_message()` (`fusion_bootstrap.py:307-311`) uses PySide6-only `.exec()`, while `runtime.py:11-16` carries a PySide2 fallback. Pick one Qt baseline and state it.
- `except Exception` with only a console warning appears in five places (`runtime.py:127`, `:157`, `:177`, `:249`, `:400`). Failures there are invisible in normal use; route them into the status file so Verify UI can report them.
- `verify()` reports pass/fail per check but no remediation text. Each failed check should say what to do next.

## What not to change

- The capture/restore model in `fusion_bootstrap.py`. It is the right design; the fixes above harden it rather than replace it.
- `_atomic_json` / temp-file-plus-`os.replace` throughout. Correct.
- The AST-based assertion that Ribbon's startup cache check cannot raise a modal dialog (`validate_addon.py:141-149`). That is a well-chosen test for a real, reported failure mode.
- The fake-FreeCAD harness in `validate_addon.py`. Promote it, do not discard it.
- `MAINTAINING.md`'s explicit statement that passing offline validation does not prove Qt renders correctly or that geometry is correct. Keep that disclaimer in any rewrite.

## Suggested order of work

1. Items 1, 2, 3, 4, 5 — trust and safety of the user's profile.
2. Item 13 + 14 — tests and CI, so the rest can be changed safely.
3. Items 9, 10, 11 — collapse duplication and retire the Windows-only setup path.
4. Items 15, 16, 17 — repository and licensing cleanup, gated before add-on index submission.
5. Items 7, 8, 12 — architecture, once there is a net under it.

---

# Implementation status — 2026-08-26

Worked through on branch `main`, package version bumped **1.0.0 → 1.1.0**.
Verification: `95 passed`, `ruff check` clean, `ruff format --check` clean,
`python validate_addon.py` → `VALID: self-contained add-on 1.1.0; 3.7 MiB unpacked`.

## Done

| # | Item | What changed |
|---|---|---|
| 1 | `prepare()` failure disables recovery | `InitGui.py` wraps every step in `_step()`; commands and the preferences page register **first**; failures go to the console and `FusionMyFreeCAD-startup.json`, and Verify UI reports them |
| 2 | Baseline re-capture destroys the profile | `FusionMyFreeCAD-Backups/baseline.json`, written once and never overwritten; lost state now returns `"recovered"` and reuses it |
| 3 | Preferences overwritten every launch | Split into `_apply_structural()` (every launch, paths only) and `_apply_defaults()` (once per version, gated on `AppliedVersion`); new **Reapply UI** command |
| 4 | Silent shortcut theft | Displaced bindings are recorded, logged, written to the status file, and listed by Verify UI; skipped entirely when `SetShortcuts` is off |
| 5 | Starter design on by default | Now defaults to off |
| 6 | Ribbon edits lost on upgrade | `ribbonSha256` is now *read*: the adaptive rewrite updates it, so a mismatch means a genuine external edit, which is flagged and kept at `externalRibbonEdit` |
| 7 | `QTimer` delay ladder | Replaced with `_defer(label, fn, attempts, interval)`; steps return True when done, and exhaustion is reported rather than swallowed |
| 9 | Version duplicated 5× | `PACKAGE_VERSION` reads `package.xml`; the two `layoutVersion` fields are asserted against it |
| 10 | Hardcoded `_verify_layout` | Fully derived from `layout-v3.json` + the adaptive manifest; returns `(valid, checks, problems)` with actionable detail |
| 11 | Windows setup coupled to the validator | Duplicate assertions and payload removed; the obsolete setup tree and launcher artifacts were subsequently deleted from `main` on 2026-08-30 |
| 12 | Twitchy adaptive promotion | `PROMOTION_BASELINE` 0.75 → 2.5, so displacing a default takes sustained use. Slot-swap behaviour kept (see correction above) |
| 13 | String-matching validator | 95-test pytest suite; `tests/fake_freecad.py` promoted to a reusable fixture; `validate_addon.py` kept as the documented entry point |
| 14 | No CI or lint config | `pyproject.toml` (pytest + ruff) and `.github/workflows/ci.yml` — 3 OSes × Python 3.11/3.13, plus a `package-hygiene` job |
| 16 | README was two documents | Rewritten as a real README; the research prose moved to `research/native-freecad-baseline-2026-07-30.md` |
| 17 | Licence story unclear | `THIRD_PARTY_NOTICES.md` states the effective licence, tabulates components, and documents the upstream SearchBar LGPL-2.1-vs-CC0 discrepancy |
| 18 | Stale metadata | `lxml` dependency removed from SearchBar's `package.xml` **and** `sync_bundled_addons.py` now strips such declarations mechanically; stale `dist/` artifacts removed |
| 19 | No preferences page | `Resources/FusionMyFreeCAD/preferences.ui`, registered via `register_preferences_page()`; a test derives the required controls from the runtime's own `PREFERENCES` reads |
| 20 | Orphaned state after removal | `tools/RestoreFusionMyFreeCAD.FCMacro`, shipped inside the archive and tested |

Smaller notes also addressed: `restore()` is now step-independent and returns `(directory, problems)`; `_restore_preferences` no longer abandons the remaining keys on one bad entry; module-load flags moved off the `FreeCAD` module into a module-level `_loaded` set; `_exec()` handles both Qt bindings; broad `except Exception` handlers now route into the status file; Verify UI names the next step for every failure.

Two defects surfaced *during* implementation, neither in the original review:

- **Adaptive slot truncation.** `zip(candidate_positions, reordered)` truncates silently if the pool and the panel disagree, dropping a promoted command. Now length-checked and reported.
- **`primaryCommands` gap.** `Sketcher_Translate` and `Sketcher_Rotate` were in the layout but absent from the manifest, so runtime status never tracked them. Added, and a test now enforces coverage.

## Not done — deliberately left for you

| # | Item | Why |
|---|---|---|
| 8 | Depend on FreeCAD-Ribbon / SearchBar instead of bundling | A product decision, not a cleanup. The groundwork is in: patches are codified in the sync tool and asserted by tests, so the maintenance burden is now visible and mechanical. Upstreaming the dependency-removal patches is still the highest-value move |
| 15 | Shrink the repository | **This one matters before index submission.** `.git` is ~138 MB for a 3.7 MiB add-on. Deleting `docs/a-freecad-manual.pdf` from the tree would achieve nothing — a clone still fetches the history. It needs `git filter-repo` or a fresh publishing repo, then a force-push: destructive and coordinated. Documented as a pre-submission gate in `MAINTAINING.md`; the `package-hygiene` CI job warns on tracked files over 1 MiB |
| 18 | `<content><workbench>` with no `Gui.addWorkbench` | Left as-is: the bundled FreeCAD-Ribbon declares it the same way. Worth confirming how Addon Manager presents it before submission |

## Verifying the tests actually protect anything

Every Priority-1 fix was mutation-checked — the bug was reintroduced and the suite had to fail:

| Reintroduced bug | Caught by |
|---|---|
| Preferences applied every launch | `test_user_changes_survive_the_next_launch` |
| Silent shortcut theft | `test_a_displaced_shortcut_is_recorded_and_reported`, `test_displaced_shortcuts_reach_the_status_file` |
| Old 0.75 promotion baseline | `test_a_single_click_does_not_displace_a_default` |
| Starter design on by default | `test_starter_design_is_off_by_default` |
| Baseline re-captured over own settings | `test_lost_state_does_not_capture_fusion_settings_as_the_baseline` |
| Restore leaves machine-local files | `test_restore_moves_machine_local_runtime_files_aside` |
| Deferral without retry | `test_install_waits_for_a_slow_main_window` |
| A new opt-out with no UI control | `test_the_preferences_page_covers_every_switch_the_runtime_reads` |

The last two exist *because* of this pass: the first mutation round found no test failed when `_defer` was reduced to a single attempt, which meant nothing covered the slow-startup case the fix was written for.

## Still requires a human in FreeCAD

Offline validation cannot prove Qt renders the ribbon correctly. Before release, run the interactive
checklist in `MAINTAINING.md`, and specifically exercise the paths this pass changed:

1. Clean profile → first start → confirm no dialogs and a correct ribbon.
2. Change an icon size in FreeCAD's preferences → restart → **confirm it survives** (item 3).
3. **Verify UI** → confirm the displaced-shortcut list matches reality (item 4).
4. **Reapply UI** → confirm defaults return and the ribbon regenerates.
5. **Restore UI** → confirm the original profile returns.
6. Remove the add-on without restoring, then run the recovery macro (item 20).
7. Preferences → FusionMyFreeCAD → toggle each switch and confirm it takes effect after Reapply.

---

# Icon vendoring resolved — 2026-08-26

Investigated against a real **FreeCAD 1.1.1** install (`F:\Portable Programs\FreeCAD`) rather than
by inspection, because the question "does FreeCAD already provide this?" is empirical.

## The trap that made this worth measuring

`Gui.getIcon(name)` **never fails**. Given a name FreeCAD does not know, it returns the "unknown
icon" placeholder — a perfectly valid, non-null `QIcon`. Every `isNull()`-based check therefore
reports success for names that are simply wrong.

My first probe fell straight into this and reported all 80 icons resolving. Adding negative controls
(deliberately impossible names) exposed it: those returned a non-null 16×16 icon too. The working
method is to fingerprint the placeholder's rendered pixels and compare every candidate against it.

## What the measurement showed

Of the 78 distinct icon names in `layout-v3.json`:

| | Count |
|---|---|
| Served by FreeCAD with **no workbench loaded** | 64 |
| Served once the owning workbench loads (`Spreadsheet`) | 1 |
| Returned the placeholder — **wrong names** | 13 |

The 13 that failed were exactly the 13 that had **no bundled file either**. So those buttons have
been rendering a grey question mark. Asking each command what it actually declares gave the fix:

```python
Gui.Command.get("Std_Measure").getInfo()["pixmap"]  # -> 'umf-measurement'
```

| Layout said | FreeCAD actually uses |
|---|---|
| `Std_Measure` | `umf-measurement` |
| `Std_ViewFitAll` | `zoom-all` |
| `Std_DlgCustomize` | `applications-accessories` |
| `Sketcher_Dimension` | `Constraint_Dimension` |
| `Sketcher_ConstrainCoincident` | `Constraint_PointOnPoint` |
| `Sketcher_ConstrainEqual` | `Constraint_EqualLength` |
| `Sketcher_ConstrainHorVer` / `Parallel` / `Perpendicular` / `Tangent` | `Constraint_HorVer` / `_Parallel` / `_Perpendicular` / `_Tangent` |
| `Part_ShapeFromMesh` | `Part_Shape_from_Mesh` |

The icon name is generally **not** the command name. Two command groups
(`PartDesign_CompPrimitiveAdditive`, `Sketcher_CompConstrainTools`) declare no pixmap at all; they
now name a representative member, which is the convention FreeCAD-Ribbon already uses for dropdowns.

## What changed

- **13 icon names corrected** in `layout-v3.json` (18 button entries). A real, visible bug fix.
- **`bundled-addons/FreeCAD-Ribbon/Resources/FreeCAD Icons/` deleted** — 69 files, 1.2 MiB of images
  FreeCAD already installs. The Ribbon's own chrome (`Resources/icons`) is untouched.
- **`tools/probe_freecad_icons.py`** added: fingerprints the placeholder, checks every layout icon
  against a real install, writes `Resources/FusionMyFreeCAD/verified-icons.json`, exits non-zero on
  any unresolved name. Uses a throwaway config so it cannot touch the user's profile.
- **`sync_bundled_addons.py`** no longer copies FreeCAD icons and now *refuses* to, so an upstream
  refresh cannot silently reintroduce them.
- **Three tests** guard it offline: no vendored icon set, every layout icon in the verified list, and
  no stale entries in that list.

| | Before | After |
|---|---|---|
| Archive | 0.68 MiB | **0.49 MiB** |
| Unpacked | 3.7 MiB | **2.6 MiB** |
| Payload files | 201 | **132** |

## Why this is the better maintenance story

Vendoring did not just duplicate 1.2 MiB. The Ribbon matches bundled filenames **by substring,
before it ever asks FreeCAD**, so a vendored file silently masks a wrong icon name — and a *missing*
one produces a placeholder that no `isNull()` check will catch. Deleting the folder makes FreeCAD the
single source, and the probe plus the committed manifest make correctness checkable offline and
re-checkable against any future FreeCAD version in one command.

## Still needs a human

Icon *rendering* cannot be verified headlessly. Launch FreeCAD with the add-on installed and confirm
the corrected buttons show real icons — particularly **Measure**, **Fit All**, **Restore UI**, the
Sketcher constraint row, and the two dropdown buttons (**More Create**, **More Constraints**).
