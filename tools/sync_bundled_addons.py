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
ICON_SOURCE_MANIFEST = ROOT / "Resources" / "FMF" / "source-icons.json"

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
    """Every icon the shipped layout references, FMF's own included."""
    layout_path = ROOT / "Resources" / "FMF" / "layout-v3.json"
    layout = json.loads(layout_path.read_text(encoding="utf-8"))
    return {
        Path(entry[4]).stem
        for panels in layout["workbenches"].values()
        for panel in panels
        for entry in panel["commands"] + panel.get("overflow", [])
    }


def authored_icon_names() -> set[str]:
    """The icons FMF draws itself.

    These have no counterpart in FreeCAD's source tree, so looking for one
    fails the whole sync -- which is what stopped the icon refresh working at
    all once the first authored icon was added. They also have to survive the
    prune in sync_layout_icons, which otherwise deletes anything it did not
    just copy from source.
    """
    manifest_path = ROOT / "Resources" / "FMF" / "layout-manifest.json"
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
    # Keep FMF's own icons: they are not in the source tree, so the
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
# FMF makes the whole title open it, which is how a Fusion section
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
        "    FMF local change: the title doubles as the trigger for the\n"
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

# Files FMF adds that upstream never ships. main() clears the whole
# bundled tree before copying, so these are carried across that wipe rather than
# kept as a second tracked copy somewhere else.
FMF_OWNED_FILES = (
    ("FreeCAD-Ribbon", "Resources", "packages", "pyqtribbon_local", "fmf_layout_math.py"),
    ("FreeCAD-Ribbon", "Resources", "packages", "pyqtribbon_local", "fmf_widgets.py"),
    ("FreeCAD-Ribbon", "fmf_ribbon_support.py"),
    *(
        ("FreeCAD-Ribbon", "Resources", "FreeCAD Icons", "{}.svg".format(name))
        for name in sorted(authored_icon_names())
    ),
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
        "    # FMF local change: emitted as (panel, pixel delta) when the user\n"
        "    # finishes dragging this panel's divider. FCBinding turns the delta into a\n"
        "    # column budget for this panel alone.\n"
        "    panelResizeRequested = Signal(object, int)\n",
    ),
    (
        "        # Add a separator\n        self._separator = RibbonVerticalSeparator(width=3)\n",
        "        # Add a separator. FMF local change: draggable, so a panel's\n"
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
        "        # FMF local change: honour the ActivateButtons argument,\n"
        "        # which upstream declares and then ignores. Force-enabling every button\n"
        "        # in the window is right while arranging the ribbon, where a disabled\n"
        "        # button cannot be right-clicked, but it is wrong after an ordinary\n"
        "        # rebuild: a divider drag left commands that are genuinely unavailable\n"
        "        # looking as though they could be used.\n"
        "        if ActivateButtons is True:\n"
        "            self.activateButtons()\n",
    ),
)

# A dropdown can legitimately resolve to no native actions while FreeCAD is still
# loading a workbench. Upstream indexes the empty result and takes down the whole
# ribbon; FMF omits that unavailable button and lets the next rebuild discover it.
FCBINDING_EMPTY_DROPDOWN_PATCH = (
    (
        "                                    QuickAction = self.returnCustomDropDown(key, dict=Dict)\n"
        "                                    menu = QMenu()\n"
        "                                    for action in QuickAction:\n"
        "                                        if len(action) > 0:\n"
        "                                            menu.addAction(action[0])\n",
        "                                    QuickAction = self.returnCustomDropDown(key, dict=Dict)\n"
        "                                    QuickAction = [action for action in QuickAction if len(action) > 0]\n"
        "                                    if not QuickAction:\n"
        "                                        continue\n"
        "                                    menu = QMenu()\n"
        "                                    for action in QuickAction:\n"
        "                                        menu.addAction(action[0])\n",
    ),
)

FCBINDING_WORKBENCH_FAMILY_PATCH = (
    (
        "    def onWbActivated(self):        \n"
        '        if len(mw.findChildren(QDockWidget, "Ribbon")) > 0:\n',
        "    def onWbActivated(self):        \n"
        "        # The Ribbon is the application chrome for every workbench. FMF only\n"
        "        # owns the layouts of its four namespaced workbenches; selecting a stock\n"
        "        # or unrelated workbench must never blank the entire Ribbon.\n"
        "        self._setFmfChromeVisible(True)\n"
        '        if len(mw.findChildren(QDockWidget, "Ribbon")) > 0:\n',
        1,
        "        self._setFmfChromeVisible(True)\n",
    ),
    (
        "                    replacedPanel = self.currentCategory().replacePanel(objPanel, newPanel)\n",
        "                    if newPanel is None:\n"
        "                        App.Console.PrintWarning(\n"
        "                            \"FMF: could not expand panel '{}' for \"\n"
        '                            "customization; leaving the existing panel unchanged.\\n".format(\n'
        "                                objPanel.objectName()\n"
        "                            )\n"
        "                        )\n"
        "                        continue\n"
        "                    replacedPanel = self.currentCategory().replacePanel(objPanel, newPanel)\n",
    ),
)

# Workbench activation used to grow two pieces of Qt state without bound: it
# appended another tooltip rule to the tab stylesheet and replaced the
# application button's menu with a newly allocated child menu. Keep those safe
# lifecycle fixes when refreshing the vendored Ribbon sources. Do not suppress
# the apparent duplicate onWbActivated/ApplicationMenus/toolbar synchronization
# in onUserChangedWorkbench: FreeCAD's Sketcher-exit signal can precede Ribbon's
# category selection, and removing that second pass merges two workbench panels.
FCBINDING_UI_LATENCY_PATCH = (
    (
        "            if tabActivated is True:\n"
        "                self.onWbActivated()\n"
        "                self.ApplicationMenus()           \n"
        "        \n"
        "        # hide normal toolbars\n",
        "            if tabActivated is True:\n"
        "                self.onWbActivated()\n"
        "                self.ApplicationMenus()\n"
        "\n"
        "        # Do not remove this second synchronization pass as a performance\n"
        "        # shortcut. FreeCAD can emit its Sketcher-exit workbench signal before\n"
        "        # Ribbon has finished selecting the matching destination category.\n"
        "        self.onWbActivated()\n"
        "        self.ApplicationMenus()\n"
        "\n"
        "        # hide normal toolbars\n",
        1,
        "        Activate a workbench only for a genuine user-selected Ribbon tab.\n",
    ),
    (
        "        styleSheet = self.tabBar().styleSheet()\n"
        '        self.tabBar().setStyleSheet(styleSheet + """\\n QToolTip {\n'
        "                    background-color: #FFFFE1;\n"
        "                    color: black;\n"
        "                    border: black solid 1px;\n"
        "                    border-radius: 2px;\n"
        '                    }""")\n',
        "        styleSheet = self.tabBar().styleSheet()\n"
        '        tooltipStyle = """\\n QToolTip {\n'
        "                    background-color: #FFFFE1;\n"
        "                    color: black;\n"
        "                    border: black solid 1px;\n"
        "                    border-radius: 2px;\n"
        '                    }"""\n'
        "        # FMF local change: do not append another copy on every activation.\n"
        "        # Repeated copies force Qt to reparse and repolish an ever-growing sheet.\n"
        "        if tooltipStyle not in styleSheet:\n"
        "            self.tabBar().setStyleSheet(styleSheet + tooltipStyle)\n",
    ),
    (
        "    def ApplicationMenus(self):\n"
        "        # Add a file menu\n"
        "        ApplictionMenu = self.addFileMenu()\n"
        "\n"
        "        # add the menus from the menubar to the application button\n"
        "        MenuBar = mw.menuBar()\n",
        "    def ApplicationMenus(self):\n"
        "        # add the menus from the menubar to the application button\n"
        "        MenuBar = mw.menuBar()\n"
        "        menuSignature = tuple(\n"
        "            (child.objectName(), child.text()) for child in MenuBar.actions()\n"
        "        )\n"
        '        ApplictionMenu = getattr(self, "_applicationMenu", None)\n'
        "        if (\n"
        "            ApplictionMenu is not None\n"
        '            and menuSignature == getattr(self, "_applicationMenuSignature", None)\n'
        "        ):\n"
        "            return\n"
        "        if ApplictionMenu is None:\n"
        "            ApplictionMenu = self.addFileMenu()\n"
        "            self._applicationMenu = ApplictionMenu\n"
        "        else:\n"
        "            ApplictionMenu.clear()\n"
        "        self._applicationMenuSignature = menuSignature\n",
    ),
)

# Focus changes must not mutate top-level window or dock structure. Those writes
# force Windows/Qt relayout work every time the user returns to FreeCAD.
FCBINDING_FOCUS_PATCH = (
    (
        "        if event.type() == QEvent.Type.WindowActivate or event.type() == QEvent.Type.WindowDeactivate:\n"
        "            mw = Gui.getMainWindow()\n"
        '            DockWidget_Ribbon: QDockWidget = mw.findChild(QDockWidget, "Ribbon")\n'
        "            if DockWidget_Ribbon is not None:\n"
        '                RibbonBar: ModernMenu = mw.findChild(ModernMenu, "Ribbon")\n'
        "                if DockWidget_Ribbon.isFloating() is False:\n"
        "                    try:\n"
        "                        DockWidget_Ribbon.setTitleBarWidget(QWidget())\n"
        "                    except Exception:\n"
        "                        pass       \n",
        "",
    ),
    (
        "        if event.type() == QEvent.Type.ApplicationActivated:\n"
        "            mw = Gui.getMainWindow()\n"
        "            mw.setWindowState(Qt.WindowState.WindowMaximized)\n"
        "            Style = mw.style()\n"
        '            RibbonBar: ModernMenu = mw.findChild(ModernMenu, "Ribbon")\n'
        "            RestoreButton: QToolButton = RibbonBar.rightToolBar().findChildren(\n"
        '                QToolButton, "RestoreButton"\n'
        "            )[0]\n"
        "            try:\n"
        "                RestoreButton.setIcon(\n"
        "                    Style.standardIcon(QStyle.StandardPixmap.SP_TitleBarNormalButton)\n"
        "                )\n"
        "            except Exception:\n"
        "                pass\n"
        "                                            \n"
        "            return QObject.eventFilter(self, obj, event)\n",
        "",
    ),
)


