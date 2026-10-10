# FreeCAD Addon Index readiness research

Date: 2026-10-09

## Decision summary

FusionMyFreeCAD should not be submitted to the official Addon Index yet. The immediate metadata
defects are straightforward, but the larger acceptance risk is product-level: the Index qualities
say an add-on must not modify or hide FreeCAD's core interface or interfere with other add-ons,
while FusionMyFreeCAD intentionally applies a global ribbon, preferences, navigation settings, and
shortcuts across several core workbenches.

The product's multi-workbench feature set takes precedence over Index inclusion. The recommended
path is therefore a no-regression best-practices refactor. It may register several FMF-owned
workbenches, but it must not collapse the experience into one workbench or remove useful behavior
merely to obtain catalog approval. Index submission remains an optional outcome after the complete
feature set is preserved and the written requirements can be met.

No project version change is part of this plan. The main version remains 1.8.0 unless the project
owner explicitly approves a later change.

## Scope and method

This review compared the current project with:

- the current official Addon Academy quality and publishing guidance;
- the official workbench-less toolbar example;
- seven public Addon Index review discussions, emphasizing UI add-ons and concrete reviewer
  objections;
- public repository metadata and selected local implementation/documentation evidence.

The review did not modify application code, packaging metadata, release state, or GitHub settings.
It also did not inspect or modify the upstream FreeCAD reference source.

## Confirmed official requirements

The official quality criteria require accurate metadata, the correct content type, compatible
license declarations, current FreeCAD compatibility, limited startup work, and substantially
complete functionality. They also state that add-ons must confine commands and UI side effects to
their own workbench and must not modify, hide, or interfere with FreeCAD's core interface or other
add-ons. Vendoring is strongly discouraged and may be grounds for rejection. The modern
`freecad/<ModName>/` layout is preferred, and a legacy layout must not manipulate `sys.path`.

