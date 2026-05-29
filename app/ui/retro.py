"""Retro editorial widgets — direct ports of the HTML mockup components.

These are NEW widgets, deliberately separate from app/ui/widgets.py so the
mockup-faithful look isn't entangled with the v1-era widgets. The MainView
(and friends) compose these instead of the older equivalents.

Each widget mirrors a piece from NoteNara.html:
  RetroDropZone   — .dropzone (yellow circle + serif italic title + chips)
  FileCard        — .file-card (loaded state)
  OrnamentLabel   — .orn-row (◆ text with rule on both sides)
  FormatChip      — .chip (small pill, mono 10px)
  FlatCard        — .card.flat (subtle bg, thin border)
  RecentItem      — .row.between in recent (text col + tiny Open button)
  RecentList      — .card.flat containing RecentItems + dashed dividers
"""

from __future__ import annotations

import os
import tkinter as tk
from pathlib import Path
from typing import Callable, Optional

from ..constants import C, F
from .widgets import HAS_DND, MEDIA_EXTS
from .smooth import (
    HeaderSmoothIconButton, RoundedButton, SmoothChip, SmoothCircleIcon,
    SmoothIcon, SmoothPlayIcon,
)


# ============================================================================
# OrnamentLabel — "◆ text" with thin rules on both sides
# ============================================================================

class OrnamentLabel(tk.Frame):
    """Mockup ornament row: side line · ◆ text · side line."""

    def __init__(self, parent, text: str, **kw):
        super().__init__(parent, bg=C["card"], **kw)
        # Left rule
        tk.Frame(self, height=1, bg=C["border_soft"]).pack(
            side="left", fill="x", expand=True, padx=(0, 8), pady=8)
        # The label
        tk.Label(self, text=f"◆   {text}",
                 bg=C["card"], fg=C["ink3"],
                 font=F("mono", 9)).pack(side="left")
        # Right rule
        tk.Frame(self, height=1, bg=C["border_soft"]).pack(
            side="left", fill="x", expand=True, padx=(8, 0), pady=8)


# ============================================================================
# FormatChip — small rounded pill for "mp4", "mp3", etc.
# ============================================================================

def FormatChip(parent, text: str, bg: Optional[str] = None):
    """A real rounded pill chip (PIL-rendered) — was a square tk.Label before."""
    return SmoothChip(parent, text, bg=bg or C["card"])


class ChipRow(tk.Frame):
    """Horizontal row of SmoothChips with consistent gaps."""

    def __init__(self, parent, items: list[str], **kw):
        bg = kw.pop("bg", C["card"])
        super().__init__(parent, bg=bg, **kw)
        for i, item in enumerate(items):
            chip = SmoothChip(self, item, bg=bg)
            chip.pack(side="left", padx=(0 if i == 0 else 5))


# ============================================================================
# RetroDropZone — the headline drop zone from the mockup
# ============================================================================