FCBINDING_HOST_ISOLATION_PATCH = (
    (
        "            if self.wbNameMapping[tabName] is not None:                \n",
        "            if self.wbNameMapping[tabName] is not None:\n",
        1,
        "        Activate a workbench only for a genuine user-selected Ribbon tab.\n",
    ),
    (
        "        self.hideClassicToolbars()\n        \n        if self.CustomizeEnabled:\n",
        "        self.hideClassicToolbars()\n\n        if self.CustomizeEnabled:\n",
        2,
    ),
    (
        "            self.activateButtons()\n"
        "        \n"
        '        # Emit a signal when switching to a new tab. Used to update the "addcommands" panel\n',
        "            self.activateButtons()\n"
        "\n"
        '        # Emit a signal when switching to a new tab. Used to update the "addcommands" panel\n',
    ),
    (
        "        self.CreateMenus()  # Create the menus\n"
        "        self.createModernMenu()  # Create the ribbon\n",
        "        self.CreateMenus()  # Create the menus\n"
        "        self._fmfBuildingMenu = True\n"
        "        self.createModernMenu()  # Create the ribbon\n"
        "        self._fmfBuildingMenu = False\n",
    ),
    (
        "    def onUserChangedWorkbench(self, tabActivated=True):\n"
        '        """\n'
        "        Import selected workbench toolbars to ModernMenu section.\n"
        '        """                \n',
        "    def onUserChangedWorkbench(self, tabActivated=True):\n"
        '        """\n'
        "        Import selected workbench toolbars to ModernMenu section.\n"
        '        """                \n'
        '        if getattr(self, "_fmfBuildingMenu", False):\n'
        "            return\n",
        1,
        "        Activate a workbench only for a genuine user-selected Ribbon tab.\n",
    ),
    (
        "            LatestVersion = StandardFunctions.ReturnXML_Value_Git(\n"
        "                User=User, Repository=Repo, Branch=Branch, File=File, ElementName=ElementName, attribKey=attribKey, attribValue=attribValue, host=host\n"
        "            )\n",
        "            # FMF delegates updates to FreeCAD's Addon Manager. Never put DNS,\n"
        "            # proxy, TLS, or repository availability on GUI-thread startup.\n"
        "            LatestVersion = None\n",
    ),
    (
        "        for Wb in self.WBtoLoadFirst:\n",
        '        for Wb in ([] if os.environ.get("FREECAD_RIBBON_CACHE_WORKBENCHES") else self.WBtoLoadFirst):\n',
    ),
    (
        '                            and CommandItem[1] != "Standard"\n'
        "                        ):\n"
        "                            # Activate the workbench if not loaded\n",
        '                            and CommandItem[1] != "Standard"\n'
        '                            and not os.environ.get("FREECAD_RIBBON_CACHE_WORKBENCHES")\n'
        "                        ):\n"
        "                            # Activate the workbench if not loaded\n",
        1,
    ),
    (
        '                        and CommandItem[1] != "Standard"\n'
        "                    ):\n"
        "                        # Activate the workbench if not loaded\n",
        '                        and CommandItem[1] != "Standard"\n'
        '                        and not os.environ.get("FREECAD_RIBBON_CACHE_WORKBENCHES")\n'
        "                    ):\n"
        "                        # Activate the workbench if not loaded\n",
        1,
    ),
    (
        "    def CreateButtonFromCommand(self, CommandName: str, ActivateWorkBench = True, Dict=ribbonStructure):\n"
        '        if CommandName.endswith("_ddb") is False:\n',
        "    def CreateButtonFromCommand(self, CommandName: str, ActivateWorkBench = True, Dict=ribbonStructure):\n"
        '        if os.environ.get("FREECAD_RIBBON_CACHE_WORKBENCHES"):\n'
        "            ActivateWorkBench = False\n"
        '        if CommandName.endswith("_ddb") is False:\n',
    ),
    (
        "                    ActivateWorkbench = True,\n"
        "                    ):\n"
        "\n"
        "        if UpdateDict is True:\n",
        "                    ActivateWorkbench = True,\n"
        "                    ):\n"
        "\n"
        '        if os.environ.get("FREECAD_RIBBON_CACHE_WORKBENCHES"):\n'
        "            ActivateWorkbench = False\n"
        "\n"
        "        if UpdateDict is True:\n",
    ),
    (
        "                if len(QuickAction) == 0:\n",
        '                if len(QuickAction) == 0 and not os.environ.get("FREECAD_RIBBON_CACHE_WORKBENCHES"):\n',
    ),
)


FCBINDING_ACTION_BINDING_PATCH = (
    (
        "    def onUserChangedWorkbench(self, tabActivated=True):\n",
        "    def _fmfAuthoritativeWorkbenchActive(self):\n"
        "        enabled = App.ParamGet(\n"
        '            "User parameter:BaseApp/Preferences/Mod/FMF"\n'
        '        ).GetBool("Enabled", True)\n'
        "        if not enabled:\n"
        "            return False\n"
        "        try:\n"
        "            active = Gui.activeWorkbench().name()\n"
        "        except Exception:\n"
        "            return False\n"
        '        return active in self.ribbonStructure.get("authoritativeWorkbenches", [])\n'
        "\n"
        "    def _fmfBindNativeAction(self, commandName, button):\n"
        '        """Attach FMF lifecycle tracking without replacing QAction invocation."""\n'
        "        if button is None or not self._fmfAuthoritativeWorkbenchActive():\n"
        "            return button\n"
        "        try:\n"
        "            import fmf_bootstrap\n"
        "\n"
        "            fmf_bootstrap.bind_ribbon_button(commandName, button)\n"
        "        except (ImportError, AttributeError, RuntimeError, TypeError) as error:\n"
        "            if Parameters.DEBUG_MODE is True:\n"
        "                StandardFunctions.Print(\n"
        '                    "FMF action binding failed for {}: {}".format(commandName, error),\n'
        '                    "Warning",\n'
        "                )\n"
        "        return button\n"
        "\n"
        "    def _setFmfChromeVisible(self, visible):\n"
        '        """Keep the vendored ribbon scoped to FMF-owned workbenches."""\n'
        '        dock = mw.findChild(QDockWidget, "Ribbon")\n'
        "        if dock is not None:\n"
        "            dock.setVisible(visible)\n"
        "        mw.menuBar().setVisible(not visible)\n"
        "\n"
        "    def onUserChangedWorkbench(self, tabActivated=True):\n",
    ),
    (
        "                    return Button\n\n"
        "                # If the command is None, it is probally a command from a FreeCAD dropdow button.\n",
        "                    return self._fmfBindNativeAction(CommandName, Button)\n\n"
        "                # If the command is None, it is probally a command from a FreeCAD dropdow button.\n",
    ),
    (
        "                                                        return Button\n"
        "                    \n"
        "            except Exception as e:\n",
        "                                                        return self._fmfBindNativeAction(\n"
        "                                                            CommandName, Button\n"
        "                                                        )\n"
        "                    \n"
        "            except Exception as e:\n",
    ),
    (
        "                return Button\n            except Exception as e:\n",
        "                return self._fmfBindNativeAction(CommandName, Button)\n"
        "            except Exception as e:\n",
    ),
)


SEARCHBAR_DISCOVERY_PATCH = (
    (
        "    activeWorkbench = Gui.activeWorkbench().name()\n\n",
        "    activeWorkbench = Gui.activeWorkbench().name()\n\n"
        '    if os.environ.get("FREECAD_RIBBON_CACHE_WORKBENCHES"):\n'
        '        print("SearchBox: using commands already registered by FreeCAD; workbenches were not activated for discovery.")\n'
        "        return\n\n",
    ),
)


SEARCHBAR_EVENT_FILTER_PATCH = (
    (
        "tbr = None\n",
        "tbr = None\n"
        "_event_filter = None\n"
        "_event_filter_targets = []\n"
        "_workbench_signal_connected = False\n",
    ),
    (
        "        global wax, sea, tbr, ChangeDialogLoaded\n",
        "        global wax, sea, tbr, ChangeDialogLoaded, _event_filter\n",
    ),
    (
        "                mw.installEventFilter(EventInspector_SB(mw))\n"
        "                mw.centralWidget().installEventFilter(EventInspector_SB(mw))\n"
        "                vp.installEventFilter(EventInspector_SB(mw))\n"
        "                for child in vp.children():\n"
        "                    child.installEventFilter(EventInspector_SB(mw))\n",
        "                if _event_filter is None:\n"
        "                    _event_filter = EventInspector_SB(mw)\n"
        "                for target in (mw, mw.centralWidget(), vp, *vp.children()):\n"
        "                    if target not in _event_filter_targets:\n"
        "                        target.installEventFilter(_event_filter)\n"
        "                        _event_filter_targets.append(target)\n",
    ),
    (
        "SearchBar.addToolSearchBox()\n"
        "Gui.getMainWindow().workbenchActivated.connect(SearchBar.addToolSearchBox)\n",
        "def install():\n"
        '    """Install one shared event filter and one coordinated transition phase."""\n'
        "    global _workbench_signal_connected\n"
        "    SearchBar.addToolSearchBox()\n"
        "    if not _workbench_signal_connected:\n"
        "        import fmf_transitions\n"
        "\n"
        "        fmf_transitions.register_phase(\n"
        '            "searchbar", lambda _name: SearchBar.addToolSearchBox(), order=40\n'
        "        )\n"
        "        _workbench_signal_connected = True\n"
        "\n\n"
        "def uninstall():\n"
        '    """Release SearchBar\'s long-lived callbacks and event filters."""\n'
        "    global _event_filter, _workbench_signal_connected\n"
        "    if _workbench_signal_connected:\n"
        "        try:\n"
        "            import fmf_transitions\n"
        "\n"
        '            fmf_transitions.unregister_phase("searchbar")\n'
        "        except Exception:\n"
        "            pass\n"
        "        _workbench_signal_connected = False\n"
        "    if _event_filter is not None:\n"
        "        for target in tuple(_event_filter_targets):\n"
        "            try:\n"
        "                target.removeEventFilter(_event_filter)\n"
        "            except RuntimeError:\n"
        "                pass\n"
        "        _event_filter_targets.clear()\n"
        "        _event_filter.deleteLater()\n"
        "        _event_filter = None\n"
        "\n\n"
        "install()\n",
    ),
)


RIBBON_INIT_TRANSITION_PATCH = (
    (
        "        mw.workbenchActivated.connect(FCBinding.run)\n",
        "        import fmf_transitions\n"
        "\n"
        '        fmf_transitions.register_phase("ribbon-initialize", FCBinding.run, order=10)\n',
        2,
    ),
)


FCBINDING_TRANSITION_PATCH = (
    (
        "    def connectSignals(self):\n"
        "        self.tabBar().currentChanged.connect(self.onUserChangedWorkbench)\n"
        "        mw.workbenchActivated.connect(self.onWbActivated)\n"
        "        return\n",
        "    def connectSignals(self):\n"
        "        self.tabBar().currentChanged.connect(self.onUserChangedWorkbench)\n"
        "        import fmf_transitions\n"
        "\n"
        "        self._fmfTransitionCallback = self.onWbActivated\n"
        "        fmf_transitions.register_phase(\n"
        '            "ribbon", self._fmfTransitionCallback, order=20\n'
        "        )\n"
        "        return\n",
    ),
    (
        "    def disconnectSignals(self):\n"
        "        self.tabBar().currentChanged.disconnect(self.onUserChangedWorkbench)\n"
        "        mw.workbenchActivated.disconnect(self.onWbActivated)\n"
        "        return\n",
        "    def disconnectSignals(self):\n"
        "        self.tabBar().currentChanged.disconnect(self.onUserChangedWorkbench)\n"
        "        import fmf_transitions\n"
        "\n"
        "        fmf_transitions.unregister_phase(\n"
        '            "ribbon", getattr(self, "_fmfTransitionCallback", None)\n'
        "        )\n"
        "        return\n",
    ),
    (
        "            # Disable connection after activation\n"
        "            mw.workbenchActivated.disconnect(run)\n",
        "            # The one-time initializer is owned by FMF's transition coordinator.\n"
        "            import fmf_transitions\n"
        "\n"
        '            fmf_transitions.unregister_phase("ribbon-initialize")\n',
    ),
)


