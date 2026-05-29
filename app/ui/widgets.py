"""Custom Tk widgets used by the main app — ProgressBar, PhaseChip, TerminalLog,
plus shared log-file helpers and file-validation helpers.

Most of the v1 widgets that used to live here (DropZone, BrandMark, IconCanvas,
TextField, pill_button, etc.) were replaced by Smooth* widgets and removed in
Round 21 to keep this file focused.
"""

from __future__ import annotations

import datetime
import os
import tkinter as tk

from ..constants import C, F, FONTS, LOGS_DIR
from ..i18n import t

try:
    from tkinterdnd2 import DND_FILES  # noqa: F401  (re-exported by retro.py)
    HAS_DND = True
except ImportError:
    HAS_DND = False


MEDIA_EXTS = {".mp4", ".mp3", ".wav", ".m4a", ".mkv", ".webm", ".ogg", ".flac",
              ".aac", ".opus", ".mov", ".avi"}


# ---------- shared log-file helpers ----------

def today_log_path():
    """Return Path to today's rotating log file. Creates the dir if needed."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.date.today().strftime("%Y-%m-%d")
    return LOGS_DIR / f"notenara-{today}.log"


def open_today_log_file() -> bool:
    """Open today's log file in the OS default text viewer.

    Used from PreviewView / DoneView so the user can read the full pipeline
    history (including chunk failures) after a run finishes.
    """
    try:
        path = today_log_path()
        path.touch(exist_ok=True)
    except OSError:
        return False
    try:
        os.startfile(str(path))  # type: ignore[attr-defined]
        return True
    except (AttributeError, OSError):
        import subprocess
        try:
            subprocess.Popen(["xdg-open", str(path.parent)])
            return True
        except (FileNotFoundError, OSError):
            return False



# ============================================================================
# (Legacy BrandMark / IconCanvas / pill_button / DropZone were removed in
# Round 21 — replaced by BrandLogo / SmoothIcon / RoundedButton / RetroDropZone.)
# ============================================================================

def is_valid_media(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in MEDIA_EXTS

# ============================================================================
# (Legacy _item_title / TextField / WorkspaceField / ProjectField were removed
# in Round 21 — replaced by SmoothInput + SmoothDropdown in settings.py.)
# ============================================================================

class ProgressBar(tk.Canvas):
    """Canvas progress bar with rounded fill + optional inline phase chip."""

    def __init__(self, parent, **kw):
        super().__init__(parent, bg=C["bg_card"], highlightthickness=0,
                         height=8, **kw)
        self._pct = 0.0
        self.bind("<Configure>", lambda e: self._redraw())

    def set_progress(self, pct: float) -> None:
        self._pct = max(0.0, min(100.0, pct))
        self._redraw()

    def reset(self) -> None:
        self._pct = 0.0
        self._redraw()

    def _redraw(self) -> None:
        self.delete("all")
        w = self.winfo_width() or 460
        h = self.winfo_height() or 8
        # Track with rounded ends
        self.create_oval(0, 0, h, h, fill=C["bg_field2"], outline="")
        self.create_oval(w - h, 0, w, h, fill=C["bg_field2"], outline="")
        self.create_rectangle(h // 2, 0, w - h // 2, h,
                              fill=C["bg_field2"], outline="")
        # Fill
        fill_w = int(w * (self._pct / 100.0))
        if fill_w > h:
            self.create_oval(0, 0, h, h, fill=C["accent"], outline="")
            self.create_rectangle(h // 2, 0, fill_w - h // 2, h,
                                  fill=C["accent"], outline="")
            self.create_oval(fill_w - h, 0, fill_w, h,
                              fill=C["accent"], outline="")
        elif fill_w > 0:
            # Just a small cap, no straight middle
            self.create_oval(0, 0, fill_w, h, fill=C["accent"], outline="")


class PhaseChip(tk.Frame):
    """Small status chip shown during processing — current phase + step count."""

    def __init__(self, parent, **kw):
        super().__init__(parent, bg=C["bg_card"], **kw)
        self._inner = tk.Frame(self, bg=C["bg_field2"],
                                highlightthickness=1,
                                highlightbackground=C["border2"])
        # Don't pack automatically; caller decides visibility.

        self._dot = tk.Canvas(self._inner, width=8, height=8,
                                bg=C["bg_field2"], highlightthickness=0)
        self._dot.pack(side="left", padx=(10, 6), pady=6)
        self._dot.create_oval(0, 0, 8, 8, fill=C["accent2"], outline="")

        self._label = tk.Label(self._inner, text="",
                                 bg=C["bg_field2"], fg=C["text2"],
                                 font=("Consolas", 9))
        self._label.pack(side="left", padx=(0, 10), pady=4)

    def show(self, text: str):
        self._label.config(text=text)
        if not self._inner.winfo_ismapped():
            self._inner.pack(side="left", pady=(0, 8))
        if not self.winfo_ismapped():
            self.pack(fill="x", pady=(0, 6))

    def hide(self):
        self.pack_forget()


# ============================================================================
# TerminalLog
# ============================================================================

class TerminalLog(tk.Frame):
    def __init__(self, parent, **kw):
        super().__init__(parent, bg=C["bg_card"],
                         highlightthickness=1,
                         highlightbackground=C["border"], **kw)
        self._lines = 0
        # Mirror every log line to a daily rotating file so users can scroll
        # back past the visible buffer (and email it to support).
        try:
            self._log_file_path = today_log_path()
        except OSError:
            self._log_file_path = None

        hdr = tk.Frame(self, bg=C["bg_field2"], height=26)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        tk.Label(hdr, text=t("log.header"), bg=C["bg_field2"], fg=C["text2"],
                 font=("Consolas", 8, "bold")).pack(side="left", padx=(12, 6))
        tk.Label(hdr, text="·", bg=C["bg_field2"], fg=C["text3"],
                 font=("Consolas", 8)).pack(side="left", padx=(0, 6))
        tk.Label(hdr, text=t("log.stdout"), bg=C["bg_field2"], fg=C["text3"],
                 font=("Consolas", 8)).pack(side="left")

        # Right-side cluster: open-file + clear + line counter
        right = tk.Frame(hdr, bg=C["bg_field2"])
        right.pack(side="right", padx=(0, 12))

        self._counter_var = tk.StringVar(value=t("log.lines", n=0, s=""))
        tk.Label(right, textvariable=self._counter_var, bg=C["bg_field2"],
                 fg=C["text3"], font=("Consolas", 8)).pack(side="right")
        clear_btn = tk.Label(right, text=t("log.clear"),
                              bg=C["bg_field2"], fg=C["text3"],
                              font=("Consolas", 8), cursor="hand2")
        clear_btn.pack(side="right", padx=(0, 10))
        clear_btn.bind("<Button-1>", lambda e: self.clear())
        clear_btn.bind("<Enter>", lambda e: clear_btn.config(fg=C["accent2"]))
        clear_btn.bind("<Leave>", lambda e: clear_btn.config(fg=C["text3"]))

        if self._log_file_path is not None:
            open_btn = tk.Label(right, text=t("log.open"),
                                 bg=C["bg_field2"], fg=C["text3"],
                                 font=("Consolas", 8), cursor="hand2")
            open_btn.pack(side="right", padx=(0, 10))
            open_btn.bind("<Button-1>", lambda e: self._open_log_file())
            open_btn.bind("<Enter>",
                           lambda e: open_btn.config(fg=C["accent2"]))
            open_btn.bind("<Leave>",
                           lambda e: open_btn.config(fg=C["text3"]))

        body = tk.Frame(self, bg=C["bg_card"])
        body.pack(fill="both", expand=True)

        self._text = tk.Text(body, bg=C["bg_card"], fg=C["log_text"],
                             insertbackground=C["accent"],
                             relief="flat", bd=0,
                             font=("Consolas", 10),
                             state="disabled", wrap="word",
                             padx=14, pady=10,
                             height=8)
        self._text.tag_configure("prompt", foreground=C["log_pmt"])
        self._text.tag_configure("dim",    foreground=C["log_dim"])
        self._text.tag_configure("ok",     foreground=C["success"])
        self._text.tag_configure("err",    foreground=C["red"])
        self._text.tag_configure("warn",   foreground=C["warn"])
        self._text.tag_configure("info",   foreground=C["log_text"])
        self._text.tag_configure("link",   foreground=C["accent2"], underline=True)

        sb = tk.Scrollbar(body, command=self._text.yview, bg=C["bg_card"],
                          troughcolor=C["bg_card"], bd=0, width=6,
                          activebackground=C["border2"])
        self._text.configure(yscrollcommand=sb.set)
        self._text.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        self._show_cursor()

    def _show_cursor(self):
        self._text.configure(state="normal")
        self._text.insert("end", "$ ", "prompt")
        self._text.insert("end", t("log.awaiting"), "dim")
        self._text.configure(state="disabled")

    def clear(self):
        self._text.configure(state="normal")
        self._text.delete("1.0", "end")
        self._text.configure(state="disabled")
        self._lines = 0
        self._counter_var.set(t("log.lines", n=0, s=""))
        self._show_cursor()

    def log(self, msg: str, kind: str = "info"):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        # Mirror to disk first — even if Tk dies during the after(), the
        # line is already persisted. Multiline messages get one timestamp
        # at the start and each subsequent line is indented for readability.
        if self._log_file_path is not None:
            try:
                with open(self._log_file_path, "a", encoding="utf-8") as f:
                    prefix = f"[{ts}] [{kind:4}] "
                    pad = " " * len(prefix)
                    lines = msg.splitlines() or [""]
                    f.write(prefix + lines[0] + "\n")
                    for extra in lines[1:]:
                        f.write(pad + extra + "\n")
            except OSError:
                pass

        def _do():
            self._text.configure(state="normal")
            content = self._text.get("1.0", "end-1c")
            if t("log.awaiting") in content and self._lines == 0:
                self._text.delete("1.0", "end")
            self._text.insert("end", f"[{ts}] ", "dim")
            self._text.insert("end", f"{msg}\n", kind)
            self._text.see("end")
            self._text.configure(state="disabled")
            self._lines += 1
            self._counter_var.set(t(
                "log.lines", n=self._lines,
                s="s" if self._lines != 1 else ""))
        self.after(0, _do)

    def _open_log_file(self):
        """Open today's log file in the OS default text viewer."""
        open_today_log_file()
