"""NoteNara app — view-stack with the new preview-first flow.

Flow:
  Welcome (first run) → Main (drop + transcribe) → Preview (edit summary)
                                                       ├→ Copy (in place)
                                                       └→ Notion setup → Done

Each major screen is a Frame mounted into a single content area. App owns:
  * Navigation (.navigate / .go_back)
  * Shared session state for the current run (transcript, summary, etc.)
  * Background pipeline thread + cached Whisper service
"""

from __future__ import annotations

import os
import sys
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, ttk
from typing import Optional

from .. import APP_NAME, APP_TAGLINE, __version__
from ..config import (
    apply_theme_from_cfg, get_active_profile, is_first_run, load_config,
    resolve_output_dir, save_config, set_active_profile,
)
from ..constants import C, F, FONTS, ASSETS_DIR, apply_theme, resolve_fonts
from ..pipeline import MeetingPipeline, PipelineInputs, PipelineResult
from ..services.llm import LLMClient, SummaryResult
from ..services.notion import (
    CreatedPage, DatabaseRef, NotionClient, PageRef, format_page_title,
    today_iso,
)
from ..services.telegram import TelegramClient
from ..services.discord import DiscordClient
from ..services.whisper import TranscriptionCancelled, WhisperService
from .settings import SettingsView, WorkspaceEditorView
from .widgets import (
    HAS_DND, PhaseChip, ProgressBar, TerminalLog, is_valid_media,
)
from .retro import (
    FileCard, OrnamentLabel, RecentList, RetroDropZone, scan_recent,
)
from .smooth import (
    BrandLogo, HeaderSmoothIconButton, RoundedButton, SmoothCard,
    SmoothCheckBox, SmoothCheckMark, SmoothDropdown, SmoothIcon, SmoothInput,
    SmoothStepBadge,
)

if HAS_DND:
    from tkinterdnd2 import TkinterDnD
    _Base = TkinterDnD.Tk
else:
    _Base = tk.Tk  # type: ignore[assignment,misc]


# ============================================================================
# BaseView contract
# ============================================================================

class BaseView(tk.Frame):
    title: str = ""
    can_go_back: bool = False
    show_chrome: bool = True  # show app header (brand + settings)

    def __init__(self, parent, app):
        super().__init__(parent, bg=C["card"])
        self.app = app

    def on_enter(self, **kwargs):
        pass

    def on_exit(self):
        pass


# ============================================================================
# App
# ============================================================================

