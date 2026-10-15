"""Unit tests for FMF aesthetic modernization features:

- Modern Zinc Studio Viewport preset (3-point lighting, radial zinc canvas, MSAA)
- Viewport backup and 1-click restore
- Modern Zinc stylesheet theme installation
- Strict preference baseline tracking and appearance restoration guarantee
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# 1. Viewport Presets & Backup / Restore
# ---------------------------------------------------------------------------


def test_hex_to_uint_conversion(env):
    env.install().load_bootstrap()
    import fmf_viewport

    # Zinc-800: #27272a
    val = fmf_viewport.hex_to_uint("#27272a", 255)
    r = (val >> 24) & 0xFF
    g = (val >> 16) & 0xFF
    b = (val >> 8) & 0xFF
    a = val & 0xFF
    assert (r, g, b, a) == (0x27, 0x27, 0x2A, 255)


def test_apply_studio_viewport_and_restore(env):
    env.install()
    import fmf_viewport

    view_grp = env.param("User parameter:BaseApp/Preferences/View")
    nav_grp = env.param("User parameter:BaseApp/Preferences/NaviCube")
    backup_grp = env.param("User parameter:BaseApp/Preferences/Mod/FMF/ViewportBackup")

    # Set initial custom dummy values
    view_grp.SetBool("RadialGradient", False)
    view_grp.SetUnsigned("BackgroundColor", 12345)
    view_grp.SetFloat("KeyLightIntensity", 0.5)
    view_grp.SetInt("AntiAliasing", 0)
    nav_grp.SetInt("InactiveOpacity", 80)

    # 1. Apply Studio Viewport
    res = fmf_viewport.apply_studio_viewport(backup=True)
    assert res["status"] == "ok"
    assert fmf_viewport.has_viewport_backup() is True
    assert backup_grp.GetBool("HasBackup") is True
    assert backup_grp.GetUnsigned("View_BackgroundColor") == 12345
    assert backup_grp.GetInt("Nav_InactiveOpacity") == 80

    # Verify new values applied
    assert view_grp.GetBool("RadialGradient") is True
    assert view_grp.GetInt("AntiAliasing") == 8
    assert abs(view_grp.GetFloat("KeyLightIntensity") - 0.80) < 1e-5
    assert nav_grp.GetInt("InactiveOpacity") == 30

    # 2. Restore Viewport
    res_restore = fmf_viewport.restore_default_viewport()
    assert res_restore["status"] == "ok"
    assert fmf_viewport.has_viewport_backup() is False

    # Verify original values restored
    assert view_grp.GetBool("RadialGradient") is False
    assert view_grp.GetUnsigned("BackgroundColor") == 12345
    assert abs(view_grp.GetFloat("KeyLightIntensity") - 0.5) < 1e-5
    assert view_grp.GetInt("AntiAliasing") == 0
    assert nav_grp.GetInt("InactiveOpacity") == 80


def test_apply_modern_zinc_theme(env):
    env.install()
    import fmf_viewport

    res = fmf_viewport.apply_modern_zinc_theme()
    assert res["status"] == "ok"

    # Verify stylesheet file was copied to user stylesheets directory
    dest = Path(env.user_root) / "Gui" / "Stylesheets" / "modern_zinc.qss"
    assert dest.is_file()
    content = dest.read_text(encoding="utf-8")
    assert "MODERN ZINC CAD UI STYLESHEET" in content

    # Verify preference was set
    gen_grp = env.param("User parameter:BaseApp/Preferences/General")
    assert gen_grp.GetString("StyleSheet") == str(dest)


def test_viewport_restore_removes_unregistered_keys(env):
    """When preferences did not exist prior to applying, restore must delete them."""
    env.install()
    import fmf_viewport

    view_grp = env.param("User parameter:BaseApp/Preferences/View")
    nav_grp = env.param("User parameter:BaseApp/Preferences/NaviCube")

    # Start with empty preference group (no keys exist)
    assert "RadialGradient" not in view_grp.GetBools()
    assert "KeyLightIntensity" not in view_grp.GetFloats()
    assert "InactiveOpacity" not in nav_grp.GetInts()

    # Apply
    res = fmf_viewport.apply_studio_viewport(backup=True)
    assert res["status"] == "ok"
    assert "RadialGradient" in view_grp.GetBools()
    assert "KeyLightIntensity" in view_grp.GetFloats()
    assert "InactiveOpacity" in nav_grp.GetInts()

    # Restore
    res_restore = fmf_viewport.restore_default_viewport()
    assert res_restore["status"] == "ok"

    # Nonexistent keys should have been removed, not set to fallback values
    assert "RadialGradient" not in view_grp.GetBools()
    assert "KeyLightIntensity" not in view_grp.GetFloats()
    assert "InactiveOpacity" not in nav_grp.GetInts()


def test_theme_restore_with_prior_stylesheet_and_without(env):
    env.install()
    import fmf_viewport

    gen_grp = env.param("User parameter:BaseApp/Preferences/General")

    # Scenario A: User had an existing stylesheet
    gen_grp.SetString("StyleSheet", "/custom/path/custom.qss")
    assert gen_grp.GetString("StyleSheet") == "/custom/path/custom.qss"

    res_apply = fmf_viewport.apply_modern_zinc_theme(backup=True)
    assert res_apply["status"] == "ok"
    assert "modern_zinc.qss" in gen_grp.GetString("StyleSheet")

    res_restore = fmf_viewport.restore_theme()
    assert res_restore["status"] == "ok"
    assert gen_grp.GetString("StyleSheet") == "/custom/path/custom.qss"

    # Scenario B: User had no stylesheet initially
    gen_grp.RemString("StyleSheet")
    assert "StyleSheet" not in gen_grp.GetStrings()

    fmf_viewport.apply_modern_zinc_theme(backup=True)
    assert "StyleSheet" in gen_grp.GetStrings()

    fmf_viewport.restore_theme()
    assert "StyleSheet" not in gen_grp.GetStrings()


def test_bootstrap_restore_rolls_back_appearance(env):
    """Calling main fmf_bootstrap.restore() must also restore viewport and theme."""
    bootstrap = env.install().load_bootstrap()
    import fmf_viewport

    bootstrap.prepare()
    view_grp = env.param("User parameter:BaseApp/Preferences/View")
    gen_grp = env.param("User parameter:BaseApp/Preferences/General")

    # Ensure clean slate
    view_grp.RemBool("RadialGradient")
    gen_grp.RemString("StyleSheet")

    fmf_viewport.apply_studio_viewport(backup=True)
    fmf_viewport.apply_modern_zinc_theme(backup=True)

    assert "RadialGradient" in view_grp.GetBools()
    assert "StyleSheet" in gen_grp.GetStrings()

    # Run main restore
    _removed, problems = bootstrap.restore()
    assert problems == []

    # Verify appearance preferences rolled back
    assert "RadialGradient" not in view_grp.GetBools()
    assert "StyleSheet" not in gen_grp.GetStrings()
