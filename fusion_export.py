"""Selection-aware Export for FusionMyFreeCAD.

In Autodesk Fusion, Export is a single prominent button: it reads what you have
selected and opens the save dialog already pointed at the format that suits it.
Native FreeCAD offers Std_Export, which always opens on whichever filter was used
last, so exporting a solid right after exporting a drawing starts on the wrong
one.

This module keeps Std_Export as the thing that actually writes the file and only
pre-selects its filter, so nothing here can produce a file FreeCAD would not have
produced itself.

It is deliberately implemented as ordinary FreeCAD commands rather than as a
widget inside the vendored ribbon. A command inherits the ribbon's own enable and
dim behaviour from ``IsActive()``, survives ``tools/sync_bundled_addons.py``, and
cannot leave the ribbon half-built if it raises.
"""

from __future__ import annotations

from typing import Any

import FreeCAD as App
import FreeCADGui as Gui

from fusion_common import notify

EXPORT_FILTER_GROUP = "User parameter:BaseApp/Preferences/General"
EXPORT_FILTER_KEY = "FileExportFilter"

# Reference geometry carries a Shape but is meaningless on its own in an export.
_REFERENCE_TYPES = frozenset(
    {
        "App::Line",
        "App::Plane",
        "App::Origin",
        "App::OriginFeature",
        "Part::Datum",
        "PartDesign::Plane",
        "PartDesign::Line",
        "PartDesign::Point",
        "PartDesign::CoordinateSystem",
    }
)

# Each entry: extensions that identify the registered filter, and the literal to
# fall back on when the running FreeCAD does not report its filters.
_FORMATS: dict[str, tuple[tuple[str, ...], str, str]] = {
    "step": ((".step", ".stp"), "STEP with colors (*.step *.stp)", "STEP"),
    "stl": ((".stl",), "Binary STL (*.stl)", "STL"),
    "obj": ((".obj",), "Wavefront OBJ (*.obj)", "OBJ"),
    "3mf": ((".3mf",), "3D Manufacturing Format (*.3mf)", "3MF"),
    "dxf": ((".dxf",), "Autodesk DXF (*.dxf)", "DXF"),
    "pdf": ((".pdf",), "Portable Document Format (*.pdf)", "PDF"),
}

# Checked in order, so a selection holding both a solid and a mesh exports as
# STEP rather than silently degrading the solid to a triangle soup.
_CLASSIFIERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("step", ("Part::Feature", "PartDesign::Body", "PartDesign::Feature", "App::Part")),
    ("stl", ("Mesh::Feature",)),
    ("pdf", ("TechDraw::DrawPage",)),
    ("dxf", ("Sketcher::SketchObject",)),
)


def _derives_from(obj: Any, type_name: str) -> bool:
    """``isDerivedFrom`` without letting an odd proxy object raise into a caller."""
    checker = getattr(obj, "isDerivedFrom", None)
    if not callable(checker):
        return False
    try:
        return bool(checker(type_name))
    except Exception:
        return False


def is_exportable(obj: Any) -> bool:
    """Return whether `obj` is worth handing to Std_Export.

    Reference geometry is rejected, and so is a body with no features: reading
    ``Shape`` on an empty ``PartDesign::Body`` raises ``Part.OCCError`` from
    OpenCASCADE rather than returning a null shape.
    """
    if obj is None:
        return False

    type_id = getattr(obj, "TypeId", "") or ""
    if type_id in _REFERENCE_TYPES or "Origin" in type_id:
        return False

    if _derives_from(obj, "PartDesign::Body"):
        group = getattr(obj, "Group", None)
        if group is not None and len(group) == 0:
            return False

    for _kind, types in _CLASSIFIERS:
        for type_name in types:
            if _derives_from(obj, type_name):
                return True

    if getattr(obj, "Mesh", None) is not None:
        return True

    shape = getattr(obj, "Shape", None)
    if shape is None:
        return False
    is_null = getattr(shape, "isNull", None)
    if callable(is_null):
        try:
            return not is_null()
        except Exception:
            # OpenCASCADE raises rather than reporting a null shape. Treat an
            # object whose shape cannot even be inspected as not exportable.
            return False
    return True


def classify_selection(objects: list[Any]) -> str | None:
    """Return the format key that suits `objects`, or None when none applies."""
    exportable = [obj for obj in objects if is_exportable(obj)]
    if not exportable:
        return None
    for kind, types in _CLASSIFIERS:
        for obj in exportable:
            for type_name in types:
                if _derives_from(obj, type_name):
                    return kind
    for obj in exportable:
        if getattr(obj, "Mesh", None) is not None:
            return "stl"
    return "step"