class App(_Base):  # type: ignore[misc, valid-type]
    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        apply_theme_from_cfg(self.cfg)
        resolve_fonts(self)

        # Per-session state — shared between views during one transcription run.
        self._file_path: Optional[Path] = None
        self._materi_hint: str = ""
        self._transcript_text: Optional[str] = None
        self._transcript_path: Optional[Path] = None
        self._summary: Optional[SummaryResult] = None
        self._notion_page: Optional[CreatedPage] = None

        self._processing = False
        self._cancel_event: Optional[threading.Event] = None
        self._whisper: Optional[WhisperService] = None

        # View management
        self._views: dict[str, BaseView] = {}
        self._current_view: Optional[BaseView] = None
        self._current_name: str = ""
        self._nav_stack: list[str] = []

        self.title(APP_NAME)
        self.geometry("640x820")
        self.configure(bg=C["bg"])
        self.minsize(560, 720)
        self._apply_window_icon()

        self._setup_ttk_style()
        self._build_chrome()
        self._build_views()

        if is_first_run(self.cfg):
            self.navigate("welcome")
        else:
            self.navigate("main")

    def _apply_window_icon(self):
        """Use the NoteNara logo for title bar AND Windows taskbar.

        Two Tk calls, two purposes:

          * `iconbitmap(default=...)` with a multi-size .ico is what makes
            Windows pick up the icon for the taskbar and alt-tab thumbnail.
            Without this, Windows shows the python.exe feather even though
            iconphoto was set — taskbar grouping uses the host exe icon.

          * `iconphoto(True, ...)` covers title bar slots and cross-platform
            window managers that ignore .ico.

        Combined with the AppUserModelID set in app.run(), Windows treats
        NoteNara as its own taskbar group with our logo, not a Python child.
        """
        ico = ASSETS_DIR / "NoteNara.ico"
        if ico.exists():
            try:
                self.iconbitmap(default=str(ico))
            except tk.TclError:
                pass

        # On Windows, iconbitmap with a multi-frame .ico handles every slot
        # (title bar, taskbar, alt-tab) with proper alpha. Calling iconphoto
        # AFTER iconbitmap overrides the title bar with a PNG that Tk
        # composites against a white background — visible as a white square
        # around the rounded logo. So we only set iconphoto on non-Windows
        # platforms where iconbitmap isn't supported.
        if sys.platform == "win32":
            return

        try:
            from PIL import Image, ImageTk
        except ImportError:
            return
        sizes = (16, 32, 48, 64)
        photos = []
        for s in sizes:
            p = ASSETS_DIR / f"logo_light-{s}.png"
            if not p.exists():
                continue
            try:
                photos.append(ImageTk.PhotoImage(Image.open(p)))
            except (OSError, ValueError):
                pass
        if photos:
            self._icon_photos = photos  # keep refs alive
            try:
                self.iconphoto(True, *photos)
            except tk.TclError:
                pass

    # ---------- ttk styling ----------

    def _setup_ttk_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("App.TCombobox",
                        fieldbackground=C["card"],
                        background=C["card"],
                        foreground=C["ink"],
                        arrowcolor=C["ink2"],
                        bordercolor=C["ink"],
                        lightcolor=C["ink"],
                        darkcolor=C["ink"],
                        insertcolor=C["orange"],
                        padding=8)
        style.map("App.TCombobox",
                  fieldbackground=[("readonly", C["card"]),
                                    ("focus", C["card"]),
                                    ("disabled", C["bg2"])],
                  selectbackground=[("readonly", C["card"]),
                                     ("focus", C["card"])],
                  selectforeground=[("readonly", C["ink"]),
                                     ("focus", C["ink"])],
                  bordercolor=[("focus", C["orange"])],
                  lightcolor=[("focus", C["orange"])],
                  darkcolor=[("focus", C["orange"])],
                  foreground=[("disabled", C["ink3"])])
        self.option_add("*TCombobox*Listbox.background", C["card"])
        self.option_add("*TCombobox*Listbox.foreground", C["ink"])
        self.option_add("*TCombobox*Listbox.selectBackground", C["yellow"])
        self.option_add("*TCombobox*Listbox.selectForeground", C["ink"])
        self.option_add("*TCombobox*Listbox.font", F("body", 11))
        self.option_add("*TCombobox*Listbox.borderWidth", 0)
        self.option_add("*TCombobox*Listbox.relief", "flat")

    # ---------- chrome (always-visible header) ----------

    def _build_chrome(self):
        outer = tk.Frame(self, bg=C["bg"])
        outer.pack(fill="both", expand=True, padx=10, pady=10)

        # Rounded outer card. expand_cell=True so the grid cell stretches to
        # fill the parent vertically (otherwise the cell sizes to inner-content
        # height and the bottom of the card is empty parent_bg, hiding the
        # bottom rounded corners). padding=6 keeps the curve visible.
        self._card_outer = SmoothCard(outer, radius=18, padding=6,
                                          fill=C["card"], border=C["ink"],
                                          border_width=1.2, bg=C["bg"],
                                          expand_cell=True)
        self._card_outer.pack(fill="both", expand=True)
        self._card = self._card_outer.inner

        # Header
        hdr = tk.Frame(self._card, bg=C["card"], height=42)
        hdr.pack(fill="x", padx=20, pady=(14, 0))
        hdr.pack_propagate(False)

        # Back (toggled per-view)
        self._back_btn = tk.Label(hdr, text="←", bg=C["card"], fg=C["ink2"],
                                    font=F("display", 20),
                                    cursor="hand2", padx=4)
        self._back_btn.bind("<Button-1>", lambda e: self.go_back())
        self._back_btn.bind("<Enter>", lambda e: self._back_btn.config(fg=C["ink"]))
        self._back_btn.bind("<Leave>", lambda e: self._back_btn.config(fg=C["ink2"]))

        # Title block — small rounded logo + wordmark + version
        self._brand_frame = tk.Frame(hdr, bg=C["card"])
        self._brand_frame.pack(side="left", fill="y")
        self._brand_logo = BrandLogo(self._brand_frame, size=28,
                                        bg=C["card"])
        self._brand_logo.pack(side="left", padx=(0, 8), pady=(2, 0))
        self._title_label = tk.Label(self._brand_frame, text=APP_NAME,
                                       bg=C["card"], fg=C["ink"],
                                       font=F("display", 20, italic=True))
        self._title_label.pack(side="left")
        self._version_label = tk.Label(self._brand_frame, text=f"  v{__version__}",
                                         bg=C["card"], fg=C["ink3"],
                                         font=F("mono", 9))
        self._version_label.pack(side="left", pady=(5, 0))

        # Right cluster — icon-only buttons (matches mockup exactly)
        self._right_actions = tk.Frame(hdr, bg=C["card"])
        self._right_actions.pack(side="right", pady=(8, 0))

        self._recent_btn = HeaderSmoothIconButton(
            self._right_actions, "recent",
            on_click=lambda: self._show_recent_toast())
        self._settings_icon_btn = HeaderSmoothIconButton(
            self._right_actions, "gear",
            on_click=lambda: self.navigate("settings"))
        # Quick-escape to home — shown on every non-main view so the user
        # can bail out from deep nav (Done → home, Preview → home, etc.).
        self._home_icon_btn = HeaderSmoothIconButton(
            self._right_actions, "home",
            on_click=lambda: self._jump_home())
        # View today's log file — visible on Preview / Done / NotionSetup so
        # user can audit chunk failures or full pipeline trail after a run.
        self._log_icon_btn = HeaderSmoothIconButton(
            self._right_actions, "log",
            on_click=lambda: self._open_log())

        # Divider
        tk.Frame(self._card, height=1, bg=C["ink"]).pack(
            fill="x", padx=18, pady=(10, 0))

        # Content area
        self._content = tk.Frame(self._card, bg=C["card"])
        self._content.pack(fill="both", expand=True)

    def _update_chrome(self):
        view = self._current_view
        if view is None:
            return
        # Back arrow
        if view.can_go_back and self._nav_stack:
            self._back_btn.pack(side="left", padx=(0, 10),
                                  before=self._brand_frame)
        else:
            self._back_btn.pack_forget()
        # Title
        if view.title:
            self._title_label.config(text=view.title)
            self._version_label.pack_forget()
        else:
            self._title_label.config(text=APP_NAME)
            self._version_label.pack(side="left", pady=(5, 0))
        # Header icons:
        # - On main view: recent + gear (settings)
        # - On every other view: home (quick-escape) + log (in-app log viewer)
        # The home icon is the answer to "I want to jump back to home from
        # anywhere" without walking the back-stack one step at a time.
        for btn in (self._recent_btn, self._settings_icon_btn,
                     self._home_icon_btn, self._log_icon_btn):
            btn.pack_forget()
        if self._current_name == "main":
            self._settings_icon_btn.pack(side="right", padx=(0, 0))
            self._recent_btn.pack(side="right", padx=(0, 10))
        else:
            self._home_icon_btn.pack(side="right", padx=(0, 0))
            self._log_icon_btn.pack(side="right", padx=(0, 10))

    def _show_recent_toast(self):
        # Stub — click scrolls to recent section on main view for now.
        main = self._views.get("main")
        if isinstance(main, MainView):
            main.refresh_recent()

    def _jump_home(self):
        """Quick-escape from any view back to the main screen. Resets the
        nav stack so the back arrow doesn't try to climb back into the
        finished pipeline state."""
        self._nav_stack = []
        self.navigate("main", push=False)

    def _open_log(self):
        from .widgets import open_today_log_file
        open_today_log_file()

    # ---------- views ----------

    def _build_views(self):
        self._views["main"] = MainView(self._content, app=self)
        self._views["preview"] = PreviewView(self._content, app=self)
        self._views["notion_setup"] = NotionSetupView(self._content, app=self)
        self._views["done"] = DoneView(self._content, app=self)
        self._views["settings"] = SettingsView(self._content, app=self)
        self._views["workspace_editor"] = WorkspaceEditorView(self._content, app=self)
        self._views["welcome"] = WelcomeView(self._content, app=self)

    def navigate(self, name: str, push: bool = True, **kwargs):
        if name not in self._views:
            return
        if self._current_view is not None:
            if push and self._current_name:
                self._nav_stack.append(self._current_name)
            self._current_view.on_exit()
            self._current_view.pack_forget()
        view = self._views[name]
        view.on_enter(**kwargs)
        view.pack(fill="both", expand=True)
        self._current_view = view
        self._current_name = name
        self._update_chrome()

    def go_back(self):
        if not self._nav_stack:
            return
        prev = self._nav_stack.pop()
        if self._current_view is not None:
            self._current_view.on_exit()
            self._current_view.pack_forget()
        view = self._views[prev]
        view.on_enter()
        view.pack(fill="both", expand=True)
        self._current_view = view
        self._current_name = prev
        self._update_chrome()

    # ---------- session reset ----------

    def reset_session(self):
        self._file_path = None
        self._materi_hint = ""
        self._transcript_text = None
        self._transcript_path = None
        self._summary = None
        self._notion_page = None
        self._cancel_event = None

    def on_settings_saved(self):
        old_whisper = (self.cfg.get("whisper") or {}) if self.cfg else {}
        self.cfg = load_config()
        new_whisper = self.cfg.get("whisper") or {}
        # Invalidate cached Whisper model whenever any field that affects
        # loading changes — otherwise the user's hardware/model swap silently
        # has no effect until app restart.
        load_keys = ("device", "model", "compute_type")
        if any(old_whisper.get(k) != new_whisper.get(k) for k in load_keys):
            self._whisper = None
        main = self._views.get("main")
        if isinstance(main, MainView):
            main.refresh_from_config()


