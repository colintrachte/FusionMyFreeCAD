"""Unit tests for the selection-aware Export commands."""

from __future__ import annotations

import pytest
from fake_freecad import FakeObject


@pytest.fixture
def export(env):
    import fusion_export

    return fusion_export


def _obj(type_id, name="Obj", **attributes):
    obj = FakeObject(type_id, name)
    for key, value in attributes.items():
        setattr(obj, key, value)
    return obj


# ---------------------------------------------------------------------------
# What counts as exportable
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "type_id",
    [
        "Part::Feature",
        "PartDesign::Feature",
        "App::Part",
        "Mesh::Feature",
        "TechDraw::DrawPage",
        "Sketcher::SketchObject",
    ],
)
def test_modelling_output_is_exportable(export, type_id):
    assert export.is_exportable(_obj(type_id)) is True


@pytest.mark.parametrize(
    "type_id",
    [
        "App::Line",
        "App::Plane",
        "App::Origin",
        "PartDesign::CoordinateSystem",
        "PartDesign::Plane",
    ],
)
def test_reference_geometry_is_not_exportable(export, type_id):
    """Datums and origins carry a Shape but mean nothing on their own."""
    assert export.is_exportable(_obj(type_id)) is False


def test_nothing_is_not_exportable(export):
    assert export.is_exportable(None) is False


def test_an_empty_body_is_not_exportable(export):
    """A PartDesign::Body with no features must not be probed for a Shape.

    Reading .Shape there raises Part.OCCError from OpenCASCADE rather than
    returning a null shape, so the feature count has to be checked first.
    """
    body = _obj("PartDesign::Body", "Body", Group=[])

    class Exploding:
        def isNull(self):
            raise RuntimeError("Standard_NullObject")

    body.Shape = Exploding()
    assert export.is_exportable(body) is False


def test_a_body_with_features_is_exportable(export):
    body = _obj("PartDesign::Body", "Body", Group=[_obj("PartDesign::Pad", "Pad")])
    assert export.is_exportable(body) is True


def test_a_shape_that_raises_on_inspection_is_not_exportable(export):
    class Exploding:
        def isNull(self):
            raise RuntimeError("Standard_NullObject")

    assert export.is_exportable(_obj("Some::Unknown", "X", Shape=Exploding())) is False


def test_a_null_shape_is_not_exportable(export):
    class Null:
        def isNull(self):
            return True

    assert export.is_exportable(_obj("Some::Unknown", "X", Shape=Null())) is False


# ---------------------------------------------------------------------------
# Choosing the format
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("type_id", "expected"),
    [
        ("Part::Feature", "step"),
        ("PartDesign::Feature", "step"),
        ("App::Part", "step"),
        ("Mesh::Feature", "stl"),
        ("TechDraw::DrawPage", "pdf"),
        ("Sketcher::SketchObject", "dxf"),
    ],
)
def test_each_domain_picks_its_own_format(export, type_id, expected):
    assert export.classify_selection([_obj(type_id)]) == expected


def test_a_solid_beside_a_mesh_exports_as_step(export):
    """Mixed selections must not silently degrade a solid to a triangle soup."""
    selection = [_obj("Mesh::Feature", "Mesh"), _obj("Part::Feature", "Solid")]
    assert export.classify_selection(selection) == "step"


def test_a_selection_of_only_reference_geometry_classifies_as_nothing(export):
    assert export.classify_selection([_obj("App::Plane"), _obj("App::Line")]) is None


def test_an_empty_selection_classifies_as_nothing(export):
    assert export.classify_selection([]) is None


# ---------------------------------------------------------------------------
# Resolving the filter against the running FreeCAD
# ---------------------------------------------------------------------------


def test_the_filter_comes_from_the_running_freecad(export, env):
    """FreeCAD's own wording wins over the fallback literal.

    The fake registers "Autodesk DXF 2D (*.dxf)", which is not the string the
    module falls back to. A filter FreeCAD does not recognise leaves the save
    dialog on whatever was used last, which is the bug being avoided.
    """
    assert export.resolve_filter("dxf") == "Autodesk DXF 2D (*.dxf)"
    assert export.resolve_filter("dxf") in env.export_filters


def test_the_preferred_variant_wins_when_freecad_offers_several(export):
    """Both STEP filters match the extension; the one with colors is preferred."""
    assert export.resolve_filter("step") == "STEP with colors (*.step *.stp)"