# Workbench signals describe host state; they must never trigger another host
# transition or rebuild live panel widgets. The Ribbon changes presentation only.
FCBINDING_PASSIVE_TRANSITION_PATCH = (
    (
        "            ribbonDock.setEnabled(True)\n"
        "            ribbonDock.setVisible(True)\n"
        "            ribbonDock.show()\n"
        "\n"
        "            return\n",
        "            ribbonDock.setEnabled(True)\n"
        "            ribbonDock.setVisible(True)\n"
        "            ribbonDock.show()\n"
        "            # Menu-construction tab signals are suppressed. Build the settled\n"
        "            # startup category once, after the Ribbon is fully attached.\n"
        "            ribbon.onWbActivated(name)\n"
        "\n"
        "            return\n",
    ),
    (
        '        super().__init__(title="")\n'
        '        self.setObjectName("Ribbon")\n',
        '        super().__init__(title="")\n'
        '        self.setObjectName("Ribbon")\n'
        "        self._fmfProgrammaticTabChange = False\n"
        "        self._fmfBuiltWorkbenches = set()\n",
    ),
    (
        "    def onUserChangedWorkbench(self, tabActivated=True):\n"
        '        """\n'
        "        Import selected workbench toolbars to ModernMenu section.\n"
        '        """                \n'
        '        if getattr(self, "_fmfBuildingMenu", False):\n'
        "            return\n"
        '        if len(mw.findChildren(QDockWidget, "Ribbon")) > 0:\n'
        "            if Parameters.AUTOHIDE_RIBBON is False:\n"
        "                self.UnfoldRibbon()\n"
        "            # else:\n"
        "            #     self.FoldRibbon(True)\n"
        "\n"
        "        index = self.tabBar().currentIndex()\n"
        "        tabName = self.tabBar().tabText(index)\n"
        "\n"
        '        if tabName is not None and tabName != "" and tabName != "test":\n'
        "            # activate selected workbench\n"
        '            tabName = tabName.replace("&", "")\n'
        "            if self.wbNameMapping[tabName] is not None:\n"
        "                Gui.activateWorkbench(self.wbNameMapping[tabName])\n"
        "\n"
        "            if tabActivated is True:\n"
        "                self.onWbActivated()\n"
        "                self.ApplicationMenus()\n"
        "\n"
        "        # Do not remove this second synchronization pass as a performance\n"
        "        # shortcut. FreeCAD can emit its Sketcher-exit workbench signal before\n"
        "        # Ribbon has finished selecting the matching destination category.\n"
        "        self.onWbActivated()\n"
        "        self.ApplicationMenus()\n"
        "\n"
        "        # hide normal toolbars\n"
        "        self.hideClassicToolbars()\n"
        "\n"
        "        if self.CustomizeEnabled:\n"
        "            self.on_Customize_Clicked()\n"
        "            # Activate all commands\n"
        "            self.activateButtons()\n"
        "\n"
        '        # Emit a signal when switching to a new tab. Used to update the "addcommands" panel\n'
        "        self.TabChanged.emit()\n"
        "        return\n",
        "    def onUserChangedWorkbench(self, tabActivated=True):\n"
        '        """\n'
        "        Activate a workbench only for a genuine user-selected Ribbon tab.\n"
        '        """                \n'
        '        if getattr(self, "_fmfBuildingMenu", False) or self._fmfProgrammaticTabChange:\n'
        "            return\n"
        "        workbenchName = self.tabBar().tabData(self.tabBar().currentIndex())\n"
        "        if workbenchName and workbenchName != Gui.activeWorkbench().name():\n"
        "            Gui.activateWorkbench(workbenchName)\n"
        "        self.hideClassicToolbars()\n"
        "        self.TabChanged.emit()\n",
    ),
    (
        "    def onWbActivated(self):        \n"
        "        # The Ribbon is the application chrome for every workbench. FMF only\n"
        "        # owns the layouts of its four namespaced workbenches; selecting a stock\n"
        "        # or unrelated workbench must never blank the entire Ribbon.\n"
        "        self._setFmfChromeVisible(True)\n",
        "    def selectFmfWorkbenchContext(self, workbenchName, buildIfNeeded=True):\n"
        '        """Show one existing category without emitting a workbench request."""\n'
        "        index = next(\n"
        "            (\n"
        "                candidate\n"
        "                for candidate in range(self.tabBar().count())\n"
        "                if self.tabBar().tabData(candidate) == workbenchName\n"
        "            ),\n"
        "            -1,\n"
        "        )\n"
        "        if index < 0:\n"
        "            return False\n"
        "        self._fmfProgrammaticTabChange = True\n"
        "        try:\n"
        "            self.tabBar().setCurrentIndex(index)\n"
        "        finally:\n"
        "            self._fmfProgrammaticTabChange = False\n"
        "        if buildIfNeeded and workbenchName not in self._fmfBuiltWorkbenches:\n"
        "            if self.CustomizeEnabled is False:\n"
        "                self.buildPanels()\n"
        "            else:\n"
        "                self.buildPanels(Dict=self.workBenchDict, UpdateDict=False)\n"
        "            self._fmfBuiltWorkbenches.add(workbenchName)\n"
        "        return True\n"
        "\n"
        "    def onWbActivated(self, workbenchName=None):\n"
        "        # The Ribbon is the application chrome for every workbench. FMF only\n"
        "        # owns the layouts of its four namespaced workbenches; selecting a stock\n"
        "        # or unrelated workbench must never blank the entire Ribbon.\n"
        "        self._setFmfChromeVisible(True)\n"
        "        workbenchName = workbenchName or Gui.activeWorkbench().name()\n"
        "        self.selectFmfWorkbenchContext(workbenchName)\n",
    ),
    (
        "        # ensure that workbench is already loaded\n"
        "        workbench = Gui.activeWorkbench()\n"
        '        if not hasattr(workbench, "__Workbench__"):\n'
        "            # XXX for debugging purposes\n"
        "            if Parameters.DEBUG_MODE is True:\n"
        '                StandardFunctions.Print(f"wb {workbench.MenuText} not loaded", "Log")\n'
        "\n"
        "            # wait for 0.1s hoping that after that time the workbench is loaded\n"
        "            timer.timeout.connect(self.onWbActivated)\n"
        "            timer.setSingleShot(True)\n"
        "            timer.start(1000)\n"
        "            return\n"
        "\n"
        "        # hide normal toolbars\n"
        "        self.hideClassicToolbars()\n"
        "\n"
        "        # switch tab if necessary\n"
        "        self.updateCurrentTab()\n"
        "\n"
        "        # create panels. Do this after updateCurrentTab.\n"
        "        # Otherwise, the sketcher workbench won;t be loaded properly the first time\n"
        "        if self.CustomizeEnabled is False: \n"
        "            self.buildPanels()\n"
        "        if self.CustomizeEnabled:\n"
        "            self.buildPanels(Dict=self.workBenchDict, UpdateDict=False)\n"
        "        \n"
        "        # hide normal toolbars\n"
        "        self.hideClassicToolbars()\n"
        "\n"
        "        if self.CustomizeEnabled:\n"
        "            self.on_Customize_Clicked()\n"
        "            # If not activated, activate all buttons    \n"
        "            self.activateButtons() \n"
        "\n"
        "        # if self.DesignMenuLoaded is True:\n"
        "        #     # Disable the quick toolbar, righttoolbar and application menu\n"
        "        #     self.rightToolBar().setDisabled(True)\n"
        "        #     self.quickAccessToolBar().setDisabled(True)\n"
        "        #     self.applicationOptionButton().setDisabled(True)\n"
        "        #     Gui.updateGui()\n"
        "        \n"
        "        return\n",
        "        # hide normal toolbars\n"
        "        self.hideClassicToolbars()\n"
        "        self.ApplicationMenus()\n",
    ),
)