# ============================================================================
# Helper widgets used by views
# ============================================================================

def _ornament_label(parent, text: str) -> tk.Frame:
    """Mockup-style label: '◆  ringkasan' with thin rules left/right."""
    row = tk.Frame(parent, bg=C["card"])
    tk.Frame(row, height=1, bg=C["border_soft"]).pack(side="left", fill="x",
                                                          expand=False, padx=(0, 8),
                                                          ipadx=6, pady=8)
    tk.Label(row, text=f"◆  {text}", bg=C["card"], fg=C["ink3"],
             font=F("mono", 9)).pack(side="left")
    tk.Frame(row, height=1, bg=C["border_soft"]).pack(side="left", fill="x",
                                                          expand=True, padx=(8, 0),
                                                          pady=8)
    return row


def _card(parent, **kw) -> SmoothCard:
    """Returns a SmoothCard — caller packs children into card.inner."""
    return SmoothCard(parent, radius=18, padding=18, bg=C["card"], **kw)


def _editable_text(parent, value: str, height: int = 3,
                    font_role: str = "body", font_size: int = 11) -> tk.Text:
    """A Text widget styled to feel like editable inline text."""
    t = tk.Text(parent, bg=C["card"], fg=C["ink"],
                 insertbackground=C["orange"],
                 relief="flat", bd=0, height=height,
                 wrap="word", padx=14, pady=10,
                 font=F(font_role, font_size),
                 highlightthickness=0)
    t.insert("1.0", value)
    return t


# ============================================================================
# Welcome view (first-run)
# ============================================================================

class WelcomeView(BaseView):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self._build()

    def _build(self):
        body = tk.Frame(self, bg=C["card"])
        body.pack(fill="both", expand=True, padx=44, pady=(36, 26))

        # Hero mark — large NoteNara logo (user-designed rounded-square N)
        BrandLogo(body, size=96, bg=C["card"]).pack()

        tk.Label(body, text="Welcome to",
                 bg=C["card"], fg=C["ink2"],
                 font=F("body", 11)).pack(pady=(24, 0))
        tk.Label(body, text=APP_NAME,
                 bg=C["card"], fg=C["ink"],
                 font=F("display", 32, italic=True)).pack()
        tk.Label(body, text=APP_TAGLINE,
                 bg=C["card"], fg=C["ink2"],
                 font=F("body", 11)).pack(pady=(2, 28))

        steps = [
            ("1", "Drop your meeting recording",
             "audio · video — mp4, mp3, wav, m4a, mov…"),
            ("2", "Review the auto-summary",
             "edit anything before publishing"),
            ("3", "Copy it — or send it to Notion",
             "workspace setup is asked on demand"),
        ]
        for num, title, desc in steps:
            row = tk.Frame(body, bg=C["card"])
            row.pack(fill="x", pady=6)
            badge = SmoothStepBadge(row, int(num), size=32, bg=C["card"])
            badge.pack(side="left", anchor="n")
            txt = tk.Frame(row, bg=C["card"])
            txt.pack(side="left", fill="x", expand=True, padx=(14, 0))
            tk.Label(txt, text=title, bg=C["card"], fg=C["ink"],
                     font=F("body", 11, "bold"), anchor="w").pack(fill="x")
            tk.Label(txt, text=desc, bg=C["card"], fg=C["ink3"],
                     font=F("mono", 9), anchor="w").pack(fill="x", pady=(2, 0))

        # Footer
        footer = tk.Frame(body, bg=C["card"])
        footer.pack(fill="x", side="bottom", pady=(28, 0))
        RoundedButton(footer, "Skip", lambda: self.app.navigate("main", push=False),
                     kind="ghost", size="md").pack(side="left")
        RoundedButton(footer, "Get started  →",
                     lambda: self._start(), kind="primary",
                     size="lg").pack(side="right")

    def _start(self):
        # If there are profiles, go straight to main. Else open workspace editor.
        if self.app.cfg.get("profiles"):
            self.app.navigate("main", push=False)
        else:
            self.app._nav_stack.append("main")
            self.app.navigate("workspace_editor", slug=None)


# ============================================================================
# Main view (drop + processing)
# ============================================================================

