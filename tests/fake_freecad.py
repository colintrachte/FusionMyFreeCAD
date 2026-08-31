"""A minimal in-process stand-in for the FreeCAD, FreeCADGui, and PySide APIs.

FusionMyFreeCAD cannot be imported without FreeCAD, and FreeCAD cannot be run
headlessly in CI. These fakes implement just enough of the real API surface for
the add-on's own logic to execute unchanged, so tests assert on behaviour rather
than on the text of the source file.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from typing import ClassVar

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# FreeCAD parameters
# ---------------------------------------------------------------------------


class ParameterGroup:
    """Mimics FreeCAD's ParameterGrp Get/Set/Rem accessors."""

    def __init__(self):
        self.values = {"String": {}, "Bool": {}, "Int": {}, "Float": {}}

    def __getattr__(self, name):
        if (
            name.startswith("Get")
            and name.endswith("s")
            and name[3:-1] in ("String", "Bool", "Int", "Float")
        ):
            kind = name[3:-1]
            return lambda: list(self.values[kind])
        if name.startswith("Get") and name[3:] in self.values:
            kind = name[3:]
            return lambda key, default=None: self.values[kind].get(key, default)
        if name.startswith("Set") and name[3:] in self.values:
            kind = name[3:]
            return lambda key, value: self.values[kind].__setitem__(key, value)
        if name.startswith("Rem") and name[3:] in self.values:
            kind = name[3:]
            return lambda key: self.values[kind].pop(key, None)
        raise AttributeError(name)


class Console:
    def __init__(self):
        self.messages = []
        self.warnings = []
        self.errors = []
        self.log = []

    def PrintMessage(self, text):
        self.messages.append(text)

    def PrintWarning(self, text):
        self.warnings.append(text)

    def PrintError(self, text):
        self.errors.append(text)

    def PrintLog(self, text):
        self.log.append(text)


# ---------------------------------------------------------------------------
# FreeCAD documents
# ---------------------------------------------------------------------------


class FakeObject:
    def __init__(self, type_name, name):
        self.TypeId = type_name
        self.Name = name
        self.Label = name

    def isDerivedFrom(self, type_name):
        return type_name == self.TypeId


class FakeSheet(FakeObject):
    def __init__(self, name):
        super().__init__("Spreadsheet::Sheet", name)
        self.cells = {}
        self.styles = []
        self.widths = {}

    def set(self, cell, value):
        self.cells[cell] = value

    def setStyle(self, *arguments):
        self.styles.append(arguments)

    def setColumnWidth(self, column, width):
        self.widths[column] = width


class FakeDocument:
    def __init__(self):
        self.Name = "Untitled"
        self.Objects = []
        self.recomputes = 0

    def addObject(self, type_name, name):
        obj = FakeSheet(name) if type_name == "Spreadsheet::Sheet" else FakeObject(type_name, name)
        self.Objects.append(obj)
        return obj

    def recompute(self):
        self.recomputes += 1


# ---------------------------------------------------------------------------
# Qt
# ---------------------------------------------------------------------------


class FakeTimer:
    """Collects deferred callbacks so tests can run them deterministically."""

    queue: ClassVar[list] = []

    @classmethod
    def singleShot(cls, _delay, callback):
        cls.queue.append(callback)

    @classmethod
    def pump(cls, rounds=25):
        """Run queued callbacks, including any they schedule, to a bounded depth."""
        for _ in range(rounds):
            if not cls.queue:
                return
            pending, cls.queue = cls.queue, []
            for callback in pending:
                callback()

    @classmethod
    def reset(cls):
        cls.queue = []


class FakeKeySequence:
    def __init__(self, value=""):
        if isinstance(value, FakeKeySequence):
            value = value.toString()
        self._value = (value or "").strip()

    def toString(self):
        return self._value

    def __eq__(self, other):
        return isinstance(other, FakeKeySequence) and other._value == self._value

    def __repr__(self):
        return "FakeKeySequence({!r})".format(self._value)


class Signal:
    def __init__(self):
        self.handlers = []

    def connect(self, handler):
        self.handlers.append(handler)

    def emit(self, *arguments):
        for handler in list(self.handlers):
            handler(*arguments)


class FakeAction:
    def __init__(self, name, shortcut="", text=""):
        self._name = name
        self._text = text or name
        self._shortcut = FakeKeySequence(shortcut)
        self._context = None
        self._properties = {}
        self.triggered = Signal()

    def objectName(self):
        return self._name

    def text(self):
        return self._text

    def shortcut(self):
        return self._shortcut

    def setShortcut(self, sequence):
        self._shortcut = FakeKeySequence(sequence)

    def setShortcutContext(self, context):
        self._context = context

    def property(self, key):
        return self._properties.get(key)

    def setProperty(self, key, value):
        self._properties[key] = value


class FakeDock:
    def __init__(self, object_name="", window_title=""):
        self._object_name = object_name
        self._window_title = window_title
        self.visible = False
        self.raised = False
        self._width = 100
        self.tabs = None

    def objectName(self):
        return self._object_name

    def windowTitle(self):
        return self._window_title

    def show(self):
        self.visible = True

    def hide(self):
        self.visible = False

    def raise_(self):
        self.raised = True

    def width(self):
        return self._width

    def height(self):
        return 400

    def resize(self, width, _height):
        self._width = width

    def findChild(self, _type):
        return self.tabs


