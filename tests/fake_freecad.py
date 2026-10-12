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
        self.values = {"String": {}, "Bool": {}, "Int": {}, "Float": {}, "Unsigned": {}}

    def __getattr__(self, name):
        if (
            name.startswith("Get")
            and name.endswith("s")
            and name[3:-1] in ("String", "Bool", "Int", "Float", "Unsigned")
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
        self.Reversed = False
        self.Length = 0.0
        self.Visibility = True

    def isDerivedFrom(self, type_name):
        return type_name == self.TypeId

    def isValid(self):
        return True

    def recompute(self):
        pass

    def getGlobalPlacement(self):
        return self.Placement


class FakeSheet(FakeObject):
    def __init__(self, name):
        super().__init__("Spreadsheet::Sheet", name)
        self.cells = {}
        self.aliases = {}
        self.styles = []
        self.widths = {}

    def set(self, cell, value):
        self.cells[cell] = value

    def get(self, cell):
        return self.cells.get(cell, None)

    def setAlias(self, cell, alias):
        self.aliases[cell] = alias

    def getAlias(self, cell):
        return self.aliases.get(cell, None)

    def setStyle(self, *arguments):
        self.styles.append(arguments)

    def setColumnWidth(self, column, width):
        self.widths[column] = width


class FakePlane(FakeObject):
    def __init__(self, name):
        super().__init__("PartDesign::Plane", name)
        self.AttachmentSupport = []
        self.MapMode = ""


class FakeBody(FakeObject):
    def __init__(self, name):
        super().__init__("PartDesign::Body", name)
        self.Group = []
        self.Tip = None

    def newObject(self, type_name, name):
        obj = FakePlane(name) if type_name == "PartDesign::Plane" else FakeObject(type_name, name)
        doc = getattr(self, "Document", None)
        obj.Document = doc
        self.Group.append(obj)
        self.Tip = obj
        if doc is not None and obj not in doc.Objects:
            doc.Objects.append(obj)
        return obj

    def addObject(self, obj):
        if obj not in self.Group:
            self.Group.append(obj)
        self.Tip = obj
        doc = getattr(self, "Document", None)
        if doc is not None and obj not in doc.Objects:
            doc.Objects.append(obj)
        if getattr(obj, "Document", None) is None:
            obj.Document = doc


class FakeDocument:
    def __init__(self):
        self.Name = "Untitled"
        self.Objects = []
        self.recomputes = 0
        self.transactions = []
        self._transaction_snapshot = []
        self.open_transaction = None

    def addObject(self, type_name, name):
        if type_name == "Spreadsheet::Sheet":
            obj = FakeSheet(name)
        elif type_name == "PartDesign::Body":
            obj = FakeBody(name)
        elif type_name == "PartDesign::Plane":
            obj = FakePlane(name)
        else:
            obj = FakeObject(type_name, name)
        obj.Document = self
        self.Objects.append(obj)
        return obj

    def getObject(self, name):
        for obj in self.Objects:
            if getattr(obj, "Name", None) == name or getattr(obj, "Label", None) == name:
                return obj
        return None

    def recompute(self):
        self.recomputes += 1

    # Transactions: record the sequence so tests can assert one-step Undo.
    def openTransaction(self, label):
        self.open_transaction = label
        self.transactions.append(("open", label))
        # Snapshot what an abort has to be able to put back. FreeCAD rolls the
        # document back on abort; without modelling that, a test cannot tell a
        # command that refused cleanly from one that refused after editing.
        self._transaction_snapshot = [
            (obj, list(obj.Geometry), list(obj.Constraints))
            for obj in self.Objects
            if hasattr(obj, "Geometry") and hasattr(obj, "Constraints")
        ]

    def commitTransaction(self):
        self.transactions.append(("commit", self.open_transaction))
        self.open_transaction = None
        self._transaction_snapshot = []

    def abortTransaction(self):
        self.transactions.append(("abort", self.open_transaction))
        self.open_transaction = None
        for obj, geometry, constraints in self._transaction_snapshot:
            obj.Geometry = geometry
            obj.Constraints = constraints
        self._transaction_snapshot = []

    def removeObject(self, obj_or_name):
        name = obj_or_name if isinstance(obj_or_name, str) else getattr(obj_or_name, "Name", None)
        self.Objects = [o for o in self.Objects if getattr(o, "Name", None) != name]
        for obj in self.Objects:
            if getattr(obj, "TypeId", "") == "PartDesign::Body" and hasattr(obj, "Group"):
                obj.Group = [g for g in obj.Group if getattr(g, "Name", None) != name]


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


class FakeCircle:
    """Stand-in for Part.Circle inside a sketch."""

    def __init__(self, center, axis_or_radius=None, radius=1.0, construction=False):
        self.TypeId = "Part::GeomCircle"
        self.Center = (
            FakeVector(center[0], center[1], 0.0)
            if hasattr(center, "__getitem__")
            else FakeVector(center.x, center.y, getattr(center, "z", 0.0))
        )
        if isinstance(axis_or_radius, (int, float)):
            self.Radius = float(axis_or_radius)
        elif radius is not None:
            self.Radius = float(radius)
        else:
            self.Radius = 1.0
        self.Construction = construction

    def reflected(self, axis_a, axis_b):
        return FakeCircle(
            _reflect(self.Center, axis_a, axis_b),
            self.Radius,
            construction=self.Construction,
        )


class FakeArcOfCircle:
    """Stand-in for Part.ArcOfCircle inside a sketch."""

    def __init__(self, circle_or_p1, p2_or_u1=None, p3_or_u2=None, construction=False):
        import math

        self.TypeId = "Part::GeomArcOfCircle"
        self.Construction = construction
        if hasattr(circle_or_p1, "Center") and hasattr(circle_or_p1, "Radius"):
            self.Center = FakeVector(circle_or_p1.Center.x, circle_or_p1.Center.y, 0.0)
            self.Radius = float(circle_or_p1.Radius)
            u1 = float(p2_or_u1) if p2_or_u1 is not None else 0.0
            u2 = float(p3_or_u2) if p3_or_u2 is not None else math.pi
            self.StartPoint = FakeVector(
                self.Center.x + self.Radius * math.cos(u1),
                self.Center.y + self.Radius * math.sin(u1),
                0.0,
            )
            self.EndPoint = FakeVector(
                self.Center.x + self.Radius * math.cos(u2),
                self.Center.y + self.Radius * math.sin(u2),
                0.0,
            )
        elif hasattr(circle_or_p1, "x") or (
            hasattr(circle_or_p1, "__len__") and len(circle_or_p1) >= 2
        ):
            p1 = circle_or_p1 if hasattr(circle_or_p1, "x") else FakeVector(*circle_or_p1)
            p3 = (
                p3_or_u2
                if hasattr(p3_or_u2, "x")
                else (FakeVector(*p3_or_u2) if p3_or_u2 is not None else FakeVector(0.0, 0.0, 0.0))
            )
            self.StartPoint = p1
            self.EndPoint = p3
            if p2_or_u1 is not None and (
                hasattr(p2_or_u1, "x") or (hasattr(p2_or_u1, "__len__") and len(p2_or_u1) >= 2)
            ):
                p2 = p2_or_u1 if hasattr(p2_or_u1, "x") else FakeVector(*p2_or_u1)
                ax, ay = p1.x, p1.y
                bx, by = p2.x, p2.y
                cx, cy = p3.x, p3.y
                d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
                if abs(d) > 1e-6:
                    ux = (
                        (ax * ax + ay * ay) * (by - cy)
                        + (bx * bx + by * by) * (cy - ay)
                        + (cx * cx + cy * cy) * (ay - by)
                    ) / d
                    uy = (
                        (ax * ax + ay * ay) * (cx - bx)
                        + (bx * bx + by * by) * (ax - cx)
                        + (cx * cx + cy * cy) * (bx - ax)
                    ) / d
                    self.Center = FakeVector(ux, uy, 0.0)
                else:
                    self.Center = FakeVector((ax + cx) / 2.0, (ay + cy) / 2.0, 0.0)
            else:
                self.Center = FakeVector((p1.x + p3.x) / 2.0, (p1.y + p3.y) / 2.0, 0.0)
            dx = self.StartPoint.x - self.Center.x
            dy = self.StartPoint.y - self.Center.y
            self.Radius = math.hypot(dx, dy)
        else:
            self.StartPoint = FakeVector(0.0, 0.0, 0.0)
            self.EndPoint = FakeVector(1.0, 0.0, 0.0)
            self.Center = FakeVector(0.5, 0.0, 0.0)
            self.Radius = 0.5

    def reflected(self, axis_a, axis_b):
        return FakeArcOfCircle(
            _reflect(self.StartPoint, axis_a, axis_b),
            _reflect(self.Center, axis_a, axis_b),
            _reflect(self.EndPoint, axis_a, axis_b),
            self.Construction,
        )


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

    def __init__(self, _parent=None):
        self.timeout = Signal()
        self.interval = None
        self.started = False

    def setInterval(self, interval):
        self.interval = interval

    def start(self):
        self.started = True

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

    def disconnect(self, handler):
        self.handlers.remove(handler)

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
    def __init__(self, *args, **kwargs):
        self._object_name = kwargs.get("object_name", "")
        self._window_title = kwargs.get("window_title", "")
        self._parent = kwargs.get("parent", None)
        if args:
            if len(args) == 1:
                if isinstance(args[0], str):
                    self._window_title = args[0]
                else:
                    self._parent = args[0]
            elif len(args) == 2:
                if isinstance(args[0], str) and isinstance(args[1], str):
                    self._object_name = args[0]
                    self._window_title = args[1]
                elif isinstance(args[0], str):
                    self._window_title = args[0]
                    self._parent = args[1]
        self.visible = False
        self.raised = False
        self._width = 100
        self.tabs = None
        self._widget = None

    def objectName(self):
        return self._object_name

    def setObjectName(self, name):
        self._object_name = name

    def windowTitle(self):
        return self._window_title

    def setWindowTitle(self, title):
        self._window_title = title

    def setWidget(self, widget):
        self._widget = widget

    def widget(self):
        return self._widget

    def show(self):
        self.visible = True

    def hide(self):
        self.visible = False

    def isVisible(self):
        return self.visible

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

    def closeEvent(self, event):
        pass

    def close(self):
        self.closeEvent(None)
        self.hide()

    def deleteLater(self):
        self.visible = False


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


class FakeLayout:
    def __init__(self, parent=None):
        self._parent = parent
        self.widgets = []
        self.layouts = []

    def addWidget(self, widget):
        self.widgets.append(widget)

    def addLayout(self, layout):
        self.layouts.append(layout)

    def setContentsMargins(self, *args):
        pass

    def setSpacing(self, *args):
        pass

    def addStretch(self, *args):
        pass


class FakeQtWidget(FakeQtObject):
    def __init__(self, parent=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._parent = parent
        self._width = 800
        self._height = 600
        self._x = 0
        self._y = 0
        self._visible = True
        self._installed_filters = []
        self._text = ""
        self.clicked = Signal()
        self.returnPressed = Signal()

    def parent(self):
        return self._parent

    def width(self):
        return self._width

    def height(self):
        return self._height

    def move(self, x, y):
        self._x = x
        self._y = y

    def show(self):
        self._visible = True

    def hide(self):
        self._visible = False

    def close(self):
        self._visible = False

    def isVisible(self):
        return self._visible

    def setObjectName(self, name):
        self._name = name

    def objectName(self):
        return getattr(self, "_name", "")

    def setAttribute(self, *args):
        pass

    def setStyleSheet(self, *args):
        pass

    def installEventFilter(self, flt):
        self._installed_filters.append(flt)

    def eventFilter(self, watched, event):
        return False

    def text(self):
        return self._text

    def setText(self, val):
        self._text = str(val)

    def setToolTip(self, *args):
        pass

    def adjustSize(self):
        pass

    def setLayout(self, layout):
        self._layout = layout

    def setKeyboardTracking(self, tracking):
        self._keyboard_tracking = bool(tracking)

    def keyboardTracking(self):
        return getattr(self, "_keyboard_tracking", False)

    def isChecked(self):
        return getattr(self, "_checked", False)

    def setChecked(self, checked):
        self._checked = bool(checked)

    def selectAll(self):
        self._all_selected = True

    def setFocus(self):
        self._focused = True

    def interpretText(self):
        self._text_interpreted = True

    def lineEdit(self):
        return self

    def insert(self, text):
        self._text = (getattr(self, "_text", "") or "") + str(text)


class FakePushButton(FakeQtWidget):
    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self._text = text
        self._tooltip = ""
        self.clicked = Signal()

    def text(self):
        return self._text

    def setText(self, text):
        self._text = str(text)

    def setToolTip(self, tip):
        self._tooltip = tip


class FakeTableWidgetItem:
    def __init__(self, text=""):
        self._text = str(text)
        self._flags = 0xFFFF
        self._roles = {}

    def text(self):
        return self._text

    def setText(self, text):
        self._text = str(text)

    def flags(self):
        return self._flags

    def setFlags(self, flags):
        self._flags = flags

    def data(self, role):
        return self._roles.get(role, None)

    def setData(self, role, val):
        self._roles[role] = val


class FakeHeaderView:
    Stretch = "stretch"

    def __init__(self):
        self.mode = None

    def setSectionResizeMode(self, mode):
        self.mode = mode


class FakeTableWidget(FakeQtWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.columns = 0
        self.headers = []
        self._rows = []
        self.cellChanged = Signal()
        self._header = FakeHeaderView()
        self._current_row = -1

    def horizontalHeader(self):
        return self._header

    def setColumnCount(self, count):
        self.columns = count

    def setHorizontalHeaderLabels(self, labels):
        self.headers = list(labels)

    def rowCount(self):
        return len(self._rows)

    def setRowCount(self, count):
        while len(self._rows) > count:
            self._rows.pop()
        while len(self._rows) < count:
            self._rows.append([None] * self.columns)

    def insertRow(self, index):
        self._rows.insert(index, [None] * self.columns)

    def removeRow(self, index):
        if 0 <= index < len(self._rows):
            self._rows.pop(index)

    def setItem(self, row, col, item):
        while len(self._rows) <= row:
            self._rows.append([None] * self.columns)
        while len(self._rows[row]) <= col:
            self._rows[row].append(None)
        self._rows[row][col] = item

    def item(self, row, col):
        if 0 <= row < len(self._rows) and 0 <= col < len(self._rows[row]):
            return self._rows[row][col]
        return None

    def currentRow(self):
        return self._current_row

    def setCurrentRow(self, row):
        self._current_row = row

    def currentColumn(self):
        return getattr(self, "_current_col", -1)

    def setCurrentCell(self, row, col):
        self._current_row = row
        self._current_col = col

    def triggerCellChanged(self, row, col):
        self.cellChanged.emit(row, col)


class FakeCoinNode:
    def __init__(self, name=""):
        self.name = name
        self.children = []

    def addChild(self, child):
        self.children.append(child)

    def insertChild(self, child, idx):
        self.children.insert(idx, child)

    def removeChild(self, child):
        if child in self.children:
            self.children.remove(child)


class FakeViewer:
    def __init__(self, widget=None):
        self._widget = widget if widget is not None else FakeQtWidget()
        self.navicube_enabled = False
        self.navicube_corner = 0

    def setEnabledNaviCube(self, enabled):
        self.navicube_enabled = enabled

    def setNaviCubeCorner(self, corner):
        self.navicube_corner = corner

    def getWidget(self):
        return self._widget

    def getGLWidget(self):
        return self._widget

    def getSceneGraph(self):
        return FakeCoinNode("SoSeparator")


class FakeView:
    def __init__(self):
        self.calls = []
        self._viewer = FakeViewer()

    def getViewer(self):
        return self._viewer

    def getWidget(self):
        return self._viewer.getWidget()

    def getPointOnScreen(self, _pos):
        return (100, 100)

    def redraw(self):
        self.calls.append("redraw")

    def viewAxonometric(self):
        self.calls.append("axonometric")

    def viewTop(self):
        self.calls.append("top")

    def viewFront(self):
        self.calls.append("front")

    def fitAll(self):
        self.calls.append("fitAll")

    def setCameraCenter(self, center, height):
        self.calls.append(("centerCamera", center, height))


class FakeApplication:
    def __init__(self):
        self.filters = []
        self.focus_widget = None

    def installEventFilter(self, event_filter):
        self.filters.append(event_filter)

    def removeEventFilter(self, event_filter):
        if event_filter in self.filters:
            self.filters.remove(event_filter)

    def sendEvent(self, receiver, event):
        if hasattr(receiver, "event"):
            return receiver.event(event)
        return False


class FakeButton:
    def __init__(self, enabled=True):
        self.enabled = enabled
        self.clicks = 0

    def isEnabled(self):
        return self.enabled

    def isVisible(self):
        return True

    def click(self):
        self.clicks += 1

    def animateClick(self):
        self.clicks += 1


class FakeDialogButtonBox:
    AcceptRole = "accept"
    YesRole = "yes"
    RejectRole = "reject"
    Ok = "ok"
    Cancel = "cancel"

    def __init__(self, roles=(AcceptRole, RejectRole), visible=True):
        self.visible = visible
        self._buttons = [(FakeButton(), role) for role in roles]

    def isVisible(self):
        return self.visible

    def buttons(self):
        return [button for button, _role in self._buttons]

    def buttonRole(self, wanted):
        return next(role for button, role in self._buttons if button is wanted)

    def button(self, role_or_type):
        if role_or_type in ("ok", self.AcceptRole, self.Ok):
            for b, r in self._buttons:
                if r == self.AcceptRole:
                    return b
        elif role_or_type in ("cancel", self.RejectRole, self.Cancel):
            for b, r in self._buttons:
                if r == self.RejectRole:
                    return b
        return None


class FakeMainWindow:
    def __init__(self):
        self.actions = []
        self.docks = []
        self.button_boxes = []
        self.widgets = []
        self.areas = {}
        self.workbenchActivated = Signal()
        self._menu_shown = False
        self.status_messages = []
        self._stylesheet = ""
        self._maximized = False
        self._central_widget = FakeQtWidget()

    def styleSheet(self):
        return self._stylesheet

    def setStyleSheet(self, sheet):
        self._stylesheet = str(sheet) if sheet else ""

    def menuBar(self):
        window = self

        class MenuBar:
            def show(self):
                window._menu_shown = True

            def hide(self):
                window._menu_shown = False

            def setVisible(self, visible):
                window._menu_shown = bool(visible)

            def isVisible(self):
                return window._menu_shown

        return MenuBar()

    def centralWidget(self):
        return self._central_widget

    def isMaximized(self):
        return self._maximized

    def windowFlags(self):
        return 0

    def setWindowFlag(self, *_args):
        pass

    def show(self):
        pass

    def showMaximized(self):
        self._maximized = True

    def findChildren(self, kind):
        matches = [w for w in self.widgets if isinstance(w, kind)]
        if kind is FakeAction:
            return list(self.actions) + matches
        if kind is FakeDock:
            return list(self.docks) + matches
        if kind is FakeDialogButtonBox:
            return list(self.button_boxes) + matches
        return matches

    def findChild(self, kind, name=""):
        for child in self.findChildren(kind):
            if not name or getattr(child, "objectName", lambda: "")() == name:
                return child
        return None

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
    qtcore.QEvent = types.SimpleNamespace(
        KeyPress="key-press",
        Show="show",
        FocusIn="focus-in",
        WindowActivate="window-activate",
    )
    qt_dict = {
        "LeftDockWidgetArea": "left",
        "RightDockWidgetArea": "right",
        "DockWidgetArea": types.SimpleNamespace(
            LeftDockWidgetArea="left",
            RightDockWidgetArea="right",
        ),
        "ApplicationShortcut": "application",
        "Key_Return": "return",
        "Key_Enter": "enter",
        "Key_Escape": "escape",
        "Key_Period": "period",
        "Key_Comma": "comma",
        "Key_Minus": "minus",
        "Key_Plus": "plus",
        "Key_Backspace": "backspace",
        "Key_Delete": "delete",
        "UserRole": 0x0100,
        "ItemIsEditable": 1,
        "WindowType": types.SimpleNamespace(
            CustomizeWindowHint="customize",
            WindowTitleHint="title",
            WindowSystemMenuHint="system-menu",
            WindowMinimizeButtonHint="minimize",
            WindowMaximizeButtonHint="maximize",
            WindowCloseButtonHint="close",
        ),
    }
    for i in range(10):
        qt_dict[f"Key_{i}"] = f"key_{i}"
    qtcore.Qt = types.SimpleNamespace(**qt_dict)

    qtgui = types.ModuleType("PySide.QtGui")
    qtgui.QKeySequence = FakeKeySequence
    qtgui.QAction = FakeAction

    qtwidgets = types.ModuleType("PySide.QtWidgets")
    qtwidgets.QDockWidget = FakeDock
    qtwidgets.QTabWidget = FakeTabWidget
    qtwidgets.QToolBar = type("QToolBar", (), {})
    qtwidgets.QAction = FakeAction
    qtwidgets.QDialogButtonBox = FakeDialogButtonBox
    qtwidgets.QWidget = FakeQtWidget
    qtwidgets.QFrame = FakeQtWidget
    qtwidgets.QToolButton = FakeQtWidget
    qtwidgets.QLineEdit = FakeQtWidget
    qtwidgets.QPushButton = FakePushButton
    qtwidgets.QTableWidget = FakeTableWidget
    qtwidgets.QTableWidgetItem = FakeTableWidgetItem
    qtwidgets.QHeaderView = FakeHeaderView
    qtwidgets.QHBoxLayout = FakeLayout
    qtwidgets.QVBoxLayout = FakeLayout
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
        # Wording taken from a real FreeCAD 1.1 App.getExportFilters(); the DXF
        # entry is deliberately not the literal fusion_export falls back to, so
        # the tests exercise resolution rather than the hardcoded string.
        self.export_filters = [
            "STEP with colors (*.step *.stp)",
            "STEP (*.step *.stp)",
            "Binary STL (*.stl)",
            "Wavefront OBJ (*.obj)",
            "3D Manufacturing Format (*.3mf)",
            "Autodesk DXF 2D (*.dxf)",
            "Portable Document Format (*.pdf)",
        ]
        self.command_handlers = {}
        self.documents = {}
        self.document_observers = []

        app = types.ModuleType("FreeCAD")
        app.Version = lambda: version
        app.getUserAppDataDir = lambda: str(self.user_root) + "/"
        app.getResourceDir = lambda: str(self.user_root / "Resources") + "/"
        app.ParamGet = lambda path: self.groups.setdefault(path, ParameterGroup())
        app.saveParameter = self._save_parameter
        app.Console = self.console
        app.ActiveDocument = None
        app.newDocument = self._new_document
        app.getDocument = lambda name: self.documents.get(name)
        app.listDocuments = lambda: dict(self.documents)
        app.addDocumentObserver = self.document_observers.append
        app.removeDocumentObserver = lambda obs: (
            self.document_observers.remove(obs) if obs in self.document_observers else None
        )
        app.getExportFilters = lambda: list(self.export_filters)
        app.setActiveDocument = self._set_active_document
        app.Vector = FakeVector
        app.Rotation = FakeRotation
        self.app = app

        gui = types.ModuleType("FreeCADGui")

        class Workbench:
            pass

        self.workbenches = {}
        gui.Workbench = Workbench
        gui.addWorkbench = lambda workbench: self.workbenches.__setitem__(
            workbench.__class__.__name__, workbench
        )
        gui.removeWorkbench = lambda name: self.workbenches.pop(name, None)
        gui.listWorkbenches = lambda: dict(self.workbenches)
        gui.getWorkbench = lambda name: self.workbenches[name]
        gui.getMainWindow = lambda: self.main_window
        gui.addCommand = lambda name, command: self.commands.__setitem__(name, command)
        self.preference_pages = []
        gui.addPreferencePage = lambda path, group: self.preference_pages.append((path, group))
        gui.addDocumentObserver = self.document_observers.append
        gui.removeDocumentObserver = lambda obs: (
            self.document_observers.remove(obs) if obs in self.document_observers else None
        )
        gui.activateWorkbench = self._activate_workbench
        gui.runCommand = self._run_command
        gui.listCommands = lambda: list(self.registered_commands)
        gui.activeWorkbench = lambda: types.SimpleNamespace(name=lambda: self.active_workbench)
        gui.Control = types.SimpleNamespace(activeDialog=lambda: self.task_dialog_active)
        self.active_view = FakeView()
        gui.ActiveDocument = types.SimpleNamespace(
            getInEdit=lambda: getattr(self, "_in_edit", None),
            ActiveView=self.active_view,
        )
        self.selection_observers = []
        gui.Selection = types.SimpleNamespace(
            clearSelection=lambda: self.gui_events.append(("selection", "clear")),
            addSelection=lambda *args: self.gui_events.append(
                (
                    "selection",
                    args[1] if len(args) > 1 else getattr(args[0], "Name", str(args[0])),
                )
            ),
            getSelectionEx=lambda *args: list(self.selection_ex),
            getSelection=lambda *args: [entry.Object for entry in self.selection_ex],
            hasSelection=lambda *args: bool(self.selection_ex),
            addObserver=self.selection_observers.append,
            removeObserver=lambda obs: (
                self.selection_observers.remove(obs) if obs in self.selection_observers else None
            ),
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
        self.part.Circle = FakeCircle
        self.part.ArcOfCircle = FakeArcOfCircle

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
            ActiveView=self.active_view,
        )
        return sketch

    def select_objects(self, *objects):
        """Set the whole-object selection that Gui.Selection.getSelection() reports."""
        self.selection_ex = [
            types.SimpleNamespace(
                Object=obj,
                ObjectName=getattr(obj, "Name", "Object"),
                SubElementNames=[],
            )
            for obj in objects
        ]

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

    def _new_document(self, name=None):
        doc = FakeDocument()
        self._doc_counter = getattr(self, "_doc_counter", 0) + 1
        if name:
            doc.Name = name
        elif self._doc_counter > 1:
            doc.Name = f"Document_{self._doc_counter}"
        else:
            doc.Name = "Untitled"
        self.documents[doc.Name] = doc
        self._set_active_document(doc)
        return doc

    def _set_active_document(self, doc_or_name):
        doc = self.documents.get(doc_or_name) if isinstance(doc_or_name, str) else doc_or_name
        self.app.ActiveDocument = doc
        for obs in list(self.document_observers):
            if hasattr(obs, "slotActiveDocument"):
                try:
                    obs.slotActiveDocument(doc)
                except Exception:
                    pass

    def close_document(self, doc_or_name):
        name = doc_or_name if isinstance(doc_or_name, str) else getattr(doc_or_name, "Name", None)
        doc = self.documents.pop(name, None)
        if doc is not None:
            for obs in list(self.document_observers):
                if hasattr(obs, "slotDeletedDocument"):
                    try:
                        obs.slotDeletedDocument(doc)
                    except Exception:
                        pass
            if self.app.ActiveDocument is doc:
                next_doc = next(iter(self.documents.values()), None)
                self._set_active_document(next_doc)

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
        for name in [
            k
            for k in list(sys.modules.keys())
            if k.startswith("fusion_") or k == "_fusion_my_freecad_runtime"
        ]:
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
