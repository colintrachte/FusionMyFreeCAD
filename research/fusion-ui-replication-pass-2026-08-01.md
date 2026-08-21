# Research brief: Fusion UI replication for FusionMyFreeCAD

**Status:** Independent research pass used to revise the installer payload  
**Date:** 2026-08-01  
**Question:** Which Fusion toolbar hierarchy, contextual behavior, and navigation affordances should
the FreeCAD makeover reproduce, and which FreeCAD-native mechanisms should implement them?  
**Method:** Reviewed current Autodesk help, Autodesk-hosted UI captures, the user's local captures,
FreeCAD 1.1 documentation, FreeCAD source, and the installed Ribbon add-on's view-panel behavior.

## Executive finding

The makeover should reproduce Fusion's hierarchy, not merely its vocabulary. In the Solid context,
**Create Sketch is a visually independent gateway command** before the CREATE group. Invoking it
switches to a contextual Sketch toolbar whose default surface keeps common geometry and constraints
visible and places a conspicuous Finish Sketch action at the far right.[1][2] FreeCAD 1.1 already
has the matching context-sensitive Dimension tool; the installer should select its Single Tool mode
and Auto radius/diameter behavior rather than implement another dimension dispatcher.[7][8]

The Ribbon add-on's Views/Individual Views panel is redundant with FreeCAD's native on-canvas
navigation cube. The revised profile should hide all view ribbon panels and explicitly enable the
native cube at the upper right. This retains the more direct spatial control while reclaiming ribbon
width for modeling commands.

## What already exists / key findings

1. Autodesk places Create Sketch in Solid, Surface, Form, Sheet Metal, and base-feature contexts.
   The Sketch contextual tab and Finish Sketch are highlighted to communicate a temporary mode.[1]
2. Fusion's Sketch toolbar hierarchy is CREATE, MODIFY, CONSTRAINTS, INSPECT, INSERT, SELECT, then
   FINISH SKETCH. Its default capture pins Line, Rectangle, Circle/Arc families, Fillet/Trim/Offset,
   several common constraints, Measure, Insert, selection, and Finish Sketch.[2][3]
3. Fusion's Solid toolbar uses a few pinned commands plus deep menus for CREATE, MODIFY, ASSEMBLE,
   CONSTRUCT, INSPECT, INSERT, and SELECT. The menus are the full command inventory; the pinned row
   is a frequency-weighted subset.[4]
4. Fusion's Construct menu is deliberately organized into coordinate systems, planes, axes, and
   points. FreeCAD exposes fewer specialized commands, but its datum Plane, Line, Point, and
   Coordinate System tools are the correct conceptual grouping.[5]
5. Fusion's Inspect inventory is much broader than FreeCAD Part Design. The safe native subset is
   Measure, Check Geometry, and view/section tools; unsupported analysis labels should not be faked.[6]
6. FreeCAD's Dimension tool is context-sensitive: it proposes a constraint from the current
   selection, updates the proposal as selection changes, uses placement direction to choose
   horizontal/vertical/distance, and uses `M` to cycle alternatives.[7]
7. FreeCAD preferences support Single Tool, Separated Tools, or Both. Single Tool is the closest
   Fusion behavior; Auto applies radius to arcs and diameter to circles by default.[8]

## Ideas or implications

- Make Create Sketch the first, large, standalone Part Design ribbon action. Put New Body beside it
  as a smaller setup action; do not bury Create Sketch inside CREATE.
- Follow it with CREATE, MODIFY, CONSTRUCT, INSPECT, INSERT, and SELECT. Do not add an ASSEMBLE panel
  until a verified native Assembly command set is installed and tested.
- Keep Extrude (Pad), Cut (Pocket), Revolve, Hole, Sweep, Loft, Fillet, Chamfer, and Shell visible.
  Put subtractive sweep/loft/helix, primitives, patterns, and less frequent features into deep menus.
- In Sketcher, keep Smart Dimension large and visible. Put explicit X/Y/length/radius/diameter/angle
  commands only in its dropdown for intentional overrides.
- Suppress Ribbon `View`, `Views - Ribbon`, and `Individual views` panels. Set FreeCAD-Ribbon's
  `Preferred_view` to 3, set `ShowNaviCube` true, and re-enable the active viewer's NaviCube after
  document/workbench changes.

## Contradictions and uncertainty

- Autodesk screenshots span more than one toolbar generation. Exact icon spacing and pinned-command
  counts vary, but the contextual Create Sketch transition and group order are consistent.
- FreeCAD does not have exact native equivalents for Fusion Rib, Web, Emboss, Boundary Fill,
  Replace Face, Silhouette Split, most analysis commands, or the complete Insert inventory. Those
  should be omitted or mapped only when a real command with comparable behavior is verified.
- The official FreeCAD wiki was protected by an interactive anti-bot page during collection. The
  mirrored documentation was cross-checked against the local FreeCAD source for preference names
  and command registration.

## Gaps and open questions