def resolve_filter(kind: str, filters: list[str] | None = None) -> str:
    """Return the filter string this FreeCAD registered for `kind`.

    FreeCAD's exact wording moves between releases -- "Autodesk DXF (*.dxf)" in
    one, "Autodesk DXF 2D (*.dxf)" in another -- and a string it does not
    recognise leaves the dialog on its previous filter. Asking the running
    instance avoids guessing.
    """
    extensions, fallback, token = _FORMATS[kind]
    if filters is None:
        getter = getattr(App, "getExportFilters", None)
        if callable(getter):
            try:
                filters = list(getter())
            except Exception:
                filters = None
    if not filters:
        return fallback

    matches = [f for f in filters if any(ext in f.lower() for ext in extensions)]
    if not matches:
        return fallback
    for match in matches:
        if token.lower() in match.lower():
            return match
    return matches[0]


def _set_export_filter(value: str) -> None:
    App.ParamGet(EXPORT_FILTER_GROUP).SetString(EXPORT_FILTER_KEY, value)


def export_selection(kind: str | None = None, objects: list[Any] | None = None) -> dict[str, Any]:
    """Pre-select the export filter, then hand over to Std_Export.

    `kind` forces a format; leaving it None classifies the selection instead.
    """
    if getattr(App, "ActiveDocument", None) is None:
        _notify_export("no active document.", error=True)
        return {"status": "no-document"}

    if objects is None:
        getter = getattr(Gui.Selection, "getSelection", None)
        objects = list(getter() or []) if callable(getter) else []

    resolved = kind or classify_selection(objects)
    if resolved is None:
        _notify_export("select a body, solid, mesh, drawing page or sketch to export.", error=True)
        return {"status": "nothing-exportable"}

    export_filter = resolve_filter(resolved)
    _set_export_filter(export_filter)

    runner = getattr(Gui, "runCommand", None)
    if not callable(runner):
        return {"status": "no-runner", "kind": resolved, "filter": export_filter}
    runner("Std_Export", 0)

    _notify_export("exporting as {}.".format(_FORMATS[resolved][2]))
    return {"status": "ok", "kind": resolved, "filter": export_filter}


def _notify_export(text: str, error: bool = False) -> None:
    notify("Export", text, error=error)


class _ExportCommand:
    """Shared ``FusionMyFreeCAD_Export*`` ribbon command."""

    def __init__(self, kind: str | None, menu_text: str, tool_tip: str):
        self._kind = kind
        self._menu_text = menu_text
        self._tool_tip = tool_tip

    def GetResources(self):
        return {
            "Pixmap": "FusionMyFreeCAD_Export",
            "MenuText": self._menu_text,
            "ToolTip": self._tool_tip,
        }

    def IsActive(self):
        """Enabled only while something is selected.

        FreeCAD polls this on a timer for every visible ribbon button, so it stays
        to two in-memory reads. Deciding whether the selection is *exportable*
        would mean touching shapes on every poll, which is what froze 1.3.2.
        """
        if getattr(App, "ActiveDocument", None) is None:
            return False
        selection = getattr(Gui, "Selection", None)
        if selection is None:
            return False
        has_selection = getattr(selection, "hasSelection", None)
        if callable(has_selection):
            try:
                return bool(has_selection())
            except Exception:
                return False
        getter = getattr(selection, "getSelection", None)
        if callable(getter):
            try:
                return bool(getter())
            except Exception:
                return False
        return False

    def Activated(self):
        export_selection(self._kind)


COMMANDS: tuple[tuple[str, str | None, str, str], ...] = (
    (
        "FusionMyFreeCAD_Export",
        None,
        "Export",
        "Export the selection, with the save dialog already set to the format that "
        "suits it: STEP for solids and bodies, STL for meshes, PDF for drawing "
        "pages, DXF for sketches. A selection holding both a solid and a mesh "
        "exports as STEP.",
    ),
    (
        "FusionMyFreeCAD_ExportSTEP",
        "step",
        "Export as STEP",
        "Export the selection as STEP, whatever it is.",
    ),
    (
        "FusionMyFreeCAD_ExportSTL",
        "stl",
        "Export as STL",
        "Export the selection as binary STL, whatever it is.",
    ),
    (
        "FusionMyFreeCAD_Export3MF",
        "3mf",
        "Export as 3MF",
        "Export the selection as 3MF, whatever it is.",
    ),
    (
        "FusionMyFreeCAD_ExportDXF",
        "dxf",
        "Export as DXF",
        "Export the selection as DXF, whatever it is.",
    ),
)


def register(add_command=None):
    register_with = add_command or Gui.addCommand
    for name, kind, menu_text, tool_tip in COMMANDS:
        register_with(name, _ExportCommand(kind, menu_text, tool_tip))
