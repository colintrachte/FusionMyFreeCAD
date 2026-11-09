# FMF 1.9.6

FMF 1.9.6 replaces the broken 1.9.5 release. It fixes a first-launch ordering race that could run
UI validation before the Ribbon was constructed and then permanently disable FMF.

Validation now runs as the final phase of FMF's coordinated workbench transition, after Ribbon
initialization. FMF also requests an initial reconciliation pass once all startup phases are
registered. If Ribbon chrome is delayed or unavailable, FreeCAD's native menu remains usable and
FMF records a recoverable degraded state instead of rewriting the user's enabled preference.

Users who attempted to install 1.9.5 can update by replacing the complete `Mod/FMF` folder. If
1.9.5 already disabled FMF, start FreeCAD and choose **FMF → Enable FMF** once. No manual
`user.cfg` editing is necessary.

## Install or update

Download `FMF-1.9.6.zip` and `FMF-1.9.6.zip.sha256` from this release. Replace the entire existing `Mod/FMF` folder; do not merge it with an older version.

See the [installation guide](https://github.com/colintrachte/FusionMyFreeCAD/blob/v1.9.6/docs/user-guide/INSTALL-FREECAD-ADDON.md) and [full changelog](https://github.com/colintrachte/FusionMyFreeCAD/blob/v1.9.6/CHANGELOG.md).
