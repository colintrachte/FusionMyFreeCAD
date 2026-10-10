# Activation and restoration contract

FMF owns three distinct layers of state: the immutable pre-FMF baseline, shipped FMF defaults, and
user deltas made after activation. They must never be collapsed into one snapshot.

## States

- **Installed inactive:** commands and recovery are registered; no opinionated profile changes.
- **Activating:** the original baseline is durably captured before the first managed write.
- **Active:** FMF defaults plus user deltas are in effect.
- **Restoring:** observers are stopped before values and UI structure are restored.
- **Inactive restored:** original values and visibility are restored; activation remains available.
- **Recovery required:** an interrupted transition is detected and completed or rolled back before
  normal startup continues.

## Transition rules

Activation is atomic from the user's perspective: capture baseline, apply managed state, verify,
then commit the active marker. Failure reverses completed writes. Declining activation performs no
managed writes. Repeated activation, disable, and restoration are idempotent.

Restore and disable remove observers and event filters, restore exact preference existence/type/
value, restore each prior shortcut owner, restore stock-workbench visibility, and make native
toolbars discoverable. Shutdown must never persist an empty native toolbar strip. Uninstall is
preceded by disable where the host supports it; the standalone recovery macro remains the recovery
path when files are already removed.

## Canonical ownership

`fusion_bootstrap.py` owns the original baseline and transition journal. Runtime services own only
their current subscriptions. Layout defaults remain in the layout JSON; user personalization is a
delta keyed by stable IDs. No service may overwrite the baseline during upgrade or Reapply.

## Required failure tests

Exercise failure after baseline capture, after preference writes, during layout generation, during
observer installation, and before active-marker commit. Every case must restart into either the
verified active experience or usable restored FreeCAD, never a mixed state.

## Verification evidence

The deterministic suite injects failures during layout merge, ribbon write, and state commit. Every
case retains the original baseline, leaves no committed state, and succeeds as a recovered install
on retry. It also verifies restoration of an originally absent typed preference.

A live isolated-profile run on source build `26.3.0devR47870` exercised Verify, Restore, Reapply,
and a second Prepare. Restore reported no problems, recreated the exact baseline preference
signature, removed active state, and created a recovery directory. Reapply returned `recovered`, a
second Prepare returned `unchanged`, both health checks passed, and `baseline.json` remained
byte-for-byte unchanged. See `tests/fixtures/freecad-lifecycle.json`.