class MainView(BaseView):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self._build()

    def _build(self):
        # Single body Frame with TOP and BOTTOM regions — recent anchors bottom.
        body = tk.Frame(self, bg=C["card"])
        body.pack(fill="both", expand=True, padx=20, pady=(14, 14))

        # === BOTTOM REGION (recent) — packed first via side='bottom' so it
        # anchors and the top region expands into the space above.
        self._bottom_region = tk.Frame(body, bg=C["card"])
        self._bottom_region.pack(side="bottom", fill="x")

        self._recent_label = OrnamentLabel(self._bottom_region, "recent")
        self._recent_label.pack(fill="x", pady=(0, 8))
        self._recent_holder = tk.Frame(self._bottom_region, bg=C["card"])
        self._recent_holder.pack(fill="x")
        self._recent_list: Optional[RecentList] = None

        # === TOP REGION
        top = tk.Frame(body, bg=C["card"])
        top.pack(side="top", fill="both", expand=True)

        # --- Idle subtree: tagline + drop zone --------------------------------
        self._idle_frame = tk.Frame(top, bg=C["card"])
        self._idle_frame.pack(fill="x")

        # Short description — single small line above drop zone
        tk.Label(self._idle_frame,
                 text="Drop a recording — get a clean summary in seconds. Local & private.",
                 bg=C["card"], fg=C["ink3"],
                 font=F("mono", 9),
                 anchor="w", wraplength=460,
                 justify="left").pack(fill="x", pady=(0, 10))

        # Drop zone — mockup-faithful
        self._drop = RetroDropZone(self._idle_frame,
                                      on_click=self._browse,
                                      on_drop=self._on_drop)
        self._drop.pack(fill="x", pady=(0, 0))

        # --- Loaded subtree: file card + start button -------------------------
        self._loaded_frame = tk.Frame(top, bg=C["card"])
        # Not packed until file is set. Built lazily in _set_file().

        # --- Processing subtree: progress + phase chip + log + cancel --------
        self._proc_frame = tk.Frame(top, bg=C["card"])
        self._phase_chip = PhaseChip(self._proc_frame)
        self._progress = ProgressBar(self._proc_frame)
        self._progress.pack(fill="x", pady=(8, 12))
        self._log_widget = TerminalLog(self._proc_frame)
        self._log_widget.pack(fill="both", expand=True)
        self._cancel_btn_row = tk.Frame(self._proc_frame, bg=C["card"])
        self._cancel_btn = RoundedButton(self._cancel_btn_row, "Cancel",
                                            self._cancel_processing,
                                            kind="secondary", size="md")

    def on_enter(self, **_):
        # Re-show idle UI on entry; refresh recent list from disk.
        self._exit_processing_state()
        self._show_idle_subtree()
        self.refresh_recent()

    def refresh_from_config(self):
        # Called by App after settings save — nothing config-dependent here
        # to gate the start button (file presence is the only requirement).
        pass

    def refresh_recent(self):
        # Replace the recent list with a fresh scan.
        if self._recent_list is not None:
            self._recent_list.destroy()
        items = scan_recent(resolve_output_dir(self.app.cfg), max_items=3)
        self._recent_list = RecentList(
            self._recent_holder, items,
            on_open=lambda p: self._open_recent(p))
        self._recent_list.pack(fill="x")

    def _open_recent(self, path: str):
        # Open the transcript text file with the OS default app.
        try:
            os.startfile(path)  # type: ignore[attr-defined]
        except (AttributeError, OSError):
            import subprocess
            subprocess.Popen(["xdg-open", path])

    def _show_idle_subtree(self):
        # Hide loaded + processing, show idle.
        self._loaded_frame.pack_forget()
        self._proc_frame.pack_forget()
        for child in self._loaded_frame.winfo_children():
            child.destroy()
        if not self._idle_frame.winfo_ismapped():
            self._idle_frame.pack(fill="x")

    def _show_loaded_subtree(self):
        # Hide idle + processing, build loaded subtree.
        self._idle_frame.pack_forget()
        self._proc_frame.pack_forget()
        for child in self._loaded_frame.winfo_children():
            child.destroy()
        if not self._loaded_frame.winfo_ismapped():
            self._loaded_frame.pack(fill="x")

        # File card
        fp = self.app._file_path
        size_mb = fp.stat().st_size / 1_048_576
        card = FileCard(self._loaded_frame, fp.name, size_mb,
                          on_remove=self._reset_file)
        card.pack(fill="x", pady=(4, 16))

        # Start transcription button — full-width primary, smooth pill
        self._start_btn = RoundedButton(
            self._loaded_frame, "Start transcription  →",
            self._start, kind="primary", size="lg", stretch=True)
        self._start_btn.pack(fill="x")

    def _show_processing_subtree(self):
        self._idle_frame.pack_forget()
        self._loaded_frame.pack_forget()
        if not self._proc_frame.winfo_ismapped():
            self._proc_frame.pack(fill="both", expand=True)
        self._phase_chip.show("Starting…")
        self._cancel_btn_row.pack(fill="x", pady=(8, 0))
        self._cancel_btn.pack(side="right")
        self._progress.set_progress(0)

    def _reset_file(self):
        self.app._file_path = None
        self._show_idle_subtree()

    # ---------- file ----------

    def _browse(self):
        if self.app._processing:
            return
        path = filedialog.askopenfilename(
            title="Choose audio / video",
            filetypes=[("Audio/Video",
                         "*.mp4 *.mp3 *.wav *.m4a *.mkv *.webm *.ogg *.flac "
                         "*.aac *.opus *.mov *.avi"),
                        ("All files", "*.*")])
        if path:
            self._set_file(path)

    def _on_drop(self, event):
        if self.app._processing:
            return
        path = event.data.strip().strip("{}")
        if not os.path.exists(path):
            return
        if not is_valid_media(path):
            return
        self._set_file(path)

    def _set_file(self, path: str):
        self.app._file_path = Path(path)
        # Swap from idle subtree → loaded subtree
        self._show_loaded_subtree()

    # ---------- processing ----------

    def _start(self):
        if self.app._processing:
            return
        if not self.app._file_path or not self.app._file_path.exists():
            return
        # No upfront materi field anymore — pass filename stem as a weak hint
        # for the LLM. User refines the actual topic in Notion Setup.
        self.app._materi_hint = self.app._file_path.stem

        self._enter_processing_state()
        self.app._cancel_event = threading.Event()
        threading.Thread(target=self._pipeline_thread,
                         args=(self.app._file_path, self.app._materi_hint),
                         daemon=True).start()

    def _enter_processing_state(self):
        self.app._processing = True
        self._show_processing_subtree()

    def _exit_processing_state(self):
        self.app._processing = False
        self._proc_frame.pack_forget()
        self._cancel_btn_row.pack_forget()
        self._phase_chip.hide()
        # Return to whichever idle state matches our file presence
        if self.app._file_path:
            self._show_loaded_subtree()
        else:
            self._show_idle_subtree()

    def _cancel_processing(self):
        if self.app._cancel_event and not self.app._cancel_event.is_set():
            self.app._cancel_event.set()
            self._log_widget.log("Cancel requested — wait for safe stop point…",
                                  "warn")
            self._cancel_btn.set_enabled(False) if hasattr(
                self._cancel_btn, "set_enabled") else None
            # Force-restore UI after 5s even if the worker thread is stuck
            # inside C++ code (CUDA model load, ffmpeg decode, etc.) that
            # doesn't yield to Python's cancel check.
            self.after(5000, self._force_cancel_exit)

    def _force_cancel_exit(self):
        # If still processing, give up on the thread and let user start fresh.
        # The thread continues in the background but its results get
        # discarded since _cancel_event is set.
        if self.app._processing:
            self._log_widget.log(
                "Force-cancelled — UI restored. Background thread will "
                "finish silently and discard its work.", "warn")
            # Clear cached Whisper service. If the prior thread was stuck
            # inside WhisperModel(...) holding the load_lock, the next start
            # would deadlock waiting for that lock. Fresh instance bypasses it.
            self.app._whisper = None
            self._log_widget.log(
                "Whisper service cache cleared — next run will reload model.",
                "info")
            self._exit_processing_state()

    def _pipeline_thread(self, file_path: Path, materi_hint: str):
        log = self._log_widget.log
        # Immediate signal that the thread is running. If user sees nothing
        # after this, the hang is somewhere in service construction or the
        # Whisper model load.
        log(f"▶ Pipeline started · {file_path.name}", "info")
        self.after(0, lambda: self._phase_chip.show("Loading services…"))

        cfg = self.app.cfg
        llm_cfg = cfg.get("llm", {})
        whisper_cfg = cfg.get("whisper", {})

        if self.app._whisper is None:
            device = (whisper_cfg.get("device") or "cuda").lower()
            compute = whisper_cfg.get("compute_type", "float16")
            # CTranslate2 on CPU rejects float16 — auto-downgrade so the user
            # doesn't get a cryptic load failure after picking "Use CPU".
            if device == "cpu" and compute == "float16":
                compute = "int8"
                log("CPU device selected — using int8 (float16 is GPU-only).",
                    "info")
            log(f"Initializing Whisper service ({device.upper()})…", "info")
            self.app._whisper = WhisperService(
                model_name=whisper_cfg.get("model", "turbo"),
                compute_type=compute,
                device=device,
                beam_size=int(whisper_cfg.get("beam_size", 5)),
                vad_filter=bool(whisper_cfg.get("vad_filter", True)))
            log("Whisper service ready (model not loaded yet).", "info")

        llm = LLMClient(
            base_url=llm_cfg.get("base_url", "http://localhost:1234/v1"),
            model=llm_cfg.get("model", "auto"),
            api_key=llm_cfg.get("api_key", "lm-studio"),
            temperature=float(llm_cfg.get("temperature", 0.3)),
            timeout=int(llm_cfg.get("timeout", 300)),
            provider=llm_cfg.get("provider", "lm_studio"))

        # Notion + Telegram + Discord constructed for the API contract.
        # transcribe_and_summarize doesn't actually send notifications — that
        # happens in publish_to_notion — so disabled stubs are fine. Previously
        # this passed `discord=discord` with no `discord` var in scope, which
        # raised NameError and silently killed the thread (stuck "Loading
        # services…" with no error in the log).
        notion = NotionClient("")
        telegram = TelegramClient(enabled=False)
        discord = DiscordClient(enabled=False)

        pipeline = MeetingPipeline(
            whisper=self.app._whisper, llm=llm,
            notion=notion, telegram=telegram,
            discord=discord,
            output_dir=resolve_output_dir(cfg))

        def progress_cb(pct: float, phase: str):
            def _do():
                self._progress.set_progress(pct)
                if phase:
                    self._phase_chip.show(phase)
            self.after(0, _do)

        try:
            result = pipeline.transcribe_and_summarize(
                file_path=file_path,
                materi_hint=materi_hint,
                on_progress=progress_cb,
                on_log=log,
                cancel_event=self.app._cancel_event)
            # If cancel was requested during the run, discard results.
            if self.app._cancel_event and self.app._cancel_event.is_set():
                log("Discarded results — pipeline was cancelled.", "warn")
                self.after(0, lambda: self._progress.reset())
                self.after(0, self._exit_processing_state)
                return
            self.app._transcript_text = result["transcript_text"]
            self.app._transcript_path = result["transcript_path"]
            self.app._summary = result["summary"]
            warnings = result["warnings"]
            self.after(0, lambda: self._on_done(warnings))
        except TranscriptionCancelled:
            log("Cancelled.", "warn")
            self.after(0, lambda: self._progress.reset())
            self.after(0, self._exit_processing_state)
        except Exception as e:
            log(f"Pipeline failed · {e}", "err")
            import traceback as _tb
            log(_tb.format_exc(), "err")
            self.after(0, self._exit_processing_state)

    def _on_done(self, warnings: list[str]):
        # Move to preview regardless of LLM availability — preview can show a
        # transcript-only state if summary is None.
        self._exit_processing_state()
        self.app.navigate("preview")


