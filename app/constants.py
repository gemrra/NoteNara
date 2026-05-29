"""Paths, palette, typography, and runtime defaults.

Palette note
------------
v2 visual refresh: yellow-dominant retro editorial, orange as sparse accent,
ink for text and strong borders. Light mode is the default; dark mode swaps
the same shape via apply_theme(dark=True).

Both new canonical keys (`yellow`, `orange`, `ink`, `card`, `border_soft`, …)
and legacy v1 keys (`accent`, `text`, `bg_card`, `border2`, …) resolve to the
same hex values via _make_palette() below, so existing widget code doesn't
need to be rewritten in one go.
"""

from pathlib import Path
from tkinter import font as tkfont

# Project root = parent of the app/ package
BASE_DIR = Path(__file__).resolve().parent.parent

CONFIG_PATH = BASE_DIR / "meeting_app_config.json"
CONFIG_EXAMPLE_PATH = BASE_DIR / "meeting_app_config.example.json"

DEFAULT_MODEL_DIR = BASE_DIR / "models"
DEFAULT_OUTPUT_DIR = BASE_DIR / "output"
LOGS_DIR = BASE_DIR / "logs"
ASSETS_DIR = BASE_DIR / "app" / "assets"

# nvidia CUDA DLL search root (used by services/whisper.py setup_cuda_dlls)
VENV_NVIDIA_DIR = BASE_DIR / "venv" / "Lib" / "site-packages" / "nvidia"

# Legacy: used only by config migration v1 → v2 to preserve existing target DB
LEGACY_NOTES_DB_ID = "2c16dc1a80f0801f9895e378482a945e"


# ============================================================================
# Palette
# ============================================================================

# Palette derived from the NoteNara logo orange (#FFAA00). Yellow and orange
# are kept distinct (different hues + lightness) but live in the same warm
# amber family so nothing clashes with the logo.
LIGHT_BASE = {
    "bg":          "#F4EFDD",   # page background — warm cream (slight amber lift)
    "bg2":         "#E9E1C9",   # subtle alternate / input bg
    "card":        "#FCF9ED",   # card / panel surface
    "ink":         "#1A1308",   # primary text + strong border
    "ink2":        "#5E5036",   # secondary text
    "ink3":        "#9D8F75",   # tertiary / hint text
    "border_soft": "#C9BEA1",   # subtle divider
    "yellow":      "#FFC633",   # PRIMARY accent — warm yellow, lighter than logo
    "yellow_soft": "#FFE69A",   # hover for primary
    "tint_yellow": "#FFF1C0",   # active row backgrounds
    "orange":      "#FFAA00",   # SPARSE accent — the logo orange itself
    "orange_deep": "#E69400",   # pressed / focus orange (darker, same hue)
    "tint_orange": "#FFE2A8",   # peachy-amber tint
    "ok":          "#3E8957",
    "err":         "#C24A0C",
    "warn":        "#B47009",
}

DARK_BASE = {
    "bg":          "#1B1408",
    "bg2":         "#241C0F",
    "card":        "#241C0F",
    "ink":         "#F4EFDD",
    "ink2":        "#BDB098",
    "ink3":        "#7A6C53",
    "border_soft": "#3A301F",
    "yellow":      "#FFC633",
    "yellow_soft": "#3D2F12",
    "tint_yellow": "#3D2F12",
    "orange":      "#FFAA00",
    "orange_deep": "#FFBF40",
    "tint_orange": "#3D2810",
    "ok":          "#5DC287",
    "err":         "#F87171",
    "warn":        "#FBBF24",
}


def _make_palette(base: dict[str, str]) -> dict[str, str]:
    """Expand the base palette with v1 legacy aliases pointing at v2 colors."""
    p = dict(base)
    # Strong border = ink in light, soft cream in dark. The mockup's borders
    # are intentionally heavy in light mode.
    p["border"] = base["ink"] if base["bg"].startswith("#F") else base["border_soft"]

    # v1 → v2 aliases — let existing widget code adopt the new palette unchanged
    p["bg_card"]   = base["card"]
    p["bg_field"]  = base["card"]
    p["bg_field2"] = base["bg2"]
    p["border2"]   = p["border"]
    p["accent"]    = base["yellow"]      # was purple-ish — now yellow primary
    p["accent2"]   = base["yellow_soft"] # hover state
    p["accent3"]   = base["orange"]      # spice / deeper accent
    p["success"]   = base["ok"]
    p["text"]      = base["ink"]
    p["text2"]     = base["ink2"]
    p["text3"]     = base["ink3"]
    p["log_text"]  = base["ok"]
    p["log_pmt"]   = base["orange"]
    p["log_dim"]   = base["ink3"]
    p["red"]       = base["err"]
    return p


LIGHT = _make_palette(LIGHT_BASE)
DARK  = _make_palette(DARK_BASE)

# Mutable runtime palette — widgets read via constants.C[...]. Default light.
C: dict[str, str] = dict(LIGHT)


def apply_theme(dark: bool) -> None:
    """Swap the active palette in-place. Call BEFORE building any UI."""
    src = DARK if dark else LIGHT
    C.clear()
    C.update(src)


# ============================================================================
# Typography
# ============================================================================
#
# Mockup uses Instrument Serif, Space Grotesk, JetBrains Mono. None ship with
# Windows. We resolve to whatever's installed, falling back to system fonts.

FONT_DISPLAY_CANDIDATES = ["Instrument Serif", "Georgia", "Cambria", "Times New Roman"]
FONT_BODY_CANDIDATES    = ["Space Grotesk", "Segoe UI Variable", "Segoe UI", "Arial"]
FONT_MONO_CANDIDATES    = ["JetBrains Mono", "Cascadia Mono", "Consolas", "Courier New"]


def _pick_available(candidates: list[str], root_for_check=None) -> str:
    try:
        families = set(tkfont.families(root=root_for_check))
    except Exception:
        return candidates[-1]
    for fam in candidates:
        if fam in families:
            return fam
    return candidates[-1]


FONTS = {
    "display": "Georgia",
    "body":    "Segoe UI",
    "mono":    "Consolas",
}


def resolve_fonts(root) -> None:
    """Resolve fonts against installed families. Call after the Tk root exists."""
    FONTS["display"] = _pick_available(FONT_DISPLAY_CANDIDATES, root)
    FONTS["body"]    = _pick_available(FONT_BODY_CANDIDATES, root)
    FONTS["mono"]    = _pick_available(FONT_MONO_CANDIDATES, root)


def F(role: str, size: int, weight: str = "normal", italic: bool = False) -> tuple:
    """Build a Tk font tuple for the named role."""
    fam = FONTS.get(role, FONTS["body"])
    slant = "italic" if italic else "roman"
    return (fam, size, weight, slant)