class RetroDropZone(tk.Frame):
    """Drop zone matching the mockup's idle state.

    Layout (top to bottom, all center-aligned):
      [ Yellow ↓ circle (56×56, ink border) ]
      Drop a recording                     — Instrument Serif italic 26
      or click to browse                   — body 13, ink2
      [ mp4 ] [ mp3 ] [ wav ] [ m4a ] [ mkv ] [ mov ]   — chip row

    The outer dashed border + thick rounded corners can't be rendered with
    plain Tk borders, so we draw the dashed perimeter on a Canvas that sits
    behind the content stack. Result is mockup-fidelity within Tk limits.
    """

    HEIGHT = 260
    HOVER_HEIGHT = 260  # keep constant to avoid layout jump

    def __init__(self, parent,
                 on_click: Callable[[], None],
                 on_drop: Callable[[object], None],
                 chips: Optional[list[str]] = None,
                 **kw):
        super().__init__(parent, bg=C["card"],
                         height=self.HEIGHT, **kw)
        self.pack_propagate(False)
        self._on_click = on_click
        self._enabled = True
        self._parent_bg = C["card"]  # for PIL bg render (transparent corners)
        # Pre-rendered bg images (idle + hover), built on first Configure.
        self._bg_idle_img = None
        self._bg_hover_img = None
        self._last_bg_size = (0, 0)
        self._is_hovered = False

        # Background canvas (will hold PIL-rendered rounded rect image)
        self._bg = tk.Canvas(self, bg=C["card"],
                              highlightthickness=0)
        self._bg.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._bg.bind("<Configure>",
                        lambda e: self._redraw_border(hover=self._is_hovered))

        # Content stack (also receives clicks)
        self._content = tk.Frame(self, bg=C["card"])
        self._content.place(relx=0.5, rely=0.5, anchor="center")

        # Yellow icon circle — smooth/antialiased via PIL
        self._circle = SmoothCircleIcon(self._content, size=58,
                                          bg=C["card"])
        self._circle.pack(pady=(0, 14))

        # Title
        self._title_label = tk.Label(self._content, text="Drop a recording",
                                       bg=C["card"], fg=C["ink"],
                                       font=F("display", 24, italic=True))
        self._title_label.pack()

        # Subtitle
        self._sub_label = tk.Label(self._content, text="or click to browse",
                                     bg=C["card"], fg=C["ink2"],
                                     font=F("body", 11))
        self._sub_label.pack(pady=(6, 14))

        # Format chips
        chip_row = ChipRow(self._content,
                            chips or ["mp4", "mp3", "wav", "m4a", "mkv", "mov"],
                            bg=C["card"])
        chip_row.pack()

        # Bind clicks across the whole zone — including all chip children
        all_widgets = self._all_descendants()
        for widget in all_widgets:
            widget.bind("<Button-1>", lambda e: self._click())

        # Hover: bind Enter on every widget so children don't clear hover state.
        # Leave only clears state if mouse truly left the dropzone's geometric bounds
        # (in Tk, mouse moving onto a sibling widget fires Leave on the parent — we
        # need to check root coords to distinguish a real leave from a hand-off).
        for widget in all_widgets:
            widget.bind("<Enter>", lambda e: self._set_hover(True))
            widget.bind("<Leave>", self._on_leave_check)

        # Drag-and-drop
        if HAS_DND:
            self.drop_target_register("DND_Files")
            self.dnd_bind("<<Drop>>", on_drop)

    def _all_descendants(self) -> list:
        """Return self + every descendant widget for blanket event binding."""
        widgets = [self]
        def walk(w):
            for child in w.winfo_children():
                widgets.append(child)
                walk(child)
        walk(self)
        return widgets

    def _on_leave_check(self, event):
        """Leave fires when mouse crosses any child boundary. Distinguish:
        - True leave (mouse outside dropzone bounds) → unhover
        - Hand-off to a sibling/child (still inside bounds) → ignore
        """
        # Compute mouse position relative to dropzone root coords
        x_root = event.x_root
        y_root = event.y_root
        zx = self.winfo_rootx()
        zy = self.winfo_rooty()
        zw = self.winfo_width()
        zh = self.winfo_height()
        if zx <= x_root < zx + zw and zy <= y_root < zy + zh:
            # Still inside — don't unhover
            return
        self._set_hover(False)

    def _render_bg_image(self, w: int, h: int, hover: bool):
        """Render dropzone bg as a PIL image — rounded rect, antialiased border,
        no corner bleeding. Pre-rendered for both states."""
        from PIL import Image, ImageDraw, ImageTk
        from .smooth import _hex_rgb, _hex_rgba
        scale = 2
        sw, sh = w * scale, h * scale
        fill = C["tint_yellow"] if hover else C["card"]
        img = Image.new("RGBA", (sw, sh), _hex_rgba(self._parent_bg))
        d = ImageDraw.Draw(img)
        # Thin 1px-equivalent ink border
        border_w = max(2, scale)
        d.rounded_rectangle(
            (border_w, border_w, sw - border_w, sh - border_w),
            radius=20 * scale,
            fill=_hex_rgb(fill),
            outline=_hex_rgb(C["ink"]),
            width=border_w)
        out = img.resize((w, h), Image.LANCZOS)
        return ImageTk.PhotoImage(out)

    def _redraw_border(self, hover: bool):
        """Swap the pre-rendered bg image + sync child bg colors."""
        w = self._bg.winfo_width() or 1
        h = self._bg.winfo_height() or 1
        if w <= 1 or h <= 1:
            return
        # Re-render if size changed or no images cached
        size_key = (w, h)
        if size_key != self._last_bg_size:
            self._last_bg_size = size_key
            self._bg_idle_img = self._render_bg_image(w, h, hover=False)
            self._bg_hover_img = self._render_bg_image(w, h, hover=True)
        # Swap image on canvas
        self._bg.delete("all")
        img = self._bg_hover_img if hover else self._bg_idle_img
        self._bg.create_image(0, 0, image=img, anchor="nw")
        # Match canvas bg to current fill color so any edge pixels blend
        fill_color = C["tint_yellow"] if hover else C["card"]
        self._bg.configure(bg=self._parent_bg)
        # Recolor all children synchronously
        self._set_children_bg(fill_color)

    def _set_children_bg(self, color: str):
        """Recolor everything in the dropzone tree + re-render PIL widgets so
        their burnt-in 'parent_bg' corners match the new fill."""
        # Walk the tree once
        widgets = self._all_descendants()
        # Set Tk bg on plain widgets
        for w in widgets:
            if w is self._bg:
                continue  # already set above via self._bg.configure(bg=...)
            try:
                w.configure(bg=color)
            except tk.TclError:
                pass
        # Re-render any PIL-based widget with new parent_bg so its corners blend
        for w in widgets:
            if hasattr(w, "_parent_bg") and hasattr(w, "_render"):
                try:
                    w._parent_bg = color
                    w._photo = w._render()
                    w.configure(image=w._photo)
                except Exception:
                    pass

    def _set_hover(self, hover: bool):
        if not self._enabled:
            return
        if hover == self._is_hovered:
            return  # already in this state — no redraw needed
        self._is_hovered = hover
        self._redraw_border(hover=hover)

    def _click(self):
        if self._enabled:
            self._on_click()

    def set_enabled(self, enabled: bool):
        self._enabled = enabled
        self.configure(cursor="hand2" if enabled else "watch")


