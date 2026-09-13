"""Build the tracked third-party runtime payload from ignored upstream snapshots."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "vendor"
DESTINATION_ROOT = ROOT / "bundled-addons"
ICON_SOURCE_MANIFEST = ROOT / "Resources" / "FusionMyFreeCAD" / "source-icons.json"

RIBBON_MODULES = (
    "CacheFunctions.py",
    "CustomWidgets.py",
    "FCBinding.py",
    "InitGui.py",
    "LoadAddCommands.py",
    "LoadCombinePanel_Ribbon.py",
    "LoadDesign_Ribbon.py",
    "LoadLicenseForm_Ribbon.py",
    "LoadSettings_Ribbon.py",
    "Parameters_Ribbon.py",
    "RibbonUI.py",
    "Serialize_Ribbon.py",
    "Standard_Functions_Ribbon.py",
    "StyleMapping_Ribbon.py",
)

SEARCH_MODULES = (
    "BuiltInSearchResults.py",
    "GetItemGroups.py",
    "IndentedItemDelegate.py",
    "InitGui.py",
    "MouseBar.py",
    "Parameters_SearchBar.py",
    "RefreshTools.py",
    "ResultsDocument.py",
    "ResultsPreferences.py",
    "ResultsRefreshTools.py",
    "ResultsToolbar.py",
    "SafeViewer.py",
    "SearchBox.py",
    "SearchBoxLight.py",
    "SearchResults.py",
    "Serialize_SearchBar.py",
    "StyleMapping_SearchBar.py",
)


def copy_file(source_root: Path, destination_root: Path, relative: str | Path) -> None:
    relative = Path(relative)
    source = source_root / relative
    if not source.is_file():
        raise FileNotFoundError(f"Required vendor file is missing: {source}")
    destination = destination_root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def copy_tree(source_root: Path, destination_root: Path, relative: str | Path) -> None:
    relative = Path(relative)
    source = source_root / relative
    if not source.is_dir():
        raise FileNotFoundError(f"Required vendor directory is missing: {source}")
    shutil.copytree(source, destination_root / relative)


def configured_icon_names() -> set[str]:
    """Every icon the shipped layout references, FusionMyFreeCAD's own included."""
    layout_path = ROOT / "Resources" / "FusionMyFreeCAD" / "layout-v3.json"
    layout = json.loads(layout_path.read_text(encoding="utf-8"))
    return {
        Path(entry[4]).stem
        for panels in layout["workbenches"].values()
        for panel in panels
        for entry in panel["commands"] + panel.get("overflow", [])
    }


def authored_icon_names() -> set[str]:
    """The icons FusionMyFreeCAD draws itself.

    These have no counterpart in FreeCAD's source tree, so looking for one
    fails the whole sync -- which is what stopped the icon refresh working at
    all once the first authored icon was added. They also have to survive the
    prune in sync_layout_icons, which otherwise deletes anything it did not
    just copy from source.
    """
    manifest_path = ROOT / "Resources" / "FusionMyFreeCAD" / "layout-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return set(manifest.get("authoredIcons", []))


def freecad_sourced_icon_names() -> set[str]:
    """The layout's icons that should come from a FreeCAD source checkout."""
    return configured_icon_names() - authored_icon_names()


ICON_SOURCE_OVERRIDES = {
    # FreeCAD has a generic icon with the same name; Std_Measure uses this one.
    "umf-measurement": Path("src/Mod/Measure/Gui/Resources/icons/umf-measurement.svg"),
    # TechDraw carries private copies of these standard theme icons.
    "edit-copy": Path("src/Gui/Icons/edit-copy.svg"),
    "edit-cut": Path("src/Gui/Icons/edit-cut.svg"),
    "edit-paste": Path("src/Gui/Icons/edit-paste.svg"),
    "edit-undo": Path("src/Gui/Icons/edit-undo.svg"),
    "process-stop": Path("src/Gui/Icons/process-stop.svg"),
}


