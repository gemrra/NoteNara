"""Smooth-rendered widgets — antialiased via PIL + system icon fonts.

Why this file exists
--------------------
Tk's Canvas draws everything pixel-aligned with no antialiasing. Small icons
(16×16, 1px strokes) look jagged and "lowres". tk.Button has square corners
and can't be made truly pill-shaped without a custom widget.

This module solves both:

  * **SmoothIcon** — uses Segoe Fluent Icons (Win11) or Segoe MDL2 Assets
    (Win10+) as a system icon font. Glyphs render through the OS font engine
    with full antialiasing — crisp at any size.

  * **RoundedButton** — uses Pillow to render the button background as a 2×
    resolution image with a rounded rectangle + border, then downsamples
    with LANCZOS for clean antialiased corners. Text is rendered onto the
    same image via PIL.

  * **SmoothCircleIcon** — Pillow renders the yellow drop-zone circle with
    its arrow at 2× and downsamples. The result is a smooth circle and
    smooth strokes, unlike Canvas create_oval which is jagged.

Image handles are stored on each widget so Tk's image garbage collector
doesn't pop the images off-screen.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from typing import Callable, Optional

from PIL import Image, ImageDraw, ImageFont, ImageTk

from ..constants import C, F, FONTS, ASSETS_DIR


# ============================================================================
# System font discovery — Segoe Fluent Icons preferred, MDL2 Assets fallback
# ============================================================================

ICON_FONT_CANDIDATES = ["Segoe Fluent Icons", "Segoe MDL2 Assets",
                         "Segoe UI Symbol"]

# Lazy — resolved at first SmoothIcon construction.
_ICON_FONT: Optional[str] = None


def _resolve_icon_font() -> str:
    global _ICON_FONT
    if _ICON_FONT is not None:
        return _ICON_FONT
    try:
        from tkinter import font as tkfont
        avail = set(tkfont.families())
    except Exception:
        avail = set()
    for fam in ICON_FONT_CANDIDATES:
        if fam in avail:
            _ICON_FONT = fam
            return fam
    _ICON_FONT = ICON_FONT_CANDIDATES[-1]
    return _ICON_FONT


def _hex_rgb(hex_str: str) -> tuple[int, int, int]:
    """'#FFD83D' → (255, 216, 61)."""
    s = hex_str.lstrip("#")
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))


def _hex_rgba(hex_str: str, alpha: int = 255) -> tuple[int, int, int, int]:
    r, g, b = _hex_rgb(hex_str)
    return (r, g, b, alpha)


# ============================================================================
# Font path lookup (Windows fonts dir) — used by PIL ImageFont
# ============================================================================

_WIN_FONTS = Path("C:/Windows/Fonts")


def _try_font_paths(*candidates: str) -> Optional[Path]:
    for c in candidates:
        p = _WIN_FONTS / c
        if p.exists():
            return p
    return None


def _pil_font(role: str, size: int, weight: str = "normal") -> ImageFont.ImageFont:
    """Resolve a PIL ImageFont for the given body/display/mono role."""
    bold = weight == "bold"
    if role == "display":
        path = _try_font_paths(
            "georgiab.ttf" if bold else "georgia.ttf",
            "georgia.ttf")
    elif role == "mono":
        path = _try_font_paths(
            "JetBrainsMono-Regular.ttf",
            "cascadiamono.ttf",
            "consola.ttf",
            "consolab.ttf" if bold else "consola.ttf")
    else:  # body
        path = _try_font_paths(
            "segoeuib.ttf" if bold else "segoeui.ttf",
            "segoeui.ttf",
            "arial.ttf")
    try:
        if path:
            return ImageFont.truetype(str(path), size=size)
    except OSError:
        pass
    return ImageFont.load_default()


# ============================================================================
# SmoothIcon — Segoe Fluent / MDL2 system-font glyphs
# ============================================================================

class SmoothIcon(tk.Label):
    """A monochrome icon rendered as a system-font glyph.

    Pass the icon `name` from GLYPHS. Antialiased automatically by the OS
    font engine — no Canvas drawing involved.
    """

    GLYPHS: dict[str, str] = {
        # Settings tabs (Segoe Fluent Icons / MDL2 Assets codepoints)
        "users":         "",
        "lightning":     "",   # AI tab
        "cpu":           "",   # alias
        "mic":           "",
        "bell":          "",
        "folder":        "",
        "theme":         "",
        "info":          "",
        # Chrome / nav
        "gear":          "",
        "back":          "",
        "refresh":       "",
        "recent":        "",
        "more":          "",
        # Actions
        "x":             "",
        "check":         "",
        "play":          "",
        "copy":          "",
        "send":          "",
        "open_link":     "",
        "edit":          "",
        "save":          "",
        # Direction
        "down":          "",
        "up":            "",
        "chevron_right": "",
        "chevron_down":  "",
        # Round 21: Home (quick-escape) + log (in-app log)
        "home":          "",
        "log":           "",
    }

    def __init__(self, parent, name: str, size: int = 14,
                 color: Optional[str] = None, **kw):
        glyph = self.GLYPHS.get(name, "?")
        bg = kw.pop("bg", C["card"])
        fg = color or C["ink2"]
        family = _resolve_icon_font()
        super().__init__(parent, text=glyph,
                         font=(family, size),
                         fg=fg, bg=bg, **kw)
        self._color = fg

    def set_color(self, color: str) -> None:
        self._color = color
        self.configure(fg=color)

    def set_glyph(self, name: str) -> None:
        self.configure(text=self.GLYPHS.get(name, "?"))


# ============================================================================
# SmoothCircleIcon — yellow circle with antialiased ↓ arrow
# ============================================================================

class SmoothCircleIcon(tk.Label):
    """The drop-zone glyph: yellow circle with ink border and a down arrow.

    Rendered at 3× via PIL, downsampled with LANCZOS for crisp antialiasing.
    """

    def __init__(self, parent, size: int = 56,
                 fill: Optional[str] = None,
                 stroke: Optional[str] = None,
                 arrow: Optional[str] = None,
                 bg: Optional[str] = None, **kw):
        super().__init__(parent, bg=bg or C["card"], **kw)
        self._fill = fill or C["yellow"]
        self._stroke = stroke or C["ink"]
        self._arrow = arrow or C["ink"]
        self._size = size
        self._photo = self._render()
        self.configure(image=self._photo,
                       borderwidth=0, highlightthickness=0)

    def _render(self) -> ImageTk.PhotoImage:
        scale = 3
        s = self._size * scale
        img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        border = max(4, scale * 2)
        d.ellipse((border, border, s - border, s - border),
                  fill=_hex_rgb(self._fill),
                  outline=_hex_rgb(self._stroke),
                  width=border)
        # Smaller, more compact down arrow centered in the circle
        cx = s // 2
        top_y = int(s * 0.38)
        bot_y = int(s * 0.62)
        chev_y = int(s * 0.53)
        chev_w = int(s * 0.11)
        line_w = max(3, int(scale * 1.5))
        d.line((cx, top_y, cx, bot_y), fill=_hex_rgb(self._arrow),
               width=line_w)
        d.line((cx - chev_w, chev_y, cx, bot_y), fill=_hex_rgb(self._arrow),
               width=line_w)
        d.line((cx + chev_w, chev_y, cx, bot_y), fill=_hex_rgb(self._arrow),
               width=line_w)
        out = img.resize((self._size, self._size), Image.LANCZOS)
        return ImageTk.PhotoImage(out)


# ============================================================================
# SmoothPlayIcon — yellow square with antialiased ▶ play triangle (file card)
# ============================================================================

class SmoothPlayIcon(tk.Label):
    def __init__(self, parent, size: int = 42, bg: Optional[str] = None, **kw):
        super().__init__(parent, bg=bg or C["card"], **kw)
        self._size = size
        self._photo = self._render()
        self.configure(image=self._photo,
                       borderwidth=0, highlightthickness=0)

    def _render(self) -> ImageTk.PhotoImage:
        scale = 3
        s = self._size * scale
        img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        border = max(4, scale * 2)
        radius = int(s * 0.20)
        d.rounded_rectangle((border, border, s - border, s - border),
                             radius=radius,
                             fill=_hex_rgb(C["yellow"]),
                             outline=_hex_rgb(C["ink"]),
                             width=border)
        # Play triangle
        cx, cy = s // 2, s // 2
        w_t = int(s * 0.22)
        h_t = int(s * 0.28)
        d.polygon(
            [(cx - w_t // 2, cy - h_t),
             (cx - w_t // 2, cy + h_t),
             (cx + w_t, cy)],
            fill=_hex_rgb(C["ink"]))
        out = img.resize((self._size, self._size), Image.LANCZOS)
        return ImageTk.PhotoImage(out)


# (Round 21: SmoothBrandMark removed — superseded by BrandLogo, which
# rasterises the actual NoteNara SVG instead of approximating it.)


# ============================================================================
# RoundedButton — PIL-rendered rounded pill with hover state
# ============================================================================

class RoundedButton(tk.Label):
    """A pill button rendered as a PIL image.

    kind: "primary" (yellow fill, ink border, bold ink text) |
          "secondary" (cream fill, ink border, ink text) |
          "ghost" (transparent fill, ink border)
    size: "sm" | "md" | "lg"
    """

    SIZE_PRESETS = {
        "sm": dict(h=28, padx=12, font_size=10, radius=14),
        "md": dict(h=36, padx=18, font_size=10, radius=18),
        "lg": dict(h=44, padx=24, font_size=11, radius=22),
    }

    def __init__(self, parent, text: str,
                 command: Optional[Callable[[], None]] = None,
                 kind: str = "secondary",
                 size: str = "md",
                 width: Optional[int] = None,
                 stretch: bool = False,
                 bg: Optional[str] = None,
                 hover_fill: Optional[str] = None,
                 **kw):
        self._parent_bg = bg or C["card"]
        super().__init__(parent, bg=self._parent_bg,
                         borderwidth=0, highlightthickness=0,
                         cursor="hand2", **kw)
        self._text = text
        self._command = command
        self._kind = kind
        self._size = size
        self._enabled = True
        self._hovered = False
        # Optional per-instance hover fill override (e.g. yellow on a secondary)
        self._hover_fill_override = hover_fill

        preset = self.SIZE_PRESETS.get(size, self.SIZE_PRESETS["md"])
        self._h = preset["h"]
        self._padx = preset["padx"]
        self._font_size = preset["font_size"]
        self._radius = preset["radius"]
        # Width: explicit, stretch-to-parent, or auto-fit text
        self._explicit_w = width
        self._stretch = stretch

        # Pre-render both states at construction — hover just swaps which
        # image is shown. No PIL work in the hover/leave hot path = no
        # flicker, no race conditions.
        self._img_default: Optional[ImageTk.PhotoImage] = None
        self._img_hover: Optional[ImageTk.PhotoImage] = None
        self._img_disabled: Optional[ImageTk.PhotoImage] = None
        self._last_render_w: int = 0
        self._render_states()

        self.bind("<Button-1>", self._on_click)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

        if stretch:
            self.bind("<Configure>", self._on_configure)

    def _measure_text_width(self, text: str, font_size: int) -> int:
        # Use PIL to measure the text width with the actual font we'll render.
        try:
            f = _pil_font("body", font_size * 3, weight="bold")
            bbox = f.getbbox(text)
            return int((bbox[2] - bbox[0]) / 3)
        except Exception:
            return len(text) * font_size

    def _compute_width(self) -> int:
        if self._explicit_w:
            return self._explicit_w
        if self._stretch:
            w = self.winfo_width()
            return max(w, 100) if w > 1 else 200
        text_w = self._measure_text_width(self._text, self._font_size)
        return text_w + self._padx * 2

    def _palette(self):
        if self._kind == "primary":
            fill_hex = C["yellow"]
            hover_hex = self._hover_fill_override or C["yellow_soft"]
            border_hex = C["ink"]
            text_hex = C["ink"]
            weight = "bold"
        elif self._kind == "ghost":
            fill_hex = self._parent_bg
            hover_hex = self._hover_fill_override or C["bg2"]
            border_hex = C["ink"]
            text_hex = C["ink"]
            weight = "normal"
        else:
            fill_hex = C["card"]
            hover_hex = self._hover_fill_override or C["bg2"]
            border_hex = C["ink"]
            text_hex = C["ink"]
            weight = "normal"
        return fill_hex, hover_hex, border_hex, text_hex, weight

    def _render_image(self, w: int, fill_hex: str, border_hex: str,
                       text_hex: str, weight: str) -> ImageTk.PhotoImage:
        h = self._h
        scale = 3
        sw, sh = w * scale, h * scale
        img = Image.new("RGBA", (sw, sh), _hex_rgba(self._parent_bg))
        d = ImageDraw.Draw(img)
        border = max(4, scale + 1)
        radius = self._radius * scale
        # Slight inset so border isn't clipped
        d.rounded_rectangle(
            (border, border, sw - border, sh - border),
            radius=radius,
            fill=_hex_rgb(fill_hex),
            outline=_hex_rgb(border_hex),
            width=border)
        # Center text
        font = _pil_font("body", self._font_size * scale, weight=weight)
        try:
            bbox = d.textbbox((0, 0), self._text, font=font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            tx = (sw - tw) // 2 - bbox[0]
            ty = (sh - th) // 2 - bbox[1]
        except Exception:
            tx, ty = sw // 4, sh // 3
        d.text((tx, ty), self._text, fill=_hex_rgb(text_hex), font=font)
        out = img.resize((w, h), Image.LANCZOS)
        return ImageTk.PhotoImage(out)

    def _render_states(self, w: Optional[int] = None):
        """Render default + hover images once. Called on construction and on
        width changes for stretch mode."""
        if w is None:
            w = self._compute_width()
        if w < 40:
            w = 40
        if w == self._last_render_w:
            return
        self._last_render_w = w
        # Force a re-show next time even if image objects change
        self._current_img = None
        self._size_set = False
        fill_hex, hover_hex, border_hex, text_hex, weight = self._palette()
        self._img_default = self._render_image(
            w, fill_hex, border_hex, text_hex, weight)
        self._img_hover = self._render_image(
            w, hover_hex, border_hex, text_hex, weight)
        self._img_disabled = self._render_image(
            w, fill_hex, C["border_soft"], C["ink3"], weight)
        self._show_current_image(w)

    def _show_current_image(self, w: int):
        if not self._enabled:
            img = self._img_disabled
        elif self._hovered:
            img = self._img_hover
        else:
            img = self._img_default
        # Skip if already showing this image (avoids redundant Tk redraw)
        if getattr(self, "_current_img", None) is img:
            return
        self._current_img = img
        # Only set width/height on initial render; hover doesn't change size.
        if not getattr(self, "_size_set", False):
            self.configure(image=img, width=w, height=self._h)
            self._size_set = True
        else:
            self.configure(image=img)

    def _on_click(self, _):
        if self._enabled and self._command:
            self._command()

    def _on_enter(self, _):
        if not self._enabled:
            return
        self._hovered = True
        self._show_current_image(self._last_render_w or self._compute_width())

    def _on_leave(self, _):
        self._hovered = False
        self._show_current_image(self._last_render_w or self._compute_width())

    def _on_configure(self, event):
        if self._stretch and event.width > 1:
            # Only re-render if width actually changed by more than a couple px
            if abs(event.width - self._last_render_w) > 2:
                self._render_states(event.width)

    def set_text(self, text: str):
        self._text = text
        # Force re-render
        self._last_render_w = 0
        self._render_states()

    def set_enabled(self, enabled: bool):
        self._enabled = enabled
        self.configure(cursor="hand2" if enabled else "arrow")
        self._show_current_image(self._last_render_w or self._compute_width())


# ============================================================================
# SmoothCard — frame with PIL-rendered rounded background
# ============================================================================

class SmoothCard(tk.Frame):
    """Frame with PIL-rendered rounded background. Sizes to content.

    Layout: bg_canvas + content frame are both grid()'d in cell (0,0). Content
    has padx/pady = padding. Card's natural size = content size + 2*padding,
    so packing children into `card.inner` automatically grows the card.
    """

    def __init__(self, parent,
                 fill: Optional[str] = None,
                 border: Optional[str] = None,
                 border_width: float = 1.5,
                 radius: int = 18,
                 padding: int = 18,
                 bg: Optional[str] = None,
                 expand_cell: bool = False,
                 **kw):
        self._parent_bg = bg or C["card"]
        super().__init__(parent, bg=self._parent_bg,
                         borderwidth=0, highlightthickness=0, **kw)
        self._fill = fill or C["card"]
        self._border = border or C["ink"]
        self._border_w = border_width
        self._radius = radius
        self._padding = padding

        # Grid layout: both children in cell (0,0). bg_canvas behind (added
        # first), inner content on top.
        # columnconfigure: cell stretches horizontally to parent width.
        # rowconfigure: opt-in via expand_cell=True for cards that should
        # fill parent vertically (e.g. the outer chrome card). Default False
        # so content-sized cards (like RecentItem) don't elastically grow.
        self.columnconfigure(0, weight=1)
        if expand_cell:
            self.rowconfigure(0, weight=1)

        self._bg_canvas = tk.Canvas(self, bg=self._parent_bg,
                                       highlightthickness=0, borderwidth=0,
                                       width=0, height=0)
        self._bg_canvas.grid(row=0, column=0, sticky="nsew")

        self.inner = tk.Frame(self, bg=self._fill)
        self.inner.grid(row=0, column=0, sticky="nsew",
                         padx=padding, pady=padding)

        self._photo: Optional[ImageTk.PhotoImage] = None
        self._last_size: tuple[int, int] = (0, 0)
        self.bind("<Configure>", self._on_resize)

    def _on_resize(self, event):
        if event.width <= 1 or event.height <= 1:
            return
        if (event.width, event.height) == self._last_size:
            return
        self._last_size = (event.width, event.height)
        self._render_bg(event.width, event.height)

    def _render_bg(self, w: int, h: int):
        scale = 2
        sw, sh = w * scale, h * scale
        img = Image.new("RGBA", (sw, sh), _hex_rgba(self._parent_bg))
        d = ImageDraw.Draw(img)
        border = max(2, int(self._border_w * scale))
        radius_px = self._radius * scale
        d.rounded_rectangle(
            (border, border, sw - border, sh - border),
            radius=radius_px,
            fill=_hex_rgb(self._fill),
            outline=_hex_rgb(self._border),
            width=border)
        out = img.resize((w, h), Image.LANCZOS)
        self._photo = ImageTk.PhotoImage(out)
        self._bg_canvas.delete("all")
        self._bg_canvas.create_image(0, 0, image=self._photo, anchor="nw")


# ============================================================================
# SmoothInput — rounded Entry with focus state
# ============================================================================

class SmoothInput(tk.Frame):
    """A pill-rounded Entry with focus state.

    Composition: SmoothCard background + tk.Entry on top. Border colour
    swaps to orange when the entry has focus.
    """

    def __init__(self, parent,
                 placeholder: str = "",
                 width_chars: int = 20,
                 show: str = "",
                 height: int = 38,
                 radius: int = 11,
                 bg: Optional[str] = None,
                 **kw):
        self._parent_bg = bg or C["card"]
        super().__init__(parent, bg=self._parent_bg,
                         borderwidth=0, highlightthickness=0,
                         height=height, **kw)
        self._height = height
        self._radius = radius
        self._focused = False

        self._bg_canvas = tk.Canvas(self, bg=self._parent_bg,
                                       highlightthickness=0, borderwidth=0,
                                       height=height)
        self._bg_canvas.place(relx=0, rely=0, relwidth=1, relheight=1)

        self.entry = tk.Entry(self, bg=C["card"], fg=C["ink"],
                                insertbackground=C["orange"],
                                relief="flat", bd=0,
                                highlightthickness=0,
                                font=F("body", 11),
                                show=show, width=width_chars)
        self.entry.place(relx=0.5, rely=0.5, anchor="center",
                          relwidth=0.92, relheight=0.6)
        if placeholder:
            self._placeholder = placeholder
            self.entry.insert(0, placeholder)
            self.entry.config(fg=C["ink3"])
            self._has_real = False
            self.entry.bind("<FocusIn>", self._on_focus_in)
            self.entry.bind("<FocusOut>", self._on_focus_out)
        else:
            self._placeholder = ""
            self._has_real = True
            self.entry.bind("<FocusIn>", lambda e: self._set_focused(True))
            self.entry.bind("<FocusOut>", lambda e: self._set_focused(False))

        self._photo: Optional[ImageTk.PhotoImage] = None
        self._last_size = (0, 0)
        self.bind("<Configure>", self._on_resize)
        self.pack_propagate(False)

    def _on_resize(self, event):
        if event.width <= 1:
            return
        if (event.width, event.height) == self._last_size:
            return
        self._last_size = (event.width, event.height)
        self._render(event.width, event.height)

    def _render(self, w: int, h: int):
        scale = 2
        sw, sh = w * scale, h * scale
        img = Image.new("RGBA", (sw, sh), _hex_rgba(self._parent_bg))
        d = ImageDraw.Draw(img)
        border = max(2, scale * 2)
        radius_px = self._radius * scale
        border_color = C["orange"] if self._focused else C["ink"]
        d.rounded_rectangle(
            (border, border, sw - border, sh - border),
            radius=radius_px,
            fill=_hex_rgb(C["card"]),
            outline=_hex_rgb(border_color),
            width=border)
        out = img.resize((w, h), Image.LANCZOS)
        self._photo = ImageTk.PhotoImage(out)
        self._bg_canvas.delete("all")
        self._bg_canvas.create_image(0, 0, image=self._photo, anchor="nw")

    def _set_focused(self, focused: bool):
        self._focused = focused
        if self._last_size != (0, 0):
            self._render(*self._last_size)

    def _on_focus_in(self, _):
        if not self._has_real:
            self.entry.delete(0, "end")
            self.entry.config(fg=C["ink"])
        self._set_focused(True)

    def _on_focus_out(self, _):
        if not self.entry.get().strip():
            self.entry.delete(0, "end")
            self.entry.insert(0, self._placeholder)
            self.entry.config(fg=C["ink3"])
            self._has_real = False
        else:
            self.entry.config(fg=C["ink"])
            self._has_real = True
        self._set_focused(False)

    def get(self) -> str:
        v = self.entry.get().strip()
        if v == self._placeholder and not self._has_real:
            return ""
        return v

    def set(self, value: str):
        self.entry.delete(0, "end")
        if value:
            self.entry.insert(0, value)
            self.entry.config(fg=C["ink"])
            self._has_real = True
        elif self._placeholder:
            self.entry.insert(0, self._placeholder)
            self.entry.config(fg=C["ink3"])
            self._has_real = False


# ============================================================================
# SmoothCheckBox — rounded check, yellow when on
# ============================================================================

class SmoothCheckBox(tk.Label):
    def __init__(self, parent, checked: bool = False,
                 on_toggle: Optional[Callable[[bool], None]] = None,
                 size: int = 20,
                 bg: Optional[str] = None, **kw):
        super().__init__(parent, bg=bg or C["card"],
                         borderwidth=0, highlightthickness=0,
                         cursor="hand2", **kw)
        self._parent_bg = bg or C["card"]
        self._size = size
        self._checked = checked
        self._on_toggle = on_toggle
        self._render()
        self.bind("<Button-1>", self._click)

    def _render(self):
        scale = 3
        s = self._size * scale
        img = Image.new("RGBA", (s, s), _hex_rgba(self._parent_bg))
        d = ImageDraw.Draw(img)
        border = max(3, scale)
        # CIRCULAR checkbox — round shape matches retro aesthetic
        fill = C["yellow"] if self._checked else C["card"]
        d.ellipse((border, border, s - border, s - border),
                  fill=_hex_rgb(fill),
                  outline=_hex_rgb(C["ink"]),
                  width=border)
        if self._checked:
            # checkmark — sized + positioned for circle
            stroke = max(4, scale * 2)
            d.line((s * 0.30, s * 0.52, s * 0.45, s * 0.66,
                     s * 0.45, s * 0.66, s * 0.72, s * 0.36),
                    fill=_hex_rgb(C["ink"]),
                    width=stroke, joint="curve")
        out = img.resize((self._size, self._size), Image.LANCZOS)
        self._photo = ImageTk.PhotoImage(out)
        self.configure(image=self._photo)

    def _click(self, _):
        self._checked = not self._checked
        self._render()
        if self._on_toggle:
            self._on_toggle(self._checked)

    def set_checked(self, checked: bool):
        if self._checked != checked:
            self._checked = checked
            self._render()

    def is_checked(self) -> bool:
        return self._checked


# ============================================================================
# SmoothRadio — single radio button option
# ============================================================================

class SmoothRadio(tk.Label):
    """One option in a radio group. Caller manages the group's mutual-exclusion."""

    def __init__(self, parent, selected: bool = False,
                 on_select: Optional[Callable[[], None]] = None,
                 size: int = 20,
                 bg: Optional[str] = None, **kw):
        super().__init__(parent, bg=bg or C["card"],
                         borderwidth=0, highlightthickness=0,
                         cursor="hand2", **kw)
        self._parent_bg = bg or C["card"]
        self._size = size
        self._selected = selected
        self._on_select = on_select
        self._render()
        self.bind("<Button-1>", self._click)

    def _render(self):
        scale = 3
        s = self._size * scale
        img = Image.new("RGBA", (s, s), _hex_rgba(self._parent_bg))
        d = ImageDraw.Draw(img)
        border = max(3, scale)
        d.ellipse((border, border, s - border, s - border),
                  fill=_hex_rgb(C["card"]),
                  outline=_hex_rgb(C["ink"]),
                  width=border)
        if self._selected:
            inset = int(s * 0.27)
            d.ellipse((inset, inset, s - inset, s - inset),
                      fill=_hex_rgb(C["orange"]))
        out = img.resize((self._size, self._size), Image.LANCZOS)
        self._photo = ImageTk.PhotoImage(out)
        self.configure(image=self._photo)

    def _click(self, _):
        if self._on_select:
            self._on_select()

    def set_selected(self, selected: bool):
        if self._selected != selected:
            self._selected = selected
            self._render()