# ============================================================================
# Preview view
# ============================================================================

class PreviewView(BaseView):
    title = "Review"
    can_go_back = True

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self._build()

    def _build(self):
        # Scrollable body
        wrap = tk.Frame(self, bg=C["card"])
        wrap.pack(fill="both", expand=True)

        self._canvas = tk.Canvas(wrap, bg=C["card"], highlightthickness=0)
        self._canvas.pack(side="left", fill="both", expand=True)
        sb = tk.Scrollbar(wrap, orient="vertical", command=self._canvas.yview,
                           bg=C["card"], troughcolor=C["card"], bd=0, width=6,
                           activebackground=C["border_soft"])
        sb.pack(side="right", fill="y")
        self._canvas.configure(yscrollcommand=sb.set)

        self._inner = tk.Frame(self._canvas, bg=C["card"])
        self._inner_id = self._canvas.create_window((0, 0), window=self._inner,
                                                       anchor="nw")
        self._inner.bind("<Configure>",
                          lambda e: self._canvas.configure(
                              scrollregion=self._canvas.bbox("all")))
        self._canvas.bind("<Configure>",
                           lambda e: self._canvas.itemconfigure(
                               self._inner_id, width=e.width))

        # Mouse-wheel scroll. The canvas + every descendant of _inner needs
        # the binding because Tk delivers wheel events to the widget under
        # the cursor, not the canvas. _bind_wheel_recursively is called
        # after on_enter rebuilds _inner so new children get the binding too.
        def _on_wheel(event):
            if event.delta:
                self._canvas.yview_scroll(-int(event.delta / 120), "units")
            else:
                self._canvas.yview_scroll(-1 if event.num == 4 else 1, "units")
        self._wheel = _on_wheel
        self._canvas.bind("<MouseWheel>", _on_wheel)
        self._canvas.bind("<Button-4>", _on_wheel)
        self._canvas.bind("<Button-5>", _on_wheel)

        # Content (built lazily in on_enter)
        # Footer
        self._footer = tk.Frame(self, bg=C["card"],
                                 highlightbackground=C["border_soft"],
                                 highlightthickness=1)
        self._footer.pack(fill="x", side="bottom")
        self._build_footer()

    def _build_footer(self):
        row = tk.Frame(self._footer, bg=C["card"])
        row.pack(fill="x", padx=20, pady=12)
        RoundedButton(row, "Copy markdown", self._copy_md,
                       kind="secondary", size="sm").pack(side="left", padx=(0, 6))
        RoundedButton(row, "Copy plain", self._copy_plain,
                       kind="secondary", size="sm").pack(side="left", padx=6)
        RoundedButton(row, "View log", self._view_log,
                       kind="ghost", size="sm").pack(side="left", padx=6)
        RoundedButton(row, "Send to Notion  →", self._send_to_notion,
                       kind="primary", size="md").pack(side="right")

    def _view_log(self):
        from .widgets import open_today_log_file
        open_today_log_file()

    def on_enter(self, **_):
        for child in self._inner.winfo_children():
            child.destroy()
        self._populate()
        # Rebind wheel after fresh population so new widgets respond.
        self.after(50, self._bind_wheel_recursively)

    def _bind_wheel_recursively(self):
        def walk(w):
            w.bind("<MouseWheel>", self._wheel)
            w.bind("<Button-4>", self._wheel)
            w.bind("<Button-5>", self._wheel)
            for c in w.winfo_children():
                walk(c)
        walk(self._inner)
        # Also reset scroll to top so reopening Preview doesn't land mid-page.
        self._canvas.yview_moveto(0)

    def _populate(self):
        inner = self._inner

        # Header strip
        head = tk.Frame(inner, bg=C["card"])
        head.pack(fill="x", padx=24, pady=(16, 4))
        fname = self.app._file_path.stem if self.app._file_path else "transcript"
        tk.Label(head, text=fname, bg=C["card"], fg=C["ink"],
                 font=F("display", 22, italic=True),
                 anchor="w").pack(fill="x")
        chars = len(self.app._transcript_text or "")
        summary = self.app._summary
        kp = len(summary.key_points) if summary else 0
        ai_n = len(summary.action_items) if summary else 0
        meta = f"{chars} chars  ·  {kp} key points  ·  {ai_n} action items"
        if summary and getattr(summary, "truncated", False):
            meta += "  ·  truncated"
        tk.Label(head, text=meta, bg=C["card"], fg=C["ink3"],
                 font=F("mono", 9), anchor="w").pack(fill="x", pady=(4, 0))

        if summary is None:
            # LLM failed — show only transcript + manual options
            tk.Label(inner,
                     text="No summary available (LLM unreachable).",
                     bg=C["card"], fg=C["warn"],
                     font=F("body", 11), anchor="w").pack(
                fill="x", padx=24, pady=(14, 6))
            tk.Label(inner,
                     text="The transcript is saved locally. Open Settings → AI "
                           "model to fix the connection, then try again.",
                     bg=C["card"], fg=C["ink2"],
                     font=F("body", 10), wraplength=480, justify="left",
                     anchor="w").pack(fill="x", padx=24, pady=(0, 14))
        else:
            self._populate_summary_section(inner, summary)
            self._populate_keypoints_section(inner, summary)
            self._populate_actions_section(inner, summary)

        # Raw transcript (collapsed)
        self._populate_raw_section(inner)

    def _populate_summary_section(self, inner, summary):
        _ornament_label(inner, "summary").pack(fill="x", padx=24, pady=(18, 8))
        card = _card(inner)
        card.pack(fill="x", padx=24)
        self._summary_text = _editable_text(card.inner, summary.summary,
                                              height=4, font_role="body",
                                              font_size=11)
        self._summary_text.pack(fill="x")

    def _populate_keypoints_section(self, inner, summary):
        n = len(summary.key_points)
        _ornament_label(inner, f"key points · {n}").pack(fill="x", padx=24,
                                                            pady=(18, 8))
        card = _card(inner)
        card.pack(fill="x", padx=24)
        self._keypoints_widgets = []
        for kp in summary.key_points:
            self._add_point_row(card.inner, kp, self._keypoints_widgets)

    def _populate_actions_section(self, inner, summary):
        n = len(summary.action_items)
        _ornament_label(inner, f"action items · {n}").pack(fill="x", padx=24,
                                                                pady=(18, 8))
        card = _card(inner)
        card.pack(fill="x", padx=24)
        self._action_widgets = []
        for ai in summary.action_items:
            self._add_action_row(card.inner, ai, self._action_widgets)

    def _populate_raw_section(self, inner):
        _ornament_label(inner, "raw transcript").pack(fill="x", padx=24,
                                                          pady=(18, 8))
        card = _card(inner)
        card.pack(fill="x", padx=24, pady=(0, 24))
        # Just show first ~280 chars + size; full text in the local file
        preview = (self.app._transcript_text or "")[:280]
        if len(self.app._transcript_text or "") > 280:
            preview += "  …"
        tk.Label(card.inner, text=preview, bg=C["card"], fg=C["ink2"],
                 font=F("mono", 10), wraplength=460, justify="left",
                 anchor="w").pack(fill="x", pady=(0, 6))
        if self.app._transcript_path:
            tk.Label(card.inner,
                     text=f"full → {self.app._transcript_path.name}",
                     bg=C["card"], fg=C["ink3"],
                     font=F("mono", 9), anchor="w").pack(fill="x")

    def _add_action_row(self, parent, text: str, store: list):
        row = tk.Frame(parent, bg=C["card"])
        row.pack(fill="x", pady=4)
        cb = SmoothCheckBox(row, checked=False, size=18, bg=C["card"])
        cb.pack(side="left", padx=(0, 10), anchor="n", pady=(4, 0))
        entry = tk.Entry(row, bg=C["card"], fg=C["ink"],
                          insertbackground=C["orange"],
                          relief="flat", bd=0,
                          highlightthickness=1,
                          highlightbackground=C["border_soft"],
                          highlightcolor=C["orange"],
                          font=F("body", 11))
        entry.insert(0, text)
        entry.pack(side="left", fill="x", expand=True, ipady=4)
        store.append((entry, cb))

    def _add_point_row(self, parent, text: str, store: list):
        row = tk.Frame(parent, bg=C["card"])
        row.pack(fill="x", pady=4)
        tk.Label(row, text="▸", bg=C["card"], fg=C["ink2"],
                 font=F("body", 11)).pack(side="left", padx=(0, 8), anchor="n")
        entry = tk.Entry(row, bg=C["card"], fg=C["ink"],
                          insertbackground=C["orange"],
                          relief="flat", bd=0,
                          highlightthickness=1,
                          highlightbackground=C["border_soft"],
                          highlightcolor=C["orange"],
                          font=F("body", 11))
        entry.insert(0, text)
        entry.pack(side="left", fill="x", expand=True, ipady=4)
        store.append(entry)

    # ---------- collect edits + actions ----------

    def _collect_summary(self) -> Optional[SummaryResult]:
        if self.app._summary is None:
            return None
        text = self._summary_text.get("1.0", "end-1c").strip()
        points = [e.get().strip() for e in self._keypoints_widgets
                   if e.get().strip()]
        actions = [e.get().strip() for (e, _) in self._action_widgets
                    if e.get().strip()]
        return SummaryResult(
            summary=text,
            key_points=points,
            action_items=actions,
            raw=self.app._summary.raw,
            truncated=self.app._summary.truncated,
        )

    def _render_markdown(self) -> str:
        s = self._collect_summary()
        if s is None:
            return self.app._transcript_text or ""
        lines = [f"## Summary\n\n{s.summary}\n",
                 "## Key points", *[f"- {p}" for p in s.key_points], "",
                 "## Action items", *[f"- [ ] {a}" for a in s.action_items], ""]
        return "\n".join(lines)

    def _render_plain(self) -> str:
        s = self._collect_summary()
        if s is None:
            return self.app._transcript_text or ""
        out = [s.summary, "", "Key points:"]
        out += [f"  • {p}" for p in s.key_points]
        out += ["", "Action items:"]
        out += [f"  □ {a}" for a in s.action_items]
        return "\n".join(out)

    def _copy_md(self):
        self._copy_to_clipboard(self._render_markdown(), "Markdown copied")

    def _copy_plain(self):
        self._copy_to_clipboard(self._render_plain(), "Text copied")

    def _copy_to_clipboard(self, text: str, toast: str):
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update()
        # Tiny visual hint — flash the footer
        original = self._footer.cget("bg")
        self._footer.configure(bg=C["tint_yellow"])
        self.after(220, lambda: self._footer.configure(bg=original))

    def _send_to_notion(self):
        # Persist the edited summary back to app state
        self.app._summary = self._collect_summary()
        if self.app._summary is None:
            return
        self.app.navigate("notion_setup")


