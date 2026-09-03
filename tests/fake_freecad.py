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


class FakePlacement:
    def __init__(self, base=None, rotation=None):
        self.Base = base if base is not None else FakeVector(0.0, 0.0, 0.0)
        self.Rotation = rotation if rotation is not None else FakeRotation()


class FakeObject:
    def __init__(self, type_name, name):
        self.TypeId = type_name
        self.Name = name
        self.Label = name
        self.Placement = FakePlacement()

    def isDerivedFrom(self, type_name):
        return type_name == self.TypeId

    def getGlobalPlacement(self):
        return self.Placement


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
        self.transactions = []
        self.open_transaction = None

    def addObject(self, type_name, name):
        obj = FakeSheet(name) if type_name == "Spreadsheet::Sheet" else FakeObject(type_name, name)
        self.Objects.append(obj)
        return obj

    def recompute(self):
        self.recomputes += 1

    # Transactions: record the sequence so tests can assert one-step Undo.
    def openTransaction(self, label):
        self.open_transaction = label
        self.transactions.append(("open", label))

    def commitTransaction(self):
        self.transactions.append(("commit", self.open_transaction))
        self.open_transaction = None

    def abortTransaction(self):
        self.transactions.append(("abort", self.open_transaction))
        self.open_transaction = None


# ---------------------------------------------------------------------------
# Sketcher geometry, constraints, and a live sketch
# ---------------------------------------------------------------------------


class FakeVector:
    def __init__(self, x=0.0, y=0.0, z=0.0):
        if isinstance(x, (tuple, list)):
            self.x, self.y, self.z = float(x[0]), float(x[1]), float(x[2])
        elif hasattr(x, "x") and hasattr(x, "y") and hasattr(x, "z"):
            self.x, self.y, self.z = float(x.x), float(x.y), float(x.z)
        else:
            self.x, self.y, self.z = float(x), float(y), float(z)

    def __iter__(self):
        return iter((self.x, self.y, self.z))

    def __add__(self, other):
        return FakeVector(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other):
        return FakeVector(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, scalar):
        s = float(scalar)
        return FakeVector(self.x * s, self.y * s, self.z * s)

    def __rmul__(self, scalar):
        return self.__mul__(scalar)

    def __repr__(self):
        return f"FakeVector({self.x}, {self.y}, {self.z})"


class FakeRotation:
    def __init__(self, *args):
        self._q = tuple(args) if args else (0.0, 0.0, 0.0, 1.0)

    def multVec(self, vec):
        return vec

    @property
    def Q(self):
        return self._q


class FakeLineSegment:
    """Stand-in for Part.LineSegment inside a sketch."""

    def __init__(self, start, end, construction=False):
        self.TypeId = "Part::GeomLineSegment"
        self.StartPoint = FakeVector(*start)
        self.EndPoint = FakeVector(*end)
        self.Construction = construction

    def reflected(self, axis_a, axis_b):
        return FakeLineSegment(
            _reflect(self.StartPoint, axis_a, axis_b),
            _reflect(self.EndPoint, axis_a, axis_b),
            self.Construction,
        )


def _reflect(point, axis_a, axis_b):
    px, py = point.x, point.y
    ax, ay = axis_a
    bx, by = axis_b
    dx, dy = bx - ax, by - ay
    length_squared = dx * dx + dy * dy or 1.0
    t = ((px - ax) * dx + (py - ay) * dy) / length_squared
    foot_x, foot_y = ax + t * dx, ay + t * dy
    return (2.0 * foot_x - px, 2.0 * foot_y - py)


class FakePoint:
    """Stand-in for Part.Point inside a sketch."""

    def __init__(self, point, construction=False):
        self.TypeId = "Part::GeomPoint"
        self.X = float(point.x if hasattr(point, "x") else point[0])
        self.Y = float(point.y if hasattr(point, "y") else point[1])
        self.Z = float(point.z if hasattr(point, "z") else (point[2] if len(point) > 2 else 0.0))
        self.Construction = construction


