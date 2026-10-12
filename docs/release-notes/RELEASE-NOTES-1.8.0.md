# FusionMyFreeCAD 1.8.0

- Added bounded structured startup diagnostics, session health states, vendor-load timing, UI
  snapshots, and menu commands for copying a support summary or opening the diagnostics folder.
- FMF no longer reports activation healthy until the Ribbon is visibly usable; failed activation
  is logged and automatically rolls back to the native interface.

Arrange the ribbon around the way you work, keep complex sketches responsive,
and recover more quickly when changes leave downstream features out of date.

## Install or update

Download `FusionMyFreeCAD-1.8.0.zip` and
`FusionMyFreeCAD-1.8.0.zip.sha256` from this release. Replace the entire
existing `Mod/FusionMyFreeCAD` folder; do not merge it with an older version,
then restart FreeCAD.

See the [installation guide](https://github.com/colintrachte/FusionMyFreeCAD/blob/v1.8.0/docs/user-guide/INSTALL-FREECAD-ADDON.md)
and [full changelog](https://github.com/colintrachte/FusionMyFreeCAD/blob/v1.8.0/CHANGELOG.md).

## Sections you can arrange

Drag the divider between two sections to resize the section on its left. A guide
shows where the edge will land, and the commands that no longer fit move into
that section's drawer. Click a section title to open that drawer, aligned below
the section rather than below the small title-bar icon. **Reset this panel**
clears its saved width together with the rest of that panel's customization.

A dragged width is now a ceiling rather than empty space FusionMyFreeCAD must
fill. The section measures its actual buttons, shows the fullest set that fits,
and stops at the width those buttons need. This works for mixed sections where
large buttons and stacks of small buttons use different amounts of room.

**UTILITIES** replaces the Ribbon add-on's global Tools panel: the same standard
commands, but part of the layout, so it can be ordered, resized and reset.

The **EXPORT** section ends the Part Design, Part and Surface tabs, as Create
Sketch begins them. It reads the selection and opens the save dialog already set
to a sensible format -- STEP for solids and bodies, STL for meshes, PDF for
drawing pages, and DXF for sketches. The STEP, STL, 3MF and DXF buttons beside
it each have their own mark and caption.

## FREQUENT, in every workbench

Sketcher now has a **FREQUENT** section, so every workbench has one. Every
command offered by that workbench's ribbon can rise into it through use, rather
than only a short hand-picked list.

Commands dragged into FREQUENT stay ahead of automatically promoted commands;
commands dragged back out stay out. A command brought in from another workbench
keeps its label and icon. The section keeps a fixed arrangement of two large
slots followed by small ones so learned button positions do not continually
move.

Usage promotions appear when you next return to the workbench. A command you
drag into FREQUENT appears immediately.

## A faster sketcher and workbench switch

FusionMyFreeCAD rebuilds a sketch's internal faces so multi-region profiles stay
selectable and padable. That rebuild runs an OpenCASCADE boolean, and it had been
running on every solve, which means every frame of a drag. It now waits until you
leave the sketch and skips entirely when nothing about the shape has changed.

Entering or leaving a sketch no longer repeatedly walks every main-window
action for every shortcut FusionMyFreeCAD manages. Shortcut processing runs
after the window is ready, and repeated workbench activations now replace older
pending copies of the same UI task instead of accumulating redundant shortcut,
navigation-cube and model-tree retries. Adaptive-command tracking also uses a
cached command index instead of searching every adaptive panel after each click.

## Stable selectable regions

The faces made from a multi-region sketch are now ordered by where their regions
are. Moving a dimension no longer lets OpenCASCADE's incidental output order
change `InternalFace2` into a different profile and break the Pad and features
below it.

Adding or removing a region can still renumber the regions from that position;
there is no persistent element map available to prevent that. This release does
remove the unrelated renumbering caused by ordinary edits.

## Mirror + Constraints is safer

A tangency sitting on the mirror line cannot be carried across to the
reflection. The command used to skip it, report success, and leave a profile
that would not close, so the Pad failed later with no clue why. It now leaves
the sketch exactly as it was and names the joins it could not make.

Mirrored arcs no longer receive an `Equal` constraint on top of symmetry links
for their centre and endpoints. Those links already fix the radius, so the extra
constraint was redundant. Mirrored circles still receive `Equal`, because their
centre link alone does not set their size.

## Coincident chooses the applicable constraint

The Sketcher ribbon's **Coincident** controls now use FreeCAD's unified
Coincident command. Selecting two endpoints creates a point-to-point Coincident
constraint. Selecting an endpoint and an edge creates Point-on-Object instead
of leaving the button with no applicable action.

## Repair References

**Repair References** in UTILITIES scans the document for face and edge
references that no longer resolve -- the breakage reported as `missing element
reference`, `Invalid edge link`, or `subshape not found` -- and repairs the cases
it can identify safely.

A sketch or datum whose former support face can still be identified from its
placement is reattached to that face. Matching requires both the plane and the
object's position within the face, so two faces at the same height are not
treated as interchangeable. Attachments to origin planes are recognized as
valid and are not reported as broken.

If a broken attachment has fallen back to the default placement, the likely
face is reported but not applied: there is not enough information left to move
the object safely. Unrecoverable edge references are likewise named in the
Report view and left alone. Repairs are one transaction, so one Undo restores
the previous state.

## Update Model

**Update Model** in UTILITIES marks every feature for recompute and then rebuilds
the document, carrying an upstream change through features that FreeCAD still
considers current. This is more thorough than Refresh or
`recompute(force=True)`, which can still skip objects that are not marked for
rebuild.

If rebuilding fails, the report distinguishes the feature that actually failed
from downstream features that were never reached. This avoids presenting one
broken input as a separate failure in every dependent feature.

## Reliability safeguards

Failures while rebuilding selectable sketch regions or assigning a selected
region to a Pad are now shown by **Verify FusionMyFreeCAD** instead of being silently
ignored. If a Pad assignment fails, its previous profile and the sketch's
visibility are restored.

Release and layout checks now guard behavior-sensitive commands and reject
incomplete or contradictory release metadata before an archive is uploaded.

## Other fixes retained from 1.5.0

- Ribbon icons can be dragged to reorder them again. Qt 6 removed the call every
  icon drag used, and the failure went to a log FreeCAD does not display.
- Resizing a section no longer makes unavailable commands look usable.
- Layout changes reach an existing installation instead of being overridden by
  the panel order saved from the previous version.

## Upgrading

Widths saved before the current measurement scheme are retired, so affected
sections size themselves automatically until you drag their dividers again.
Commands you explicitly placed in or removed from FREQUENT remain pinned or
excluded.

The stable region order differs from the older OpenCASCADE-dependent order. On
upgrade, check any Pad that uses a specific region such as `InternalFace2`; it
may need its profile selected once. After that, ordinary sketch edits retain the
new deterministic ordering.

FMF now owns separate FMF Design, FMF Part, FMF Sketch, and FMF Surface
workbenches. Its ribbon no longer replaces the layouts of the stock
workbenches. **Disable FusionMyFreeCAD** switches back to the corresponding
stock workbench, restores managed preferences and shortcuts, disconnects its
runtime callbacks and observers, closes its Parameters dock, and hides the FMF
workbenches without deleting their saved layout or personalization. Restarting
FreeCAD after the switch refreshes the workbench selector.
**Enable FusionMyFreeCAD** exposes them again. Hiding the corresponding stock
workbenches is a separate reversible preference. **Reset FusionMyFreeCAD**
restores FMF's shipped defaults without disabling it.
