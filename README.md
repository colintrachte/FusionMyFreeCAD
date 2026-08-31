# FusionMyFreeCAD

A self-contained, Fusion-familiar adaptive interface for FreeCAD 1.1 and newer on Windows, macOS,
and Linux.

FusionMyFreeCAD reorganises FreeCAD's Part Design, Part, Sketcher, and Surface workbenches into a
Fusion-style ribbon, adds command search and Fusion keyboard shortcuts, and sets Fusion-like mouse
navigation. It is a configuration layer: it does not modify FreeCAD's modelling kernel or document
format, and everything it changes can be undone from inside FreeCAD.

## Status

Version **1.2.0** is available from [GitHub Releases](https://github.com/colintrachte/FusionMyFreeCAD/releases/tag/v1.2.0)
as a self-contained archive. FusionMyFreeCAD has not yet been submitted to FreeCAD's add-on index;
catalog publication remains separate work.

## Install

Download `FusionMyFreeCAD-1.2.0.zip` from the
[1.2.0 release](https://github.com/colintrachte/FusionMyFreeCAD/releases/tag/v1.2.0), extract its
top-level `FusionMyFreeCAD` folder into FreeCAD's user `Mod` directory, and restart FreeCAD. Full
platform-by-platform steps, verification, update, and removal instructions are in
[`docs/INSTALL-FREECAD-ADDON.md`](docs/INSTALL-FREECAD-ADDON.md).

The archive contains everything needed: the ribbon engine, command search, layouts, shortcuts,
Smart Dimension settings, the navigation cube, adaptive FREQUENT panels, verification, and
restoration. There are no separate repositories, system-Python packages, .NET runtimes, PowerShell
scripts, or configuration files to install.

## First run

On first launch FusionMyFreeCAD records your existing ribbon layout and the preferences it manages,
then applies its own. **The recorded baseline is written once and never overwritten**, so the
original profile stays recoverable even if later state is lost.

Managed preferences are applied **once per installed version**, not at every launch. Changing one of
them in FreeCAD's own preferences dialog afterwards sticks; FusionMyFreeCAD will not quietly put it
back on the next start.

## Ribbon access and personalisation

Every panel has a dropdown containing its complete command inventory, including commands that do
not fit on the ribbon face. A normal click runs a visible command; click, hold, and drag past the
platform's normal drag distance to reorder its icon within that panel. The new order is saved
automatically and survives FreeCAD restarts and FusionMyFreeCAD layout updates.

Each panel's dropdown ends with **Reset this panel**. It restores only that panel's shipped order
and pinned commands, leaving every other panel alone. There is deliberately no top-level reset
button. **Reapply UI** remains the explicit whole-interface reset and clears all ribbon
personalisation along with restoring the other shipped defaults.

## The three UI commands

Each lives in an **INSPECT** panel:

| Command | What it does |
|---|---|
| **Verify UI** | Checks the installed layout, the restore point, the bundled payload, and any startup or runtime failure, and reports what to do next |
| **Reapply UI** | Returns the whole ribbon, managed preferences, and shortcuts to the shipped defaults; this clears all panel personalisation |
| **Restore UI** | Undoes everything FusionMyFreeCAD changed, using the first-run baseline |

Run **Restore UI** *before* removing FusionMyFreeCAD in Addon Manager. If you have already removed
it, [`tools/RestoreFusionMyFreeCAD.FCMacro`](tools/RestoreFusionMyFreeCAD.FCMacro) does the same job
as a standalone macro.

## Settings

**Edit → Preferences → FusionMyFreeCAD** exposes the opt-outs:

| Setting | Default | Effect |
|---|---|---|
| Start in the Part Design workbench | on | Sets Part Design as the autoload workbench |
| Use Fusion-style navigation and the navigation cube | on | Revit navigation style, navigation cube top-right |
| Apply Fusion keyboard shortcuts | on | `L` `R` `C` `D` `E` `H` `T` `O` `P` `X` and friends |
| Open a starter design on launch | off | Creates an empty document and body at every start |

Applying the Fusion shortcuts takes a binding from any command already holding it. **Verify UI**
lists every shortcut that was moved, and which command lost it.

## Compatibility and licence

FreeCAD 1.1.0 or newer, Python 3.11 or newer, as declared in `package.xml`.

The distributed package is **GPL-3.0-or-later**, because it bundles FreeCAD-Ribbon (GPL-3.0-or-later)
and SearchBar (LGPL-2.1). FusionMyFreeCAD's own first-party source is additionally offered under MIT;
see [`LICENSES/FusionMyFreeCAD-MIT.txt`](LICENSES/FusionMyFreeCAD-MIT.txt) and
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

Installing or updating a user interface does not validate CAD geometry, toolpaths, or manufacturing
output.

## Documentation

- [`docs/INSTALL-FREECAD-ADDON.md`](docs/INSTALL-FREECAD-ADDON.md) — install, verify, update, remove
- [`CHANGELOG.md`](CHANGELOG.md) — user-visible release history
- [`MAINTAINING.md`](MAINTAINING.md) — architecture, change procedures, validation, release checklist
- [`command-map.md`](command-map.md) — Fusion-to-FreeCAD command and shortcut decisions
- [`setup-guide.md`](setup-guide.md) — the manual, native-FreeCAD workflow baseline
- [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) — bundled component provenance and local changes
- [`research/`](research/) — design rationale, source evidence, and independent reviews

## Development

```bash
python -m pytest tests -q
```

`python validate_addon.py` runs the same suite and reports the packaged size.
`ruff check . && ruff format --check .` matches CI.

Only the FreeCAD command icons referenced by the layout are bundled; the full collection remains
in FreeCAD's official repository. After changing a button icon, verify its name against a real
installation and rebuild the curated subset from an official FreeCAD source checkout:

```bash
python tools/probe_freecad_icons.py --freecad "/path/to/FreeCADCmd"
python tools/sync_bundled_addons.py --freecad-source "/path/to/FreeCAD"
```
