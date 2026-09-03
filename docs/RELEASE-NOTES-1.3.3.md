# FusionMyFreeCAD 1.3.3

**1.3.3 replaces the withdrawn 1.3.2.** On FreeCAD 1.1.3, version 1.3.2 could intermittently
freeze and then crash with an "Access violation" while the Sketcher ribbon was being built —
typically on the first launch after updating, before any command was used. It did not always
reproduce on a later restart.

## What happened

The new **Mirror + Constraints** command's `IsActive()` check — which FreeCAD polls on a timer
for every visible button — reached into live GUI edit state (`getInEdit()`). When a sketch opens,
that poll could run while FreeCAD was still mid-`setEdit` and get back a half-built object whose
C++ access faulted in a way Python cannot catch.

## What changed in 1.3.3

### Crash fix

- `IsActive()` is now cheap and side-effect free: it checks only that a document is open and the
  Sketcher workbench is active. The real "is a sketch being edited?" check happens when the button
  is actually clicked.
- The workbench switch when a sketch opens is deferred out of the document-observer callback, so
  it can no longer re-enter an edit that is still in progress.

### Mirror + Constraints — live symmetry on every pair

- The button returns in front of native **Mirror**, which keeps its 1.3.1 size, so the Sketcher
  **MODIFY** panel is virtually unchanged from 1.3.1. It has a distinct icon — FreeCAD's Mirror
  glyph with a green "+" badge.
- Select geometry, then a mirror line or sketch axis. **Every** mirrored element now gets a live
  **Symmetric** link to its source across that line — including dividers and other geometry pinned
  to the borders, which the previous build reattached but left unlinked. Drag either element and
  the other follows. **Equal** keeps a mirrored circle or arc the same size. The mirror takes no
  independent driving dimensions; it tracks the source, the Fusion 360 way.
- The sketch stays clean instead of going orange. `addSymmetric` auto-copies single-element
  **Vertical** / **Horizontal** / **Block** constraints onto the copy; with a Symmetric link on
  both endpoints those are redundant, so the command strips them first. Boundary endpoint
  attachments are then added only where a Symmetric link does not already pin the point. On a
  bordered card-divider box the result is fully constrained with no redundant or conflicting
  constraints.
- After the mirror, the sketch's internal faces are rebuilt from a complete planar decomposition,
  so every enclosed region — including the middle cells between dividers — is selectable and can
  be padded. FreeCAD's native internal-face builder drops interior faces that share an edge with
  a neighbour.
- A constraint touching only a sketch axis or the origin, with nothing mirrored, is left alone
  rather than reported as skipped. The whole operation is one Undo step, and anything the command
  cannot reproduce safely is reported in the Report view.
- The 1.3.2 **Coincident** → `Sketcher_ConstrainCoincidentUnified` swap and the new **Point on
  Object** button are **not** part of 1.3.3. Point-to-point **Coincident** stays as it was in 1.3.1.

### Selectable regions and profile picking

- A sketch's face decomposition is kept current on every recompute, so multi-region sketches stay
  fully selectable while you edit them, not only right after a mirror.
- Pick the profile after the command: click **Pad**, then click an enclosed region in the 3D view
  and it is assigned to that Pad.
- New empty sketches open centred on the sketch-plane origin at roughly a 100 mm range; the
  origin-plane view no longer drifts up and to the right. A sketch that already has geometry keeps
  the camera you left it at.

## Install or update

Download `FusionMyFreeCAD-1.3.3.zip` and `FusionMyFreeCAD-1.3.3.zip.sha256` from this release.
Replace the entire existing `Mod/FusionMyFreeCAD` folder; do not merge it with an older version.
Restart FreeCAD. No sketch or document data is affected.

See the [installation guide](https://github.com/colintrachte/FusionMyFreeCAD/blob/v1.3.3/docs/INSTALL-FREECAD-ADDON.md) and [full changelog](https://github.com/colintrachte/FusionMyFreeCAD/blob/v1.3.3/CHANGELOG.md).