def canonical_svg_bytes(path: Path) -> bytes:
    """Return SVG bytes with repository-standard LF line endings."""
    return path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def freecad_icon_sources(freecad_source: Path) -> dict[str, Path]:
    """Find the configured icons in an official FreeCAD source checkout."""
    freecad_source = freecad_source.resolve()
    source_tree = freecad_source / "src"
    if not source_tree.is_dir():
        raise FileNotFoundError(
            "FreeCAD source checkout has no src directory: {}".format(freecad_source)
        )

    required = freecad_sourced_icon_names()
    candidates: dict[str, list[Path]] = {name: [] for name in required}
    for path in source_tree.rglob("*.svg"):
        if path.stem in candidates:
            candidates[path.stem].append(path)

    selected: dict[str, Path] = {}
    missing = []
    ambiguous = []
    for name, paths in candidates.items():
        override = ICON_SOURCE_OVERRIDES.get(name)
        if override is not None:
            preferred = freecad_source / override
            if preferred.is_file():
                selected[name] = preferred
                continue
        if len(paths) == 1:
            selected[name] = paths[0]
        elif not paths:
            missing.append(name)
        else:
            ambiguous.append("{}: {}".format(name, ", ".join(map(str, paths))))

    if missing or ambiguous:
        raise RuntimeError(
            "Could not select FreeCAD icons (missing={}, ambiguous={}).".format(
                sorted(missing), sorted(ambiguous)
            )
        )
    return selected


def sync_layout_icons(freecad_source: Path, destination: Path) -> dict[str, Path]:
    """Refresh only the curated FreeCAD command icons used by the layout."""
    icon_destination = destination / "Resources" / "FreeCAD Icons"
    icon_destination.mkdir(parents=True, exist_ok=True)
    sources = freecad_icon_sources(freecad_source)
    # Keep FusionMyFreeCAD's own icons: they are not in the source tree, so the
    # prune below would delete every one of them.
    keep = {"{}.svg".format(name) for name in sources} | {
        "{}.svg".format(name) for name in authored_icon_names()
    }
    for path in icon_destination.iterdir():
        if path.is_file() and path.name not in keep:
            path.unlink()
    for name, source_icon in sources.items():
        (icon_destination / "{}.svg".format(name)).write_bytes(canonical_svg_bytes(source_icon))
    return sources


def sync_ribbon(freecad_source: Path) -> dict[str, Path]:
    source = SOURCE_ROOT / "FreeCAD-Ribbon"
    destination = DESTINATION_ROOT / "FreeCAD-Ribbon"
    for name in (
        *RIBBON_MODULES,
        "CreateStructure.txt",
        "Toolbar name mapping.json",
        "LICENSE",
        "package.xml",
    ):
        copy_file(source, destination, name)

    for relative in (
        "Resources/icons",
        "Resources/packages",
        "Resources/stylesheets",
        "Resources/ui",
    ):
        copy_tree(source, destination, relative)

    translations = source / "translations"
    for translation in translations.glob("*.qm"):
        copy_file(source, destination, translation.relative_to(source))

    # Ribbon asks its local command-icon directory before every source workbench is
    # guaranteed to have registered Qt resources. Copy only the icons used by the
    # current layout, sourced from FreeCAD's official repository checkout.
    return sync_layout_icons(freecad_source, destination)