# ============================================================================
# SmoothCheckMark — large yellow celebratory badge for Done view
# ============================================================================

class SmoothCheckMark(tk.Label):
    def __init__(self, parent, size: int = 96, bg: Optional[str] = None, **kw):
        super().__init__(parent, bg=bg or C["card"],
                         borderwidth=0, highlightthickness=0, **kw)
        self._parent_bg = bg or C["card"]
        self._size = size
        scale = 3
        s = self._size * scale
        img = Image.new("RGBA", (s, s), _hex_rgba(self._parent_bg))
        d = ImageDraw.Draw(img)
        border = max(4, scale * 2)
        d.ellipse((border, border, s - border, s - border),
                  fill=_hex_rgb(C["yellow"]),
                  outline=_hex_rgb(C["ink"]),
                  width=border)
        # Big checkmark
        stroke = max(6, scale * 3)
        cx, cy = s / 2, s / 2
        d.line((cx - s * 0.20, cy + s * 0.02,
                 cx - s * 0.04, cy + s * 0.18,
                 cx - s * 0.04, cy + s * 0.18,
                 cx + s * 0.22, cy - s * 0.18),
                fill=_hex_rgb(C["ink"]),
                width=stroke, joint="curve")
        out = img.resize((self._size, self._size), Image.LANCZOS)
        self._photo = ImageTk.PhotoImage(out)
        self.configure(image=self._photo)


