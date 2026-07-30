# FreeCAD Fusion Makeover — Conversation Progress

Date: 2026-07-30  
Workspace: `C:\Users\Colin\Documents\FreeCad Makeover`

## Goal

Make FreeCAD feel sufficiently similar to Fusion 360 that the same modeling habits can be used in both applications with minimal retraining. The priority is everyday part creation:

- Lines, rectangles, circles, arcs, and slots
- Dimensions and sketch constraints
- Mirror and rectangular/polar patterns
- Extrude/add, extrude/cut, and new-body workflows
- Fillet, chamfer, hole, and other frequently used Part Design tools
- Fusion-like command search and keyboard access

The initially installed FreeCAD version was confirmed locally as **1.1.1** (`1.1.1R20260414`).

## User direction for external AI material

Material supplied from another AI is untrusted input. Codex is the reviewer and implementation authority. Claims, code, schemas, and configuration must be independently checked. Codex decides what is accepted, modified, or rejected and records the reasoning.

## Research completed

The research folder currently contains:

- `README.md` — research index and high-level recommendation
- `setup-guide.md` — proposed setup process
- `command-map.md` — Fusion-to-FreeCAD workflow mapping
- `sources.md` — online sources and evidence
- `open-source-projects.md` — assessment of reusable open-source projects
- This progress/handoff document

### Current project recommendation

The strongest configuration-layer stack is:

1. **FreeCAD-Ribbon** by APEbbers as the main ribbon shell.
2. **SearchBar** by APEbbers for a Fusion-like `S` command toolbox.
3. **OpenTheme** or FreeCAD 1.1's native theme system for appearance.
4. **SaveAndRestore** installed first for rollback and configuration backup.

The older Modern-UI addon should not be ported wholesale. FreeCAD-Ribbon is a maintained successor to its main ribbon concept.

The proposed first ribbon layout is:

- Solid: New Body, Create Sketch, Pad, Pocket, Hole
- Sketch Create: Line, Rectangle, Circle, Arc, Slot
- Sketch Modify: Dimension, Trim, Offset, Construction, External Projection
- Sketch Pattern: Mirror and rectangular/polar transformations
- Feature Modify: Fillet, Chamfer, Thickness, Draft
- Feature Pattern: Mirror, Linear Pattern, Polar Pattern, MultiTransform
- Inspect: Measure, Fit All, and closely related helpers

A context-sensitive Extrude command remains a possible custom component, but it should only be implemented after a working configuration prototype proves what is actually missing.

## Version update finding

FreeCAD 1.1.3 is now available. The upgrade recommendation is valid, but the other AI described the release incorrectly:

- FreeCAD **1.1.2** contains important fixes, including security fixes.
- FreeCAD **1.1.3** adds a missing backport that fixes repeated version-update warnings when saving. The official 1.1.3 announcement explicitly says that its additional fix is not for a security risk or crash.

Therefore, upgrading from 1.1.1 to 1.1.3 is sensible, but it should not be described as though 1.1.3 itself introduced the `.FCStd` security fixes.

Sources:

- https://blog.freecad.org/2026/07/23/freecad-1-1-2-released/
- https://blog.freecad.org/2026/07/25/freecad-1-1-3-released/

## Other-AI artifact audit in progress

The following supplied files are in `C:\Users\Colin\Downloads`:

- `Fusion_DESIGN_Panels.json`
- `Fusion_Dropdowns.json`
- `Fusion_Ribbon_Preset_PartDesign.json`
- `fusion_shortcuts.py`
- `README (1).md`
- `ExtrudeDispatch.FCMacro`

All three JSON files are syntactically valid JSON. That does **not** mean they conform to FreeCAD-Ribbon's schema.

### Blocking findings already confirmed

#### 1. The supplied Ribbon JSON schema is not the current FreeCAD-Ribbon schema

Inspection of the current FreeCAD-Ribbon source shows these actual top-level structures:

- `newPanels`
- `customToolbars`
- `dropdownButtons`
- `workbenches`
- `quickAccessCommands`
- `iconOnlyToolbars`
- Other complete `RibbonStructure.json` fields

Custom dropdown names use an `_ddb` suffix, and dropdown members are stored as command/workbench pairs. Custom panels are stored under `newPanels` as command/source-panel pairs.

The supplied files instead invent structures such as:

- `custom_panels_global`
- `dropdown_buttons`
- `workbench_layouts`
- Arbitrary `tabs`, `settings`, `title`, `tooltip`, and `commands` arrays

FreeCAD-Ribbon's importer looks specifically for the real section names. Consequently, the supplied panel and dropdown imports would either import nothing or fail to produce the claimed layout. The three JSON files must not be installed as provided.

Relevant checked source:

- `FreeCAD-Ribbon/LoadDesign_Ribbon.py`, especially `ReadJson()` and the import handlers
- `FreeCAD-Ribbon/CreateStructure.txt`, which demonstrates the real structure

Upstream repository: https://github.com/APEbbers/FreeCAD-Ribbon

#### 2. Command identifiers contain errors

Examples already established from the Ribbon project's generated FreeCAD command structure:

- The New Body command is `PartDesign_Body`, not `PartDesign_NewBody`.
- Create Sketch is `Sketcher_NewSketch`; `PartDesign_NewSketch` is not supported by the checked command structure.
- The supplied sketch-pattern command `Sketcher_Symmetric` does not represent the claimed whole-sketch mirror operation. `Sketcher_MirrorSketch` exists, but the intended Fusion behavior still needs to be defined and tested.
- The dimension tool exposed in the checked structure includes `Sketcher_CompDimensionTools`; the supplied use of `Sketcher_ConstrainDimension` still requires direct FreeCAD 1.1 command verification.