def write_source_icon_manifest(freecad_source: Path, sources: dict[str, Path]) -> None:
    """Record the official source file and content hash behind every bundled icon."""
    freecad_source = freecad_source.resolve()
    icons = {
        name: {
            "path": source.relative_to(freecad_source).as_posix(),
            "sha256": hashlib.sha256(canonical_svg_bytes(source)).hexdigest(),
        }
        for name, source in sorted(sources.items())
    }
    ICON_SOURCE_MANIFEST.write_text(
        json.dumps(
            {
                "_comment": (
                    "Generated by tools/sync_bundled_addons.py from an official "
                    "FreeCAD source checkout."
                ),
                "icons": icons,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def sync_search() -> None:
    source = SOURCE_ROOT / "SearchBar"
    destination = DESTINATION_ROOT / "SearchBar"
    for name in (*SEARCH_MODULES, "LICENSE", "package.xml"):
        copy_file(source, destination, name)
    copy_tree(source, destination, "Resources/Icons")
    copy_file(source, destination, "Resources/ui/PreferencesUI_SearchBar.ui")


def strip_python_dependencies() -> list[str]:
    """Drop declared third-party Python requirements the local patches removed.

    Bundling exists so installation needs nothing from PyPI. Upstream metadata still
    advertises lxml, so re-applying this mechanically keeps a refresh from quietly
    reintroducing an install-time requirement the runtime no longer has.
    """
    pattern = re.compile(
        r"[ \t]*<depend type=\"python\"(?![^>]*optional=\"true\")>(?P<name>[^<]+)</depend>\r?\n"
    )
    removed = []
    for addon in ("FreeCAD-Ribbon", "SearchBar"):
        path = DESTINATION_ROOT / addon / "package.xml"
        text = path.read_text(encoding="utf-8")
        removed.extend(f"{addon}: {match.group('name')}" for match in pattern.finditer(text))
        stripped = pattern.sub("", text)
        if stripped != text:
            path.write_text(stripped, encoding="utf-8", newline="\n")
    return removed


# Upstream puts the panel's overflow drawer behind a small icon in the title bar.
# FusionMyFreeCAD makes the whole title open it, which is how a Fusion section
# header behaves. Each pair is (anchor, replacement); a missing anchor raises so an
# upstream refactor surfaces here instead of silently dropping the behaviour.
PANEL_TITLE_DRAWER_PATCH = (
    (
        "class RibbonPanelTitle(QLabel):\n"
        '    """Widget to display the title of a panel."""\n'
        "    \n"
        "    pass\n",
        "class RibbonPanelTitle(QLabel):\n"
        '    """Widget to display the title of a panel.\n'
        "\n"
        "    FusionMyFreeCAD local change: the title doubles as the trigger for the\n"
        "    panel's overflow drawer, so the whole header reads as the dropdown it\n"
        "    already is rather than only the small icon beside it.\n"
        '    """\n'
        "\n"
        "    clicked = Signal()\n"
        "\n"
        "    #: Set by RibbonPanel to report whether the drawer can currently open.\n"
        "    #: A plain callable rather than a signal so the cursor can be decided at\n"
        "    #: hover time; FCBinding shows and hides the option button directly, so\n"
        "    #: anything cached at construction time would go stale.\n"
        "    drawerAvailable: Callable[[], bool] = staticmethod(lambda: False)\n"
        "\n"
        "    def mousePressEvent(self, event):\n"
        "        if event.button() == Qt.MouseButton.LeftButton and self.drawerAvailable():\n"
        "            self.clicked.emit()\n"
        "            event.accept()\n"
        "            return\n"
        "        super().mousePressEvent(event)\n"
        "\n"
        "    def enterEvent(self, event):\n"
        "        self.setCursor(\n"
        "            Qt.CursorShape.PointingHandCursor\n"
        "            if self.drawerAvailable()\n"
        "            else Qt.CursorShape.ArrowCursor\n"
        "        )\n"
        "        super().enterEvent(event)\n",
    ),
    (
        "        self._titleLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)\n"
        "        self._titleLayout.addWidget(self._titleLabel, 0)\n",
        "        self._titleLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)\n"
        "        self._titleLabel.drawerAvailable = self.isDrawerAvailable\n"
        "        self._titleLabel.clicked.connect(self.openDrawer)\n"
        "        self._titleLayout.addWidget(self._titleLabel, 0)\n",
    ),
    (
        "    def panelOptionButton(self) -> RibbonPanelOptionButton:\n",
        "    def isDrawerAvailable(self) -> bool:\n"
        '        """Whether clicking the title can open anything.\n'
        "\n"
        "        A panel built without an option button has no drawer, so the title stays\n"
        "        inert there instead of swallowing the click.\n"
        "\n"
        "        Visibility is deliberately not part of this. FCBinding only calls\n"
        "        show() on the option button when a command actually overflows, but it\n"
        "        populates the menu from the panel's whole command inventory on every\n"
        "        panel. Requiring the button to be visible therefore left the titles of\n"
        '        panels that happen to fit doing nothing, which is not what "every panel\n'
        '        has a dropdown" means.\n'
        "\n"
        "        Reads __dict__ directly: __getattr__ below raises AssertionError for any\n"
        "        name that is not add[Small|Medium|Large]*, and getattr's default only\n"
        "        swallows AttributeError.\n"
        '        """\n'
        '        option = self.__dict__.get("_panelOption")\n'
        "        if option is None:\n"
        "            return False\n"
        "        menu = option.menu()\n"
        "        return menu is not None and len(menu.actions()) > 0\n"
        "\n"
        "    def openDrawer(self):\n"
        '        """Open the panel\'s overflow drawer, aligned with the panel itself.\n'
        "\n"
        "        Not showMenu(): that anchors to the option button at the right end of\n"
        "        the title bar, so a menu opened by clicking the title appeared off to\n"
        "        one side of the section it belongs to.\n"
        '        """\n'
        "        if self.isDrawerAvailable():\n"
        "            popup_menu_at(self._panelOption.menu(), self)\n"
        "\n"
        "    def panelOptionButton(self) -> RibbonPanelOptionButton:\n",
    ),
)

# Files FusionMyFreeCAD adds that upstream never ships. main() clears the whole
# bundled tree before copying, so these are carried across that wipe rather than
# kept as a second tracked copy somewhere else.
FMF_OWNED_FILES = (
    ("FreeCAD-Ribbon", "Resources", "packages", "pyqtribbon_local", "fmf_layout_math.py"),
    ("FreeCAD-Ribbon", "Resources", "packages", "pyqtribbon_local", "fmf_widgets.py"),
    ("FreeCAD-Ribbon", "fmf_ribbon_support.py"),
)

# Hooks into upstream's own modules for the draggable panel dividers. The widget
# itself lives in fmf_widgets.py, so what has to survive a refresh here is only
# the wiring.
PANEL_DIVIDER_PATCH = (
    (
        "from .separator import RibbonSeparator, RibbonVerticalSeparator\n",
        "from .fmf_widgets import DraggablePanelSeparator, popup_menu_at\n"
        "from .separator import RibbonSeparator, RibbonVerticalSeparator\n",
    ),
    (
        "    # Panel options signal\n    panelOptionClicked = Signal(bool)\n",
        "    # Panel options signal\n"
        "    panelOptionClicked = Signal(bool)\n"
        "    # FusionMyFreeCAD local change: emitted as (panel, pixel delta) when the user\n"
        "    # finishes dragging this panel's divider. FCBinding turns the delta into a\n"
        "    # column budget for this panel alone.\n"
        "    panelResizeRequested = Signal(object, int)\n",
    ),
    (
        "        # Add a separator\n        self._separator = RibbonVerticalSeparator(width=3)\n",
        "        # Add a separator. FusionMyFreeCAD local change: draggable, so a panel's\n"
        "        # width is the user's to set rather than a single global column budget.\n"
        "        self._separator = DraggablePanelSeparator(width=3)\n"
        "        self._separator.dividerReleased.connect(\n"
        "            lambda delta: self.panelResizeRequested.emit(self, delta)\n"
        "        )\n",
    ),
)

# Hooks in FCBinding for the draggable dividers. The arithmetic and the rebuild
# live in fmf_widgets.resize_panel, so what must survive a refresh here is four
# short edits rather than a method body.
# Upstream applies a panel's overflow list before it considers how much room
# the panel has, so a section dragged wider stayed sparse with its remaining
# commands hidden. This lets a section the user sized fill the space it was
# given.
# Upstream declares an ActivateButtons argument on CreatePanel and then calls
# activateButtons() unconditionally, force-enabling every button in the window
# on any rebuild. That is right while arranging the ribbon and wrong afterwards:
# a divider drag left unavailable commands looking usable.
FCBINDING_ACTIVATE_PATCH = (
    (
        # The comment alone appears thirteen times upstream; the spacer line
        # above it is what identifies the call inside CreatePanel.
        "        panel.addWidget(spacer, rowSpan=6)\n"
        "\n"
        "        # Enable all buttons, so you can access them with a right click\n"
        "        self.activateButtons()\n",
        "        panel.addWidget(spacer, rowSpan=6)\n"
        "\n"
        "        # Enable all buttons, so you can access them with a right click.\n"
        "        # FusionMyFreeCAD local change: honour the ActivateButtons argument,\n"
        "        # which upstream declares and then ignores. Force-enabling every button\n"
        "        # in the window is right while arranging the ribbon, where a disabled\n"
        "        # button cannot be right-clicked, but it is wrong after an ordinary\n"
        "        # rebuild: a divider drag left commands that are genuinely unavailable\n"
        "        # looking as though they could be used.\n"
        "        if ActivateButtons is True:\n"
        "            self.activateButtons()\n",
    ),
)

FCBINDING_OVERFLOW_PATCH = (
    (
        "                if (\n"
        "                    CommandName in explicitOverflow\n"
        "                    and not responsiveVisible\n"
        "                    and ignoreColumnLimit is False\n"
        "                ):\n",
        "                # FusionMyFreeCAD local change: once the user has sized a\n"
        "                # section by dragging its divider, its width is the only thing\n"
        "                # that decides what it shows. The shipped overflow list still\n"
        "                # governs every section nobody has touched.\n"
        "                #\n"
        "                # Consulting both left commands stuck in the drawer: the list\n"
        "                # sent them there regardless of room, so shrinking a section\n"
        "                # and widening it again never brought them back, and the\n"
        "                # section stayed wider than the icons left in it.\n"
        "                if (\n"
        "                    CommandName in explicitOverflow\n"
        "                    and not responsiveVisible\n"
        "                    and ignoreColumnLimit is False\n"
        "                    and not fmfHasUserWidth\n"
        "                ):\n",
    ),
)


FCBINDING_DIVIDER_PATCH = (
    (
        "from pyqtribbon_local.separator import RibbonSeparator\n",
        "from pyqtribbon_local.separator import RibbonSeparator\n"
        "from pyqtribbon_local import fmf_widgets\n",
    ),
    (
        "    def _resetOnePanel(self, panel):\n",
        "    def _onPanelResized(self, panel, deltaX: int):\n"
        '        """FusionMyFreeCAD local change: a divider drag resizes one panel."""\n'
        "        fmf_widgets.resize_panel(self, panel, deltaX)\n"
        "\n"
        "    def _resetOnePanel(self, panel):\n",
    ),
    (
        "        # Set the maximum columns\n"
        "        maxColumns = Parameters.MAX_COLUMN_PANELS\n"
        "\n"
        "        # Define an action list of the actions that are beyond the maximum columns\n",
        "        # Define an action list of the actions that are beyond the maximum columns\n",
    ),
    (
        '        explicitPanelMenu = set(panelDefinition.get("panelMenu", []))\n',
        "        # Set the maximum columns. FusionMyFreeCAD local change: a panel whose\n"
        "        # divider the user has dragged carries its own budget; everything else\n"
        "        # still follows the global preference. The budget is only honoured\n"
        "        # alongside a stored width, so column budgets written by an earlier\n"
        "        # build -- which derived them from the contents rather than from the\n"
        "        # space -- go inert instead of truncating a panel nobody resized.\n"
        "        maxColumns = Parameters.MAX_COLUMN_PANELS\n"
        "        try:\n"
        "            if (\n"
        '                panelDefinition.get("minWidth") is not None\n'
        '                and panelDefinition.get("maxColumns") is not None\n'
        "            ):\n"
        '                maxColumns = max(1, int(panelDefinition["maxColumns"]))\n'
        "        except (TypeError, ValueError):\n"
        "            pass\n"
        "        # Whether this section carries a width the user dragged it to. Only\n"
        "        # then may commands be pulled back out of its drawer to fill the space.\n"
        '        fmfHasUserWidth = panelDefinition.get("minWidth") is not None\n'
        '        explicitPanelMenu = set(panelDefinition.get("panelMenu", []))\n',
    ),
    (
        "        # Set the font for the panel title\n        Font = QFont()\n",
        "        # FusionMyFreeCAD local change: let this panel's divider resize it.\n"
        "        # setPanelProperties runs for every panel, including rebuilt ones, so the\n"
        "        # connection is guarded rather than made unconditionally. The guard reads\n"
        "        # __dict__ directly because RibbonPanel.__getattr__ raises AssertionError\n"
        "        # for any name that is not add[Small|Medium|Large]*, and getattr's default\n"
        "        # only swallows AttributeError.\n"
        '        if panel.__dict__.get("_fmfResizeConnected") is not True:\n'
        "            try:\n"
        "                panel.panelResizeRequested.connect(self._onPanelResized)\n"
        "                panel._fmfResizeConnected = True\n"
        "            except (AttributeError, TypeError):\n"
        "                pass\n"
        "        # A width the user dragged out has to be re-claimed every time the panel\n"
        "        # is built, or it is lost on the next workbench switch.\n"
        "        fmf_widgets.apply_panel_width(self, panel)\n"
        "\n"
        "        # Set the font for the panel title\n"
        "        Font = QFont()\n",
    ),
)

# Hooks in CustomWidgets so every icon drag runs through fmf_ribbon_support.
# Upstream repeats the same handler five times, hence the counts.
CUSTOM_WIDGETS_DRAG_PATCH = (
    (
        "import Parameters_Ribbon\n",
        "import Parameters_Ribbon\nimport fmf_ribbon_support  # FusionMyFreeCAD local change\n",
    ),
    # The deeper-indented site first: the shallower anchor below is a substring
    # of this line, so replacing that one first would corrupt this one.
    (
        "                if drag is not None:\n"
        "                    drag.exec_(Qt.DropAction.MoveAction)\n"
        "            except Exception as e:\n"
        "                print(e)\n",
        "                if drag is not None:\n"
        "                    fmf_ribbon_support.start_drag(drag)\n"
        "            except Exception as error:\n"
        "                fmf_ribbon_support.report_drag_failure(error)\n",
    ),
    (
        "                drag.exec_(Qt.DropAction.MoveAction)\n"
        "            except Exception as e:\n"
        "                print(e)\n",
        "                fmf_ribbon_support.start_drag(drag)\n"
        "            except Exception as error:\n"
        "                fmf_ribbon_support.report_drag_failure(error)\n",
        4,
    ),
)

LOCAL_PATCHES = (
    (
        ("FreeCAD-Ribbon", "Resources", "packages", "pyqtribbon_local", "panel.py"),
        PANEL_TITLE_DRAWER_PATCH + PANEL_DIVIDER_PATCH,
    ),
    (
        ("FreeCAD-Ribbon", "FCBinding.py"),
        FCBINDING_DIVIDER_PATCH + FCBINDING_OVERFLOW_PATCH + FCBINDING_ACTIVATE_PATCH,
    ),
    (
        ("FreeCAD-Ribbon", "CustomWidgets.py"),
        CUSTOM_WIDGETS_DRAG_PATCH,
    ),
)


def preserve_fmf_files() -> dict[tuple, bytes]:
    """Read the files FusionMyFreeCAD owns before the bundled tree is replaced."""
    saved = {}
    for parts in FMF_OWNED_FILES:
        path = DESTINATION_ROOT.joinpath(*parts)
        if not path.is_file():
            raise RuntimeError(
                "{} is missing. It is FusionMyFreeCAD's own file and cannot be "
                "recovered from upstream; restore it from git before syncing.".format(path)
            )
        saved[parts] = path.read_bytes()
    return saved


def restore_fmf_files(saved: dict[tuple, bytes]) -> None:
    """Put FusionMyFreeCAD's own files back after the bundled tree is replaced."""
    for parts, content in saved.items():
        path = DESTINATION_ROOT.joinpath(*parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


def patch_marker(anchor: str, replacement: str) -> str | None:
    """The first whole line a patch introduces, or None when it only removes.

    Substring tests are not safe here. Upstream repeats the same drag handler at
    two indentation levels, so the shallower patch's text is a substring of the
    deeper one's, and checking `replacement in text` let an applied patch mask an
    unapplied one -- four of the five drag sites were silently skipped that way.
    Some patches also insert around their anchor rather than consuming it, so the
    anchor surviving proves nothing either way. Comparing a whole line against
    the file's lines avoids both traps.
    """
    anchor_lines = set(anchor.splitlines(keepends=True))
    for line in replacement.splitlines(keepends=True):
        if line not in anchor_lines and line.strip():
            return line
    return None


def patch_is_applied(text: str, lines: list[str], anchor: str, replacement: str) -> bool:
    """Whether this patch has already been made to `text`."""
    marker = patch_marker(anchor, replacement)
    if marker is not None:
        return marker in lines
    # A patch that only deletes introduces nothing to look for, so the absence
    # of what it removes is the only evidence available.
    return anchor not in text


def apply_local_patches() -> list[str]:
    """Re-apply every hook FusionMyFreeCAD adds to upstream's own modules.

    Each patch is skipped when it is already applied, so running the sync twice
    is harmless. A missing anchor raises rather than silently shipping a ribbon
    with the behaviour quietly removed.
    """
    applied = []
    for parts, patches in LOCAL_PATCHES:
        path = DESTINATION_ROOT.joinpath(*parts)
        text = path.read_text(encoding="utf-8")
        for patch in patches:
            # A patch is (anchor, replacement), or (anchor, replacement, count)
            # where upstream repeats the same code, as the drag handlers do.
            anchor, replacement = patch[0], patch[1]
            expected = patch[2] if len(patch) > 2 else 1
            if patch_is_applied(text, text.splitlines(keepends=True), anchor, replacement):
                continue
            if text.count(anchor) != expected:
                raise RuntimeError(
                    "{} holds {} copies of a FusionMyFreeCAD anchor, expected {}. "
                    "Re-apply it by hand, then update LOCAL_PATCHES:\n{}".format(
                        path.name, text.count(anchor), expected, anchor
                    )
                )
            text = text.replace(anchor, replacement)
            applied.append("{}: {}".format(path.name, anchor.strip().splitlines()[0]))
        path.write_text(text, encoding="utf-8", newline="\n")
    return applied


def assert_minimal_freecad_icons() -> None:
    """Fail unless the bundle contains exactly the icons used by the layout."""
    directory = DESTINATION_ROOT / "FreeCAD-Ribbon" / "Resources" / "FreeCAD Icons"
    bundled = {path.stem for path in directory.iterdir() if path.is_file()}
    required = configured_icon_names()
    if bundled != required:
        raise RuntimeError(
            "Bundled Ribbon icons differ from the layout (missing={}, extra={}).".format(
                sorted(required - bundled), sorted(bundled - required)
            )
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--freecad-source",
        type=Path,
        default=ROOT.parent / "FreeCAD",
        help="Official FreeCAD source checkout (default: sibling ../FreeCAD)",
    )
    parser.add_argument(
        "--icons-only",
        action="store_true",
        help="Refresh the curated command icons without replacing the bundled add-ons",
    )
    arguments = parser.parse_args()
    destination = DESTINATION_ROOT.resolve()
    expected = (ROOT / "bundled-addons").resolve()
    if destination != expected or destination.parent != ROOT.resolve():
        raise RuntimeError(f"Refusing to replace unexpected destination: {destination}")
    if arguments.icons_only:
        icon_sources = sync_layout_icons(
            arguments.freecad_source, DESTINATION_ROOT / "FreeCAD-Ribbon"
        )
        write_source_icon_manifest(arguments.freecad_source, icon_sources)
        assert_minimal_freecad_icons()
        print("Refreshed {} curated FreeCAD icons.".format(len(icon_sources)))
        return
    preserved = preserve_fmf_files()
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir()
    icon_sources = sync_ribbon(arguments.freecad_source)
    write_source_icon_manifest(arguments.freecad_source, icon_sources)
    sync_search()
    removed = strip_python_dependencies()
    restore_fmf_files(preserved)
    patched = apply_local_patches()
    assert_minimal_freecad_icons()
    file_count = sum(1 for path in destination.rglob("*") if path.is_file())
    byte_count = sum(path.stat().st_size for path in destination.rglob("*") if path.is_file())
    print(f"Bundled {file_count} runtime files ({byte_count / 1024 / 1024:.2f} MiB).")
    print(f"Stripped Python dependencies: {removed or 'none'}")
    print(f"Re-applied local UI patches: {len(patched)} ({len(preserved)} owned files restored)")
    print(
        "FreeCAD command icons: {} layout icons copied from {}.".format(
            len(configured_icon_names()), arguments.freecad_source.resolve()
        )
    )


if __name__ == "__main__":
    main()