FCBINDING_OVERFLOW_PATCH = (
    (
        "                if (\n"
        "                    CommandName in explicitOverflow\n"
        "                    and not responsiveVisible\n"
        "                    and ignoreColumnLimit is False\n"
        "                ):\n",
        "                # FMF local change: once the user has sized a\n"
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

SEARCH_BOX_FMF_PATCH = (
    (
        ")\n\nfrom SearchBoxLight import SearchBoxLight\n",
        ")\n\n\n"
        "def fmfSearchableText(group):\n"
        '    """Return visible, native, and FMF discovery vocabulary for a result."""\n'
        "    import re\n"
        "\n"
        '    tooltip = group.get("toolTip", "")\n'
        '    match = re.search(r"<i>([^<]+)</i>", tooltip)\n'
        '    command_id = group.get("action", {}).get("commandId", "") or (\n'
        '        match.group(1) if match else ""\n'
        "    )\n"
        "    try:\n"
        "        from fmf_catalog import entry_map\n"
        "\n"
        "        entry = entry_map().get(command_id)\n"
        "    except (ImportError, OSError, ValueError):\n"
        "        entry = None\n"
        '    aliases = " ".join(entry.aliases) if entry else ""\n'
        '    return "{} {} {}".format(group["text"], tooltip, aliases)\n'
        "\n\n"
        "def fmfResultText(group):\n"
        '    """Disambiguate commands whose Fusion discovery terms overlap."""\n'
        '    tooltip = group.get("toolTip", "")\n'
        '    command_id = group.get("action", {}).get("commandId", "")\n'
        '    if command_id == "PartDesign_Pad" or "PartDesign_Pad" in tooltip:\n'
        '        return "Pad / Extrude (Part Design)"\n'
        '    if command_id == "Part_Extrude" or "Part_Extrude" in tooltip:\n'
        '        return "Extrude (Part)"\n'
        '    return group["text"]\n'
        "\n\n"
        "def fmfSearchScore(userInput, group):\n"
        '    """Rank catalog commands while preserving SearchBar-only result types."""\n'
        "    import re\n"
        "\n"
        '    tooltip = group.get("toolTip", "")\n'
        '    match = re.search(r"<i>([^<]+)</i>", tooltip)\n'
        '    command_id = group.get("action", {}).get("commandId", "") or (\n'
        '        match.group(1) if match else ""\n'
        "    )\n"
        "    try:\n"
        "        from fmf_catalog import entry_map, score\n"
        "\n"
        "        entry = entry_map().get(command_id)\n"
        "        value = score(userInput, entry) if entry else None\n"
        "    except (ImportError, OSError, ValueError):\n"
        "        value = None\n"
        "    # Python's sort is stable. Equal fallback scores retain SearchBar's native\n"
        "    # object, preference, help, and tree ordering.\n"
        "    return value if value is not None else 10000\n"
        "\n"
        "from SearchBoxLight import SearchBoxLight\n",
    ),
    (
        '            if matches(group["text"]):\n',
        "            if matches(fmfSearchableText(group)):\n",
        1,
    ),
    (
        '                if len(subitems) > 0 or matches(group["text"]):\n',
        "                if len(subitems) > 0 or matches(fmfSearchableText(group)):\n",
    ),
    (
        '                        QStandardItem(group["icon"] or genericToolIcon, group["text"]),\n',
        '                        QStandardItem(group["icon"] or genericToolIcon, fmfResultText(group)),\n',
    ),
    (
        "            return [group for group in groups if group is not None]\n",
        "            groups = [group for group in groups if group is not None]\n"
        "            return sorted(groups, key=lambda group: fmfSearchScore(userInput, group))\n",
    ),
)


SEARCH_RESULTS_COMMAND_ID_PATCH = (
    (
        '                                action = {\n                                    "handler": "subTool",\n',
        '                                action = {\n                                    "handler": "subTool",\n'
        '                                    "commandId": mac.objectName(),\n',
    ),
    (
        '                    action = {\n                        "handler": "tool",\n',
        '                    action = {\n                        "handler": "tool",\n'
        '                        "commandId": act.objectName() if act is not None else tbt.objectName(),\n',
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
        '        """FMF local change: a divider drag resizes one panel."""\n'
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
        "        # Set the maximum columns. FMF local change: a panel whose\n"
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
        "        # FMF local change: let this panel's divider resize it.\n"
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
        "import Parameters_Ribbon\nimport fmf_ribbon_support  # FMF local change\n",
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

# Modifications that used to be edited straight into the ignored vendor snapshot,
# where nothing re-applied them and nothing could tell them apart from upstream's
# own code. They are patches like the rest now, so vendor/ can be a plain upstream
# checkout and an upstream refresh either re-applies them or says which anchor moved.


# The cache module, which upstream reaches the network from and interrogates the
# user from. Three changes, in file order: the icon download uses urllib instead of
# requests (and writes the icon it fetched rather than over setup.py); the progress
# dialog keeps its close button; and the startup cache check regenerates what it
# needs, reporting to the console, instead of putting modal questions behind the
# splash screen where they cannot be seen or dismissed.
CACHE_FUNCTIONS_PATCH = (
    (
        "    if HideOnly is False:\n"
        "        activeWorkbench = Gui.activeWorkbench().name()\n"
        "        progressBar.show()\n",
        "    if HideOnly is False:\n        progressBar.show()\n",
    ),
    (
        "        WorkBench = Gui.getWorkbench(List_Workbenches[i][0])\n"
        "        WorkBenchName = List_Workbenches[i][0]\n"
        "        # Get the toolbar items\n"
        "        ToolbarItems: dict = WorkBench.getToolbarItems()\n",
        "        WorkBenchName = List_Workbenches[i][0]\n"
        "        # Reuse the toolbar items captured above. Asking Python-defined\n"
        "        # workbenches again can require FreeCAD's private __Workbench__.\n"
        "        ToolbarItems: dict = List_Workbenches[i][3]\n",
    ),
    (
        "            wbToolbars = Gui.getWorkbench(WorkBench[0]).listToolbars()\n",
        "            wbToolbars = returnWorkBenchToolbars(WorkBench[0])\n",
    ),
    (
        "    except Exception:\n"
        "        Gui.activateWorkbench(WorkBenchName)\n"
        "        wbToolbars: list = Gui.getWorkbench(WorkBenchName).listToolbars()\n"
        "    return wbToolbars\n",
        "    except Exception:\n"
        "        try:\n"
        "            wbToolbars = list(Gui.getWorkbench(WorkBenchName).listToolbars())\n"
        "        except Exception:\n"
        "            wbToolbars = []\n"
        "    return wbToolbars\n",
    ),
    (
        "    except Exception:\n"
        "        Gui.activateWorkbench(WorkBenchName)\n"
        "        Toolbars = Gui.getWorkbench(WorkBenchName).getToolbarItems()\n"
        "        return Toolbars\n",
        "    except Exception:\n"
        "        try:\n"
        "            return Gui.getWorkbench(WorkBenchName).getToolbarItems()\n"
        "        except Exception:\n"
        "            return {}\n",
    ),
    (
        "        progressBar.show()\n"
        "        lst = Gui.listWorkbenches()\n"
        "        progressBar.setMaximum(len(lst) - 1 + maximum)\n",
        "        progressBar.show()\n"
        "        lst = Gui.listWorkbenches()\n"
        '        if os.environ.get("FREECAD_RIBBON_CACHE_WORKBENCHES"):\n'
        "            # FMF supplies curated manifests. Cache generation may inspect what\n"
        "            # FreeCAD has already registered, but it must not activate workbenches\n"
        "            # as a discovery mechanism: activation initializes unrelated host and\n"
        "            # third-party code and emits user-visible transition signals.\n"
        "            progressBar.setMaximum(maximum)\n"
        "            progressBar.setValue(maximum)\n"
        '            if FinishMessage != "":\n'
        "                print(FinishMessage)\n"
        "            return\n"
        "        activeWorkbench = Gui.activeWorkbench().name()\n"
        "        progressBar.setMaximum(len(lst) - 1 + maximum)\n",
    ),
    (
        "import Serialize_Ribbon\n"
        "import webbrowser\n"
        "import StyleMapping_Ribbon\n"
        "import requests\n"
        "\n"
        "# Get the resources\n"
        "ConfigDirectory = Parameters.CONFIG_DIR\n",
        "import Serialize_Ribbon\n"
        "import webbrowser\n"
        "import StyleMapping_Ribbon\n"
        "from urllib.request import urlopen\n"
        "\n"
        "# Get the resources\n"
        "ConfigDirectory = Parameters.CONFIG_DIR\n",
    ),
    (
        "    progressBar.setWindowFlag(Qt.WindowType.CustomizeWindowHint, True)\n"
        "    progressBar.setWindowFlag(Qt.WindowType.WindowMinMaxButtonsHint, False)\n"
        "    progressBar.setWindowFlag(Qt.WindowType.WindowMinimizeButtonHint, True)\n"
        "    progressBar.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)\n"
        "    progressBar.setMinimumSize(400, 20)\n"
        "\n"
        "    # Get the stylesheet from the main window and use it for this form\n",
        "    progressBar.setWindowFlag(Qt.WindowType.CustomizeWindowHint, True)\n"
        "    progressBar.setWindowFlag(Qt.WindowType.WindowMinMaxButtonsHint, False)\n"
        "    progressBar.setWindowFlag(Qt.WindowType.WindowMinimizeButtonHint, True)\n"
        "    progressBar.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, True)\n"
        "    progressBar.setMinimumSize(400, 20)\n"
        "\n"
        "    # Get the stylesheet from the main window and use it for this form\n",
    ),
    (
        "# endregion---------------------------------------------------------------------------------------\n"
        "\n"
        "def DownLoadIcons():\n"
        "    PathList = []\n"
        "\n"
        "    url = 'https://raw.githubusercontent.com/FreeCAD/FreeCAD/main/src/Gui/Icons/3dx_pivot.png'\n"
        "    \n"
        "    \n"
        "    response = requests.get(url)\n"
        "    response.raise_for_status() # proper handle HTTP errors\n"
        "\n"
        "    file_content = response.text\n"
        '    print(f"HTTP status: {response.status_code}")\n'
        "\n"
        '    with open("setup.py", "w") as file:\n'
        "        file.write(file_content)\n"
        "\n"
        "        \n"
        "def CheckDataFileVersion():\n"
        "    DataFileIsUpToDate = False\n"
        "    \n"
        "    # Check if there is a datafile. if not, ask the user to create one.\n"
        '    DataFile = os.path.join(ConfigDirectory, "RibbonDataFile.dat")\n'
        "    if os.path.exists(DataFile) is False:\n"
        "        Question = translate(\n"
        '            "FreeCAD Ribbon",\n'
        '            "The first time, a data file must be generated!\\n"\n'
        '            "This can take a while! Do you want to proceed?",\n'
        "        )\n"
        '        Answer = StandardFunctions.Mbox(Question, "FreeCAD Ribbon", 1, "Question")\n'
        '        if Answer == "yes":\n'
        "            CreateCache()\n"
        "        else:\n"
        "            return\n"
        "\n"
        "    # region - Load data------------------------------------------------------------------\n"
        "    #\n"
        "    Data = {}\n"
        "    # read ribbon structure from JSON file\n"
        '    with open(DataFile, "r") as file:\n'
        "        Data.update(json.load(file))\n"
        "    file.close()\n"
        "\n"
        "    DataUpdateNeeded = False\n"
        "    try:\n"
        '        FileVersion = Data["dataVersion"]\n'
        "        if FileVersion != DataFileVersion:\n"
        "            DataUpdateNeeded = True\n"
        "    except Exception:\n"
        "        DataUpdateNeeded = True\n"
        "    if DataUpdateNeeded is True:\n"
        "        Question = translate(\n"
        '            "FreeCAD Ribbon",\n'
        '            "The current data file is based on an older format!\\n"\n'
        '            "It is important to update the data!\\n"\n'
        '            "Do you want to proceed?\\n"\n'
        '            "This can take a while!",\n'
        "        )\n"
        "\n"
        '        Answer = StandardFunctions.Mbox(Question, "FreeCAD Ribbon", 1, "Question")\n'
        '        if Answer == "yes":\n'
        "            CreateCache()\n"
        "\n"
        "    # get the system language\n"
        '    FreeCAD_preferences = App.ParamGet("User parameter:BaseApp/Preferences/General")\n'
        "    try:\n"
        '        FCLanguage = FreeCAD_preferences.GetString("Language")\n'
        "        # Check if the language in the data file machtes the system language\n"
        "        IsSystemLanguage = True\n"
        '        if FCLanguage != Data["Language"]:\n'
        "            IsSystemLanguage = False\n"
        "        # If the languguage doesn't match, ask the user to update the data\n"
        "        if IsSystemLanguage is False:\n"
        "            Question = translate(\n"
        '                "FreeCAD Ribbon",\n'
        '                "The data was generated for a differernt language!\\n"\n'
        '                "Do you want to update the data?\\n"\n'
        '                "This can take a while!",\n'
        "            )\n"
        "\n"
        "            Answer = StandardFunctions.Mbox(\n"
        '                Question, "FreeCAD Ribbon", 1, "Question"\n'
        "            )\n"
        '            if Answer == "yes":\n'
        "                CreateCache()                    \n"
        "    except Exception:\n"
        "        pass\n"
        "\n"
        "    # test if List_Commands is correct\n"
        "    i = 5\n"
        "    if len(List_Commands) > 0:\n"
        "        for item in List_Commands:\n"
        "            if len(item) < 5:\n"
        "                i = len(item)\n"
        "                break\n"
        "    if i < 5:\n"
        "        Question = translate(\n"
        '            "FreeCAD Ribbon",\n'
        '            "It seems that the data file is not up-to-date.\\n"\n'
        '            "Do you want to update the data?\\n"\n'
        '            "This can take a while!",\n'
        "        )\n"
        '        Answer = StandardFunctions.Mbox(Question, "FreeCAD Ribbon", 1, "Question")\n'
        '        if Answer == "yes":\n'
        "            DataFileIsUpToDate = CreateCache()\n"
        "    \n"
        "    return DataFileIsUpToDate",
        "# endregion---------------------------------------------------------------------------------------\n"
        "\n"
        "def DownLoadIcons():\n"
        "    url = 'https://raw.githubusercontent.com/FreeCAD/FreeCAD/main/src/Gui/Icons/3dx_pivot.png'\n"
        "    with urlopen(url, timeout=15) as response:\n"
        "        file_content = response.read()\n"
        '        print(f"HTTP status: {response.status}")\n'
        '    with open(os.path.join(pathIcons, "3dx_pivot.png"), "wb") as file:\n'
        "        file.write(file_content)\n"
        "\n"
        "        \n"
        "def CheckDataFileVersion():\n"
        '    """Ensure the cache exists without putting a modal dialog behind other startup UI."""\n'
        '    DataFile = os.path.join(ConfigDirectory, "RibbonDataFile.dat")\n'
        '    language = App.ParamGet("User parameter:BaseApp/Preferences/General").GetString("Language")\n'
        "\n"
        "    def regenerate(reason):\n"
        '        App.Console.PrintMessage("FreeCAD Ribbon: {} Generating command cache...\\n".format(reason))\n'
        "        try:\n"
        "            return bool(CreateCache())\n"
        "        except Exception as error:\n"
        '            App.Console.PrintWarning("FreeCAD Ribbon cache generation failed: {}\\n".format(error))\n'
        "            return False\n"
        "\n"
        "    if not os.path.isfile(DataFile):\n"
        '        if not regenerate("First startup."):\n'
        "            return False\n"
        "\n"
        "    try:\n"
        '        with open(DataFile, "r", encoding="utf-8") as file:\n'
        "            data = json.load(file)\n"
        "    except (OSError, ValueError, TypeError):\n"
        '        if not regenerate("The existing cache is unreadable."):\n'
        "            return False\n"
        '        with open(DataFile, "r", encoding="utf-8") as file:\n'
        "            data = json.load(file)\n"
        "\n"
        '    commands = data.get("List_Commands", [])\n'
        "    stale = (\n"
        '        data.get("dataVersion") != DataFileVersion\n'
        '        or data.get("Language", "") != language\n'
        "        or any(len(item) < 5 for item in commands)\n"
        "    )\n"
        "    if stale:\n"
        '        return regenerate("The cache is out of date.")\n'
        "    return True\n",
    ),
)


# The colour helper, so the package needs no Matplotlib at runtime.
STANDARD_FUNCTIONS_COLOUR_PATCH = (
    (
        "    ColorRGB:   [255,255,255]\n"
        "    Alpha:      0-1\n"
        '    """\n'
        "    from matplotlib import colors as mcolors\n"
        "\n"
        "    ColorRed = ColorRGB[0] / 255\n"
        "    colorGreen = ColorRGB[1] / 255\n"
        "    colorBlue = ColorRGB[2] / 255\n"
        "\n"
        "    color = (ColorRed, colorGreen, colorBlue)\n"
        "\n"
        "    result = mcolors.to_rgba(color, Alpha)\n"
        "    if Hex is True:\n"
        "        result = mcolors.to_hex((ColorRed, colorGreen, colorBlue, Alpha), KeepHexAlpha)\n"
        "\n"
        "    return result\n"
        "\n",
        "    ColorRGB:   [255,255,255]\n"
        "    Alpha:      0-1\n"
        '    """\n'
        "    ColorRed = ColorRGB[0] / 255\n"
        "    colorGreen = ColorRGB[1] / 255\n"
        "    colorBlue = ColorRGB[2] / 255\n"
        "\n"
        "    color = (ColorRed, colorGreen, colorBlue)\n"
        "\n"
        "    result = (ColorRed, colorGreen, colorBlue, Alpha)\n"
        "    if Hex is True:\n"
        "        channels = [ColorRed, colorGreen, colorBlue]\n"
        "        if KeepHexAlpha:\n"
        "            channels.append(Alpha)\n"
        '        result = "#" + "".join("{:02x}".format(max(0, min(255, round(value * 255)))) for value in channels)\n'
        "\n"
        "    return result\n"
        "\n",
    ),
    (
        "    \n"
        "def CompareIcons(icon1: QIcon, icon2: QIcon):\n"
        '    icon1 = Gui.getIcon("Std_OnlineHelp")\n'
        "    return (icon1.pixmap(icon1.actualSize(QSize(16,16))).toImage() == icon2.pixmap(icon2.actualSize(QSize(16,16))).toImage())",
        "    \n"
        "def CompareIcons(icon1: QIcon, icon2: QIcon):\n"
        '    icon1 = Gui.getIcon("Std_OnlineHelp")\n'
        "    return (icon1.pixmap(icon1.actualSize(QSize(16,16))).toImage() == icon2.pixmap(icon2.actualSize(QSize(16,16))).toImage())\n",
    ),
)


# FreeCAD's development command Part_PickCurveNet advertises the placeholder
# pixmap "Test1", which does not exist and produces a warning during cache
# inspection. Use a real upstream Part icon with the closest visual meaning.
STANDARD_FUNCTIONS_ICON_PATCH = (
    (
        "            # Sketcher\n",
        '            if CommandName == "Part_PickCurveNet":\n'
        '                CommandInfo["pixmap"] = "Part_Spline_Parametric.svg"\n'
        "\n"
        "            # Sketcher\n",
    ),
)


# Native commands already expose their authoritative QAction icon. Resolve it
# before treating a command ID as a pixmap name; otherwise Gui.getIcon logs a
# false missing-icon warning for valid commands such as Std_ViewFitAll.
STANDARD_FUNCTIONS_NATIVE_ICON_PATCH = (
    (
        '    icon = QIcon()\n    \n    if pixmap != "":\n',
        "    icon = QIcon()\n"
        "\n"
        "    # Prefer the command's live QAction. Command IDs are often used as\n"
        "    # fallback pixmap names, but asking Gui.getIcon for those IDs first emits\n"
        "    # a misleading warning even when the command already owns a valid icon.\n"
        "    try:\n"
        "        Command = Gui.Command.get(CommandName)\n"
        "        action = Command.getAction()[0]\n"
        "        icon = action.icon()\n"
        "        if icon is not None and icon.isNull() is False:\n"
        "            return icon\n"
        "    except Exception:\n"
        "        pass\n"
        "\n"
        '    if pixmap != "":\n',
    ),
    (
        "    if icon is None or (icon is not None and icon.isNull()):\n"
        "        try:\n"
        "            Command = Gui.Command.get(CommandName)\n"
        "            action = Command.getAction()[0]\n"
        "            icon = action.icon()\n"
        "            if icon is not None and icon.isNull() is False:\n"
        "                return icon\n"
        "        except Exception:\n"
        "            pass\n"
        "        \n",
        "",
    ),
)


# Upstream seeds a missing large-icon size from the small-icon setting, which
# makes every large ribbon button come back the size of a small one.
PARAMETERS_ICON_SIZE_PATCH = (
    (
        '        or Settings.GetIntSetting("IconSize_Large") == 0\n'
        "    ):\n"
        '        ICON_SIZE_LARGE = int(DefaultSettings["IconSize_Large"])\n'
        '        Settings.SetIntSetting("IconSize_Large", ICON_SIZE_SMALL)\n'
        '    ICON_SIZE_LARGE = Settings.GetIntSetting("IconSize_Large")\n'
        "\n"
        "    if (\n",
        '        or Settings.GetIntSetting("IconSize_Large") == 0\n'
        "    ):\n"
        '        ICON_SIZE_LARGE = int(DefaultSettings["IconSize_Large"])\n'
        '        Settings.SetIntSetting("IconSize_Large", ICON_SIZE_LARGE)\n'
        '    ICON_SIZE_LARGE = Settings.GetIntSetting("IconSize_Large")\n'
        "\n"
        "    if (\n",
    ),
)


# The panel grid helper, so the package needs no NumPy at runtime. It tracks a few
# hundred booleans; Python lists are enough, and the search is the same search.
PANEL_NUMPY_PATCH = (
    (
        "from pydoc import text\n"
        "import re\n"
        "from typing import Any, Callable, Dict, List, Union, overload\n"
        "\n"
        "import numpy as np\n"
        "\n"
        "from PySide.QtGui import QIcon, QKeySequence, QFontMetrics\n"
        "from PySide.QtWidgets import (\n",
        "from pydoc import text\n"
        "import re\n"
        "from typing import Any, Callable, Dict, List, Union, overload\n"
        "\n"
        "from PySide.QtGui import QIcon, QKeySequence, QFontMetrics\n"
        "from PySide.QtWidgets import (\n",
    ),
    (
        "        :param rows: The number of rows in the grid layout.\n"
        '        """\n'
        "        self.rows = rows\n"
        "        self.cells = np.ones((rows, 1), dtype=bool)\n"
        "\n"
        "    def request_cells(\n"
        "        self, rowSpan: int = 1, colSpan: int = 1, mode: RibbonSpaceFindMode = ColumnWise\n",
        "        :param rows: The number of rows in the grid layout.\n"
        '        """\n'
        "        self.rows = rows\n"
        "        self.cells = [[True] for _ in range(rows)]\n"
        "\n"
        "    def request_cells(\n"
        "        self, rowSpan: int = 1, colSpan: int = 1, mode: RibbonSpaceFindMode = ColumnWise\n",
    ),
    (
        "        if rowSpan > self.rows:\n"
        '            raise ValueError("RowSpan is too large")\n'
        "        if mode == ColumnWise:\n"
        "            for row in range(self.cells.shape[0] - rowSpan + 1):\n"
        "                for col in range(self.cells.shape[1] - colSpan + 1):\n"
        "                    if self.cells[row : row + rowSpan, col : col + colSpan].all():\n"
        "                        self.cells[row : row + rowSpan, col : col + colSpan] = False\n"
        "                        return row, col\n"
        "        else:\n"
        "            for col in range(self.cells.shape[1]):\n"
        "                if self.cells[0, col:].all():\n"
        "                    if self.cells.shape[1] - col < colSpan:\n"
        "                        self.cells = np.append(\n"
        "                            self.cells,\n"
        "                            np.ones(\n"
        "                                (self.rows, colSpan - (self.cells.shape[1] - col)),\n"
        "                                dtype=bool,\n"
        "                            ),\n"
        "                            axis=1,\n"
        "                        )\n"
        "                    self.cells[0, col:] = False\n"
        "                    return 0, col\n"
        "        cols = self.cells.shape[1]\n"
        "        colSpan1 = colSpan\n"
        "        if self.cells[:, -1].all():\n"
        "            cols -= 1\n"
        "            colSpan1 -= 1\n"
        "        self.cells = np.append(\n"
        "            self.cells, np.ones((self.rows, colSpan1), dtype=bool), axis=1\n"
        "        )\n"
        "        self.cells[:rowSpan, cols : cols + colSpan] = False\n"
        "        return 0, cols\n"
        "\n"
        "\n",
        "        if rowSpan > self.rows:\n"
        '            raise ValueError("RowSpan is too large")\n'
        "        if mode == ColumnWise:\n"
        "            for row in range(len(self.cells) - rowSpan + 1):\n"
        "                for col in range(len(self.cells[0]) - colSpan + 1):\n"
        "                    if all(\n"
        "                        self.cells[r][c]\n"
        "                        for r in range(row, row + rowSpan)\n"
        "                        for c in range(col, col + colSpan)\n"
        "                    ):\n"
        "                        for r in range(row, row + rowSpan):\n"
        "                            for c in range(col, col + colSpan):\n"
        "                                self.cells[r][c] = False\n"
        "                        return row, col\n"
        "        else:\n"
        "            for col in range(len(self.cells[0])):\n"
        "                if all(self.cells[0][col:]):\n"
        "                    missing = colSpan - (len(self.cells[0]) - col)\n"
        "                    if missing > 0:\n"
        "                        for row in self.cells:\n"
        "                            row.extend([True] * missing)\n"
        "                    for c in range(col, len(self.cells[0])):\n"
        "                        self.cells[0][c] = False\n"
        "                    return 0, col\n"
        "        cols = len(self.cells[0])\n"
        "        colSpan1 = colSpan\n"
        "        if all(row[-1] for row in self.cells):\n"
        "            cols -= 1\n"
        "            colSpan1 -= 1\n"
        "        if colSpan1 > 0:\n"
        "            for row in self.cells:\n"
        "                row.extend([True] * colSpan1)\n"
        "        for row in range(rowSpan):\n"
        "            for col in range(cols, cols + colSpan):\n"
        "                self.cells[row][col] = False\n"
        "        return 0, cols\n"
        "\n"
        "\n",
    ),
)


# A ribbon button only starts a drag once the pointer has moved past the platform's
# drag distance, so a slow click on a command no longer tears it out of its panel.
CUSTOM_WIDGETS_DRAG_THRESHOLD_PATCH = (
    (
        "    QGridLayout,\n"
        "    QPushButton,\n"
        "    QGraphicsEffect,\n"
        ")\n"
        "from PySide.QtCore import (\n"
        "    Qt,\n",
        "    QGridLayout,\n"
        "    QPushButton,\n"
        "    QGraphicsEffect,\n"
        "    QApplication,\n"
        ")\n"
        "from PySide.QtCore import (\n"
        "    Qt,\n",
    ),
    (
        "        self.layout.setAlignment(Qt.AlignmentFlag.AlignLeft)\n"
        "        self.setFixedSize(self.widget.size())\n"
        "          \n"
        "    def mouseMoveEvent(self, e):\n"
        "        if e.buttons() == Qt.MouseButton.LeftButton:\n"
        "            try:\n"
        "                drag = QDrag(self)\n",
        "        self.layout.setAlignment(Qt.AlignmentFlag.AlignLeft)\n"
        "        self.setFixedSize(self.widget.size())\n"
        "          \n"
        "    def mousePressEvent(self, e):\n"
        "        self._dragStartPosition = e.pos()\n"
        "        QToolButton.mousePressEvent(self, e)\n"
        "\n"
        "    def mouseMoveEvent(self, e):\n"
        '        start = getattr(self, "_dragStartPosition", None)\n'
        "        if start is None:\n"
        "            return\n"
        "        if (e.pos() - start).manhattanLength() < QApplication.startDragDistance():\n"
        "            return\n"
        "        if e.buttons() == Qt.MouseButton.LeftButton:\n"
        "            try:\n"
        "                drag = QDrag(self)\n",
    ),
    (
        "            Label_Text.setToolTip(CommandButton.toolTip())\n"
        "\n"
        "        btn.mouseMoveEvent = lambda mouseEvent: CustomControls.mouseMoveEvent(\n"
        "            btn, mouseEvent\n"
        "        )\n"
        "\n",
        "            Label_Text.setToolTip(CommandButton.toolTip())\n"
        "\n"
        "        btn.mouseMoveEvent = lambda mouseEvent: CustomControls.mouseMoveEvent(\n"
        "            btn, mouseEvent\n"
        "        )\n"
        "        btn.mousePressEvent = lambda mouseEvent: CustomControls.mousePressEvent(\n"
        "            btn, mouseEvent\n"
        "        )\n"
        "\n",
    ),
    (
        "        btn.mouseMoveEvent = lambda mouseEvent: CustomControls.mouseMoveEvent(\n"
        "            btn, mouseEvent\n"
        "        )\n"
        "        \n"
        "        # Hide the text if set in preferences\n"
        "        if showText is False:\n",
        "        btn.mouseMoveEvent = lambda mouseEvent: CustomControls.mouseMoveEvent(\n"
        "            btn, mouseEvent\n"
        "        )\n"
        "        btn.mousePressEvent = lambda mouseEvent: CustomControls.mousePressEvent(\n"
        "            btn, mouseEvent\n"
        "        )\n"
        "        \n"
        "        # Hide the text if set in preferences\n"
        "        if showText is False:\n",
    ),
    (
        "    def EmptyButton():\n"
        "        btn = QToolButton()\n"
        "        btn.mouseMoveEvent = lambda mouseEvent: CustomControls.mouseMoveEvent(\n"
        "            btn, mouseEvent\n"
        "        )\n"
        "        return btn\n",
        "    def EmptyButton():\n"
        "        btn = QToolButton()\n"
        "        btn.mouseMoveEvent = lambda mouseEvent: CustomControls.mouseMoveEvent(\n"
        "            btn, mouseEvent\n"
        "        )\n"
        "        btn.mousePressEvent = lambda mouseEvent: CustomControls.mousePressEvent(\n"
        "            btn, mouseEvent\n"
        "        )\n"
        "        return btn\n",
    ),
    (
        "        \n"
        "    def setClearButtonEnabled(self, enable: bool):\n"
        "        self.lineEdit.setClearButtonEnabled(enable)\n"
        "        return",
        "        \n"
        "    def setClearButtonEnabled(self, enable: bool):\n"
        "        self.lineEdit.setClearButtonEnabled(enable)\n"
        "        return\n",
    ),
)


# FMF's hooks into the ribbon binding itself: rebuilding width-aware
# panels when the window crosses a responsive tier, recording a layout the user has
# dragged into shape, keeping direct drag usable outside customize mode, honouring
# an authoritative layout's explicit overflow, and offering Reset this panel.
FCBINDING_INTEGRATION_PATCH = (
    (
        '        with open(Parameters.RIBBON_STRUCTURE_JSON, "r") as file:\n'
        "            self.ribbonStructure.update(json.load(file))\n"
        "        file.close()\n"
        "        \n"
        '        DataFile2 = os.path.join(ConfigDirectory, "RibbonDataFile2.dat")\n'
        "        if os.path.exists(DataFile2) is True:\n",
        '        with open(Parameters.RIBBON_STRUCTURE_JSON, "r") as file:\n'
        "            self.ribbonStructure.update(json.load(file))\n"
        "        file.close()\n"
        "        self._responsiveWidthTierValue = self._responsiveWidthTier()\n"
        "        self._responsiveRebuildPending = False\n"
        "        \n"
        '        DataFile2 = os.path.join(ConfigDirectory, "RibbonDataFile2.dat")\n'
        "        if os.path.exists(DataFile2) is True:\n",
    ),
    (
        "        mw.menuBar().show()\n"
        "        return True\n"
        "\n"
        "    def eventFilter(self, obj, event):\n"
        "        # Disable the standard hover behavior\n"
        "        if event.type() == QEvent.Type.HoverMove:\n",
        "        mw.menuBar().show()\n"
        "        return True\n"
        "\n"
        "    def _responsiveWidthTier(self, Dict=None):\n"
        '        """Return the highest responsive command threshold reached by the window."""\n'
        '        structure = Dict if isinstance(Dict, dict) else getattr(self, "ribbonStructure", {})\n'
        "        thresholds = {0}\n"
        '        for workbench in structure.get("workbenches", {}).values():\n'
        '            for panel in workbench.get("toolbars", {}).values():\n'
        "                if not isinstance(panel, dict):\n"
        "                    continue\n"
        '                for minimumWidth in panel.get("responsive", {}).values():\n'
        "                    try:\n"
        "                        thresholds.add(int(minimumWidth))\n"
        "                    except (TypeError, ValueError):\n"
        "                        continue\n"
        "        width = mw.width()\n"
        "        return max(threshold for threshold in thresholds if width >= threshold)\n"
        "\n"
        "    def _fmfReplacePanel(self, category, panel, replacement):\n"
        '        """Replace one panel without leaving stale aliases in the category."""\n'
        "        category.replaceWidget(panel, replacement)\n"
        "        for key, candidate in list(category._panels.items()):\n"
        "            if candidate is panel:\n"
        "                category._panels.pop(key, None)\n"
        "        category._panels[replacement.objectName()] = replacement\n"
        "        panel.close()\n"
        "        panel.deleteLater()\n"
        "        return replacement\n"
        "\n"
        "    def resizeEvent(self, event):\n"
        "        super().resizeEvent(event)\n"
        "        # Runtime panel replacement is intentionally disabled. Replacing widgets\n"
        "        # while FreeCAD is changing workbenches can mix two categories, and the\n"
        "        # initial width tier already places narrower commands in overflow menus.\n"
        "\n"
        "    def eventFilter(self, obj, event):\n"
        "        # Disable the standard hover behavior\n"
        "        if event.type() == QEvent.Type.HoverMove:\n",
    ),
    (
        "            \n"
        "                    \n"
        "        # update the ribbonstructure before writing it to disk\n"
        '        if "quickAccessCommands" in self.workBenchDict:\n'
        '            self.ribbonStructure["quickAccessCommands"] = self.workBenchDict["quickAccessCommands"]\n'
        '        if "newPanels" in self.workBenchDict:\n',
        "            \n"
        "                    \n"
        "        # update the ribbonstructure before writing it to disk\n"
        "        # FMF panels declare a stable number of pinned commands. In\n"
        "        # Arrange mode every menu command is shown, so the user's final order\n"
        "        # determines which commands remain on the face of the panel.\n"
        '        for workbench in self.workBenchDict.get("authoritativeWorkbenches", []):\n'
        '            toolbars = self.workBenchDict.get("workbenches", {}).get(workbench, {}).get("toolbars", {})\n'
        "            for panelName, toolbar in toolbars.items():\n"
        '                if not isinstance(toolbar, dict) or "pinCount" not in toolbar:\n'
        "                    continue\n"
        '                order = list(toolbar.get("order", []))\n'
        '                pinCount = max(0, min(int(toolbar.get("pinCount", 0)), len(order)))\n'
        '                toolbar["overflow"] = order[pinCount:]\n'
        '                toolbar["panelMenu"] = list(order)\n'
        '        if "quickAccessCommands" in self.workBenchDict:\n'
        '            self.ribbonStructure["quickAccessCommands"] = self.workBenchDict["quickAccessCommands"]\n'
        '        if "newPanels" in self.workBenchDict:\n',
    ),
    (
        '            self.ribbonStructure["customToolbars"] = self.workBenchDict["customToolbars"]\n'
        "        \n"
        '        for WorkBench in self.workBenchDict["workbenches"].keys():\n'
        '            self.ribbonStructure["workbenches"][WorkBench] == self.workBenchDict["workbenches"][WorkBench]\n'
        "        \n"
        "        # CopyDict = {}\n"
        '        # for WorkBench in self.workBenchDict["workbenches"].keys():\n',
        '            self.ribbonStructure["customToolbars"] = self.workBenchDict["customToolbars"]\n'
        "        \n"
        '        for WorkBench in self.workBenchDict["workbenches"].keys():\n'
        '            self.ribbonStructure["workbenches"][WorkBench] = self.workBenchDict["workbenches"][WorkBench]\n'
        "        \n"
        "        # CopyDict = {}\n"
        '        # for WorkBench in self.workBenchDict["workbenches"].keys():\n',
    ),
    (
        "        JsonFile = Parameters.RIBBON_STRUCTURE_JSON\n"
        '        with open(JsonFile, "w") as outfile:\n'
        "            json.dump(self.ribbonStructure, outfile, indent=4)\n"
        "                \n"
        "        # Close the temporary document\n"
        "        try:\n",
        "        JsonFile = Parameters.RIBBON_STRUCTURE_JSON\n"
        '        with open(JsonFile, "w") as outfile:\n'
        "            json.dump(self.ribbonStructure, outfile, indent=4)\n"
        "        try:\n"
        "            import fmf_bootstrap\n"
        "\n"
        "            fmf_bootstrap.record_customization(self.ribbonStructure)\n"
        "        except (ImportError, AttributeError):\n"
        "            # FreeCAD-Ribbon is also usable without FMF.\n"
        "            pass\n"
        "                \n"
        "        # Close the temporary document\n"
        "        try:\n",
    ),
    (
        '    AddCommand_ActionData = ""\n'
        "    AddCommand_Icon = None\n"
        '    AddCommand_Text = ""\n'
        "    \n"
        "    def dragEnterEvent(self, event: QDragEnterEvent):         \n"
        "        if self.CustomizeEnabled is True:\n"
        "            if self.dragIndicator_QuickAccess is None:\n"
        '                self.dragIndicator_QuickAccess = DragTargetIndicator(orientation="right")\n'
        "            \n",
        '    AddCommand_ActionData = ""\n'
        "    AddCommand_Icon = None\n"
        '    AddCommand_Text = ""\n'
        "\n"
        "    def _ensureDirectDragState(self):\n"
        '        """Use the live ribbon structure as the editable model for direct dragging."""\n'
        '        if self.workBenchDict.get("workbenches") is self.ribbonStructure.get("workbenches"):\n'
        "            return\n"
        "        for key in (\n"
        '            "workbenches",\n'
        '            "quickAccessCommands",\n'
        '            "newPanels",\n'
        '            "dropdownButtons",\n'
        '            "ignoredToolbars",\n'
        '            "ignoredWorkbenches",\n'
        '            "iconOnlyToolbars",\n'
        '            "customToolbars",\n'
        '            "authoritativeWorkbenches",\n'
        "        ):\n"
        "            if key in self.ribbonStructure:\n"
        "                self.workBenchDict[key] = self.ribbonStructure[key]\n"
        "\n"
        "    def _saveDirectDragState(self):\n"
        '        """Persist a completed drop immediately; direct manipulation has no edit mode."""\n'
        '        self.ribbonStructure["workbenches"] = self.workBenchDict["workbenches"]\n'
        '        self.ribbonStructure["quickAccessCommands"] = self.workBenchDict.get(\n'
        '            "quickAccessCommands", []\n'
        "        )\n"
        '        for workbench in self.workBenchDict.get("authoritativeWorkbenches", []):\n'
        '            toolbars = self.workBenchDict["workbenches"].get(workbench, {}).get("toolbars", {})\n'
        "            for toolbar in toolbars.values():\n"
        "                if not isinstance(toolbar, dict):\n"
        "                    continue\n"
        '                order = list(toolbar.get("order", []))\n'
        '                if "panelMenu" in toolbar:\n'
        '                    toolbar["panelMenu"] = list(order)\n'
        '                if "pinCount" in toolbar:\n'
        '                    pinCount = max(0, min(int(toolbar["pinCount"]), len(order)))\n'
        '                    pinned = [item for item in order if item not in toolbar.get("overflow", [])]\n'
        '                    toolbar["overflow"] = [\n'
        "                        item for item in order if item not in pinned[:pinCount]\n"
        "                    ]\n"
        '        with open(Parameters.RIBBON_STRUCTURE_JSON, "w") as outfile:\n'
        "            json.dump(self.ribbonStructure, outfile, indent=4)\n"
        "        try:\n"
        "            import fmf_bootstrap\n"
        "\n"
        "            fmf_bootstrap.record_customization(self.ribbonStructure)\n"
        "        except (ImportError, AttributeError):\n"
        "            pass\n"
        "\n"
        "    def _resetOnePanel(self, panel):\n"
        '        """Restore one FMF panel while retaining every other customization."""\n'
        "        try:\n"
        "            import fmf_bootstrap\n"
        "\n"
        "            workbenchName = self.tabBar().tabData(self.tabBar().currentIndex())\n"
        "            panelName = panel.objectName()\n"
        "            ribbon = fmf_bootstrap.reset_panel_customization(workbenchName, panelName)\n"
        "            self.ribbonStructure.clear()\n"
        "            self.ribbonStructure.update(ribbon)\n"
        "            self.workBenchDict.clear()\n"
        "            self._ensureDirectDragState()\n"
        "            replacement = self.CreatePanel(\n"
        "                workbenchName,\n"
        "                panelName,\n"
        "                addPanel=False,\n"
        "                Dict=self.workBenchDict,\n"
        "                ignoreColumnLimit=False,\n"
        "                showEnableControl=False,\n"
        "                enableSeparator=False,\n"
        "                ActivateButtons=True,\n"
        "            )\n"
        "            self._fmfReplacePanel(self.currentCategory(), panel, replacement)\n"
        "            self.setPanelProperties(replacement)\n"
        "            App.Console.PrintMessage(\n"
        '                "FMF reset the {} panel.\\n".format(replacement.title())\n'
        "            )\n"
        "        except (ImportError, AttributeError):\n"
        "            return\n"
        "    \n"
        "    def dragEnterEvent(self, event: QDragEnterEvent):         \n"
        "        self._ensureDirectDragState()\n"
        "        if self.CustomizeEnabled is True or self.workBenchDict:\n"
        "            if self.dragIndicator_QuickAccess is None:\n"
        '                self.dragIndicator_QuickAccess = DragTargetIndicator(orientation="right")\n'
        "            \n",
        1,
        "    def _ensureDirectDragState(self):\n",
    ),
    (
        "        return\n"
        "                       \n"
        "    def dragLeaveEvent(self, event: QDragLeaveEvent):\n"
        "        if self.CustomizeEnabled is True:\n"
        "            # Hide the drag indicator when you leave the drag area\n"
        "            self.dragIndicator_Buttons.close()\n"
        "            self.dragIndicator_Panels.close()\n",
        "        return\n"
        "                       \n"
        "    def dragLeaveEvent(self, event: QDragLeaveEvent):\n"
        "        if self.CustomizeEnabled is True or self.workBenchDict:\n"
        "            # Hide the drag indicator when you leave the drag area\n"
        "            self.dragIndicator_Buttons.close()\n"
        "            self.dragIndicator_Panels.close()\n",
    ),
    (
        "        return\n"
        "     \n"
        "    def dragMoveEvent(self, event: QDragMoveEvent):\n"
        "        if self.CustomizeEnabled is True:\n"
        "            widget = event.source()\n"
        "            \n"
        "             # If you drag and drop a new command, you actually dragging the complete QListWidget\n",
        "        return\n"
        "     \n"
        "    def dragMoveEvent(self, event: QDragMoveEvent):\n"
        "        self._ensureDirectDragState()\n"
        "        if self.CustomizeEnabled is True or self.workBenchDict:\n"
        "            widget = event.source()\n"
        "            \n"
        "             # If you drag and drop a new command, you actually dragging the complete QListWidget\n",
    ),
    (
        "                                    control = gridLayout.itemAt(n).widget().findChild(CustomControls)\n"
        "                                    separator = gridLayout.itemAt(n).widget().findChild(CustomSeparator)\n"
        "                                    if control is not None and type(control) is CustomControls:\n"
        "                                        OrderList_Compare.append(self.ReturnCommand_string(Dict=self.workBenchDict, panel=panel, widget=control))\n"
        "                                    if separator is not None and type(separator) is CustomSeparator:\n"
        "                                        OrderList_Compare.append(separator.objectName())\n"
        "                                if OrderList != OrderList_Compare:\n"
        "                                    OrderList = OrderList_Compare\n"
        "                                \n"
        "                                # Get the indexes of the widgets\n"
        "                                index_originalWidget = OrderList.index(self.ReturnCommand_string(Dict=self.workBenchDict, panel=panel, widget=OriginalWidget)) # This is the location were will be dropped\n"
        "                                if DraggedWidget is not None:\n"
        "                                    index_newWidget = OrderList.index(self.ReturnCommand_string(Dict=self.workBenchDict, panel=panel, widget=DraggedWidget)) # This is the original location of the dragged widget                                                        \n",
        "                                    control = gridLayout.itemAt(n).widget().findChild(CustomControls)\n"
        "                                    separator = gridLayout.itemAt(n).widget().findChild(CustomSeparator)\n"
        "                                    if control is not None and type(control) is CustomControls:\n"
        "                                        OrderList_Compare.append(self.ReturnCommand_string(Dict=self.workBenchDict, panel=panel, widget=control))\n"
        "                                    if separator is not None and type(separator) is CustomSeparator:\n"
        "                                        OrderList_Compare.append(separator.objectName())\n"
        '                                if OrderList != OrderList_Compare and not self.workBenchDict["workbenches"][workbenchName]["toolbars"][title].get("overflow"):\n'
        "                                    OrderList = OrderList_Compare\n"
        "                                \n"
        "                                # Get the indexes of the widgets\n"
        "                                index_originalWidget = OrderList.index(self.ReturnCommand_string(Dict=self.workBenchDict, panel=panel, widget=OriginalWidget)) # This is the location were will be dropped\n"
        "                                if DraggedWidget is not None:\n"
        "                                    index_newWidget = OrderList.index(self.ReturnCommand_string(Dict=self.workBenchDict, panel=panel, widget=DraggedWidget)) # This is the original location of the dragged widget                                                        \n",
    ),
    (
        "                                                            \n"
        "                        # Create a new panel\n"
        "                        workbenchName = self.tabBar().tabData(self.tabBar().currentIndex())\n"
        "                        newPanel = self.CreatePanel(workbenchName, panel.objectName(), addPanel=False, Dict=self.workBenchDict, ignoreColumnLimit=True, showEnableControl=True, enableSeparator=True, ActivateButtons=True)\n"
        "                                                \n"
        "                        # Add the panel to the list with long panels\n"
        "                        if newPanel.panelOptionButton().isVisible():\n",
        "                                                            \n"
        "                        # Create a new panel\n"
        "                        workbenchName = self.tabBar().tabData(self.tabBar().currentIndex())\n"
        "                        newPanel = self.CreatePanel(workbenchName, panel.objectName(), addPanel=False, Dict=self.workBenchDict, ignoreColumnLimit=False, showEnableControl=False, enableSeparator=False, ActivateButtons=True)\n"
        "                                                \n"
        "                        # Add the panel to the list with long panels\n"
        "                        if newPanel.panelOptionButton().isVisible():\n",
    ),
    (
        "                        \n"
        "                        # Enable all buttons, so you can access them with a right click\n"
        "                        self.activateButtons()\n"
        "                        \n"
        "                        event.accept()\n"
        "                        return\n",
        "                        \n"
        "                        # Enable all buttons, so you can access them with a right click\n"
        "                        self.activateButtons()\n"
        "                        self._saveDirectDragState()\n"
        "                        \n"
        "                        event.accept()\n"
        "                        return\n",
    ),
    (
        "                \n"
        "                # Close the drag indicator\n"
        "                self.dragIndicator_Panels.close()\n"
        "            except Exception as e:\n"
        "                if Parameters.DEBUG_MODE:\n"
        "                    print(e.with_traceback(e.__traceback__))\n",
        "                \n"
        "                # Close the drag indicator\n"
        "                self.dragIndicator_Panels.close()\n"
        "                self._saveDirectDragState()\n"
        "            except Exception as e:\n"
        "                if Parameters.DEBUG_MODE:\n"
        "                    print(e.with_traceback(e.__traceback__))\n",
    ),
    (
        "\n"
        "        workbench = Gui.getWorkbench(workbenchName)\n"
        "        # Get the list of toolbars from the active workbench\n"
        "        ListToolbars: list = workbench.listToolbars()\n"
        "        # Get custom toolbars that are created in the toolbar environment and add them to the list of toolbars\n"
        "        CustomToolbars = self.List_ReturnCustomToolbars()\n"
        "        for CustomToolbar in CustomToolbars:\n",
        "\n"
        "        workbench = Gui.getWorkbench(workbenchName)\n"
        "        # Get the list of toolbars from the active workbench\n"
        "        # FMF can provide a complete replacement for selected\n"
        "        # workbenches.  In that case do not rediscover native toolbars and\n"
        "        # append them after the configured panels.\n"
        '        if workbenchName in Dict.get("authoritativeWorkbenches", []):\n'
        "            ListToolbars: list = []\n"
        "        else:\n"
        "            ListToolbars: list = workbench.listToolbars()\n"
        "        # Get custom toolbars that are created in the toolbar environment and add them to the list of toolbars\n"
        "        CustomToolbars = self.List_ReturnCustomToolbars()\n"
        "        for CustomToolbar in CustomToolbars:\n",
    ),
    (
        '                OrderList: list = Dict["workbenches"][\n'
        "                    workbenchName\n"
        '                ]["toolbars"][panelName]["order"]\n'
        "                \n"
        "                # XXX check that positionsList consists of strings only\n"
        "                def sortButtons(button: QToolButton):\n",
        '                OrderList: list = Dict["workbenches"][\n'
        "                    workbenchName\n"
        '                ]["toolbars"][panelName]["order"]\n'
        "                # FreeCAD-Ribbon can prune commands that register after its\n"
        "                # initial toolbar scan. FMF's complete panelMenu remains the\n"
        "                # authoritative order and prevents late commands such as\n"
        "                # Create Sketch from wandering to the right edge.\n"
        '                if workbenchName in Dict.get("authoritativeWorkbenches", []):\n'
        '                    panelMenuOrder = Dict["workbenches"][workbenchName]["toolbars"][\n'
        "                        panelName\n"
        '                    ].get("panelMenu", [])\n'
        "                    if panelMenuOrder:\n"
        "                        OrderList = list(panelMenuOrder)\n"
        '                        Dict["workbenches"][workbenchName]["toolbars"][panelName][\n'
        '                            "order"\n'
        "                        ] = list(OrderList)\n"
        "                \n"
        "                # XXX check that positionsList consists of strings only\n"
        "                def sortButtons(button: QToolButton):\n",
    ),
    (
        "        # Set the maximum columns\n"
        "        maxColumns = Parameters.MAX_COLUMN_PANELS\n"
        "\n"
        "        # Define an action list of the actions that are byond the maximum columns\n"
        "        ButtonList = []\n"
        "\n"
        "        # Go through the button list:\n"
        "        for i in range(len(allButtons)):\n"
        "            button = allButtons[i]\n"
        "            CommandName = button.objectName()\n"
        "            \n"
        "            # count the number of buttons per type. Needed for proper sorting the buttons later.\n"
        '            buttonSize = "small"\n',
        "        # Set the maximum columns\n"
        "        maxColumns = Parameters.MAX_COLUMN_PANELS\n"
        "\n"
        "        # Define an action list of the actions that are beyond the maximum columns\n"
        "        ButtonList = []\n"
        "        PanelMenuButtons = []\n"
        "        panelDefinition = (\n"
        '            Dict.get("workbenches", {})\n'
        "            .get(workbenchName, {})\n"
        '            .get("toolbars", {})\n'
        "            .get(panelName, {})\n"
        "        )\n"
        '        explicitPanelMenu = set(panelDefinition.get("panelMenu", []))\n'
        '        explicitOverflow = set(panelDefinition.get("overflow", []))\n'
        '        responsiveCommands = panelDefinition.get("responsive", {})\n'
        "\n"
        "        # Go through the button list:\n"
        "        for i in range(len(allButtons)):\n"
        "            button = allButtons[i]\n"
        "            CommandName = button.objectName()\n"
        "\n"
        "            if CommandName in explicitPanelMenu:\n"
        "                PanelMenuButtons.append(button)\n"
        "            \n"
        "            # count the number of buttons per type. Needed for proper sorting the buttons later.\n"
        '            buttonSize = "small"\n',
        1,
        "        # Define an action list of the actions that are beyond the maximum columns\n",
    ),
    (
        "            elif shadowList.__contains__(CommandName) is True:                \n"
        "                continue\n"
        "            else:\n"
        "                # If the number of columns is more than allowed,\n"
        "                # Add the actions to the OptionPanel instead.\n"
        "                if maxColumns > 0 and ignoreColumnLimit is False:\n",
        "            elif shadowList.__contains__(CommandName) is True:                \n"
        "                continue\n"
        "            else:\n"
        "                # Explicit overflow is the user-facing command inventory for a\n"
        "                # panel. Ignore it only while arranging, when the complete panel\n"
        "                # must be visible and draggable.\n"
        "                minimumResponsiveWidth = responsiveCommands.get(CommandName)\n"
        "                responsiveVisible = False\n"
        "                try:\n"
        "                    responsiveVisible = (\n"
        "                        minimumResponsiveWidth is not None\n"
        "                        and mw.width() >= int(minimumResponsiveWidth)\n"
        "                    )\n"
        "                except (TypeError, ValueError):\n"
        "                    pass\n"
        "                if (\n"
        "                    CommandName in explicitOverflow\n"
        "                    and not responsiveVisible\n"
        "                    and ignoreColumnLimit is False\n"
        "                ):\n"
        "                    ButtonList.append(button)\n"
        "                    panel.panelOptionButton().show()\n"
        "                    continue\n"
        "                # If the number of columns is more than allowed,\n"
        "                # Add the actions to the OptionPanel instead.\n"
        "                if maxColumns > 0 and ignoreColumnLimit is False:\n",
        1,
        "                # Explicit overflow is the user-facing command inventory for a\n",
    ),
    (
        "            EnableControl.setHidden(True)\n"
        "\n"
        "        # Setup the panelOptionButton\n"
        "        panel = self.PopulateOverflowMenu(panel, ButtonList)\n"
        "                \n"
        "        # Add a spacer. Otherwise alignment of a panel with one button will always be to the top\n"
        "        # if len(allButtons) == 1:\n",
        "            EnableControl.setHidden(True)\n"
        "\n"
        "        # Setup the panelOptionButton\n"
        "        panel = self.PopulateOverflowMenu(\n"
        "            panel, PanelMenuButtons if explicitPanelMenu else ButtonList\n"
        "        )\n"
        "                \n"
        "        # Add a spacer. Otherwise alignment of a panel with one button will always be to the top\n"
        "        # if len(allButtons) == 1:\n",
    ),
    (
        "            Menu = CustomControls.CustomOptionMenu(\n"
        "                OptionButton.menu(), actionList, self\n"
        "            )\n"
        "            OptionButton.setMenu(Menu)\n"
        "            StyleSheet_Menu = (\n"
        '                "* {font-size: " + str(Parameters.FONTSIZE_MENUS) + "px;}"\n',
        "            Menu = CustomControls.CustomOptionMenu(\n"
        "                OptionButton.menu(), actionList, self\n"
        "            )\n"
        "            workbenchName = self.tabBar().tabData(self.tabBar().currentIndex())\n"
        '            if workbenchName in self.ribbonStructure.get("authoritativeWorkbenches", []):\n'
        "                Menu.addSeparator()\n"
        "                resetAction = Menu.addAction(\n"
        '                    translate("FreeCAD Ribbon", "Reset this panel")\n'
        "                )\n"
        "                resetAction.triggered.connect(lambda checked=False, item=panel: self._resetOnePanel(item))\n"
        "            OptionButton.setMenu(Menu)\n"
        "            StyleSheet_Menu = (\n"
        '                "* {font-size: " + str(Parameters.FONTSIZE_MENUS) + "px;}"\n',
    ),
)


# Order matters within a file: the patches recovered from the old vendor snapshot
# run first, because the hooks below were written against a tree that already had
# them and anchor on lines they restore.
LOCAL_PATCHES = (
    (
        ("SearchBar", "SearchBox.py"),
        SEARCH_BOX_FMF_PATCH,
    ),
    (
        ("SearchBar", "InitGui.py"),
        SEARCHBAR_EVENT_FILTER_PATCH,
    ),
    (
        ("SearchBar", "RefreshTools.py"),
        SEARCHBAR_DISCOVERY_PATCH,
    ),
    (
        ("SearchBar", "ResultsToolbar.py"),
        SEARCH_RESULTS_COMMAND_ID_PATCH,
    ),
    (
        ("FreeCAD-Ribbon", "Resources", "packages", "pyqtribbon_local", "panel.py"),
        PANEL_NUMPY_PATCH + PANEL_TITLE_DRAWER_PATCH + PANEL_DIVIDER_PATCH,
    ),
    (
        ("FreeCAD-Ribbon", "FCBinding.py"),
        FCBINDING_TRANSITION_PATCH
        + FCBINDING_INTEGRATION_PATCH
        + FCBINDING_DIVIDER_PATCH
        + FCBINDING_OVERFLOW_PATCH
        + FCBINDING_ACTIVATE_PATCH
        + FCBINDING_EMPTY_DROPDOWN_PATCH
        + FCBINDING_WORKBENCH_FAMILY_PATCH
        + FCBINDING_UI_LATENCY_PATCH
        + FCBINDING_FOCUS_PATCH
        + FCBINDING_HOST_ISOLATION_PATCH
        + FCBINDING_ACTION_BINDING_PATCH
        + FCBINDING_PASSIVE_TRANSITION_PATCH,
    ),
    (
        ("FreeCAD-Ribbon", "InitGui.py"),
        RIBBON_INIT_TRANSITION_PATCH,
    ),
    (
        ("FreeCAD-Ribbon", "CustomWidgets.py"),
        CUSTOM_WIDGETS_DRAG_THRESHOLD_PATCH + CUSTOM_WIDGETS_DRAG_PATCH,
    ),
    (
        ("FreeCAD-Ribbon", "CacheFunctions.py"),
        CACHE_FUNCTIONS_PATCH,
    ),
    (
        ("FreeCAD-Ribbon", "Standard_Functions_Ribbon.py"),
        STANDARD_FUNCTIONS_COLOUR_PATCH
        + STANDARD_FUNCTIONS_ICON_PATCH
        + STANDARD_FUNCTIONS_NATIVE_ICON_PATCH,
    ),
    (
        ("FreeCAD-Ribbon", "Parameters_Ribbon.py"),
        PARAMETERS_ICON_SIZE_PATCH,
    ),
)


def preserve_fmf_files() -> dict[tuple, bytes]:
    """Read the files FMF owns before the bundled tree is replaced."""
    saved = {}
    for parts in FMF_OWNED_FILES:
        path = DESTINATION_ROOT.joinpath(*parts)
        if not path.is_file():
            raise RuntimeError(
                "{} is missing. It is FMF's own file and cannot be "
                "recovered from upstream; restore it from git before syncing.".format(path)
            )
        saved[parts] = path.read_bytes()
    return saved


def restore_fmf_files(saved: dict[tuple, bytes]) -> None:
    """Put FMF's own files back after the bundled tree is replaced."""
    for parts, content in saved.items():
        path = DESTINATION_ROOT.joinpath(*parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


def line_run(lines: list[str], block: list[str]) -> int:
    """How many times `block` occurs in `lines` as a run of whole lines."""
    if not block:
        return 0
    span = len(block)
    return sum(1 for start in range(len(lines) - span + 1) if lines[start : start + span] == block)


def patch_is_applied(
    text: str,
    lines: list[str],
    anchor: str,
    replacement: str,
    expected: int,
    proof: str | None = None,
) -> bool:
    """Whether this patch has already been made to `text`.

    The evidence is the replacement standing in the file as a run of whole
    lines, once per site the patch covers.

    Substring tests are not safe here. Upstream repeats the same drag handler at
    two indentation levels, so the shallower patch's text is a substring of the
    deeper one's, and checking `replacement in text` let an applied patch mask an
    unapplied one -- four of the five drag sites were silently skipped that way.
    Comparing whole lines keeps the two apart, because the indentation is part of
    the line.

    Looking for a single line the patch introduces is not safe either: several
    patches add a call that upstream already makes somewhere else in the same
    file, and that line would read as "already applied" before the patch had run
    even once.

    A patch that only deletes introduces nothing, but its replacement is the
    surrounding context with the removed lines gone, which is a run that appears
    only once the deletion has been made.

    Where that is genuinely impossible -- a later patch editing inside code this
    one introduces, so the run is broken by design -- the patch names a `proof`
    line instead: one line only it can have put there.
    """
    if proof is not None:
        return proof in lines
    block = replacement.splitlines(keepends=True)
    anchor_lines = set(anchor.splitlines(keepends=True))
    if not [line for line in block if line.strip() and line not in anchor_lines]:
        # A patch that only deletes leaves a replacement that is part of its own
        # anchor, so the run matches whether or not the patch has run. What it
        # removes being gone is the only evidence there is.
        return anchor not in text
    return line_run(lines, block) == expected


def apply_local_patches() -> list[str]:
    """Re-apply every hook FMF adds to upstream's own modules.

    Each patch is skipped when it is already applied, so running the sync twice
    is harmless. A missing anchor raises rather than silently shipping a ribbon
    with the behaviour quietly removed.
    """
    applied = []
    for parts, patches in LOCAL_PATCHES:
        path = DESTINATION_ROOT.joinpath(*parts)
        text = path.read_text(encoding="utf-8")
        for patch in patches:
            # A patch is (anchor, replacement); (anchor, replacement, count) where
            # upstream repeats the same code, as the drag handlers do; or
            # (anchor, replacement, count, proof) where a later patch edits inside
            # this one's replacement and `proof` is the line that shows it ran.
            anchor, replacement = patch[0], patch[1]
            expected = patch[2] if len(patch) > 2 else 1
            proof = patch[3] if len(patch) > 3 else None
            if patch_is_applied(
                text, text.splitlines(keepends=True), anchor, replacement, expected, proof
            ):
                continue
            if text.count(anchor) != expected:
                raise RuntimeError(
                    "{} holds {} copies of a FMF anchor, expected {}. "
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