# ============================================================================
# FileCard — replaces the drop zone once a file is loaded
# ============================================================================

class FileCard(tk.Frame):
    """Card showing the loaded file: icon + name + meta + remove."""

    def __init__(self, parent,
                 filename: str, size_mb: float,
                 on_remove: Callable[[], None], **kw):
        super().__init__(parent, bg=C["card"],
                         highlightbackground=C["ink"],
                         highlightthickness=1.5,
                         **kw)
        inner = tk.Frame(self, bg=C["card"])
        inner.pack(fill="x", padx=14, pady=12)

        # Smooth yellow play-icon square (Pillow-rendered)
        play = SmoothPlayIcon(inner, size=42, bg=C["card"])
        play.pack(side="left", padx=(0, 12))

        # Text column
        text_col = tk.Frame(inner, bg=C["card"])
        text_col.pack(side="left", fill="x", expand=True)
        tk.Label(text_col, text=filename,
                 bg=C["card"], fg=C["ink"],
                 font=F("body", 11, "bold"),
                 anchor="w").pack(fill="x")
        meta = f"{size_mb:.1f} MB  ·  {Path(filename).suffix.lstrip('.')}"
        tk.Label(text_col, text=meta,
                 bg=C["card"], fg=C["ink3"],
                 font=F("mono", 9), anchor="w").pack(fill="x", pady=(2, 0))

        # X remove (using smooth icon)
        rm = SmoothIcon(inner, "x", size=14, color=C["ink3"], bg=C["card"])
        rm.pack(side="right", padx=8, pady=4)
        rm.configure(cursor="hand2")
        rm.bind("<Button-1>", lambda e: on_remove())
        rm.bind("<Enter>", lambda e: rm.set_color(C["ink"]))
        rm.bind("<Leave>", lambda e: rm.set_color(C["ink3"]))


