# Activation and restoration contract

FMF owns three distinct layers of state: the immutable pre-FMF baseline, shipped FMF defaults, and
user deltas made after activation. They must never be collapsed into one snapshot.

## States

- **Installed disabled:** lifecycle commands and Preferences are registered; no opinionated profile changes.
- **Activating:** the original baseline is durably captured before the first managed write.
- **Active:** the FMF-owned Design, Part, Sketch, and Surface workbenches are registered; FMF
  defaults plus user deltas are in effect. Their stock counterparts remain structurally untouched
  but are hidden from the selector.
- **Disabling:** an active FMF workbench is mapped to its stock counterpart, managed preferences
  and shortcuts are restored from the immutable baseline, and FMF workbench entries are hidden.
- **Disabled:** stock workbenches and the bundled Ribbon remain usable; the generated FMF layout and
  personalization stay on disk for lossless re-enable. This state persists across restarts and
  enablement remains available in Preferences and the FMF menu.
- **Recovery required:** an interrupted transition is detected and completed or rolled back before
  normal startup continues.

## Transition rules

Activation is atomic from the user's perspective: capture baseline, apply managed state, verify,
then commit the active marker. Failure reverses completed writes. Declining activation performs no
managed writes. Repeated enable, disable, and reset operations are idempotent.

Disable prevents observers and event filters from loading on the next launch, restores exact
preference existence/type/value, restores each prior shortcut owner, unhides all four corresponding
stock workbenches, hides all four FMF workbenches, disconnects live runtime callbacks, removes
feature observers, and closes the Parameters dock. Any FMF autoload workbench is mapped to its stock
counterpart, so disabled FMF never starts in a hidden FMF workbench. It refreshes the workbench
selector immediately without hiding the Ribbon or unrelated workbench tabs. It does not delete the
FMF layout or personalization. Shutdown must never persist an empty native toolbar strip. Uninstall is
preceded by disable where the host supports it; the standalone recovery macro remains the recovery
path when files are already removed.

## Canonical ownership

`fmf_bootstrap.py` owns the original baseline and transition journal. Runtime services own only
their current subscriptions. Layout defaults remain in the layout JSON; user personalization is a
delta keyed by stable IDs. No service may overwrite the baseline during upgrade or Reset.

The shipped layout is authoritative only for `FMFDesignWorkbench`, `FMFPartWorkbench`,
`FMFSketchWorkbench`, and `FMFSurfaceWorkbench`. The vendored Ribbon remains the application chrome
for FMF, stock, and unrelated workbenches. Activation changes only the visibility of the four FMF
tabs and their four stock counterparts; it must never hide the whole Ribbon.

## Required failure tests

Exercise failure after baseline capture, after preference writes, during layout generation, during
observer installation, and before active-marker commit. Every case must restart into either the
verified active experience or usable disabled FreeCAD, never a mixed state.

## Verification evidence

The deterministic suite injects failures during layout merge, ribbon write, and state commit. Every
case retains the original baseline, leaves no committed state, and succeeds as a recovered install
on retry. It also verifies restoration of an originally absent typed preference.

A live isolated-profile run on source build `26.3.0devR47870` exercised the operations then named
Verify, Restore, and Reapply, plus a second Prepare. The restore operation reported no problems,
recreated the exact baseline preference signature, removed active state, and created a recovery directory. Reapply returned `recovered`, a
second Prepare returned `unchanged`, both health checks passed, and `baseline.json` remained
byte-for-byte unchanged. See `tests/fixtures/freecad-lifecycle.json`.

## Local diagnostics

FMF writes bounded structured diagnostics under
`FMF-Diagnostics` in FreeCAD's user-data directory. `events.jsonl` records ordered,
session-linked startup steps, vendor loading, durations, exceptions, and the final UI-health
snapshot. `session-status.json` reports `starting`, `healthy`, `degraded`, or
`activation_rolled_back`; `healthy` is not written until the deferred visual check confirms a
visible Ribbon, or until disabled startup restores the stock workbench tabs.

Use **FMF → Copy Diagnostic Summary** for a short support report or
**FMF → Open Diagnostics Folder** for the complete local evidence. Logs rotate at
512 KiB with three archives, contain no document contents, and are deliberately non-fatal: an
unwritable diagnostics directory must never prevent FreeCAD from starting.