# ============================================================================
# SmoothStepBadge — small numbered yellow circle for Welcome view
# ============================================================================

class SmoothStepBadge(tk.Label):
    def __init__(self, parent, number: int, size: int = 32,
                 bg: Optional[str] = None, **kw):
        super().__init__(parent, bg=bg or C["card"],
                         borderwidth=0, highlightthickness=0, **kw)
        self._parent_bg = bg or C["card"]
        self._size = size
        scale = 3
        s = self._size * scale
        img = Image.new("RGBA", (s, s), _hex_rgba(self._parent_bg))
        d = ImageDraw.Draw(img)
        border = max(3, scale)
        d.ellipse((border, border, s - border, s - border),
                  fill=_hex_rgb(C["yellow"]),
                  outline=_hex_rgb(C["ink"]),
                  width=border)
        # Number text centered
        font = _pil_font("mono", int(self._size * 0.50 * scale / 1), weight="bold")
        text = str(number)
        try:
            bbox = d.textbbox((0, 0), text, font=font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            tx = (s - tw) / 2 - bbox[0]
            ty = (s - th) / 2 - bbox[1]
        except Exception:
            tx = s / 3
            ty = s / 3
        d.text((tx, ty), text, fill=_hex_rgb(C["ink"]), font=font)
        out = img.resize((self._size, self._size), Image.LANCZOS)
        self._photo = ImageTk.PhotoImage(out)
        self.configure(image=self._photo)


# ============================================================================
# SmoothChip — tiny rounded pill for format chips, badges
# ============================================================================

class SmoothChip(tk.Label):
    def __init__(self, parent, text: str,
                 fill: Optional[str] = None,
                 text_color: Optional[str] = None,
                 border: Optional[str] = None,
                 bg: Optional[str] = None,
                 font_size: int = 9,
                 padx: int = 10, pady: int = 4, **kw):
        self._parent_bg = bg or C["card"]
        super().__init__(parent, bg=self._parent_bg,
                         borderwidth=0, highlightthickness=0, **kw)
        self._text = text
        self._fill = fill or C["bg2"]
        self._text_color = text_color or C["ink2"]
        self._border = border or C["border_soft"]
        self._padx = padx
        self._pady = pady
        self._font_size = font_size
        self._photo = self._render()
        self.configure(image=self._photo)

    def _render(self) -> ImageTk.PhotoImage:
        scale = 3
        font = _pil_font("mono", self._font_size * scale)
        bbox = font.getbbox(self._text)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        w = (tw // scale) + self._padx * 2
        h = (th // scale) + self._pady * 2
        sw, sh = w * scale, h * scale
        img = Image.new("RGBA", (sw, sh), _hex_rgba(self._parent_bg))
        d = ImageDraw.Draw(img)
        border = max(2, scale)
        d.rounded_rectangle(
            (border, border, sw - border, sh - border),
            radius=sh // 2,
            fill=_hex_rgb(self._fill),
            outline=_hex_rgb(self._border),
            width=border)
        tx = (sw - tw) // 2 - bbox[0]
        ty = (sh - th) // 2 - bbox[1]
        d.text((tx, ty), self._text,
                fill=_hex_rgb(self._text_color), font=font)
        out = img.resize((w, h), Image.LANCZOS)
        return ImageTk.PhotoImage(out)


# ============================================================================
# SmoothDropdown — rounded pill picker replacing ttk.Combobox
# ============================================================================

class SmoothDropdown(tk.Frame):
    """Rounded dropdown — trigger pill + popup with selectable rows.

    Replaces ttk.Combobox where the default theme looks rectangular.
    """

    def __init__(self, parent,
                 values: Optional[list[str]] = None,
                 initial: str = "",
                 on_change: Optional[Callable[[str], None]] = None,
                 height: int = 36,
                 radius: int = 12,
                 placeholder: str = "Select…",
                 bg: Optional[str] = None,
                 **kw):
        self._parent_bg = bg or C["card"]
        super().__init__(parent, bg=self._parent_bg,
                         borderwidth=0, highlightthickness=0,
                         height=height, **kw)
        self._height = height
        self._radius = radius
        self._values = list(values or [])
        self._value = initial or ""
        self._placeholder = placeholder
        self._on_change = on_change
        self._popup: Optional[tk.Toplevel] = None
        self._photo: Optional[ImageTk.PhotoImage] = None
        self._last_size = (0, 0)

        self._bg_canvas = tk.Canvas(self, bg=self._parent_bg,
                                       highlightthickness=0, borderwidth=0,
                                       height=height)
        self._bg_canvas.place(relx=0, rely=0, relwidth=1, relheight=1)

        # Label sits inside the rounded bg image; chevron is reserved 30px on
        # the right. relwidth=1.0 with x=14 + width=-44 = 14 left pad + 30 for
        # chevron. Avoids text being clipped under the chevron.
        self._label = tk.Label(self, bg=C["card"], fg=C["ink"],
                                 font=F("body", 10),
                                 anchor="w", padx=0, pady=0)
        self._label.place(relx=0, rely=0.5, anchor="w", x=14,
                            relwidth=1.0, width=-44, relheight=0.6)
        self._chevron = SmoothIcon(self, "chevron_down", size=11,
                                      color=C["ink2"], bg=C["card"])
        self._chevron.place(relx=1, rely=0.5, anchor="e", x=-12)

        self.pack_propagate(False)
        self.bind("<Configure>", self._on_resize)
        for w in (self, self._label, self._chevron, self._bg_canvas):
            w.bind("<Button-1>", lambda e: self.toggle_popup())
            w.configure(cursor="hand2")
        self._update_label()

    def _on_resize(self, event):
        if event.width <= 1:
            return
        if (event.width, event.height) == self._last_size:
            return
        self._last_size = (event.width, event.height)
        self._render_bg(event.width, event.height)

    def _render_bg(self, w: int, h: int):
        scale = 2
        sw, sh = w * scale, h * scale
        img = Image.new("RGBA", (sw, sh), _hex_rgba(self._parent_bg))
        d = ImageDraw.Draw(img)
        border = max(2, scale * 2)
        d.rounded_rectangle(
            (border, border, sw - border, sh - border),
            radius=self._radius * scale,
            fill=_hex_rgb(C["card"]),
            outline=_hex_rgb(C["ink"]),
            width=border)
        out = img.resize((w, h), Image.LANCZOS)
        self._photo = ImageTk.PhotoImage(out)
        self._bg_canvas.delete("all")
        self._bg_canvas.create_image(0, 0, image=self._photo, anchor="nw")

    def _update_label(self):
        if self._value:
            self._label.configure(text=self._value, fg=C["ink"])
        else:
            self._label.configure(text=self._placeholder, fg=C["ink3"])

    def set_values(self, values: list[str]):
        self._values = list(values)
        if self._value and self._value not in self._values:
            self._value = ""
            self._update_label()

    def set(self, value: str):
        if value in self._values or value == "":
            self._value = value
            self._update_label()

    def get(self) -> str:
        return self._value

    def toggle_popup(self):
        if self._popup is not None and self._popup.winfo_exists():
            self.close_popup()
        else:
            self.open_popup()

    def open_popup(self):
        if not self._values:
            return
        self.update_idletasks()
        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.winfo_height() + 4
        w = self.winfo_width()
        item_h = 30
        max_visible = 7
        visible = min(len(self._values), max_visible)
        h = visible * item_h + 12

        popup = tk.Toplevel(self)
        popup.wm_overrideredirect(True)
        popup.wm_geometry(f"{w}x{h}+{x}+{y}")
        popup.configure(bg=self._parent_bg)

        # Rounded card bg
        bg_canvas = tk.Canvas(popup, bg=self._parent_bg,
                                highlightthickness=0, borderwidth=0,
                                width=w, height=h)
        bg_canvas.pack(fill="both", expand=True)
        scale = 2
        img = Image.new("RGBA", (w*scale, h*scale),
                          _hex_rgba(self._parent_bg))
        d = ImageDraw.Draw(img)
        border = scale * 2
        d.rounded_rectangle(
            (border, border, w*scale - border, h*scale - border),
            radius=self._radius * scale,
            fill=_hex_rgb(C["card"]),
            outline=_hex_rgb(C["ink"]),
            width=border)
        out = img.resize((w, h), Image.LANCZOS)
        photo = ImageTk.PhotoImage(out)
        bg_canvas._photo_ref = photo
        bg_canvas.create_image(0, 0, image=photo, anchor="nw")

        # Items overlay
        items = tk.Frame(popup, bg=C["card"])
        items.place(x=6, y=6, width=w - 12, height=h - 12)

        if len(self._values) <= max_visible:
            for v in self._values:
                self._build_item(items, v, item_h)
        else:
            sc = tk.Canvas(items, bg=C["card"],
                             highlightthickness=0)
            sc.pack(side="left", fill="both", expand=True)
            sb = tk.Scrollbar(items, orient="vertical",
                                command=sc.yview,
                                width=6, bg=C["card"], bd=0,
                                troughcolor=C["card"])
            sb.pack(side="right", fill="y")
            sc.configure(yscrollcommand=sb.set)
            inner = tk.Frame(sc, bg=C["card"])
            inner_id = sc.create_window((0, 0), window=inner, anchor="nw")
            for v in self._values:
                self._build_item(inner, v, item_h)
            inner.update_idletasks()
            sc.configure(scrollregion=sc.bbox("all"))
            sc.bind("<Configure>",
                      lambda e: sc.itemconfigure(inner_id, width=e.width))

        self._popup = popup
        popup.bind("<FocusOut>", lambda e: self.close_popup())
        popup.focus_set()
        popup.bind("<Escape>", lambda e: self.close_popup())

    def _build_item(self, parent, value: str, h: int):
        is_current = (value == self._value)
        bg = C["tint_yellow"] if is_current else C["card"]
        row = tk.Frame(parent, bg=bg, height=h)
        row.pack(fill="x")
        row.pack_propagate(False)
        lbl = tk.Label(row, text=value, bg=bg, fg=C["ink"],
                        font=F("body", 10), anchor="w", padx=10)
        lbl.pack(fill="both", expand=True)

        def select(_=None):
            self._value = value
            self._update_label()
            if self._on_change:
                self._on_change(value)
            self.close_popup()

        def hi(_):
            if not is_current:
                row.configure(bg=C["bg2"])
                lbl.configure(bg=C["bg2"])

        def lo(_):
            if not is_current:
                row.configure(bg=C["card"])
                lbl.configure(bg=C["card"])

        for w in (row, lbl):
            w.bind("<Button-1>", select)
            w.bind("<Enter>", hi)
            w.bind("<Leave>", lo)
            w.configure(cursor="hand2")

    def close_popup(self):
        if self._popup is not None:
            try:
                self._popup.destroy()
            except Exception:
                pass
            self._popup = None


# ============================================================================
# HeaderSmoothIconButton — 32×32 icon-only header button
# ============================================================================

class HeaderSmoothIconButton(tk.Frame):
    """Square icon-only button used in app header (recent, gear, theme, etc.)."""

    def __init__(self, parent, icon_name: str,
                 on_click: Callable[[], None],
                 size: int = 26, icon_size: int = 12, **kw):
        bg = kw.pop("bg", C["card"])
        super().__init__(parent, bg=bg, width=size, height=size, **kw)
        self.pack_propagate(False)
        self._bg = bg
        self._icon = SmoothIcon(self, icon_name, size=icon_size,
                                  color=C["ink2"], bg=bg)
        self._icon.place(relx=0.5, rely=0.5, anchor="center")
        for w in (self, self._icon):
            w.bind("<Button-1>", lambda e: on_click())
            w.bind("<Enter>", lambda e: self._hover(True))
            w.bind("<Leave>", lambda e: self._hover(False))
            w.configure(cursor="hand2")

    def _hover(self, on: bool):
        bg = C["bg2"] if on else self._bg
        self.configure(bg=bg)
        self._icon.configure(bg=bg, fg=C["ink"] if on else C["ink2"])



# ============================================================================
# BrandLogo — NoteNara mark
# ============================================================================

class BrandLogo(tk.Label):
    """Static rounded-square NoteNara logo, pre-rasterized at multiple sizes.

    The user shipped two SVG variants: a white-bg variant (orange square,
    white N) and a dark/coloured-bg variant (white square, orange N). We
    rasterised both into PNGs at 16/24/32/48/64/128/256 px and pick the
    smallest size >= requested. ImageTk keeps a strong ref so Tk's GC
    doesn't blank the label after a moment.
    """

    _CACHE: dict[tuple[str, int], ImageTk.PhotoImage] = {}

    def __init__(self, parent, size: int = 28, variant: str = "auto", **kw):
        bg = kw.pop("bg", C["card"])
        super().__init__(parent, bg=bg, **kw)
        self._size = size
        self._variant = variant
        self._photo = self._load(self._resolve_variant(bg), size)
        if self._photo is not None:
            self.configure(image=self._photo, borderwidth=0,
                           highlightthickness=0)
        else:
            # Fallback: show a coloured square so the layout doesn't collapse.
            self.configure(text="N", fg=C["ink"], width=2,
                           font=F("display", int(size * 0.55), italic=True))

    def _resolve_variant(self, bg: str) -> str:
        if self._variant in ("light", "dark"):
            return self._variant
        # 'auto' — pick variant whose own bg contrasts with the surface bg.
        # Card/cream bg is the light surface → use the white-bg variant
        # (orange square, visible). Dark surfaces use the inverse.
        try:
            bg_int = int(bg.lstrip("#"), 16)
            r, g, b = (bg_int >> 16) & 0xFF, (bg_int >> 8) & 0xFF, bg_int & 0xFF
            luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
        except (ValueError, AttributeError):
            luminance = 1.0
        return "light" if luminance > 0.5 else "dark"

    @classmethod
    def _load(cls, variant: str, size: int) -> Optional[ImageTk.PhotoImage]:
        key = (variant, size)
        if key in cls._CACHE:
            return cls._CACHE[key]
        # Pick smallest source size >= requested (or largest if all smaller).
        sizes = (16, 24, 32, 48, 64, 128, 256)
        choose = next((s for s in sizes if s >= size), sizes[-1])
        path = ASSETS_DIR / f"logo_{variant}-{choose}.png"
        if not path.exists():
            return None
        try:
            img = Image.open(path).convert("RGBA")
            if img.size != (size, size):
                img = img.resize((size, size), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            cls._CACHE[key] = photo
            return photo
        except (OSError, ValueError):
            return None