class FakeConstraint:
    """Mimics Sketcher.Constraint(type, *args) argument handling."""

    def __init__(self, ctype, *args):
        self.Type = ctype
        self.First = -2000
        self.FirstPos = 0
        self.Second = -2000
        self.SecondPos = 0
        self.Third = -2000
        self.ThirdPos = 0
        self.Value = 0.0
        self.Name = ""
        self.Driving = True
        self.IsActive = True
        arguments = list(args)
        if ctype == "PointOnObject" and len(arguments) >= 3:
            self.First, self.FirstPos, self.Second = arguments[:3]
        elif ctype == "Symmetric":
            # (g1, p1, g2, p2, g3) about a line, or (g1, p1, g2, p2, g3, p3)
            # about a point.
            if len(arguments) >= 4:
                self.First, self.FirstPos, self.Second, self.SecondPos = arguments[:4]
            if len(arguments) >= 5:
                self.Third = arguments[4]
            if len(arguments) >= 6:
                self.ThirdPos = arguments[5]
        elif ctype == "Equal":
            if len(arguments) >= 2:
                self.First, self.Second = arguments[0], arguments[1]
        elif ctype in ("Coincident", "Tangent", "Perpendicular", "Parallel"):
            if len(arguments) >= 2:
                self.First, self.FirstPos = arguments[0], arguments[1]
            if len(arguments) >= 4:
                self.Second, self.SecondPos = arguments[2], arguments[3]
            elif len(arguments) == 3:
                self.Second = arguments[2]
        elif ctype in ("Horizontal", "Vertical", "Block"):
            if arguments:
                self.First = arguments[0]
            if len(arguments) >= 2:
                self.FirstPos = arguments[1]
        elif ctype in ("DistanceX", "DistanceY", "Distance", "Radius", "Diameter", "Angle"):
            if len(arguments) == 2:
                self.First, self.Value = arguments
            elif len(arguments) == 3:
                self.First, self.FirstPos, self.Value = arguments
            elif len(arguments) == 4:
                self.First, self.FirstPos, self.Second, self.Value = arguments
            elif len(arguments) == 5:
                (
                    self.First,
                    self.FirstPos,
                    self.Second,
                    self.SecondPos,
                    self.Value,
                ) = arguments


class FakeSketch(FakeObject):
    def __init__(self, name="Sketch"):
        super().__init__("Sketcher::SketchObject", name)
        self.Geometry = []
        self.Constraints = []
        self.Conflicting = []
        self.Redundant = []
        self.Malformed = []
        self.ConflictingConstraints = []
        self.RedundantConstraints = []
        self.MalformedConstraints = []
        self.PartiallyRedundantConstraints = []
        self.DoF = 0
        self.recomputes = 0
        self.solves = 0

    def addGeometry(self, geo, construction=False):
        if construction:
            geo.Construction = True
        self.Geometry.append(geo)
        return len(self.Geometry) - 1

    def setConstruction(self, index, value):
        if 0 <= index < len(self.Geometry):
            self.Geometry[index].Construction = bool(value)

    def getConstruction(self, index):
        if 0 <= index < len(self.Geometry):
            return getattr(self.Geometry[index], "Construction", False)
        return False

    def getGeoVertexIndex(self, index):
        count = 0
        for g_idx, _geo in enumerate(self.Geometry):
            for pos in (1, 2):
                if count == index:
                    return (g_idx, pos)
                count += 1
        return (-2000, 0)

    def getPoint(self, geo_id, pos_id):
        if 0 <= geo_id < len(self.Geometry):
            geo = self.Geometry[geo_id]
            if hasattr(geo, "X") and hasattr(geo, "Y"):
                return FakeVector(geo.X, geo.Y, getattr(geo, "Z", 0))
            if pos_id == 1:
                return getattr(geo, "StartPoint", FakeVector(0, 0, 0))
            elif pos_id == 2:
                return getattr(geo, "EndPoint", FakeVector(0, 0, 0))
            elif pos_id == 3:
                return getattr(geo, "Center", FakeVector(0, 0, 0))
        elif geo_id in (-1, -2) and pos_id in (0, 1):
            return FakeVector(0, 0, 0)
        return FakeVector(0, 0, 0)

    def addConstraint(self, constraint):
        self.Constraints.append(constraint)
        return len(self.Constraints) - 1

    def delConstraint(self, index):
        self.Constraints.pop(index)

    def renameConstraint(self, index, name):
        self.Constraints[index].Name = name

    def setDriving(self, index, value):
        self.Constraints[index].Driving = bool(value)

    def setActive(self, index, value):
        self.Constraints[index].IsActive = bool(value)

    def recompute(self):
        self.recomputes += 1
        self._refresh_rejections()

    def solve(self):
        self.solves += 1
        self._refresh_rejections()
        return 0

    def _refresh_rejections(self):
        """Re-evaluate solver diagnostics, like the real solver does each solve.

        Tests that set the lists directly leave the predicates unset and keep
        full control; tests that want type-driven diagnostics set
        ``sketch._reject`` (fully redundant), ``sketch._partial`` (partially
        redundant), or ``sketch._conflict`` (conflicting).
        """
        for attribute, name in (
            ("RedundantConstraints", "_reject"),
            ("PartiallyRedundantConstraints", "_partial"),
            ("ConflictingConstraints", "_conflict"),
        ):
            predicate = getattr(self, name, None)
            if predicate is None:
                continue
            setattr(
                self,
                attribute,
                [i for i, constraint in enumerate(self.Constraints) if predicate(constraint)],
            )

    def mirror_selected(self, source_indices, axis_a, axis_b):
        """Emulate native Symmetry: append reflected copies of the source edges
        and, like the real addSymmetric, reproduce their single-element
        orientation constraints onto the copies."""
        mapping = {}
        for source_id in sorted(source_indices):
            reflected = self.Geometry[source_id].reflected(axis_a, axis_b)
            mapping[source_id] = self.addGeometry(reflected)
        for source_id, mirror_id in mapping.items():
            for constraint in list(self.Constraints):
                if (
                    constraint.Type in ("Vertical", "Horizontal", "Block")
                    and constraint.First == source_id
                    and constraint.Second <= -2000
                    and constraint.Third <= -2000
                ):
                    self.addConstraint(FakeConstraint(constraint.Type, mirror_id))
        return mapping

    def addSymmetric(self, source_indices, reference_geoid, reference_pos):
        del reference_pos
        if reference_geoid == -1:
            axis = ((0.0, 0.0), (1.0, 0.0))
        elif reference_geoid == -2:
            axis = ((0.0, 0.0), (0.0, 1.0))
        else:
            points = self.Geometry[reference_geoid]
            axis = (
                (points.StartPoint.x, points.StartPoint.y),
                (points.EndPoint.x, points.EndPoint.y),
            )
        return list(self.mirror_selected(source_indices, *axis).values())


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


