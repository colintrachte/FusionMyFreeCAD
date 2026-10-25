# Research brief: FreeCAD region-based Pad workflow

**Status:** Independent research pass
**Date:** 2026-10-25
**Question:** Can current FreeCAD Pad selected regions of one sketch, including multiple regions,
and what should FMF improve?
**Method:** Inspected FMF's current profile-selection code and the supplied FCStd, then checked
current FreeCAD documentation, upstream PartDesign source, and a matching upstream defect report.

## Executive finding

FreeCAD's current PartDesign profile model can consume one or more selected faces from a sketch.
With a sketch's `MakeInternals` enabled, closed contours become selectable `InternalFaceN`
subelements. A Pad whose Profile names those subelements pads only those regions; selecting the
sketch object itself still means the whole sketch. The current FMF selection observer does not
fully implement multi-region behavior because every click replaces the prior Profile list.

## What already exists / key findings

1. The official Pad documentation says Pad accepts a sketch or one or more faces and exposes a
   `Profile` LinkSub plus `AllowMultiFace`.[1]
2. Upstream PartDesign source initializes `AllowMultiFace` to true and retains a shape containing
   multiple profile faces when that property is enabled.[2]
3. Upstream Sketcher builds an `InternalShape` when internals are enabled.[3] This is the face
   source FMF already rebuilds and spatially orders.
4. In FMF, `_PadSelectionObserver.addSelection()` recognizes `InternalFaceN`, but assigns
   `target_pad.Profile = (sketch_obj, [sub_part])`; therefore a later click replaces rather than
   accumulates earlier regions (`fmf_bootstrap.py:2128-2186`).
5. The supplied `Spool Holder.FCStd` has `MakeInternals=true`, a valid face in
   `Sketch005.InternalShape`, and `Pad002.Profile=(Sketch005, [""])`, meaning the whole sketch was
   passed instead of the selectable internal face.
6. A current FreeCAD 1.1.3 issue reports the same `Wire not closed` failure when padding an attached
   sketch with an edge coincident with its support.[4] That makes the file's failure consistent
   with a host regression as well as the whole-sketch selection path; it is not evidence that
   external geometry should be converted.

## Ideas or implications

FMF should wrap native Pad rather than implement a new extrusion feature. The wrapper can capture
the pre-command selection, accept one or several `InternalFaceN` subelements from one sketch,
create the normal `PartDesign::Pad`, and preserve those subelements in its Profile. Selecting the
sketch object should remain an explicit whole-sketch operation. If no regions are selected, FMF
can enter a clear profile-picking mode and accumulate Ctrl-clicked regions before confirmation.

This keeps native PartDesign recompute, properties, and compatibility while fixing the interaction
layer that currently loses region intent.

## Contradictions and uncertainty

The official documentation describes face selection but does not clearly teach selection of
`InternalFaceN` regions inside a sketch. Community explanations describe the FreeCAD 1.1 workflow,
but they are anecdotal.[5] A real FreeCAD 1.1.3 GUI test remains necessary to establish the exact
selection order and visual preference required by the supported FMF build.

## Gaps and open questions

- Whether the current supported build exposes a global preference to generate/show internal
  sketch faces by default.
- Whether native Pad preserves a Ctrl-selected list of multiple `InternalFaceN` entries without
  FMF intervention in this exact build.
- Whether upstream issue #31707 is the sole cause of the supplied model's failure when the whole
  sketch is selected.

## Suggested decision or next experiment

Use native region profiles as the underlying mechanism. Before implementation, run a real-GUI
matrix with one sketch containing three disjoint/adjacent regions: whole-sketch selection, one
InternalFace, two Ctrl-selected InternalFaces, and a region sharing an edge with the support.
Then plan an Undo-safe FMF Pad wrapper around the observed native behavior. Do not create a parallel
extrusion object type and do not modify External Geometry semantics.

## Sources

[1] https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/PartDesign_Pad.md

[2] https://github.com/FreeCAD/FreeCAD/blob/main/src/Mod/PartDesign/App/FeatureSketchBased.cpp

[3] https://github.com/FreeCAD/FreeCAD/blob/main/src/Mod/Sketcher/App/SketchObject.cpp

[4] https://github.com/FreeCAD/FreeCAD/issues/31707

[5] https://www.reddit.com/r/FreeCAD/comments/1s06p32/psa_yes_you_can_actually_extrude_a_portion_of/