# ============================================================================
# RecentItem + RecentList — bottom-anchored recent transcriptions
# ============================================================================

class RecentItem(tk.Frame):
    """One row inside the recent list — own rounded card."""

    def __init__(self, parent,
                 name: str, meta: str,
                 on_open: Callable[[], None], **kw):
        from .smooth import SmoothCard
        bg = kw.pop("bg", C["card"])
        super().__init__(parent, bg=bg, **kw)
        # Wrap content in SmoothCard for rounded look
        card = SmoothCard(self, radius=12, padding=10,
                            fill=C["bg2"], border=C["border_soft"],
                            border_width=1, bg=bg)
        card.pack(fill="x")

        inner = tk.Frame(card.inner, bg=C["bg2"])
        inner.pack(fill="x")

        text_col = tk.Frame(inner, bg=C["bg2"])
        text_col.pack(side="left", fill="x", expand=True)
        tk.Label(text_col, text=name,
                 bg=C["bg2"], fg=C["ink"],
                 font=F("body", 10, "bold"), anchor="w").pack(fill="x")
        tk.Label(text_col, text=meta,
                 bg=C["bg2"], fg=C["ink3"],
                 font=F("mono", 9), anchor="w").pack(fill="x", pady=(1, 0))

        open_btn = RoundedButton(inner, "Open", on_open,
                                   kind="secondary", size="sm",
                                   bg=C["bg2"],
                                   hover_fill=C["yellow"])
        open_btn.pack(side="right")


class RecentList(tk.Frame):
    """Vertical stack of RecentItem cards — no wrapping container needed."""

    def __init__(self, parent, items: list[dict],
                 on_open: Callable[[str], None],
                 max_items: int = 3, **kw):
        bg = kw.pop("bg", C["card"])
        super().__init__(parent, bg=bg, **kw)
        items = items[:max_items]
        if not items:
            from .smooth import SmoothCard
            empty = SmoothCard(self, radius=12, padding=14,
                                  fill=C["bg2"], border=C["border_soft"],
                                  border_width=1, bg=bg)
            empty.pack(fill="x")
            tk.Label(empty.inner, text="No recent transcriptions yet.",
                     bg=C["bg2"], fg=C["ink3"],
                     font=F("mono", 9)).pack()
            return
        for i, item in enumerate(items):
            row = RecentItem(self, item["name"], item["meta"],
                              on_open=lambda p=item["path"]: on_open(p),
                              bg=bg)
            row.pack(fill="x", pady=(0 if i == 0 else 6))


# ============================================================================
# scan_recent — read output/ folder for recent transcript files
# ============================================================================

def scan_recent(output_dir: Path, max_items: int = 3) -> list[dict]:
    """Return list of {name, meta, path} dicts for the most recently saved
    transcripts in `output_dir`."""
    if not output_dir.exists():
        return []
    try:
        files = sorted(
            output_dir.glob("*_transcript.txt"),
            key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return []
    import datetime
    out = []
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    for f in files[:max_items]:
        try:
            mtime = datetime.datetime.fromtimestamp(f.stat().st_mtime)
            date_str = f"{mtime.day} {months[mtime.month - 1]}"
        except (OSError, IndexError):
            date_str = "—"
        size = f.stat().st_size
        # Approx "10 min" from char count (~120 chars/min spoken)
        try:
            chars = f.stat().st_size
            mins = max(1, int(chars / 750))
        except OSError:
            mins = 0
        name = f.stem.replace("_transcript", "")
        meta = f"{date_str}  ·  ~{mins} min  ·  local only"
        out.append({"name": name, "meta": meta, "path": str(f)})
    return out
