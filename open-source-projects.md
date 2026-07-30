# Open-source projects that can accelerate the makeover

Research date: 2026-07-30  
Target: FreeCAD 1.1.1 on Windows

## Short answer

Yes. A combination of **FreeCAD-Ribbon**, **SearchBar**, **OpenTheme**, and **SaveAndRestore** can provide most of the UI shell without writing a new interface framework.

The most important discovery is that the old Modern-UI project has effectively already been carried forward: **APEbbers/FreeCAD-Ribbon** explicitly credits and builds on Modern-UI and an earlier FreeCAD-Ribbon implementation. Its releases include a specific FreeCAD 1.1.x compatibility change, and development continued after FreeCAD 1.1.1 was released.

Recommended foundation:

| Project | Use for this makeover | Current evidence | Recommendation |
|---|---|---|---|
| [FreeCAD-Ribbon](https://github.com/APEbbers/FreeCAD-Ribbon) | Fusion-like top tabs/panels, custom cross-workbench command groups, button sizing/text, dropdowns and styling | Latest release v1.11.0 in June 2026; prior release explicitly added FreeCAD 1.1.x compatibility | **Use as the main shell** |
| [SearchBar](https://github.com/APEbbers/SearchBar) | Fusion `S` toolbox equivalent; searches tools, preferences and objects and opens beside the pointer | `S` is its default MouseBar key; actively developed fork with 313 commits | **Use, but test stability** |
| [OpenTheme](https://github.com/obelisk79/OpenTheme) | Coordinated modern light/dark appearance and a maintainable SCSS base for a Fusion-colored variant | Addon catalog version 2025.05.20 updated May 2026; 221 commits | **Use or fork only the theme layer** |
| [SaveAndRestore](https://github.com/APEbbers/SaveAndRestore) | Back up/restore `user.cfg`, `system.cfg`, addons, and toolbar state | Addon Manager package; MIT licensed | **Install before experimenting** |
| [Modern-UI](https://github.com/HakanSeven12/Modern-UI) | Historical ribbon and auto-hiding-dock implementation | Still labeled Alpha, uses PySide2 in its published instructions, no releases shown | **Do not port directly** |
| [PieMenu](https://github.com/triplus/PieMenu) | Radial command menu | Small older codebase, no published releases, README still describes the legacy Tab invocation | **Optional only; SearchBar is a better first choice** |
| [IconThemes](https://github.com/triplus/IconThemes) | Replace FreeCAD icons through Qt resource bundles | Installable through Addon Manager; LGPL-2.1 | **Defer until layout works** |
| [FreeCAD-themes](https://github.com/FreeCAD/FreeCAD-themes) | First-party alternative theme bases | Official FreeCAD repository includes modern light/dark themes and a 1.1-specific variant | **Lowest-risk visual fallback** |

## Best path: configure and lightly extend FreeCAD-Ribbon

FreeCAD-Ribbon already supplies the hard infrastructure:

- replaces classic toolbars with a ribbon;
- generates panels from existing FreeCAD workbench toolbars;
- stores the design in JSON;
- creates custom panels using commands from multiple workbenches;
- changes panel and button ordering by drag and drop;
- controls button size and whether labels are visible;
- creates custom dropdown buttons;
- supports stylesheets and FreeCAD's native shortcut editor;
- exposes quick-access and auxiliary toolbars;
- can auto-hide the ribbon.

This maps unusually well to the requested goal. We would not be porting an abandoned interface; we would be creating a **Fusion-oriented ribbon preset** on a maintained successor.

### Proposed ribbon structure

Create one highly focused **Design** tab with these panels:

| Panel | Commands |
|---|---|
| Solid | New Body, Create Sketch, Pad, Pocket, Hole |
| Sketch Create | Line, Rectangle, Circle, Arc, Slot |
| Sketch Modify | Dimension, Trim, Offset, Construction, External Projection |
| Sketch Pattern | Mirror, Move/Array, Rotate/Polar Transform |
| Feature Modify | Fillet, Chamfer, Thickness, Draft |
| Feature Pattern | Mirror, Linear Pattern, Polar Pattern, MultiTransform |
| Inspect | Measure, Fit All, Section/visibility helpers |

The ribbon can make a custom **Extrude** dropdown containing Pad, Pocket, and possibly New Body. That removes much of the cognitive gap without custom command logic. A true Fusion-style Extrude dialog that selects Join/Cut/New Body remains custom development.

## SearchBar is almost exactly Fusion's `S` toolbox

SearchBar is a better match than PieMenu for the most valuable Fusion behavior:

- its MouseBar appears next to the cursor;
- the default activation key is `S`;
- typing filters tools immediately;
- it can load the workbench associated with the selected result;
- results can include preferences and document objects as well as commands.

The repository warns that Python/C++ lifetime interactions caused crashes during development and advises caution. Most are reported as fixed, but this is enough reason to validate it with autosave enabled and the 3D document preview disabled initially.

## OpenTheme can supply the visual base

OpenTheme already separates styling into SCSS and coordinated OpenLight/OpenDark preference packs. That makes a Fusion-like color variant much cheaper than designing a Qt stylesheet from scratch.

Suggested approach:

1. First test OpenLight or OpenDark unmodified with FreeCAD-Ribbon.
2. Decide whether the light or dark Fusion interface is the intended target.
3. Fork only if the remaining color/spacing differences are worth maintaining.
4. Make a new color-variable/palette variant while preserving OpenTheme's component rules.
5. Keep toolbar layout and shortcuts outside the theme so each layer can be updated independently.

OpenTheme still labels itself beta. FreeCAD 1.1 also has a native theme-token editor and first-party themes, so theme work should be treated as replaceable presentation rather than the foundation.

## Why not port Modern-UI directly?

Modern-UI is historically important, but it is the wrong starting point now:

- its repository describes the project as Alpha;
- published recovery code imports PySide2, a sign of its older Qt generation;
- it offers the ribbon and dock ideas that FreeCAD-Ribbon already inherited;
- FreeCAD-Ribbon has a larger current codebase, Addon Manager support, releases, customization UI, and explicit FreeCAD 1.1.x work.

If a useful Modern-UI detail is missing, port that isolated behavior into a FreeCAD-Ribbon fork rather than reviving the whole addon.

## Why not port the old Ondsel application?

Ondsel's own shutdown FAQ says its generally useful changes were contributed upstream, with most included in FreeCAD 1.0 and Assembly simulation merged for 1.1. The remaining Ondsel-specific presentation was chiefly OpenTheme plus a public preference pack. Therefore:

- use current FreeCAD 1.1.1;
- use OpenTheme or a native theme;
- reuse preference ideas selectively;
- do not maintain an obsolete application fork.

## What would still need to be built?

The reusable projects cover the shell, discovery, backup, and appearance. Remaining work is comparatively focused:

1. A Fusion-specific Ribbon JSON/preset with the exact command ordering above.
2. A documented shortcut preset (`L`, `R`, `C`, `D`, `E`, `Shift+E`, `H`, `T`, `O`, `P`, `X`).
3. A small preference pack for Revit navigation, panel visibility, icon sizes, units, Sketcher options, and view defaults.
4. Optional Fusion-colored OpenTheme variant.
5. Optional context-sensitive **Extrude** command.

The Extrude command is the only item likely to need meaningful new Python behavior. A conservative version could present three choices—Add (Pad), Cut (Pocket), and New Body—then invoke the existing FreeCAD command. It should delegate modeling to FreeCAD rather than implement geometry itself.

## Estimated reuse

The following is an engineering estimate, not a measured benchmark:

- **70–85% of the interface makeover** can likely be configuration and theming on existing projects.
- **15–30%** is preset authoring, compatibility testing, documentation, and optional glue commands.
- recreating a horizontal Fusion timeline or completely merging Pad/Pocket/New Body semantics would be a substantially larger core-UI project and is outside the sensible first version.

## Recommended prototype order

1. Install SaveAndRestore and make a clean configuration backup.
2. Install FreeCAD-Ribbon through Addon Manager and verify Part Design and Sketcher commands on FreeCAD 1.1.1.
3. Install SearchBar; bind/retain `S`; disable its 3D preview during initial testing.
4. Apply OpenLight/OpenDark or a current first-party modern theme.
5. Build the Fusion Design ribbon through Ribbon's layout editor.
6. Apply shortcuts and Revit navigation.
7. Model the mounting-plate validation part from the setup guide.
8. Export/copy the ribbon JSON and record all preference files.
9. Only then decide whether a fork or custom Extrude command is justified.

## Licensing implications

| Project | Published license | Consequence for a distributed derivative |
|---|---|---|
| FreeCAD-Ribbon | GPL-3.0 | A modified distributed Ribbon fork should remain GPL-3.0-compatible and provide source. A user-created JSON preset may be separable, but it is simplest to publish the complete makeover openly. |
| OpenTheme | LGPL-2.1 | Modified theme sources can be redistributed under the applicable LGPL terms. |
| SaveAndRestore | MIT | Permissive reuse with attribution/license notice. |
| SearchBar | GitHub identifies LGPL-2.1, while its README also says public domain | Resolve the repository's conflicting license statements with the maintainer before redistributing modified code. Unmodified Addon Manager installation does not require us to fork it. |
| Modern-UI | GPL-3.0 | Code copied from it into a distributed derivative carries GPL obligations. |
| IconThemes | LGPL-2.1 | Suitable for an open icon-theme layer. |

This is a practical licensing summary, not legal advice.

## Decision

Start with **FreeCAD-Ribbon + SearchBar + SaveAndRestore**, then add either **OpenTheme** or a first-party modern theme. Do not begin by porting Modern-UI, Ondsel, or PieMenu.

If the prototype is successful, the most valuable project artifact would be a small open-source **Fusion Workflow Pack for FreeCAD 1.1** containing:

- the Ribbon preset;
- a preference pack;
- shortcut documentation/import tooling if feasible;
- optional theme palette;
- optional Extrude dispatcher;
- setup and rollback instructions.

That approach keeps almost all modeling behavior in upstream FreeCAD and limits our maintenance surface to presentation and command routing.