def test_the_fallback_is_used_when_freecad_reports_no_filters(export):
    assert export.resolve_filter("stl", filters=[]) == "Binary STL (*.stl)"


def test_the_fallback_is_used_when_the_format_is_unregistered(export):
    assert export.resolve_filter("3mf", filters=["Binary STL (*.stl)"]) == (
        "3D Manufacturing Format (*.3mf)"
    )


# ---------------------------------------------------------------------------
# Exporting
# ---------------------------------------------------------------------------


def test_exporting_presets_the_filter_then_hands_over_to_std_export(export, env):
    document = env.app.newDocument("Doc")
    solid = document.addObject("Part::Feature", "Solid")
    env.select_objects(solid)

    result = export.export_selection()

    assert result["status"] == "ok"
    assert result["kind"] == "step"
    stored = env.app.ParamGet(export.EXPORT_FILTER_GROUP).GetString(export.EXPORT_FILTER_KEY)
    assert stored == "STEP with colors (*.step *.stp)"
    assert ("command", "Std_Export") in env.gui_events


def test_an_explicit_format_overrides_the_selection(export, env):
    document = env.app.newDocument("Doc")
    solid = document.addObject("Part::Feature", "Solid")
    env.select_objects(solid)

    result = export.export_selection(kind="stl")

    assert result["kind"] == "stl"
    stored = env.app.ParamGet(export.EXPORT_FILTER_GROUP).GetString(export.EXPORT_FILTER_KEY)
    assert stored == "Binary STL (*.stl)"


def test_exporting_reference_geometry_is_refused_without_touching_the_filter(export, env):
    document = env.app.newDocument("Doc")
    plane = document.addObject("App::Plane", "XY_Plane")
    env.select_objects(plane)

    result = export.export_selection()

    assert result["status"] == "nothing-exportable"
    assert env.app.ParamGet(export.EXPORT_FILTER_GROUP).GetString(export.EXPORT_FILTER_KEY) is None
    assert ("command", "Std_Export") not in env.gui_events
    assert env.console.errors


def test_exporting_without_a_document_is_refused(export, env):
    assert export.export_selection()["status"] == "no-document"
    assert ("command", "Std_Export") not in env.gui_events


# ---------------------------------------------------------------------------
# The commands themselves
# ---------------------------------------------------------------------------


def test_every_export_command_registers(export, env):
    export.register()
    assert set(env.commands) == {name for name, _kind, _text, _tip in export.COMMANDS}


def test_the_button_is_dim_until_something_is_selected(export, env):
    export.register()
    command = env.commands["FusionMyFreeCAD_Export"]

    assert command.IsActive() is False, "no document"

    document = env.app.newDocument("Doc")
    assert command.IsActive() is False, "document but empty selection"

    env.select_objects(document.addObject("Part::Feature", "Solid"))
    assert command.IsActive() is True


def test_is_active_never_inspects_shapes(export, env):
    """IsActive runs on a timer for every visible button.

    Deciding whether the selection is *exportable* rather than merely present
    would mean touching OpenCASCADE shapes on every poll. That is what froze
    1.3.2, so reading .Shape here must fail the test.
    """
    export.register()
    document = env.app.newDocument("Doc")

    class Tripwire:
        def isNull(self):
            raise AssertionError("IsActive() inspected a shape")

    obj = document.addObject("Part::Feature", "Solid")
    obj.Shape = Tripwire()
    env.select_objects(obj)

    assert env.commands["FusionMyFreeCAD_Export"].IsActive() is True


def test_each_command_reports_its_own_resources(export, env):
    export.register()
    for name, _kind, menu_text, _tip in export.COMMANDS:
        resources = env.commands[name].GetResources()
        assert resources["MenuText"] == menu_text
        assert resources["Pixmap"] == "FusionMyFreeCAD_Export"
        assert resources["ToolTip"]


def test_activating_a_format_command_exports_in_that_format(export, env):
    export.register()
    document = env.app.newDocument("Doc")
    env.select_objects(document.addObject("Part::Feature", "Solid"))

    env.commands["FusionMyFreeCAD_ExportDXF"].Activated()

    stored = env.app.ParamGet(export.EXPORT_FILTER_GROUP).GetString(export.EXPORT_FILTER_KEY)
    assert stored == "Autodesk DXF 2D (*.dxf)"
