# Third-party runtime components

FusionMyFreeCAD includes tested runtime snapshots of these projects so installation is one step and
does not depend on machine-local repositories:

- **FreeCAD Ribbon 1.11.1**, copyright Hakan Seven, Geolta, Paul Ebbers and contributors.
  Distributed under GPL-3.0-or-later. Source and license are preserved in
  `vendor/FreeCAD-Ribbon`.
- **SearchBar 1.8.1.1**, copyright its authors and contributors. Distributed under LGPL-2.1.
  Source and license are preserved in `vendor/SearchBar`.

SearchBar's optional XML preference indexing was changed to use Python's standard-library
`xml.etree.ElementTree`, removing its external `lxml` installation requirement.
FreeCAD Ribbon's bundled grid helper now uses Python lists instead of NumPy, and its optional icon
download and SearchBar's version lookup use `urllib`; its color helper uses standard Python instead
of Matplotlib. These changes remove the remaining third-party Python package requirements.

FusionMyFreeCAD's original MIT notice is preserved in `LICENSES/FusionMyFreeCAD-MIT.txt`.