# ============================================================================
# Notion Setup view
# ============================================================================

class NotionSetupView(BaseView):
    title = "Send to Notion"
    can_go_back = True

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self._databases: list[DatabaseRef] = []
        self._projects: list[PageRef] = []
        self._build()

    def _build(self):
        body = tk.Frame(self, bg=C["card"])
        body.pack(fill="both", expand=True, padx=26, pady=(16, 20))

        tk.Label(body, text="workspace · target · project · topic",
                 bg=C["card"], fg=C["ink3"],
                 font=F("mono", 9), anchor="w").pack(fill="x", pady=(0, 14))

        # Workspace dropdown
        self._field_label(body, "Workspace")
        self._workspace_dd = SmoothDropdown(body, values=[],
                                                placeholder="Select workspace…",
                                                on_change=self._on_workspace_change_v,
                                                height=36, radius=12,
                                                bg=C["card"])
        self._workspace_dd.pack(fill="x", pady=(0, 14))

        # Target DB display — rounded card, not raw label box
        self._field_label(body, "Target database")
        self._target_card = SmoothCard(body, radius=12, padding=12,
                                          bg=C["card"])
        self._target_card.pack(fill="x", pady=(0, 14))
        self._target_label = tk.Label(self._target_card.inner, text="—",
                                         bg=C["card"], fg=C["ink2"],
                                         font=F("mono", 10), anchor="w")
        self._target_label.pack(fill="x")

        # Project (optional)
        self._field_label(body, "Project   optional")
        self._project_dd = SmoothDropdown(body, values=["(no project)"],
                                              initial="(no project)",
                                              on_change=lambda v: self._refresh_preview(),
                                              placeholder="(no project)",
                                              height=36, radius=12,
                                              bg=C["card"])
        self._project_dd.pack(fill="x", pady=(0, 14))

        # Topic
        self._field_label(body, "Topic")
        self._topic_input = SmoothInput(body, placeholder="",
                                           height=38, radius=12,
                                           bg=C["card"])
        self._topic_input.pack(fill="x", pady=(0, 14))
        self._topic_entry = self._topic_input.entry  # back-compat

        # Meeting date — overridable. Defaults to the recording's mtime so a
        # transcript of yesterday's meeting doesn't get filed under today.
        # ISO format (YYYY-MM-DD); shown in title preview after parsing.
        self._field_label(body, "Meeting date   YYYY-MM-DD")
        self._date_input = SmoothInput(body, placeholder="2026-05-26",
                                          height=38, radius=12,
                                          bg=C["card"])
        self._date_input.pack(fill="x", pady=(0, 4))
        self._date_entry = self._date_input.entry
        self._date_hint = tk.Label(body, text="",
                                      bg=C["card"], fg=C["ink3"],
                                      font=F("mono", 9), anchor="w")
        self._date_hint.pack(fill="x", pady=(0, 14))
        self._date_entry.bind("<KeyRelease>", lambda e: self._refresh_preview())

        # Title preview as SmoothCard with soft tint
        prev_card = SmoothCard(body, radius=12, padding=12, bg=C["card"])
        prev_card.pack(fill="x", pady=(0, 14))
        tk.Label(prev_card.inner, text="PAGE TITLE PREVIEW",
                 bg=C["card"], fg=C["ink3"],
                 font=F("mono", 9), anchor="w").pack(fill="x", pady=(0, 4))
        self._title_preview = tk.Label(prev_card.inner, text="—",
                                          bg=C["card"], fg=C["ink"],
                                          font=F("display", 14, italic=True),
                                          anchor="w", wraplength=460,
                                          justify="left")
        self._title_preview.pack(fill="x")

        # Update preview on topic edit
        self._topic_entry.bind("<KeyRelease>", lambda e: self._refresh_preview())

        # Status / footer
        self._status = tk.Label(body, text="", bg=C["card"], fg=C["ink3"],
                                  font=F("mono", 9), anchor="w")
        self._status.pack(fill="x", pady=(0, 8))

        # Footer
        footer = tk.Frame(self, bg=C["card"],
                           highlightbackground=C["border_soft"],
                           highlightthickness=1)
        footer.pack(fill="x", side="bottom")
        row = tk.Frame(footer, bg=C["card"])
        row.pack(fill="x", padx=20, pady=12)
        RoundedButton(row, "Back", lambda: self.app.go_back(),
                       kind="secondary", size="md").pack(side="left")
        self._publish_btn = RoundedButton(row, "Publish to Notion",
                                              self._publish, kind="primary",
                                              size="md")
        self._publish_btn.pack(side="right")

    def _field_label(self, parent, text):
        tk.Label(parent, text=text.upper(), bg=C["card"], fg=C["ink3"],
                 font=F("mono", 9), anchor="w").pack(fill="x", pady=(0, 4))

    def on_enter(self, **_):
        profiles = self.app.cfg.get("profiles", {})
        labels = [p.get("label", slug) for slug, p in profiles.items()]
        self._workspace_dd.set_values(labels)
        active = self.app.cfg.get("active_profile", "")
        if active and active in profiles:
            self._workspace_dd.set(profiles[active].get("label", active))
        elif labels:
            self._workspace_dd.set(labels[0])
        self._on_workspace_change_v(self._workspace_dd.get())

        topic = self.app._materi_hint or (
            self.app._file_path.stem if self.app._file_path else "")
        self._topic_entry.delete(0, "end")
        self._topic_entry.insert(0, topic)

        # Default date = recording's mtime (when the meeting actually
        # happened) rather than today. Falls back to today_iso() if the
        # file is missing or unreadable.
        import datetime as _dt
        default_date = today_iso()
        fp = self.app._file_path
        if fp and fp.exists():
            try:
                mtime = _dt.datetime.fromtimestamp(fp.stat().st_mtime)
                default_date = mtime.date().isoformat()
            except OSError:
                pass
        self._date_entry.delete(0, "end")
        self._date_entry.insert(0, default_date)
        self._refresh_preview()

    def _on_workspace_change_v(self, label: str):
        slug = self._slug_for(label)
        if not slug:
            return
        try:
            set_active_profile(self.app.cfg, slug)
            save_config(self.app.cfg)
        except KeyError:
            return
        profile = self.app.cfg["profiles"][slug]
        db_id = profile.get("target_db_id", "")
        self._target_label.config(text=db_id or "(no database configured)")
        self._project_dd.set_values(["(no project)"])
        self._project_dd.set("(no project)")
        threading.Thread(target=self._fetch_projects_thread,
                         args=(profile,), daemon=True).start()
        threading.Thread(target=self._fetch_db_name_thread,
                         args=(profile,), daemon=True).start()

    def _slug_for(self, label: str) -> Optional[str]:
        for slug, p in self.app.cfg.get("profiles", {}).items():
            if p.get("label") == label:
                return slug
        return None

    def _fetch_projects_thread(self, profile):
        try:
            client = NotionClient(profile["notion_token"])
            if profile.get("projects_db_id"):
                pages = client.list_pages_in_db(profile["projects_db_id"])
            else:
                pages = client.search_pages_excluding_db(
                    profile.get("target_db_id", ""))
            self._projects = pages
            titles = ["(no project)"] + [p.title for p in pages]
            self.after(0, lambda: self._project_dd.set_values(titles))
        except Exception as e:
            self.after(0, lambda: self._status.config(
                text=f"Projects fetch failed: {str(e)[:60]}", fg=C["err"]))

    def _fetch_db_name_thread(self, profile):
        try:
            client = NotionClient(profile["notion_token"])
            dbs = client.list_databases()
            db_id = profile.get("target_db_id", "")
            clean = db_id.replace("-", "")
            for db in dbs:
                if db.id.replace("-", "") == clean:
                    self.after(0, lambda: self._target_label.config(
                        text=db.title, fg=C["ink"]))
                    return
        except Exception:
            pass

    def _refresh_preview(self):
        project = self._project_dd.get().strip()
        if project == "(no project)":
            project = ""
        materi = self._topic_entry.get().strip()
        date_iso = self._validated_date()
        title = format_page_title(project, materi, date_iso)
        self._title_preview.config(text=title or "(empty title)")

    def _validated_date(self) -> str:
        """Returns a valid ISO date string from the date field.

        If the user typed something unparseable, fall back to today + show a
        hint so they don't ship a broken date silently.
        """
        import datetime as _dt
        raw = self._date_entry.get().strip()
        try:
            d = _dt.date.fromisoformat(raw)
            self._date_hint.config(text="", fg=C["ink3"])
            return d.isoformat()
        except ValueError:
            self._date_hint.config(
                text="Invalid date — using today instead.",
                fg=C["warn"])
            return today_iso()

    def _publish(self):
        if self.app._processing:
            return
        materi = self._topic_entry.get().strip()
        if not materi:
            self._status.config(text="Topic is required.", fg=C["err"])
            return
        project = self._project_dd.get().strip()
        if project == "(no project)":
            project = ""

        slug = self._slug_for(self._workspace_dd.get())
        if not slug:
            self._status.config(text="Choose a workspace first.", fg=C["err"])
            return
        profile = self.app.cfg["profiles"][slug]

        inputs = PipelineInputs(
            file_path=self.app._file_path or Path(""),
            project=project,
            materi=materi,
            target_db_id=profile.get("target_db_id", ""),
            schema=profile.get("schema", {}),
            date_iso=self._validated_date())

        self.app._processing = True
        self._publish_btn.configure(state="disabled", text="Publishing…")
        self._status.config(text="Publishing to Notion…", fg=C["ink2"])

        threading.Thread(target=self._publish_thread,
                         args=(inputs, profile), daemon=True).start()

    def _publish_thread(self, inputs, profile):
        cfg = self.app.cfg
        llm_cfg = cfg.get("llm", {})
        tg_cfg = cfg.get("telegram", {})

        llm = LLMClient(
            base_url=llm_cfg.get("base_url", "http://localhost:1234/v1"),
            model=llm_cfg.get("model", "auto"),
            api_key=llm_cfg.get("api_key", "lm-studio"),
            timeout=int(llm_cfg.get("timeout", 300)),
            provider=llm_cfg.get("provider", "lm_studio"))
        notion = NotionClient(profile["notion_token"])
        telegram = TelegramClient(
            bot_token=tg_cfg.get("bot_token", ""),
            chat_id=tg_cfg.get("chat_id", ""),
            enabled=bool(tg_cfg.get("enabled", False)))
        dc_cfg = cfg.get("discord", {})
        discord = DiscordClient(
            webhook_url=dc_cfg.get("webhook_url", ""),
            enabled=bool(dc_cfg.get("enabled", False)))

        pipeline = MeetingPipeline(
            whisper=self.app._whisper, llm=llm, notion=notion, telegram=telegram,
            discord=discord,
            output_dir=resolve_output_dir(cfg))

        try:
            result = pipeline.publish_to_notion(
                transcript_text=self.app._transcript_text or "",
                summary=self.app._summary,
                inputs=inputs,
                on_log=lambda m, k: None)
            page = result["notion_page"]
            self.app._notion_page = page
            if page is None:
                warnings = result["warnings"]
                err = warnings[0] if warnings else "Unknown error"
                self.after(0, lambda: self._on_publish_failed(err))
            else:
                self.after(0, lambda: self._on_publish_done(page))
        except Exception as e:
            self.after(0, lambda: self._on_publish_failed(str(e)))

    def _on_publish_done(self, page: CreatedPage):
        self.app._processing = False
        self._publish_btn.configure(state="normal", text="Publish to Notion")
        # Optionally auto-open
        if self.app.cfg.get("auto_open_notion", False) and page.url:
            webbrowser.open(page.url)
        self.app.navigate("done")

    def _on_publish_failed(self, err: str):
        self.app._processing = False
        self._publish_btn.configure(state="normal", text="Publish to Notion")
        self._status.config(text=f"✗ {err[:80]}", fg=C["err"])


