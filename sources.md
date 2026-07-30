# Sources and research notes

Accessed 2026-07-30 unless otherwise stated. Primary and official sources are preferred. The Reqrefusion pages are a rendered mirror of the FreeCAD documentation repository and were used where the current FreeCAD wiki was difficult to index.

## FreeCAD 1.1 and interface customization

- [FreeCAD 1.1 release notes](https://freecad.github.io/Website/download/releases/1-1/)  
  Confirms the 1.1 release line, Theme Editor/theme tokens, status-bar shortcut hints, improved navigation, Part Design previews/draggers, and Sketcher improvements. The page lists 1.1.1 dated 2026-04-14.

- [FreeCAD manual PDF](https://www.freecad.org/manual/a-freecad-manual.pdf)  
  Documents deep interface customization, movable panels/toolbars, custom toolbars, and keyboard shortcuts under Tools → Customize. It also describes Part Design as the main workbench for manufactured/3D-printed solid components and lists Pad, Pocket, Mirrored, Linear Pattern, and Polar Pattern.

- [FreeCAD Interface Customization](https://reqrefusion.github.io/FreeCAD-Documentation-html/wiki/en/Interface_Customization.html)  
  Confirms Tools → Customize, custom toolbars, the requirement to load workbenches before their commands appear, and the limitation that default toolbars/menus themselves are not redesigned through this dialog.

- [FreeCAD custom toolbar tutorial](https://blog.freecad.org/2025/03/14/tutorial-custom-toolbars/)  
  Practical first-party walkthrough showing toolbar movement and creation of a custom toolbar from commands across categories/workbenches.

- [FreeCAD Status Bar](https://reqrefusion.github.io/FreeCAD-Documentation-html/wiki/en/Status_Bar.html)  
  Confirms that 1.1 added dynamic input hints for most Sketcher tools.

- [FreeCAD Addon Manager](https://reqrefusion.github.io/FreeCAD-Documentation-html/wiki/Std_AddonMgr.html)  
  Confirms that the Addon Manager installs workbenches, macros, preference packs, bundles, and other addons, and warns that addons are not part of or supported by FreeCAD core.

## FreeCAD navigation

- [FreeCAD Mouse Navigation](https://reqrefusion.github.io/FreeCAD-Documentation-html/wiki/Mouse_navigation.html)  
  Key evidence for selecting the Revit style. The documented Revit mapping is wheel zoom, middle-button pan, and Shift+middle-button orbit—the same as Fusion. It also documents the three ways to select a navigation style.

- [FreeCAD Preferences Editor](https://reqrefusion.github.io/FreeCAD-Documentation-html/wiki/fr/Preferences_Editor.html)  
  Confirms `Ctrl+,` for Preferences in version 1.1, theme selection, toolbar icon sizes, tree/property layout settings, and 3D navigation preferences.

## FreeCAD Sketcher

- [Sketcher Workbench](https://reqrefusion.github.io/FreeCAD-Documentation-html/wiki/en/Sketcher_Workbench.html)  
  Documents geometry and constraint tools, the context-sensitive Dimension command, editing dimensional values, full-constraint concepts, copy/paste behavior, and 1.1's `Ctrl+A` sketch selection.

- [Sketcher Line](https://reqrefusion.github.io/FreeCAD-Documentation-html/wiki/Sketcher_CreateLine.html)  
  Confirms the `G`, then `L` default and on-view parameter modes introduced in 1.0.

- [Sketcher Rectangle](https://reqrefusion.github.io/FreeCAD-Documentation-html/wiki/Sketcher_CreateRectangle.html)  
  Confirms the `G`, then `R` default and the four rectangle creation modes available since 1.0.

- [Sketcher Circle](https://reqrefusion.github.io/FreeCAD-Documentation-html/wiki/Sketcher_CreateCircle.html)  
  Confirms the `G`, then `C` default and center/rim-point modes.

- [Sketcher Dimension](https://reqrefusion.github.io/FreeCAD-Documentation-html/wiki/Sketcher_Dimension.html)  
  Confirms the direct `D` shortcut and that the 1.0+ tool proposes appropriate dimensional or geometric constraints based on current selection.

- [Sketcher Polyline](https://reqrefusion.github.io/FreeCAD-Documentation-html/wiki/Sketcher_CreatePolyline.html)  
  Confirms continuing connected line/arc creation and the `G`, then `M` default.

- [Sketcher Mirror / Symmetry](https://reqrefusion.github.io/FreeCAD-Documentation-html/wiki/Sketcher_Symmetry.html)  
  Confirms the `Z`, then `S` default, selected-geometry workflow, and optional symmetry-constraint behavior.

## FreeCAD Part Design

- [Part Design Workbench](https://reqrefusion.github.io/FreeCAD-Documentation-html/wiki/PartDesign_Workbench.html)  
  Primary command/workflow reference. It explains the Body container and cumulative feature model; Pad adds an extruded sketch; Pocket subtracts one; and Part Design supplies New Body, Create Sketch, Hole, Mirror, Linear Pattern, and Polar Pattern.

- [FreeCAD 1.1 release announcement](https://blog.freecad.org/2026/03/25/freecad-version-1-1-released/)  
  Confirms the 1.1 release and highlights transparent Part Design previews, interactive feature draggers, and other modeling improvements.

## Autodesk Fusion

- [Fusion keyboard shortcuts reference](https://help.autodesk.com/view/fusion360/ENU/?guid=GUID-F0491540-0324-470A-B651-2238D0EFAC30)  
  Primary basis for the proposed bindings. Autodesk lists `E` Extrude, `H` Hole, `F` Model Fillet, `S` Model Toolbox, `L` Line, `R` 2-Point Rectangle, `C` Center Diameter Circle, `T` Trim, `O` Offset, `I` Measure, `P` Project, `X` Normal/Construction, and `D` Sketch Dimension. It also documents middle-button pan, wheel zoom, and Shift+middle-button orbit.

- [Fusion desktop interface](https://help.autodesk.com/view/fusion360/ENU/?contextId=LP-STEPS-P13N-SNP-GS-OTH-CRD-1)  
  Defines the workspace/tabs/contextual Sketch tab, Browser, canvas, ViewCube, marking menu, navigation bar, and parametric timeline used in the interface comparison.

- [Fusion mirrors and patterns in sketches](https://help.autodesk.com/view/fusion360/ENU/?contextId=SKT-SKETCH-CREATE-MIRRORS-PATTERNS)  
  Confirms that Fusion's sketch Mirror and Pattern commands operate on active-sketch geometry/construction geometry.

- [Autodesk support: Fusion navigation shortcuts](https://www.autodesk.com/support/technical/article/caas/sfdcarticles/sfdcarticles/Shift-middle-mouse-button-for-orbit-no-longer-function-after-latest-update-in-Fusion.html)  
  Current support article confirming that the Fusion navigation preset uses Shift+middle-button orbit and explaining where Fusion's navigation preset is selected.

## Optional addon

- [FreeCAD addons catalog](https://www.freecad.org/addons.php?lang=eng_EN)  
  Describes PieMenu as a module intended to accelerate and simplify FreeCAD workflows.

- [PieMenu v2 discussion](https://devtalk.freecad.org/t/piemenu-v20/64141)  
  Maintainer discussion describing installation through Addon Manager and customizable toolbar pie menus. This is community evidence, so the recommendation remains optional and subject to local compatibility testing.

## Open-source reuse and porting assessment

- [APEbbers FreeCAD-Ribbon](https://github.com/APEbbers/FreeCAD-Ribbon)  
  Active GPL-3.0 ribbon implementation derived from earlier FreeCAD-Ribbon and Modern-UI work. Documents JSON-based layout, cross-workbench custom panels, sizing, labels, dropdowns, stylesheets, and Addon Manager installation.

- [FreeCAD-Ribbon releases](https://github.com/APEbbers/FreeCAD-Ribbon/releases)  
  Shows continued 2026 releases. Version 1.9.1.5 explicitly included a custom-panel compatibility update for FreeCAD 1.1.x; v1.11.0 was released in June 2026.

- [FreeCAD-Ribbon package manifest](https://raw.githubusercontent.com/APEbbers/FreeCAD-Ribbon/main/package.xml)  
  Records GPL-3.0-or-later licensing, FreeCAD 0.21 minimum compatibility metadata, and SearchBar/SaveAndRestore dependencies.

- [APEbbers SearchBar](https://github.com/APEbbers/SearchBar)  
  Documents tool/object/preference search, an `S`-key MouseBar beside the pointer, workbench loading, Addon Manager installation, extensible providers, and its stability warning.

- [APEbbers SaveAndRestore](https://github.com/APEbbers/SaveAndRestore)  
  Documents backups and restoration of FreeCAD configuration and addons, toolbar reset, safe mode, Addon Manager installation, and MIT licensing.

- [obelisk79 OpenTheme](https://github.com/obelisk79/OpenTheme)  
  LGPL-2.1 OpenLight/OpenDark preference packs built from maintainable SCSS and designed around an accessible coordinated palette. The repository labels the addon beta.

- [FreeCAD addon catalog](https://www.freecad.org/addons.php?lang=eng)  
  Lists OpenTheme version 2025.05.20 with a May 2026 update and LGPL-2.1-or-later licensing.

- [FreeCAD first-party themes](https://github.com/FreeCAD/FreeCAD-themes)  
  Official theme repository with modern light/dark options and a FreeCAD 1.1-specific variant.

- [HakanSeven12 Modern-UI](https://github.com/HakanSeven12/Modern-UI)  
  Historical GPL-3.0 ribbon/auto-hide addon. The repository labels it Alpha and its published recovery example uses PySide2.

- [triplus PieMenu](https://github.com/triplus/PieMenu)  
  Historical radial menu implementation; the repository shows no published releases and documents Tab as its invocation key.

- [triplus IconThemes](https://github.com/triplus/IconThemes)  
  LGPL-2.1 Qt resource-based icon-theme addon available through Addon Manager.

- [Ondsel shutdown FAQ](https://www.ondsel.com/faq/)  
  States that most generally useful Ondsel changes were already contributed upstream, OpenTheme and its preference pack were separate/public projects, and Assembly simulations were merged for FreeCAD 1.1.

- [Ondsel shutdown announcement](https://www.ondsel.com/blog/goodbye/)  
  Describes upstream UI/UX contributions and identifies OpenTheme as the main source of Ondsel's praised visual styling.

## Confidence and limits

High confidence:

- FreeCAD Revit navigation is the correct Fusion mouse mapping.
- Part Design is the correct home for this goal.
- the geometry and Dimension shortcut mappings are valid in 1.1.1.
- Pad/Pocket are the correct additive/subtractive FreeCAD translations.
- custom toolbars and keyboard shortcuts are supported.

Moderate confidence / verify locally:

- assigning every proposed standalone key without conflicts from locally installed workbenches;
- which of Measure versus Quick Measure is exposed in the 1.1.1 Customize dialog;
- PieMenu's exact behavior with the user's installed build and other addons;
- exact Theme Editor controls, because 1.1's official release notes announce the feature but detailed user documentation is still sparse.