Source: [Addon Index qualities](https://freecad.github.io/Addon-Academy/Topics/Addon-Index/Index/Qualities.html)

The publishing guide expects evidence of meaningful user testing and recommends the `freecad` and
`addon` repository topics. Review happens before the final release/tag requested for indexing.

Source: [Indexed publishing guide](https://freecad.github.io/Addon-Academy/Guides/Publishing/Indexed)

An InitGui-only extension that does not define a workbench is declared as `<other/>`; FreeCAD 1.1
is the first version whose Addon Manager recognizes that type. The same official example uses the
modern namespaced layout and defers command imports to keep startup light.

Source: [Workbench-less toolbar example](https://freecad.github.io/Addon-Academy/Demos/New-Toolbar/)

## Lessons from actual reviews

### NeoRibbon: accepted after behavior corrections

The reviewer required an InitGui-only ribbon to use `other`, asked for the modern namespaced
layout, and then found two usability blockers: its restore operation made every toolbar visible,
overwriting users' visibility choices, and its shortcuts lacked conflict checks. The review moved
forward after those behaviors were corrected.

Source: [FreeCAD/Addons issue 112](https://github.com/FreeCAD/Addons/issues/112)

Lesson for FusionMyFreeCAD: restoration must reproduce the exact previous state, and merely
reporting shortcut displacement may not be enough. Existing user bindings should be preserved by
default or changed only through explicit, informed opt-in.

### OpenCAD-UX: technical polish did not substitute for maturity

This Fusion-inspired UI submission reported unit and integration tests, reversible settings, no
runtime dependencies, no startup side effects, and disclosed limitations. It was nevertheless
declined as insufficiently mature and was directed to collect beta feedback through reference or
portable distribution before resubmitting.

Source: [FreeCAD/Addons issue 143](https://github.com/FreeCAD/Addons/issues/143)

Lesson for FusionMyFreeCAD: passing CI and having release artifacts do not establish Index
readiness. A documented beta cohort, real FreeCAD usage across platforms, resolved feedback, and a
stable maintenance interval are separate deliverables.

### FreeCAD Nxt: global settings and document mutation receive close scrutiny

The reviewer objected to silent changes to base preferences that were not restored on disable or
uninstall, potentially destructive sketch repair, inconsistent versions, missing experimental
labelling, an unsuitable README URL, and an incorrect `workbench` content type. The submitter then
added restoration, removed the destructive repair approach, aligned versions, added status
labelling, used a raw README URL, and changed the content type.

Source: [FreeCAD/Addons issue 162](https://github.com/FreeCAD/Addons/issues/162)

Lesson for FusionMyFreeCAD: every automatic document or profile mutation needs a narrow contract,
tests, undo/recovery behavior, and honest user-facing disclosure. Disable/uninstall behavior must
be evaluated, not just the manual **Restore UI** command.

### SketchPrint: manifest claims and implementation claims are both checked

The reviewer identified a missing manifest namespace, package icon, and repository branch, asked
for the modern namespaced layout, and found that a claimed planarity check did not perform the
stated check. The author was asked to resubmit only after the code was genuinely deployment-ready.

Source: [FreeCAD/Addons issue 117](https://github.com/FreeCAD/Addons/issues/117)

Lesson for FusionMyFreeCAD: validation must test user-visible claims and real FreeCAD behavior,
not merely XML shape or test-double behavior.

### Other recurring blockers

- An add-on intentionally capable of losing unsaved work was rejected as inappropriate for the
  Index even though the behavior was disclosed. Safety and fit matter, not disclosure alone.
  Source: [FreeCAD/Addons issue 100](https://github.com/FreeCAD/Addons/issues/100)
- An AI integration review flagged unauthenticated local code execution, incomplete disclosure of
  transmitted design data, misleading branding, incorrect compatibility metadata, and undeclared
  platform breakage. Source: [FreeCAD/Addons issue 129](https://github.com/FreeCAD/Addons/issues/129)
- FreekiCAD was initially blocked by a dependency outside the allow list; the reviewer also asked
  it to distinguish itself from existing add-ons, and tutorials helped demonstrate the value.
  Source: [FreeCAD/Addons issue 152](https://github.com/FreeCAD/Addons/issues/152)

## Current FusionMyFreeCAD assessment

### Confirmed strengths

- The repository is public, active, older than 30 days, and declares GPL-3.0 licensing.
- The project has tests, release automation, restoration code, third-party notices, and documented
  maintenance procedures.
- Runtime network access is not part of the advertised feature set.
- The add-on already targets FreeCAD 1.1, which is compatible with the `other` content type.
- The UI provides verification and restoration tools, and the implementation records displaced
  shortcuts for diagnosis.

### Confirmed defects or gaps

1. `package.xml` declares `<workbench>` even though FusionMyFreeCAD does not register a workbench
   class. It lacks the required package icon and author, and its tags are nested inside the
   workbench item instead of being package metadata. It also lacks a dedicated README/overview URL.
2. The repository has no GitHub topics, so the recommended `freecad` and `addon` topics are absent.
3. The project uses the discouraged legacy root `Init.py`/`InitGui.py` layout and manipulates
   `sys.path` in runtime paths.
4. FreeCAD-Ribbon and SearchBar are distributed inside `bundled-addons/`. That is vendoring under
   the ordinary meaning of the Index policy, regardless of the project's controlled sync process
   and license notices.
5. Fusion shortcuts currently take a binding from another command and report the displacement.
   This differs from the conflict-avoidance behavior requested during NeoRibbon review.
6. The documented uninstall procedure tells users to run **Restore UI** before Addon Manager
   removal. This does not yet demonstrate that disable/uninstall itself safely restores all state.
7. The repository has only one recorded GitHub contributor and no public GitHub topics. Public
   releases exist through 1.4.0; 1.8.0 is currently a draft release. Those facts do not demonstrate
   the community beta evidence requested by the publishing guide.
8. The local Git object store reports about 137 MiB of loose objects, and the maintenance guide
   documents historical large files. This is primarily a distribution/maintenance concern and
   should be measured against the actual archive/index delivery path before treating history
   rewriting as necessary.

### High-risk eligibility question

FusionMyFreeCAD intentionally replaces or rearranges interface elements across core Part Design,
Part, Sketcher, and related contexts and applies global preferences and shortcuts. That appears to
conflict with the written rule against modifying or hiding FreeCAD's core interface or interfering
with other add-ons. This is an inference from the policy and the product behavior, not an official
ruling on FusionMyFreeCAD.

The right next action is a narrowly worded pre-submission question to the Addons maintainers with a
short behavior summary and screenshots. If a global UI transformation is categorically unsuitable,
the project should continue through portable/reference distribution rather than contorting the
manifest. If eligibility depends on confinement or explicit activation, the architecture plan can
be revised with that target known.

## Recommended implementation plan

### Gate 0 — Freeze the product contract before structural work

1. Treat `docs/dev-guide/CURRENT-FEATURE-INVENTORY.md` as the end-user benefit baseline.
2. Turn each preservation requirement into deterministic tests where possible and a real-FreeCAD
   manual test where automation is not authoritative.
3. Record startup time, workbench-switch behavior, profile mutations, and package contents before
   changing architecture.
4. Keep the present implementation available until the replacement passes the preservation matrix.

Acceptance criterion: every current benefit has an implementation owner, a behavioral acceptance
criterion, and regression coverage. No feature is removed by implication.

### Phase 1 — Make user state non-destructive and exactly reversible

1. Inventory every FreeCAD preference, toolbar/menu/ribbon state, shortcut, stylesheet, observer,
   dock, and document property touched at startup or runtime.
2. Add tests proving an arbitrary pre-existing user profile is restored byte-for-byte or
   value-for-value after disable/restore, including originally hidden toolbars.
3. Change shortcut behavior so occupied bindings are preserved by default. Offer explicit conflict
   resolution rather than silently taking bindings; keep diagnostic reporting.
4. Ensure automatic sketch handling cannot delete or rewrite user geometry unexpectedly. Keep
   repair/update operations explicit, undoable where FreeCAD supports transactions, and clearly
   disclosed.
5. Define a supported disable/uninstall path. If Addon Manager provides no uninstall hook, make the
   limitation prominent and seek maintainer approval for the recovery design.

Acceptance criterion: clean-profile, customized-profile, disable, reinstall, upgrade, failed-start,
and removal simulations all preserve user data and recover prior UI state.

### Phase 2 — Resolve the vendoring and architecture questions

1. Prototype several FMF-owned workbenches corresponding to the existing Part Design, Part,
   Sketcher, and Surface experiences. Reuse the present declarative layouts and native commands;
   do not replace them with one generic FMF workbench.
2. Build a parity matrix for each FMF-owned workbench against its stock counterpart. The target is
   a superior everyday replacement: complete core workflows, better organization and discovery,
   and FMF enhancements without unnecessary forks of native modelling commands.
3. Define the sketch-edit transition explicitly so Create Sketch retains FreeCAD's origin-plane
   selection and opens the FMF Sketcher experience without confusing workbench jumps.
4. Add a first-run FMF-branded activation page. Its primary action applies the complete integrated
   experience atomically; declining leaves FreeCAD unchanged and keeps an activation command
   available. Consent improves user control but is not treated as permission to keep modifying core
   workbenches contrary to the written Index rule.
5. Offer hiding corresponding stock workbenches only as a separate explicit action after FMF
   activation. Show the exact affected list, record prior visibility, support one-action reversal,
   and keep FMF fully usable when stock workbenches remain visible. Because the written Index rule
   expressly says an add-on must not hide FreeCAD's core interface, treat this optional convenience
   as a likely Index blocker even when the user consents; do not weaken the standalone product to
   conceal that conflict.
6. Migrate first-party modules to `freecad/FusionMyFreeCAD/` and remove first-party `sys.path`
   manipulation. Preserve compatibility shims only where the official loader requires them.
7. Investigate replacing bundled add-on runtimes without sacrificing the one-package installation.
   Acceptable outcomes include absorbing the necessary maintained code with provenance, using a
   supported dependency mechanism that installs atomically, or retaining the controlled bundles
   for non-Index distribution. Do not remove working functionality merely to satisfy a guess.
8. Separate generated/synchronized third-party payload checks from first-party linting and retain
   exact provenance, license, version, and local-patch records.
9. Measure packaged download size and startup/switching cost. Optimize the delivered artifact
   rather than rewriting Git history unless the delivery mechanism makes history size relevant.

Acceptance criterion: the import layout follows current guidance, no first-party global path
mutation remains, all four FMF experiences and their transitions pass the feature-preservation
matrix, installation remains effectively one-step, and startup work is measured and bounded.

### Phase 3 — Correct metadata and automate policy checks

1. Change content to `<other/>`; add package icon, author, top-level tags, and an appropriate raw
   README/overview URL; retain the repository branch attribute and FreeCAD 1.1 minimum.
2. Validate against the official schema and with the current Addon Manager, not only the local
   project validator.
3. Add CI assertions for content type, icon existence, author, top-level tags, URL/branch validity,
   version consistency, license consistency, and absence of first-party `sys.path` changes.
4. Add `freecad` and `addon` GitHub topics only when the owner authorizes the external repository
   update.
5. Keep the existing rule that the main project version cannot change without explicit owner
   approval.

Acceptance criterion: official schema validation and Addon Manager inspection succeed, and CI has
regression tests for every metadata failure observed in the reviewed submissions.

### Phase 4 — Establish maturity with real users and real FreeCAD

1. Publish through portable/reference distribution first and recruit a small beta cohort.
2. Test supported Windows, Linux, and macOS configurations in actual FreeCAD, including clean and
   heavily customized profiles. Narrow platform claims if a platform is not verified.
3. Track tester version, platform, workflows, failures, restoration results, and resolution status.
4. Add a user-focused overview with screenshots, quick start, limitations, recovery instructions,
   and short demonstrations of the distinct FusionMyFreeCAD workflow.
5. Run Bandit and review findings; add a security-reporting path and document that normal runtime
   behavior makes no external connections if that remains true.
6. Allow a stabilization interval with no known data-loss, profile-corruption, startup, or major
   workflow regressions.

Acceptance criterion: documented beta evidence, verified platform matrix, zero unresolved critical
or high safety/restoration issues, and honest current limitations.

### Phase 5 — Prepare and submit

1. Consider a stable release branch if maintainers recommend it; do not create or change branches
   remotely without explicit owner instruction.
2. Run the complete release, package, lint, unit, integration, startup, restoration, security, and
   manual FreeCAD test matrix.
3. Recheck every Index quality item and compare the submission against the failure patterns in this
   report.
4. Open an Addon Addition issue only after all earlier gates pass. Make the requested final tag or
   release after reviewer approval, as the official workflow directs.

Acceptance criterion: the submission links objective evidence for safety, reversibility, maturity,
compatibility, licensing, and metadata rather than relying on unsupported claims.

If meeting the Index rules would still require removing a product-defining benefit, stop before
submission and continue distributing through GitHub releases or the documented portable/reference
channels. That is a valid project outcome, not a failed refactor.

## Risks not to “fix” speculatively

- Do not change the main project version without explicit approval.
- Do not rewrite repository history merely because the local object database is large.
- Do not remove bundled functionality before the Addons maintainers clarify eligibility and
  dependency expectations.
- Do not claim cross-platform support based only on mocked tests.
- Do not describe restoration as uninstall-safe until it is exercised through the actual removal
  workflow.

## Research limitations

- Addon Index decisions are reviewer judgments; published issues provide examples, not a complete
  binding precedent system.
- No actual FreeCAD executable was exercised in this research pass.
- GitHub metadata shows repository-level facts but cannot prove the size or quality of off-platform
  user testing.
- The current official policy creates tension between its workbench-less toolbar example and its
  broad prohibition on modifying core UI. Only the maintainers can resolve that tension for a
  full-interface add-on like FusionMyFreeCAD.