# ============================================================================
# Done view
# ============================================================================

class DoneView(BaseView):
    show_chrome = True
    can_go_back = True  # back arrow → previous view (NotionSetup → Preview → Main)

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self._build()

    def _build(self):
        body = tk.Frame(self, bg=C["card"])
        body.pack(fill="both", expand=True, padx=26, pady=(40, 30))

        # Smooth done mark
        SmoothCheckMark(body, size=96, bg=C["card"]).pack()

        tk.Label(body, text="Saved to Notion",
                 bg=C["card"], fg=C["ink"],
                 font=F("display", 28, italic=True)).pack(pady=(20, 4))
        self._meta = tk.Label(body, text="", bg=C["card"], fg=C["ink3"],
                                font=F("mono", 10))
        self._meta.pack(pady=(0, 28))

        card = SmoothCard(body, radius=18, padding=16, bg=C["card"])
        card.pack(fill="x")
        tk.Label(card.inner, text="PAGE TITLE",
                 bg=C["card"], fg=C["ink3"],
                 font=F("mono", 9), anchor="w").pack(fill="x", pady=(0, 4))
        self._title_label = tk.Label(card.inner, text="—",
                                       bg=C["card"], fg=C["ink"],
                                       font=F("display", 16, italic=True),
                                       anchor="w", wraplength=440,
                                       justify="left")
        self._title_label.pack(fill="x", pady=(0, 12))
        tk.Frame(card.inner, height=1, bg=C["border_soft"]).pack(
            fill="x", pady=(0, 12))
        RoundedButton(card.inner, "Open in Notion  ↗", self._open_page,
                       kind="primary", size="md", stretch=True).pack(fill="x")

        # Side row — primary action is "Back to home" so the user lands on
        # a clean slate ready for the next file. View-log + copy are
        # secondary ghost buttons.
        side = tk.Frame(body, bg=C["card"])
        side.pack(fill="x", pady=(18, 0))
        RoundedButton(side, "← Back to home",
                       self._new_run, kind="secondary",
                       size="md").pack(side="left")
        RoundedButton(side, "Copy link", self._copy_link,
                       kind="ghost", size="md").pack(side="left", padx=8)
        RoundedButton(side, "View log", self._view_log,
                       kind="ghost", size="md").pack(side="left", padx=(0, 0))

    def _view_log(self):
        from .widgets import open_today_log_file
        open_today_log_file()

    def on_enter(self, **_):
        page = self.app._notion_page
        if page and page.url:
            # Compose a title from inputs (we don't carry the formatted title)
            project = ""  # unknown at this point — re-format from session
            materi = self.app._materi_hint or "Meeting"
            self._title_label.config(text=page.url.split("/")[-1].replace("-", " ")[:120])
        s = self.app._summary
        if s:
            self._meta.config(text=f"{len(s.key_points)} key points · "
                                     f"{len(s.action_items)} action items")
        else:
            self._meta.config(text="")

    def _open_page(self):
        page = self.app._notion_page
        if page and page.url:
            webbrowser.open(page.url)

    def _copy_link(self):
        page = self.app._notion_page
        if page and page.url:
            self.clipboard_clear()
            self.clipboard_append(page.url)
            self.update()

    def _new_run(self):
        self.app.reset_session()
        # MainView resets itself via on_enter (calls _show_idle_subtree + refresh_recent)
        self.app._nav_stack = []
        self.app.navigate("main", push=False)