class FakeQtObject:
    def __init__(self, *_args, **_kwargs):
        pass


class FakeApplication:
    def __init__(self):
        self.filters = []
        self.focus_widget = None

    def installEventFilter(self, event_filter):
        self.filters.append(event_filter)


class FakeButton:
    def __init__(self, enabled=True):
        self.enabled = enabled
        self.clicks = 0

    def isEnabled(self):
        return self.enabled

    def click(self):
        self.clicks += 1


class FakeDialogButtonBox:
    AcceptRole = "accept"
    YesRole = "yes"
    RejectRole = "reject"

    def __init__(self, roles=(AcceptRole, RejectRole), visible=True):
        self.visible = visible
        self._buttons = [(FakeButton(), role) for role in roles]

    def isVisible(self):
        return self.visible

    def buttons(self):
        return [button for button, _role in self._buttons]

    def buttonRole(self, wanted):
        return next(role for button, role in self._buttons if button is wanted)


class FakeMainWindow:
    def __init__(self):
        self.actions = []
        self.docks = []
        self.button_boxes = []
        self.areas = {}
        self.workbenchActivated = Signal()
        self._menu_shown = False
        self.status_messages = []

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
        if kind is FakeDialogButtonBox:
            return list(self.button_boxes)
        return []

    def dockWidgetArea(self, dock):
        return self.areas.get(id(dock), "right")

    def addDockWidget(self, area, dock):
        self.areas[id(dock)] = area

    def statusBar(self):
        window = self

        class StatusBar:
            def showMessage(self, text, _timeout=0):
                window.status_messages.append(text)

        return StatusBar()


