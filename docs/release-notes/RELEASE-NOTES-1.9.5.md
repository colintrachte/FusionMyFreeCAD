# FMF 1.9.5

FMF 1.9.5 is a quality, stability, and performance release focusing on ribbon lifecycle integrity, document cleanup, and crash prevention.

## Highlights

- **Ribbon & Task Panel Stability**: Resolved an issue where opening native PartDesign task panels (such as Pad or Pocket) caused the FMF ribbon and SearchBar to gray out or rearrange unexpectedly.
- **Clean Document Lifecycle**: Starter documents created automatically on launch are now cleanly tracked and discarded on exit if left untouched, preventing unwanted save prompts.
- **Workbench Ordering**: Organized FMF workbenches in intuitive sequence: FMF Design, FMF Part, FMF Sketch, and FMF Surface.
- **Event Filter & Crash Prevention**: Scoped keyboard event filters on dress-up tools, eliminating crashes caught in `GUIApplication::notify`.
- **Geometry & Multi-Body Reliability**: Hardened multi-body feature ownership and sketch wire extraction for multi-region profiles.
- **Startup & Performance Optimization**: Reduced SearchBar focus overhead and eliminated startup warning dialogs.

## Install or update

Download `FMF-1.9.5.zip` and `FMF-1.9.5.zip.sha256` from this release. Replace the entire existing `Mod/FMF` folder; do not merge it with an older version.

See the [installation guide](https://github.com/colintrachte/FusionMyFreeCAD/blob/v1.9.5/docs/user-guide/INSTALL-FREECAD-ADDON.md) and [full changelog](https://github.com/colintrachte/FusionMyFreeCAD/blob/v1.9.5/CHANGELOG.md).