class FakeTabWidget:
    def __init__(self, labels):
        self.labels = labels
        self.current = 0

    def count(self):
        return len(self.labels)

    def tabText(self, index):
        return self.labels[index]

    def setCurrentIndex(self, index):
        self.current = index


class FakeMainWindow:
    def __init__(self):
        self.actions = []
        self.docks = []
        self.areas = {}
        self.workbenchActivated = Signal()
        self._menu_shown = False

    def menuBar(self):
        window = self

        class MenuBar:
            def show(self):
                window._menu_shown = True

        return MenuBar()

    def findChildren(self, kind):
        if kind is FakeAction:
            return list(self.actions)
        if kind is FakeDock:
            return list(self.docks)
        return []

    def dockWidgetArea(self, dock):
        return self.areas.get(id(dock), "right")

    def addDockWidget(self, area, dock):
        self.areas[id(dock)] = area


def _qt_modules():
    qtcore = types.ModuleType("PySide.QtCore")
    qtcore.QTimer = FakeTimer
    qtcore.Qt = types.SimpleNamespace(LeftDockWidgetArea="left", ApplicationShortcut="application")

    qtgui = types.ModuleType("PySide.QtGui")
    qtgui.QKeySequence = FakeKeySequence
    qtgui.QAction = FakeAction

    qtwidgets = types.ModuleType("PySide.QtWidgets")
    qtwidgets.QDockWidget = FakeDock
    qtwidgets.QTabWidget = FakeTabWidget
    qtwidgets.QToolBar = type("QToolBar", (), {})
    qtwidgets.QAction = FakeAction

    pyside = types.ModuleType("PySide")
    pyside.QtCore = qtcore
    pyside.QtGui = qtgui
    pyside.QtWidgets = qtwidgets
    return pyside, qtcore, qtgui, qtwidgets


# ---------------------------------------------------------------------------
# Environment assembly
# ---------------------------------------------------------------------------


class Environment:
    """A complete fake FreeCAD session bound to one temporary user directory."""

    def __init__(self, user_root: Path, version=("1", "1", "3")):
        self.user_root = Path(user_root)
        self.user_root.mkdir(parents=True, exist_ok=True)
        self.groups = {}
        self.commands = {}
        self.gui_events = []
        self.console = Console()
        self.main_window = FakeMainWindow()
        self.registered_commands = ["Std_ViewFitAll", "Std_Measure"]
        self.active_workbench = "PartDesignWorkbench"
        self.saved_parameters = 0

        app = types.ModuleType("FreeCAD")
        app.Version = lambda: version
        app.getUserAppDataDir = lambda: str(self.user_root) + "/"
        app.ParamGet = lambda path: self.groups.setdefault(path, ParameterGroup())
        app.saveParameter = self._save_parameter
        app.Console = self.console
        app.ActiveDocument = None
        app.newDocument = self._new_document
        self.app = app

        gui = types.ModuleType("FreeCADGui")
        gui.getMainWindow = lambda: self.main_window
        gui.addCommand = lambda name, command: self.commands.__setitem__(name, command)
        self.preference_pages = []
        gui.addPreferencePage = lambda path, group: self.preference_pages.append((path, group))
        gui.activateWorkbench = self._activate_workbench
        gui.runCommand = lambda name: self.gui_events.append(("command", name))
        gui.listCommands = lambda: list(self.registered_commands)
        gui.activeWorkbench = lambda: types.SimpleNamespace(name=lambda: self.active_workbench)
        gui.ActiveDocument = None
        gui.Selection = types.SimpleNamespace(
            clearSelection=lambda: self.gui_events.append(("selection", "clear")),
            addSelection=lambda obj: self.gui_events.append(("selection", obj.Name)),
        )
        gui.activeDocument = lambda: types.SimpleNamespace(
            setEdit=lambda name: self.gui_events.append(("edit", name))
        )
        self.gui = gui

        self.pyside, self.qtcore, self.qtgui, self.qtwidgets = _qt_modules()

    def _save_parameter(self):
        self.saved_parameters += 1

    def _new_document(self):
        self.app.ActiveDocument = FakeDocument()
        return self.app.ActiveDocument

    def _activate_workbench(self, name):
        self.active_workbench = name
        self.gui_events.append(("workbench", name))

    def param(self, path):
        return self.groups.setdefault(path, ParameterGroup())

    def install(self):
        FakeTimer.reset()
        sys.modules["FreeCAD"] = self.app
        sys.modules["FreeCADGui"] = self.gui
        sys.modules["PySide"] = self.pyside
        sys.modules["PySide.QtCore"] = self.qtcore
        sys.modules["PySide.QtGui"] = self.qtgui
        sys.modules["PySide.QtWidgets"] = self.qtwidgets
        return self

    def load_bootstrap(self):
        """Import a fresh fusion_bootstrap bound to this environment."""
        for name in ("fusion_bootstrap", "_fusion_my_freecad_runtime"):
            sys.modules.pop(name, None)
        return _import_module("fusion_bootstrap", ROOT / "fusion_bootstrap.py")

    def load_runtime(self):
        """Import runtime.py without letting it wire itself into the session."""
        sys.modules.pop("_fusion_my_freecad_runtime", None)
        import os

        os.environ["FUSION_MY_FREECAD_NO_AUTOSTART"] = "1"
        try:
            return _import_module(
                "_fusion_my_freecad_runtime", ROOT / "Resources" / "FusionMyFreeCAD" / "runtime.py"
            )
        finally:
            os.environ.pop("FUSION_MY_FREECAD_NO_AUTOSTART", None)


def _import_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module