def _qt_modules():
    application = FakeApplication()

    qtcore = types.ModuleType("PySide.QtCore")
    qtcore.QTimer = FakeTimer
    qtcore.QObject = FakeQtObject
    qtcore.QEvent = types.SimpleNamespace(KeyPress="key-press")
    qtcore.Qt = types.SimpleNamespace(
        LeftDockWidgetArea="left",
        ApplicationShortcut="application",
        Key_Return="return",
        Key_Enter="enter",
    )

    qtgui = types.ModuleType("PySide.QtGui")
    qtgui.QKeySequence = FakeKeySequence
    qtgui.QAction = FakeAction

    qtwidgets = types.ModuleType("PySide.QtWidgets")
    qtwidgets.QDockWidget = FakeDock
    qtwidgets.QTabWidget = FakeTabWidget
    qtwidgets.QToolBar = type("QToolBar", (), {})
    qtwidgets.QAction = FakeAction
    qtwidgets.QDialogButtonBox = FakeDialogButtonBox
    qtwidgets.QApplication = types.SimpleNamespace(
        instance=lambda: application,
        focusWidget=lambda: application.focus_widget,
    )

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
        self.task_dialog_active = False
        self.saved_parameters = 0
        self.selection_ex = []
        self.command_handlers = {}
        self.document_observers = []

        app = types.ModuleType("FreeCAD")
        app.Version = lambda: version
        app.getUserAppDataDir = lambda: str(self.user_root) + "/"
        app.ParamGet = lambda path: self.groups.setdefault(path, ParameterGroup())
        app.saveParameter = self._save_parameter
        app.Console = self.console
        app.ActiveDocument = None
        app.newDocument = self._new_document
        app.addDocumentObserver = self.document_observers.append
        app.Vector = FakeVector
        app.Rotation = FakeRotation
        self.app = app

        gui = types.ModuleType("FreeCADGui")
        gui.getMainWindow = lambda: self.main_window
        gui.addCommand = lambda name, command: self.commands.__setitem__(name, command)
        self.preference_pages = []
        gui.addPreferencePage = lambda path, group: self.preference_pages.append((path, group))
        gui.addDocumentObserver = self.document_observers.append
        gui.activateWorkbench = self._activate_workbench
        gui.runCommand = self._run_command
        gui.listCommands = lambda: list(self.registered_commands)
        gui.activeWorkbench = lambda: types.SimpleNamespace(name=lambda: self.active_workbench)
        gui.Control = types.SimpleNamespace(activeDialog=lambda: self.task_dialog_active)
        gui.ActiveDocument = None
        self.selection_observers = []
        gui.Selection = types.SimpleNamespace(
            clearSelection=lambda: self.gui_events.append(("selection", "clear")),
            addSelection=lambda obj: self.gui_events.append(
                ("selection", getattr(obj, "Name", str(obj)))
            ),
            getSelectionEx=lambda *args: list(self.selection_ex),
            getSelection=lambda *args: [entry.Object for entry in self.selection_ex],
            addObserver=self.selection_observers.append,
        )
        gui.activeDocument = lambda: types.SimpleNamespace(
            setEdit=lambda name: self.gui_events.append(("edit", name))
        )
        self.gui = gui

        self.sketcher = types.ModuleType("Sketcher")
        self.sketcher.Constraint = FakeConstraint
        self.part = types.ModuleType("Part")
        self.part.LineSegment = FakeLineSegment
        self.part.Point = FakePoint

        self.pyside, self.qtcore, self.qtgui, self.qtwidgets = _qt_modules()

    def _run_command(self, name, *args):
        self.gui_events.append(("command", name))
        handler = self.command_handlers.get(name)
        if handler is not None:
            handler(*args)

    def begin_sketch_edit(self, sketch):
        """Put ``sketch`` into edit mode and make it the selection target."""
        if self.app.ActiveDocument is None:
            self._new_document()
        if sketch not in self.app.ActiveDocument.Objects:
            self.app.ActiveDocument.Objects.append(sketch)
        # FreeCAD is in the Sketcher workbench whenever a sketch is being edited.
        self.active_workbench = "SketcherWorkbench"
        self._in_edit = types.SimpleNamespace(Object=sketch)
        self.gui.ActiveDocument = types.SimpleNamespace(
            getInEdit=lambda: self._in_edit,
            ActiveView=types.SimpleNamespace(),
        )
        return sketch

    def select_subelements(self, sketch, sub_element_names):
        self.selection_ex = [
            types.SimpleNamespace(
                Object=sketch,
                ObjectName=getattr(sketch, "Name", "Sketch"),
                SubElementNames=list(sub_element_names),
            )
        ]

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
        sys.modules["Sketcher"] = self.sketcher
        sys.modules["Part"] = self.part
        return self

    def load_bootstrap(self):
        """Import a fresh fusion_bootstrap bound to this environment."""
        for name in ("fusion_bootstrap", "fusion_sketch_tools", "_fusion_my_freecad_runtime"):
            sys.modules.pop(name, None)
        return _import_module("fusion_bootstrap", ROOT / "fusion_bootstrap.py")

    def load_sketch_tools(self):
        """Import a fresh fusion_sketch_tools bound to this environment."""
        sys.modules.pop("fusion_sketch_tools", None)
        return _import_module("fusion_sketch_tools", ROOT / "fusion_sketch_tools.py")

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
