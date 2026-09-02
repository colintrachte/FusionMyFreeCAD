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

- `IsActive()` is now cheap and side-effect free: it checks only that a document is open and the
  Sketcher workbench is active. The real "is a sketch being edited?" check happens when the button
  is actually clicked.
- The workbench switch when a sketch opens is deferred out of the document-observer callback, so
  it can no longer re-enter an edit that is still in progress.
- **Mirror + Constraints** returns as a small button in front of native **Mirror**. Native Mirror
  keeps its 1.3.1 size, so the Sketcher **MODIFY** panel is virtually unchanged from 1.3.1. Select
  geometry, then a mirror line or sketch axis; the command mirrors it and copies compatible
  endpoint constraints to unchanged borders or axes. Anything it cannot reproduce safely is
  reported in the Report view. The mirror and its copied constraints are one Undo step.
- The 1.3.2 **Coincident** → `Sketcher_ConstrainCoincidentUnified` swap and the new **Point on
  Object** button are **not** part of 1.3.3. Point-to-point **Coincident** stays as it was in 1.3.1.

## Install or update

Download `FusionMyFreeCAD-1.3.3.zip` and `FusionMyFreeCAD-1.3.3.zip.sha256` from this release.
Replace the entire existing `Mod/FusionMyFreeCAD` folder; do not merge it with an older version.
Restart FreeCAD. No sketch or document data is affected.

See the [installation guide](https://github.com/colintrachte/FusionMyFreeCAD/blob/v1.3.3/docs/INSTALL-FREECAD-ADDON.md) and [full changelog](https://github.com/colintrachte/FusionMyFreeCAD/blob/v1.3.3/CHANGELOG.md).
