# Third-party runtime components

FusionMyFreeCAD includes tested runtime snapshots of the projects below so installation is one step
and does not depend on machine-local repositories or on packages from PyPI.

## Effective licence of the distributed package

The combined work distributed as FusionMyFreeCAD is **GPL-3.0-or-later**, because it bundles
FreeCAD Ribbon under that licence. FusionMyFreeCAD's own first-party source files are additionally
offered under the MIT licence preserved in `LICENSES/FusionMyFreeCAD-MIT.txt`; that offer applies to
those files taken on their own, not to the bundled package as a whole.

| Component | Version | Licence | Source in this repository |
|---|---|---|---|
| FreeCAD Ribbon | 1.11.1 | GPL-3.0-or-later | `bundled-addons/FreeCAD-Ribbon` |
| SearchBar | 1.8.1.1 | LGPL-2.1 (see note) | `bundled-addons/SearchBar` |
| FusionMyFreeCAD | this package | GPL-3.0-or-later (MIT for first-party files) | repository root |

FreeCAD Ribbon is copyright Hakan Seven, Geolta, Paul Ebbers and contributors.
SearchBar is copyright its authors and contributors.

### Note on the SearchBar licence

Upstream SearchBar is internally inconsistent: the `LICENSE` file in its repository is the GNU
Lesser General Public License version 2.1, while its `package.xml` metadata declares `CCOv1`. This
package treats the `LICENSE` file as authoritative and redistributes SearchBar under LGPL-2.1, which
is compatible with the GPL-3.0-or-later combined work via LGPL-2.1 section 3. This discrepancy has
not been resolved with the upstream maintainer; anyone relying on the CC0 reading should confirm it
upstream first.

## Local modifications

These changes exist so the package installs without any third-party Python dependency and starts
without a modal dialog the user cannot dismiss. They are re-applied mechanically by
`tools/sync_bundled_addons.py` and asserted by `tests/test_package.py`, so an upstream refresh cannot
drop them silently.

**Dependency removal**

- SearchBar's optional XML preference indexing uses Python's standard-library
  `xml.etree.ElementTree` instead of `lxml`.
- FreeCAD Ribbon's bundled grid helper uses Python lists instead of NumPy.
- FreeCAD Ribbon's colour helper uses standard Python instead of Matplotlib.
- FreeCAD Ribbon's optional icon download and SearchBar's version lookup use `urllib`.
- The `<depend type="python">` entries the above made unnecessary are stripped from both bundled
  `package.xml` files.

**FreeCAD's command icons are curated**

FusionMyFreeCAD ships only the command icons referenced by
`Resources/FusionMyFreeCAD/layout-v3.json`, not FreeCAD's complete icon collection. The selected
files are copied from an official [FreeCAD source checkout](https://github.com/FreeCAD/FreeCAD) by
`tools/sync_bundled_addons.py`. Keeping the small runtime subset is necessary because Ribbon builds
buttons before every source workbench is guaranteed to have registered its Qt resources; the full
collection remains recoverable from FreeCAD's repository and is not duplicated here.

`tools/probe_freecad_icons.py` verifies names against a real installation. The source sync records
the exact official source path and SHA-256 hash in
`Resources/FusionMyFreeCAD/source-icons.json`. Package tests reject missing, unresolved, and unused
icons in the curated directory.

**Ribbon access and direct arrangement**

- Every FusionMyFreeCAD panel option menu lists the panel's complete command inventory, including
  commands intentionally kept off the ribbon face.
- Ribbon buttons start a move only after Qt's normal click-and-drag threshold, so ordinary clicks
  still run commands while click-hold-drag works without an arrangement mode.
- Direct moves are saved through FusionMyFreeCAD's customization overlay.
- Each panel menu offers a panel-scoped reset; no global reset is added to the ribbon.

**Startup behaviour**

- FreeCAD Ribbon's data-file version check no longer raises a modal dialog. The upstream first-run
  changelog could cover it and leave both windows impossible to operate.
- FreeCAD Ribbon honours an `authoritativeWorkbenches` list so it does not rediscover and prepend
  every native FreeCAD toolbar.
- SearchBar's first-run changelog dialog is suppressed. FusionMyFreeCAD provides its own release
  notes.

Upstream licence files are preserved unmodified alongside each snapshot.
