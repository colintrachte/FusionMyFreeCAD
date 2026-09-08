"""FusionMyFreeCAD Viewport & Aesthetic Presets.

Applies calibrated 3-point studio lighting, radial Zinc canvas, charcoal edge
contrast, and MSAA anti-aliasing to transform FreeCAD 1.1+'s native viewport into
a modern studio environment, with complete backup and 1-click restore.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent

VIEW_PARAM_PATH = "User parameter:BaseApp/Preferences/View"
NAVICUBE_PARAM_PATH = "User parameter:BaseApp/Preferences/NaviCube"
BACKUP_PARAM_PATH = "User parameter:BaseApp/Preferences/Mod/FusionMyFreeCAD/ViewportBackup"
GENERAL_PARAM_PATH = "User parameter:BaseApp/Preferences/General"


def _get_app():
    try:
        import FreeCAD

        return FreeCAD
    except ImportError:
        return None


def _get_gui():
    try:
        import FreeCADGui

        return FreeCADGui
    except ImportError:
        return None


def hex_to_uint(hex_code: str, alpha: int = 255) -> int:
    """Convert hex color string like '#27272a' to 32-bit unsigned RGBA int."""
    clean = hex_code.lstrip("#")
    if len(clean) == 3:
        clean = "".join(c * 2 for c in clean)
    r = int(clean[0:2], 16)
    g = int(clean[2:4], 16)
    b = int(clean[4:6], 16)
    return (r << 24) | (g << 16) | (b << 8) | (alpha & 0xFF)


# Calibrated Zinc Studio Dark Presets (Based on Research Roadmap §3)
ZINC_VIEW_PRESETS: dict[str, tuple[str, Any]] = {
    # Background & Canvas
    ("RadialGradient", "Bool"): True,
    ("UseBackgroundColor2", "Bool"): True,
    ("UseBackgroundColor3", "Bool"): True,
    ("UseBackgroundColor4", "Bool"): True,
    ("BackgroundColor", "Unsigned"): hex_to_uint("#27272a"),  # Zinc-800 center
    ("BackgroundColor2", "Unsigned"): hex_to_uint("#202023"),  # Midway falloff
    ("BackgroundColor3", "Unsigned"): hex_to_uint("#18181b"),  # Zinc-900 edge
    ("BackgroundColor4", "Unsigned"): hex_to_uint("#18181b"),
    # Shape & Edges
    ("DefaultShapeColor", "Unsigned"): hex_to_uint("#b6b8bc"),  # Matte industrial neutral
    ("DefaultShapeLineColor", "Unsigned"): hex_to_uint("#34373d"),  # Charcoal edge contrast
    ("DefaultShapeLineWidth", "Float"): 1.2,
    ("BoundingBoxColor", "Unsigned"): hex_to_uint("#4da3ff"),
    # Quality & Anti-Aliasing
    ("AntiAliasing", "Int"): 8,
    # 3-Point Studio Lighting Rig (FreeCAD 1.1+)
    ("HeadlightColor", "Unsigned"): hex_to_uint("#ffffff"),
    ("KeyLightIntensity", "Float"): 0.80,
    ("KeyLightColor", "Unsigned"): hex_to_uint("#fff7eb"),  # Warm key
    ("FillLightIntensity", "Float"): 0.35,
    ("FillLightColor", "Unsigned"): hex_to_uint("#eaf2ff"),  # Cool fill
    ("RimLightIntensity", "Float"): 0.28,
    ("RimLightColor", "Unsigned"): hex_to_uint("#ffffff"),  # Back rim
    ("AmbientLightIntensity", "Float"): 0.22,
    ("AmbientLightColor", "Unsigned"): hex_to_uint("#e2e8f0"),  # Ambient cool gray
}

THEME_BACKUP_PARAM_PATH = "User parameter:BaseApp/Preferences/Mod/FusionMyFreeCAD/ThemeBackup"

ZINC_NAVICUBE_PRESETS: dict[str, tuple[str, Any]] = {
    ("InactiveOpacity", "Int"): 30,
}


def apply_studio_viewport(backup: bool = True) -> dict[str, Any]:
    """Configure FreeCAD 1.1 native 3-point studio lighting and Zinc radial canvas."""
    app = _get_app()
    if app is None:
        return {"status": "error", "message": "FreeCAD not available"}

    view_grp = app.ParamGet(VIEW_PARAM_PATH)
    nav_grp = app.ParamGet(NAVICUBE_PARAM_PATH)
    backup_grp = app.ParamGet(BACKUP_PARAM_PATH)

    if backup and not backup_grp.GetBool("HasBackup", False):
        # Save current settings and track existence
        for (name, kind), _val in ZINC_VIEW_PRESETS.items():
            getter_names = getattr(view_grp, f"Get{kind}s", None)
            existed = name in getter_names() if getter_names else False
            backup_grp.SetBool(f"View_{name}_Existed", existed)
            if existed:
                getter = getattr(view_grp, f"Get{kind}")
                setter = getattr(backup_grp, f"Set{kind}")
                setter(f"View_{name}", getter(name))

        for (name, kind), _val in ZINC_NAVICUBE_PRESETS.items():
            getter_names = getattr(nav_grp, f"Get{kind}s", None)
            existed = name in getter_names() if getter_names else False
            backup_grp.SetBool(f"Nav_{name}_Existed", existed)
            if existed:
                getter = getattr(nav_grp, f"Get{kind}")
                setter = getattr(backup_grp, f"Set{kind}")
                setter(f"Nav_{name}", getter(name))

        backup_grp.SetBool("HasBackup", True)

    # Apply Zinc presets
    for (name, kind), val in ZINC_VIEW_PRESETS.items():
        if kind == "Bool":
            view_grp.SetBool(name, val)
        elif kind == "Unsigned":
            view_grp.SetUnsigned(name, val)
        elif kind == "Float":
            view_grp.SetFloat(name, val)
        elif kind == "Int":
            view_grp.SetInt(name, val)

    for (name, kind), val in ZINC_NAVICUBE_PRESETS.items():
        if kind == "Int":
            nav_grp.SetInt(name, val)

    if hasattr(app, "saveParameter"):
        app.saveParameter()

    # Redraw active view if present
    gui = _get_gui()
    if gui and hasattr(gui, "ActiveDocument") and gui.ActiveDocument:
        view = getattr(gui.ActiveDocument, "ActiveView", None)
        if view and hasattr(view, "redraw"):
            view.redraw()

    if hasattr(app, "Console") and app.Console:
        app.Console.PrintMessage("FusionMyFreeCAD: Applied Modern Zinc Studio Viewport preset.\n")

    return {"status": "ok", "message": "Applied Modern Zinc Studio Viewport preset"}


def has_viewport_backup() -> bool:
    """Return True if a viewport backup exists for restoration."""
    app = _get_app()
    if app is None:
        return False
    return app.ParamGet(BACKUP_PARAM_PATH).GetBool("HasBackup", False)


def restore_default_viewport() -> dict[str, Any]:
    """Restore previous viewport lighting and background settings from backup."""
    app = _get_app()
    if app is None:
        return {"status": "error", "message": "FreeCAD not available"}

    backup_grp = app.ParamGet(BACKUP_PARAM_PATH)
    if not backup_grp.GetBool("HasBackup", False):
        return {"status": "skipped", "message": "No viewport backup found"}

    view_grp = app.ParamGet(VIEW_PARAM_PATH)
    nav_grp = app.ParamGet(NAVICUBE_PARAM_PATH)

    for (name, kind), _val in ZINC_VIEW_PRESETS.items():
        existed = backup_grp.GetBool(f"View_{name}_Existed", False)
        if existed:
            getter = getattr(backup_grp, f"Get{kind}")
            setter = getattr(view_grp, f"Set{kind}")
            setter(name, getter(f"View_{name}"))
        else:
            remover = getattr(view_grp, f"Rem{kind}", None)
            if remover:
                remover(name)

    for (name, kind), _val in ZINC_NAVICUBE_PRESETS.items():
        existed = backup_grp.GetBool(f"Nav_{name}_Existed", False)
        if existed:
            getter = getattr(backup_grp, f"Get{kind}")
            setter = getattr(nav_grp, f"Set{kind}")
            setter(name, getter(f"Nav_{name}"))
        else:
            remover = getattr(nav_grp, f"Rem{kind}", None)
            if remover:
                remover(name)

    backup_grp.SetBool("HasBackup", False)

    if hasattr(app, "saveParameter"):
        app.saveParameter()

    gui = _get_gui()
    if gui and hasattr(gui, "ActiveDocument") and gui.ActiveDocument:
        view = getattr(gui.ActiveDocument, "ActiveView", None)
        if view and hasattr(view, "redraw"):
            view.redraw()

    if hasattr(app, "Console") and app.Console:
        app.Console.PrintMessage("FusionMyFreeCAD: Restored previous viewport settings.\n")

    return {"status": "ok", "message": "Restored previous viewport settings"}


def has_theme_backup() -> bool:
    """Return True if a theme backup exists for restoration."""
    app = _get_app()
    if app is None:
        return False
    return app.ParamGet(THEME_BACKUP_PARAM_PATH).GetBool("HasBackup", False)


def apply_modern_zinc_theme(backup: bool = True) -> dict[str, Any]:
    """Install and activate the modern Zinc theme stylesheet."""
    app = _get_app()
    gui = _get_gui()
    theme_source = ROOT / "Resources" / "Themes" / "modern_zinc.qss"
    if not theme_source.exists():
        return {"status": "error", "message": f"Theme file not found: {theme_source}"}

    content = theme_source.read_text(encoding="utf-8")

    if app is not None and backup:
        theme_backup_grp = app.ParamGet(THEME_BACKUP_PARAM_PATH)
        if not theme_backup_grp.GetBool("HasBackup", False):
            gen_grp = app.ParamGet(GENERAL_PARAM_PATH)
            getter_names = getattr(gen_grp, "GetStrings", None)
            existed = "StyleSheet" in getter_names() if getter_names else False
            theme_backup_grp.SetBool("StyleSheet_Existed", existed)
            if existed:
                theme_backup_grp.SetString("StyleSheet", gen_grp.GetString("StyleSheet", ""))

            if gui and hasattr(gui, "getMainWindow"):
                mw = gui.getMainWindow()
                if mw and hasattr(mw, "styleSheet"):
                    theme_backup_grp.SetString("WindowStyleSheet", mw.styleSheet() or "")
            theme_backup_grp.SetBool("HasBackup", True)

    # If GUI main window exists, apply directly to current session
    if gui and hasattr(gui, "getMainWindow"):
        mw = gui.getMainWindow()
        if mw and hasattr(mw, "setStyleSheet"):
            mw.setStyleSheet(content)

    # Also install into FreeCAD user stylesheets directory so it shows up in Preferences
    if app and hasattr(app, "getUserAppDataDir"):
        dest_dir = Path(app.getUserAppDataDir()) / "Gui" / "Stylesheets"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_file = dest_dir / "modern_zinc.qss"
        shutil.copyfile(theme_source, dest_file)

        # Set preference so it persists across restarts
        gen_grp = app.ParamGet(GENERAL_PARAM_PATH)
        gen_grp.SetString("StyleSheet", str(dest_file))
        if hasattr(app, "saveParameter"):
            app.saveParameter()

    return {"status": "ok", "message": "Modern Zinc theme applied successfully"}


def restore_theme() -> dict[str, Any]:
    """Restore previous application stylesheet and theme settings."""
    app = _get_app()
    gui = _get_gui()
    if app is None:
        return {"status": "error", "message": "FreeCAD not available"}

    theme_backup_grp = app.ParamGet(THEME_BACKUP_PARAM_PATH)
    if not theme_backup_grp.GetBool("HasBackup", False):
        return {"status": "skipped", "message": "No theme backup found"}

    gen_grp = app.ParamGet(GENERAL_PARAM_PATH)
    existed = theme_backup_grp.GetBool("StyleSheet_Existed", False)
    if existed:
        gen_grp.SetString("StyleSheet", theme_backup_grp.GetString("StyleSheet", ""))
    else:
        remover = getattr(gen_grp, "RemString", None)
        if remover:
            remover("StyleSheet")
        else:
            gen_grp.SetString("StyleSheet", "")

    if hasattr(app, "saveParameter"):
        app.saveParameter()

    if gui and hasattr(gui, "getMainWindow"):
        mw = gui.getMainWindow()
        if mw and hasattr(mw, "setStyleSheet"):
            orig_win_ss = theme_backup_grp.GetString("WindowStyleSheet", "")
            mw.setStyleSheet(orig_win_ss)

    theme_backup_grp.SetBool("HasBackup", False)
    if hasattr(app, "Console") and app.Console:
        app.Console.PrintMessage("FusionMyFreeCAD: Restored previous theme settings.\n")

    return {"status": "ok", "message": "Restored previous theme settings"}


def restore_all_appearance() -> dict[str, Any]:
    """Restore both viewport lighting/canvas and theme settings."""
    return {
        "viewport": restore_default_viewport(),
        "theme": restore_theme(),
    }


# ---------------------------------------------------------------------------
# FreeCAD Gui Commands
# ---------------------------------------------------------------------------


class ApplyStudioViewportCommand:
    """FreeCAD command to apply the Modern Zinc Studio Viewport preset."""

    def GetResources(self):
        return {
            "Pixmap": "FusionMyFreeCAD_StudioViewport",
            "MenuText": "Fusion Studio Viewport",
            "ToolTip": "Apply modern studio 3-point lighting and radial zinc canvas",
            "Accel": "",
        }

    def Activated(self):
        apply_studio_viewport()

    def IsActive(self):
        return True


class RestoreViewportCommand:
    """FreeCAD command to restore previous viewport display settings."""

    def GetResources(self):
        return {
            "Pixmap": "Std_ViewScreenShot",
            "MenuText": "Restore Viewport Defaults",
            "ToolTip": "Restore previous viewport display and lighting settings",
            "Accel": "",
        }

    def Activated(self):
        restore_default_viewport()

    def IsActive(self):
        return has_viewport_backup()


class ApplyModernZincThemeCommand:
    """FreeCAD command to apply the Modern Zinc application stylesheet."""

    def GetResources(self):
        return {
            "Pixmap": "FusionMyFreeCAD_StudioViewport",
            "MenuText": "Apply Modern Zinc Theme",
            "ToolTip": "Apply flat Tailwind Zinc theme across FreeCAD",
            "Accel": "",
        }

    def Activated(self):
        apply_modern_zinc_theme()

    def IsActive(self):
        return True


def register(add_command=None):
    """Register viewport and aesthetic commands with FreeCADGui."""
    register_with = add_command or (getattr(_get_gui(), "addCommand", None) if _get_gui() else None)
    if not callable(register_with):
        return

    register_with("FusionMyFreeCAD_StudioViewport", ApplyStudioViewportCommand())
    register_with("FusionMyFreeCAD_RestoreViewport", RestoreViewportCommand())
    register_with("FusionMyFreeCAD_ModernZincTheme", ApplyModernZincThemeCommand())