- Actual visual confirmation still requires launching the user's FreeCAD build after installing
  the revised payload. Static JSON validation cannot prove the Ribbon add-on's runtime sizing.
- Available horizontal width depends on display scale. Secondary tools must remain in dropdowns so
  Create Sketch, Extrude, Modify, Smart Dimension, and Finish Sketch do not collapse first.

## Suggested decision or next experiment

Ship layout 3.0 with the hierarchy above, native cube restoration, and Single Tool dimensioning.
Verify it in an isolated profile, then have the user upgrade and provide one full-window Solid
capture and one active-Sketch capture. Use those captures for the final spacing and icon-size pass.

## Cross-CAD usage survey addendum

Fusion's exposed defaults are not a reliable proxy for an individual modeler's frequency. A small
cross-CAD review changed the seed order while preserving personal learning as the stronger signal:

- SolidWorks puts both Corner Rectangle and Center Rectangle directly in its Sketch toolbar, along
  with Mirror Entities, Trim, Extend, Move, Rotate, patterns, and dimensioning.[9] Its center
  rectangle explicitly carries a center point, supporting origin-centered design intent.[10]
- Experienced SolidWorks users repeatedly recommend centering parts on origin planes, sketching a
  center rectangle, and using mid-plane extrusion so feature/body mirrors remain robust.[11]
- In an Onshape discussion, users called pattern, mirror, and use/project especially useful beyond
  the obvious line/dimension/circle core.[12]
- Modeler discussions strongly favor per-context personal shortcut palettes over stock ribbons;
  users report that these palettes evolve by project and file type.[13][14]

This is qualitative evidence, not instrumented telemetry and not a representative statistical
survey. The defensible design is therefore a hybrid: stable high-frequency modeling anchors,
centered rectangle and mirror promoted in the initial Sketch seed, and a decayed per-workbench
FREQUENT panel learned from the user's own command history. Ellipse remains available in the full
FreeCAD command inventory but is not seeded merely because Fusion exposes it.

Surface modeling also needs a separate context. Layout 3.0 now gives FreeCAD's Surface workbench an
independent CREATE / MODIFY / INSPECT ribbon and an independent learned FREQUENT panel. This is a
native surface-modeling context, not a claim that FreeCAD's built-in Surface workbench duplicates
Fusion's T-Spline Form sculpting; Fusion's Form UI uses its own Create, Modify, Symmetry, Utilities,
Construct, Inspect, Insert, Select, and Finish Form context.[15]

## Sources

1. Autodesk, Edit a sketch: https://help.autodesk.com/cloudhelp/ENU/Fusion-Sketch/files/GUID-0EEF7073-6CDE-4E31-AF1A-0811F969F031.htm
2. Autodesk, Sketches in Fusion: https://help.autodesk.com/cloudhelp/ENU/Fusion-Sketch/files/SKT-3D-SKETCH.htm
3. Autodesk-hosted Sketch toolbar capture: https://help.autodesk.com/cloudhelp/ENU/Fusion-Sketch/images/toolbar/design-sketch.png
4. Autodesk Community toolbar captures: https://forums.autodesk.com/t5/fusion-support-forum/why-don-t-i-have-a-sketch-panel-on-my-toolbar/td-p/9025882
5. Autodesk, Construction geometry: https://help.autodesk.com/view/fusion360/ENU/?contextId=SLD-CONSTRUCT-TOOLS
6. Autodesk, Analysis tools: https://help.autodesk.com/view/fusion360/ENU/?contextId=SLD-INSPECT-TOOLS
7. FreeCAD documentation mirror, Sketcher Dimension: https://reqrefusion.github.io/FreeCAD-Documentation-html/wiki/Sketcher_Dimension.html
8. FreeCAD documentation mirror, Sketcher Preferences: https://reqrefusion.github.io/FreeCAD-Documentation-html/wiki/en/Sketcher_Preferences.html
9. SolidWorks 2026 Help, Sketch Toolbar: https://help.solidworks.com/2026/english/SolidWorks/Sldworks/r_sketch_toolbar.htm
10. SolidWorks 2023 Help, Rectangle PropertyManager: https://help.solidworks.com/2023/english/SolidWorks/sldworks/HIDD_DVE_SKETCH_RECTANGLES.htm
11. SolidWorks user discussion, best practices: https://www.reddit.com/r/SolidWorks/comments/15mfidj/what_are_your_solidworks_best_practices/
12. Onshape forum, Sketch Mode: https://forum.onshape.com/discussion/2153/sketch-mode
13. SolidWorks user discussion, common shortcuts: https://www.reddit.com/r/SolidWorks/comments/1lqa4c8
14. SolidWorks user discussion, workflow speed: https://www.reddit.com/r/SolidWorks/comments/yudmcj
15. Autodesk, Create T-Spline forms exercise: https://help.autodesk.com/cloudhelp/ENU/Fusion-Sculpt/files/GUID-A0F0D052-A500-4632-8E35-347D98ED4AE6.htm

Downloaded visual references are preserved in `research/fusion-ui-reference-images-2026-08-01/`.
