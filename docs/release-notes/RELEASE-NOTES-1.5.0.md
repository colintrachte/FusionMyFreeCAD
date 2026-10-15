# FMF 1.5.0

Arrange the ribbon the way you want it, and keep the sketcher responsive while a
part grows.

## Sections you can arrange

Drag the divider between two sections to resize the section on its left. A guide
shows where the edge will land, and the commands that no longer fit move into
that section's drawer. Click a section title to open that drawer.

**UTILITIES** replaces the Ribbon add-on's global Tools panel: the same standard
commands, but part of the layout, so it can be ordered, resized and reset.

The **EXPORT** section now ends the Part Design, Part and Surface tabs, as
Create Sketch begins them. It reads the selection and opens the save dialog already set to a
sensible format -- STEP for solids and bodies, STL for meshes, PDF for drawing
pages, DXF for sketches -- and the STEP, STL, 3MF and DXF buttons beside it each carry their own mark and
caption, so the one you want is picked out at a glance.

## A faster sketcher

FMF rebuilds a sketch's internal faces so multi-region profiles stay
selectable and padable. That rebuild runs an OpenCASCADE boolean, and it had been
running on every solve, which means every frame of a drag. It now waits until you
leave the sketch, and skips entirely when nothing about the shape has changed.

## Mirror + Constraints tells you when it cannot help

A tangency sitting on the mirror line cannot be carried across to the reflection.
The command used to skip it, report success, and leave a profile that would not
close, so the pad failed minutes later with no clue why. It now leaves the sketch
exactly as it was and names the joins it could not make.

## Fixes

- Ribbon icons can be dragged to reorder them again. Qt 6 removed the call every
  icon drag used, and the failure went to a log FreeCAD does not display.
- Resizing a section no longer makes unavailable commands look usable.
- Layout changes now reach an existing installation instead of being overridden
  by the panel order saved from the previous one.

## Upgrading

Nothing to do. Section widths recorded by 1.4.0 are retired -- they were measured
differently -- so sections return to sizing themselves until you drag them again.
Restore UI still returns the profile to how it was before FMF first ran.