A complete command inventory must be obtained from the real FreeCAD 1.1 GUI before constructing the final preset.

#### 3. Macro command name mismatch

The JSON files reference:

`Fusion_Unified_Extrude`

The supplied macro registers:

`Fusion_ExtrudeDispatch`

The Ribbon could not invoke the supplied macro under the name used by the configuration.

#### 4. The macro is not a persistent addon command

Running `ExtrudeDispatch.FCMacro` registers its command only in that FreeCAD session and immediately invokes it. It does not install an `InitGui.py` that registers the command before FreeCAD-Ribbon builds its controls at startup. Therefore, the README's claim that the command can simply be added permanently to the Ribbon is incomplete.

If retained, this functionality should be packaged as a small proper FreeCAD addon/module with startup registration, not as a run-once macro.

#### 5. The claimed “unified Extrude” is not unified extrusion

The supplied macro displays only three choices:

- Pad
- Pocket
- New Body

It does not provide Intersect, direction handling, extent handling, preview, through-zero operation switching, or creation of a new body followed by an extrusion. “New Body” only runs the Body command. It is a launcher/dispatcher, not an 80%-complete port of UniCAD's unified Extrude task panel.

Its selection validation only checks whether anything is selected; it does not verify that the selection is a usable sketch/profile or that Pad/Pocket is currently active.

#### 6. README and delivered files disagree

The README refers to `Fusion_Unified_Extrude.FCMacro`, but the delivered file is `ExtrudeDispatch.FCMacro`.

The README claims:

- Join / Cut / New Body / Intersect
- A `Q` Smart PressPull shortcut
- `H` for constraint visibility
- Context-dependent `M`

The supplied code instead:

- Offers no Intersect option
- Defines no `Q` shortcut
- Assigns `H` to `PartDesign_Hole`
- Assigns `M` only to `Sketcher_Symmetric` and `Ctrl+M` to feature mirror

These contradictions are grounds to reject the pack in its current form.

#### 7. Shortcut script needs redesign and testing

Potential issues:

- It writes preferences without checking whether commands exist.
- It does not detect or resolve existing shortcut conflicts.
- It writes `SaveFlag=True` into the shortcut group even though no evidence has been found that this is a valid control key.
- It assigns `S` to `SearchBar_Show`, while SearchBar's MouseBar may manage its own activation key.
- It cannot supply contextual shortcuts of the kind described in the README.
- Some selected keys conflict with Fusion conventions or with one another depending on workbench/context.

The preference path may be valid, but validity of storage alone would not make this script safe to apply. It should not be executed against the user's configuration yet.

## UniCAD finding

UniCAD is a real public FreeCAD fork:

https://github.com/UNITRONIX/UniCAD

Its README claims a Fusion-style unified modeling workflow and identifies unified Extrude, Revolve, Sweep, Loft, PressPull, and face-manipulation features. It is based on FreeCAD 1.2.0-dev, not FreeCAD 1.1.1. The statement that its C++ implementation is “clean to cherry-pick” into 1.1.1 has **not** been established. A source and history comparison is required before deciding whether to port anything.

Because it is a young fork, explicitly AI-assisted, with limited independent adoption, its implementation should receive a normal code-quality and regression review rather than being treated as authoritative merely because the repository exists.

## Repository-cloning policy requested by the user

Codex should not repeatedly clone or fetch repositories. The user will create durable canonical clones. Codex should inspect those local clones thereafter.

Requested canonical clone directory:

`C:\Users\Colin\Documents\FreeCad Makeover\reference-repos\`

Repositories requested:

1. `https://github.com/FreeCAD/FreeCAD.git`
2. `https://github.com/APEbbers/FreeCAD-Ribbon.git`
3. `https://github.com/UNITRONIX/UniCAD.git`
4. `https://github.com/APEbbers/SearchBar.git`
5. `https://github.com/APEbbers/SaveAndRestore.git`
6. `https://github.com/obelisk79/OpenTheme.git`
7. Optional history/reference: `https://github.com/HakanSeven12/Modern-UI.git`

Temporary partial audit clones were created under `.audit` before this instruction. They are not canonical and should be disregarded after the user supplies the durable clones. Do not delete them without first resolving whether they are still needed for the current audit.

## Next steps

When the canonical repository clones are available:

1. Compare UniCAD's branch/base and unified-feature commits against FreeCAD 1.1.1 and 1.1.3.
2. Determine the exact dependency footprint of Unified Extrude and PressPull.
3. Generate or export a real FreeCAD-Ribbon structure using the current schema rather than inventing JSON.
4. Enumerate commands from the actual FreeCAD 1.1 GUI and validate each target command.
5. Design conflict-aware shortcut application and rollback.
6. Decide whether the first prototype should use:
   - Separate Pad/Pocket buttons,
   - A simple persistent dispatcher addon, or
   - A carefully ported UniCAD unified feature.
7. Test the prototype on a standard validation part before changing the user's main FreeCAD profile.

## Current decision

Do **not** import or execute any of the six supplied artifacts. They contain enough schema, naming, persistence, and documentation errors that installation would create misleading or broken state. The broad product direction remains useful, but the implementation must be rebuilt from verified FreeCAD-Ribbon and FreeCAD 1.1 interfaces.
