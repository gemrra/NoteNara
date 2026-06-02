"""Settings views — in-place Frames navigated via App.navigate().

No Toplevels here. The whole settings UI lives in a single Frame that the App
swaps into the content area when the user taps "Settings". Edit-workspace
likewise is its own Frame, not a modal.
"""

from __future__ import annotations

import re
import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog, ttk
from typing import Callable, Optional

from ..config import (
    DEFAULT_SCHEMA, LM_STUDIO_DEFAULTS, add_profile, delete_profile,
    save_config, set_active_profile,
)
from ..constants import C, F, apply_theme
from ..i18n import t
from ..services.llm import LLMClient
from ..services.notion import DatabaseRef, NotionClient, SchemaDetection
from .smooth import (
    BrandLogo, RoundedButton, SmoothCard, SmoothCheckBox, SmoothDropdown,
    SmoothIcon, SmoothInput, SmoothRadio,
)


# ============================================================================
# Shared tk patterns
# ============================================================================

def _labeled_entry(parent, label: str, value: str = "", show: str = "",
                    width: Optional[int] = None) -> tk.Entry:
    """Returns the underlying tk.Entry from a SmoothInput so call sites can
    still do .get() / .insert() unchanged."""
    if label:
        tk.Label(parent, text=label.upper(), bg=C["card"], fg=C["ink3"],
                 font=F("mono", 9)).pack(anchor="w", pady=(0, 3))
    inp = SmoothInput(parent, height=34, radius=11, show=show, bg=C["card"])
    inp.pack(fill="x", pady=(0, 8))
    if value:
        inp.set(value)
    return inp.entry


def _section_label(parent, text: str) -> None:
    tk.Label(parent, text=text.upper(), bg=C["card"], fg=C["ink3"],
             font=F("mono", 9)).pack(anchor="w", pady=(0, 4))


def _primary_button(parent, text: str, command: Callable[[], None]):
    """Legacy helper — now returns a RoundedButton primary."""
    return RoundedButton(parent, text, command, kind="primary", size="md")


def _ghost_button(parent, text: str, command: Callable[[], None]):
    """Legacy helper — now returns a RoundedButton secondary."""
    return RoundedButton(parent, text, command, kind="secondary", size="md")


def _slugify(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_-]+", "-", text.strip().lower())
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "workspace"


def _recolor_bg(widget, color: str) -> None:
    """Walk a widget tree and update bg of supported widgets in-place."""
    try:
        widget.configure(bg=color)
    except tk.TclError:
        pass
    for child in widget.winfo_children():
        _recolor_bg(child, color)


# ============================================================================
# SettingsView — top-level view with tabs
# ============================================================================

class SettingsView(tk.Frame):
    """Settings with vertical tab rail (mockup-style).

    Left rail: icon + label per tab, active has tint-yellow bg + ink left border.
    Right pane: tab content (the existing *Tab Frame classes).
    """

    title = "chrome.settings.title"
    can_go_back = True

    # Tab labels are localised at instance-build time (see _build) since
    # class-level attributes evaluate before the locale is set.
    TABS = [
        ("notion",        "settings.tab.notion",          "users"),
        ("ai",            "settings.tab.ai",              "lightning"),
        ("transcription", "settings.tab.transcription",   "mic"),
        ("notifications", "settings.tab.notifications",   "bell"),
        ("output",        "settings.tab.output",          "folder"),
        ("about",         "settings.tab.about",           "info"),
    ]

    def __init__(self, parent, app):
        super().__init__(parent, bg=C["card"])
        self.app = app
        self.cfg = app.cfg
        self._tab_widgets: dict[str, tk.Frame] = {}
        self._tab_rows: dict[str, dict] = {}  # slug -> {row, label, icon}
        self._active = "notion"
        self._build()

    def _build(self):
        # Body: left rail + right pane
        body = tk.Frame(self, bg=C["card"])
        body.pack(fill="both", expand=True)

        # Left rail — narrow (icon + label). Width tuned so "Transcription"
        # and "Notifications" fit without truncation.
        rail = tk.Frame(body, bg=C["card"], width=130)
        rail.pack(side="left", fill="y", padx=(10, 0), pady=(6, 0))
        rail.pack_propagate(False)
        # Add a right divider
        divider = tk.Frame(body, width=1, bg=C["border_soft"])
        divider.pack(side="left", fill="y", padx=(6, 0), pady=(6, 0))

        for slug, label_key, icon_name in self.TABS:
            row = self._build_tab_row(rail, slug, t(label_key), icon_name)
            row.pack(fill="x", pady=1)

        # Right pane — tabs are place()'d full size and lift()'ed when active.
        # Eliminates pack/forget cycle on switch (was causing flicker as all
        # widgets re-layout + SmoothCards re-render on Configure).
        right = tk.Frame(body, bg=C["card"])
        right.pack(side="left", fill="both", expand=True, padx=12, pady=(6, 0))
        self._right_pane = right

        # Create all tab frames once. Place them all overlapping with full
        # size so they all render once. Switch = lift(); no pack/forget cycle.
        self._tab_widgets["notion"] = NotionTab(right, self.cfg, app=self.app)
        self._tab_widgets["ai"] = LLMTab(right, self.cfg)
        self._tab_widgets["transcription"] = WhisperTab(right, self.cfg)
        self._tab_widgets["notifications"] = TelegramTab(right, self.cfg)
        self._tab_widgets["output"] = OutputTab(right, self.cfg)
        self._tab_widgets["about"] = AboutTab(right, self.cfg)
        for w in self._tab_widgets.values():
            w.place(relx=0, rely=0, relwidth=1, relheight=1)

        # Footer — just a thin top divider, no full box border (was looking
        # like a rectangle that didn't match the rounded outer card)
        footer = tk.Frame(self, bg=C["card"])
        footer.pack(fill="x", side="bottom")
        tk.Frame(footer, height=1, bg=C["border_soft"]).pack(
            fill="x", padx=14)
        row = tk.Frame(footer, bg=C["card"])
        row.pack(fill="x", padx=18, pady=12)
        RoundedButton(row, t("btn.cancel"), self._cancel,
                       kind="secondary", size="md").pack(side="left")
        RoundedButton(row, t("btn.save"), self._save,
                       kind="primary", size="md").pack(side="right")

        # Show default tab
        self._show_tab(self._active)

    def _build_tab_row(self, parent, slug: str, label: str,
                         icon_name: str) -> tk.Frame:
        # Wrapper holds a SmoothCard inside; cards swap visibility on active state.
        wrapper = tk.Frame(parent, bg=C["card"])
        # Active state: rounded pill with tint_yellow fill
        active_card = SmoothCard(wrapper, radius=10, padding=0,
                                    fill=C["tint_yellow"],
                                    border=C["ink"], border_width=1.3,
                                    bg=C["card"])
        # Inactive state: just a Frame (no border)
        inactive_frame = tk.Frame(wrapper, bg=C["card"])

        # We pack one or the other based on active state. Both have same
        # inner content (icon + label).
        def build_inner(parent_widget, bg):
            row = tk.Frame(parent_widget, bg=bg)
            row.pack(fill="both", expand=True)
            icon = SmoothIcon(row, icon_name, size=13, color=C["ink2"],
                                bg=bg)
            icon.pack(side="left", padx=(8, 6), pady=6)
            lbl = tk.Label(row, text=label, bg=bg, fg=C["ink2"],
                             font=F("body", 9, "normal"),
                             anchor="w", padx=0)
            lbl.pack(side="left", fill="x", expand=True, padx=(0, 8), pady=6)
            return {"row": row, "icon": icon, "lbl": lbl}

        active_inner = build_inner(active_card.inner, C["tint_yellow"])
        inactive_inner = build_inner(inactive_frame, C["card"])

        self._tab_rows[slug] = {
            "wrapper": wrapper,
            "active_card": active_card,
            "inactive_frame": inactive_frame,
            "active_inner": active_inner,
            "inactive_inner": inactive_inner,
        }

        # Click on any part triggers tab switch
        clickables = [wrapper,
                       active_card, active_card.inner, active_inner["row"],
                       active_inner["icon"], active_inner["lbl"],
                       inactive_frame, inactive_inner["row"],
                       inactive_inner["icon"], inactive_inner["lbl"]]
        for w in clickables:
            w.bind("<Button-1>", lambda e, s=slug: self._show_tab(s))
            w.configure(cursor="hand2")

        # Hover for inactive: tint the inactive frame bg slightly
        def hover_in(_):
            if slug != self._active:
                inactive_frame.configure(bg=C["bg2"])
                inactive_inner["row"].configure(bg=C["bg2"])
                inactive_inner["icon"].configure(bg=C["bg2"])
                inactive_inner["icon"].set_color(C["ink"])
                inactive_inner["lbl"].configure(bg=C["bg2"], fg=C["ink"])

        def hover_out(_):
            if slug != self._active:
                self._paint_row(slug, active=False)

        for w in (inactive_frame, inactive_inner["row"],
                   inactive_inner["icon"], inactive_inner["lbl"]):
            w.bind("<Enter>", hover_in)
            w.bind("<Leave>", hover_out)

        return wrapper

    def _paint_row(self, slug: str, active: bool):
        r = self._tab_rows[slug]
        # Swap visibility of active vs inactive
        if active:
            r["inactive_frame"].pack_forget()
            r["active_card"].pack(fill="x")
            ai = r["active_inner"]
            ai["lbl"].configure(fg=C["ink"], font=F("body", 9, "bold"))
            ai["icon"].set_color(C["ink"])
        else:
            r["active_card"].pack_forget()
            r["inactive_frame"].pack(fill="x")
            ii = r["inactive_inner"]
            ii["row"].configure(bg=C["card"])
            ii["icon"].configure(bg=C["card"])
            ii["icon"].set_color(C["ink2"])
            ii["lbl"].configure(bg=C["card"], fg=C["ink2"],
                                  font=F("body", 9, "normal"))

    def _show_tab(self, slug: str):
        if slug not in self._tab_widgets:
            return
        # Paint sidebar rows
        for s in self._tab_rows:
            self._paint_row(s, active=(s == slug))
        # Lift the selected tab to the top of the stacking order — all tabs
        # stay place()'d at full size; no pack/forget cycle = no flicker.
        self._tab_widgets[slug].lift()
        self._active = slug

    def on_enter(self, **kwargs):
        self.cfg = self.app.cfg
        # Refresh notion list (might have been mutated by editor)
        n_tab = self._tab_widgets.get("notion")
        if hasattr(n_tab, "refresh"):
            n_tab.refresh()
        self._show_tab(self._active)

    def on_exit(self):
        pass

    def _save(self):
        old_lang = self.cfg.get("language", "en")
        for w in self._tab_widgets.values():
            if hasattr(w, "commit"):
                w.commit()
        save_config(self.cfg)
        new_lang = self.cfg.get("language", "en")
        self.app.on_settings_saved()

        if old_lang != new_lang:
            # Schedule the rebuild via after() so the current event handler
            # unwinds before reload_locale destroys SettingsView (us).
            self.app.after(50, lambda: self.app.reload_locale(new_lang))
        else:
            self.app.go_back()

    def _cancel(self):
        self.app.go_back()


# ============================================================================
# Workspaces tab
# ============================================================================

class NotionTab(tk.Frame):
    """All Notion-related settings: workspaces, page format, defaults."""

    # Localised on instance build — see _build.
    TITLE_FORMATS = [
        ("settings.notion.title_fmt.standard",   "standard"),
        ("settings.notion.title_fmt.simple",     "simple"),
        ("settings.notion.title_fmt.date_first", "date_first"),
    ]

    def __init__(self, parent, cfg: dict, app):
        super().__init__(parent, bg=C["card"])
        self.cfg = cfg
        self.app = app
        notion = cfg.setdefault("notion", {})
        self._selected: Optional[str] = None
        self._row_widgets: dict[str, tk.Frame] = {}

        # Scrollable container — more sections = needs scroll
        canvas = tk.Canvas(self, bg=C["card"], highlightthickness=0)
        canvas.pack(side="left", fill="both", expand=True)
        sb = tk.Scrollbar(self, orient="vertical", command=canvas.yview,
                           bg=C["card"], troughcolor=C["card"], bd=0, width=6)
        sb.pack(side="right", fill="y")
        canvas.configure(yscrollcommand=sb.set)
        body = tk.Frame(canvas, bg=C["card"])
        body_id = canvas.create_window((0, 0), window=body, anchor="nw")
        body.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
                     lambda e: canvas.itemconfigure(body_id, width=e.width))

        # Mouse-wheel scroll (Windows / Linux / macOS conventions)
        def _on_mousewheel(event):
            if event.delta:
                canvas.yview_scroll(-int(event.delta / 120), "units")
            else:
                # X11: Button-4 = up, Button-5 = down
                canvas.yview_scroll(-1 if event.num == 4 else 1, "units")
        # Bind on the canvas + body + all children recursively (via bind_class
        # for the whole NotionTab subtree)
        def _bind_wheel(w):
            w.bind("<MouseWheel>", _on_mousewheel)
            w.bind("<Button-4>", _on_mousewheel)
            w.bind("<Button-5>", _on_mousewheel)
        _bind_wheel(canvas)
        _bind_wheel(body)
        # Also re-bind whenever new children get added — done by recursive walk
        # on refresh + after building all sections.
        self._wheel_bind = _bind_wheel
        self._scroll_canvas = canvas

        inner = tk.Frame(body, bg=C["card"])
        inner.pack(fill="both", expand=True, padx=10, pady=10)

        # ===== Section 1: Workspaces =====
        _section_label(inner, t("settings.notion.workspaces"))
        tk.Label(inner,
                 text=t("settings.notion.workspaces_hint"),
                 bg=C["card"], fg=C["ink3"], font=F("mono", 9),
                 anchor="w", wraplength=320, justify="left").pack(
            fill="x", pady=(0, 8))

        list_card = SmoothCard(inner, radius=14, padding=6, bg=C["card"])
        list_card.pack(fill="x")
        self._list_inner = tk.Frame(list_card.inner, bg=C["card"])
        self._list_inner.pack(fill="x")

        actions = tk.Frame(inner, bg=C["card"])
        actions.pack(fill="x", pady=(10, 0))
        RoundedButton(actions, t("btn.add_workspace"), self._add,
                       kind="primary", size="sm").pack(side="left")
        RoundedButton(actions, t("btn.delete"), self._delete,
                       kind="ghost", size="sm").pack(side="right", padx=(6, 0))
        RoundedButton(actions, t("btn.set_active"), self._set_active,
                       kind="secondary", size="sm").pack(side="right", padx=(6, 0))
        RoundedButton(actions, t("btn.edit"), self._edit,
                       kind="secondary", size="sm").pack(side="right")

        # ===== Section 2: Page format =====
        tk.Frame(inner, height=1, bg=C["border_soft"]).pack(
            fill="x", pady=(20, 14))
        _section_label(inner, t("settings.notion.page_format"))
        tk.Label(inner,
                 text=t("settings.notion.page_format_hint"),
                 bg=C["card"], fg=C["ink3"], font=F("mono", 9),
                 anchor="w").pack(fill="x", pady=(0, 10))

        # Page icon emoji + Title format in two-column row
        fmt_row = tk.Frame(inner, bg=C["card"])
        fmt_row.pack(fill="x", pady=(0, 12))

        icol = tk.Frame(fmt_row, bg=C["card"], width=120)
        icol.pack(side="left", padx=(0, 8))
        icol.pack_propagate(False)
        tk.Label(icol, text=t("settings.notion.page_icon"),
                 bg=C["card"], fg=C["ink3"],
                 font=F("mono", 8)).pack(anchor="w", pady=(0, 3))
        icon_inp = SmoothInput(icol, height=34, radius=11, bg=C["card"])
        icon_inp.pack(fill="x")
        icon_inp.set(notion.get("page_icon", "🎙️"))
        self._page_icon_entry = icon_inp.entry

        tcol = tk.Frame(fmt_row, bg=C["card"])
        tcol.pack(side="left", fill="x", expand=True, padx=(8, 0))
        tk.Label(tcol, text=t("settings.notion.title_format"),
                 bg=C["card"], fg=C["ink3"],
                 font=F("mono", 8)).pack(anchor="w", pady=(0, 3))
        title_fmt_labels = [t(key) for key, _ in self.TITLE_FORMATS]
        current_fmt_slug = notion.get("title_format", "standard")
        current_fmt_label = next(
            (t(key) for key, slug in self.TITLE_FORMATS
             if slug == current_fmt_slug), title_fmt_labels[0])
        self._title_fmt_dd = SmoothDropdown(
            tcol, values=title_fmt_labels, initial=current_fmt_label,
            height=34, radius=11, bg=C["card"])
        self._title_fmt_dd.pack(fill="x")

        # Include raw transcript toggle
        trans_row = tk.Frame(inner, bg=C["card"])
        trans_row.pack(fill="x", pady=(4, 4))
        self._raw_cb = SmoothCheckBox(trans_row,
                                          checked=bool(notion.get("include_raw_transcript", True)),
                                          size=18, bg=C["card"])
        self._raw_cb.pack(side="left", padx=(0, 10))
        col = tk.Frame(trans_row, bg=C["card"])
        col.pack(side="left", fill="x", expand=True)
        tk.Label(col, text=t("settings.notion.include_raw"),
                 bg=C["card"], fg=C["ink"], font=F("body", 10),
                 anchor="w").pack(fill="x")
        tk.Label(col, text=t("settings.notion.include_raw_hint"),
                 bg=C["card"], fg=C["ink3"], font=F("mono", 9),
                 anchor="w").pack(fill="x", pady=(2, 0))

        # ===== Section 3: Active workspace databases =====
        tk.Frame(inner, height=1, bg=C["border_soft"]).pack(
            fill="x", pady=(20, 14))
        _section_label(inner, t("settings.notion.active_dbs"))
        tk.Label(inner,
                 text=t("settings.notion.active_dbs_hint"),
                 bg=C["card"], fg=C["ink3"], font=F("mono", 9),
                 anchor="w", wraplength=420,
                 justify="left").pack(fill="x", pady=(0, 10))

        # Target DB picker
        tk.Label(inner, text=t("settings.notion.target_db_label"),
                 bg=C["card"], fg=C["ink3"],
                 font=F("mono", 8)).pack(anchor="w", pady=(0, 3))
        self._target_db_dd = SmoothDropdown(
            inner, values=["(load on tab open)"],
            placeholder="—", height=36, radius=11, bg=C["card"],
            on_change=lambda v: self._on_target_db_change(v))
        self._target_db_dd.pack(fill="x", pady=(0, 10))

        # Projects DB picker
        tk.Label(inner, text=t("settings.notion.projects_db_label"),
                 bg=C["card"], fg=C["ink3"],
                 font=F("mono", 8)).pack(anchor="w", pady=(0, 3))
        _projects_none = t("settings.notion.projects_db_none")
        self._projects_db_dd = SmoothDropdown(
            inner, values=[_projects_none],
            initial=_projects_none,
            placeholder=_projects_none,
            height=36, radius=11, bg=C["card"],
            on_change=lambda v: self._on_projects_db_change(v))
        self._projects_db_dd.pack(fill="x", pady=(0, 14))

        # ===== Section 4: Defaults =====
        tk.Frame(inner, height=1, bg=C["border_soft"]).pack(
            fill="x", pady=(6, 14))
        _section_label(inner, t("settings.notion.defaults"))
        tk.Label(inner,
                 text=t("settings.notion.defaults_hint"),
                 bg=C["card"], fg=C["ink3"], font=F("mono", 9),
                 anchor="w").pack(fill="x", pady=(0, 10))

        tk.Label(inner, text=t("settings.notion.default_project"),
                 bg=C["card"], fg=C["ink3"],
                 font=F("mono", 8)).pack(anchor="w", pady=(0, 3))
        _ask_each = t("settings.notion.default_project_ask")
        self._default_project_dd = SmoothDropdown(
            inner, values=[_ask_each],
            initial=notion.get("default_project") or _ask_each,
            placeholder=_ask_each,
            height=36, radius=11, bg=C["card"])
        self._default_project_dd.pack(fill="x", pady=(0, 4))
        tk.Label(inner,
                 text=t("settings.notion.default_project_hint"),
                 bg=C["card"], fg=C["ink3"], font=F("mono", 9),
                 anchor="w").pack(fill="x", pady=(0, 10))

        # Auto-publish toggle
        auto_row = tk.Frame(inner, bg=C["card"])
        auto_row.pack(fill="x", pady=(4, 4))
        self._auto_publish_cb = SmoothCheckBox(
            auto_row, checked=bool(notion.get("auto_publish", False)),
            size=18, bg=C["card"])
        self._auto_publish_cb.pack(side="left", padx=(0, 10))
        auto_col = tk.Frame(auto_row, bg=C["card"])
        auto_col.pack(side="left", fill="x", expand=True)
        tk.Label(auto_col, text=t("settings.notion.auto_publish"),
                 bg=C["card"], fg=C["ink"], font=F("body", 10),
                 anchor="w").pack(fill="x")
        tk.Label(auto_col,
                 text=t("settings.notion.auto_publish_hint"),
                 bg=C["card"], fg=C["ink3"], font=F("mono", 9),
                 anchor="w").pack(fill="x", pady=(2, 0))

        # ===== Section 4: Account info =====
        tk.Frame(inner, height=1, bg=C["border_soft"]).pack(
            fill="x", pady=(20, 14))
        _section_label(inner, t("settings.notion.active"))
        self._account_card = SmoothCard(inner, radius=12, padding=12,
                                            bg=C["card"])
        self._account_card.pack(fill="x", pady=(0, 8))
        self._account_label = tk.Label(self._account_card.inner,
                                          text="—",
                                          bg=C["card"], fg=C["ink"],
                                          font=F("body", 10),
                                          anchor="w", justify="left")
        self._account_label.pack(fill="x")
        self._account_status = tk.Label(self._account_card.inner,
                                           text="",
                                           bg=C["card"], fg=C["ink3"],
                                           font=F("mono", 9),
                                           anchor="w")
        self._account_status.pack(fill="x", pady=(4, 0))

        acc_actions = tk.Frame(inner, bg=C["card"])
        acc_actions.pack(fill="x")
        RoundedButton(acc_actions, t("btn.test_connection"),
                       self._test_active, kind="secondary",
                       size="sm").pack(side="left")

        # Bottom breathing room
        tk.Frame(inner, height=20, bg=C["card"]).pack()

        self.refresh()
        # Bind mouse wheel scroll to every descendant so wheel works anywhere
        self.after(50, self._bind_wheel_recursively)

    def _bind_wheel_recursively(self):
        def walk(w):
            self._wheel_bind(w)
            for c in w.winfo_children():
                walk(c)
        walk(self)

    def refresh(self):
        # Clear rows
        for w in self._list_inner.winfo_children():
            w.destroy()
        self._row_widgets = {}
        active = self.cfg.get("active_profile", "")
        profiles = self.cfg.get("profiles", {})

        if not profiles:
            tk.Label(self._list_inner,
                     text=t("settings.notion.empty"),
                     bg=C["card"], fg=C["ink3"],
                     font=F("mono", 9),
                     padx=10, pady=14).pack()
            # Account section shows nothing
            if hasattr(self, "_account_label"):
                self._account_label.config(text="—")
                self._account_status.config(text=t("settings.notion.no_active"))
            return

        for slug, prof in profiles.items():
            is_active = (slug == active)
            row = self._build_row(self._list_inner, slug, prof, is_active)
            row.pack(fill="x", pady=2)
            self._row_widgets[slug] = row

        # Auto-select active or first
        self._select(active if active in profiles else next(iter(profiles)))

        # Update Account section with active workspace info
        if hasattr(self, "_account_label") and active and active in profiles:
            p = profiles[active]
            label = p.get("label", active)
            db_id = (p.get("target_db_id") or "")[:12]
            self._account_label.config(
                text=f"{label}  ·  {active}\nTarget DB: …{db_id}")
            self._account_status.config(
                text=t("settings.notion.test_hint"),
                fg=C["ink3"])

        # Populate ALL three workspace-dependent dropdowns async — target DB,
        # projects DB, default project. Fetched on each refresh so changes to
        # active workspace reflect immediately.
        if active and active in profiles:
            threading.Thread(
                target=self._fetch_workspace_data_thread,
                args=(profiles[active],), daemon=True).start()

    def _fetch_workspace_data_thread(self, profile):
        """Fetch databases + projects from active workspace in one go."""
        token = profile.get("notion_token", "")
        if not token:
            return
        client = NotionClient(token)
        # 1. Databases (for target / projects pickers)
        try:
            dbs = client.list_databases()
        except Exception:
            dbs = []
        # 2. Projects (for default project picker)
        try:
            if profile.get("projects_db_id"):
                pages = client.list_pages_in_db(profile["projects_db_id"])
            else:
                pages = client.search_pages_excluding_db(
                    profile.get("target_db_id", ""))
        except Exception:
            pages = []
        # Stash for save-time mapping
        self._workspace_dbs = dbs
        self.after(0, lambda: self._apply_workspace_data(profile, dbs, pages))

    def _apply_workspace_data(self, profile, dbs, pages):
        if not hasattr(self, "_target_db_dd"):
            return
        # Target DB dropdown
        db_labels = [f"{db.icon + ' ' if db.icon else ''}{db.title}" for db in dbs]
        self._target_db_dd.set_values(db_labels or ["(no databases shared)"])
        # Preselect current target DB
        current_target = (profile.get("target_db_id") or "").replace("-", "")
        for i, db in enumerate(dbs):
            if db.id.replace("-", "") == current_target:
                self._target_db_dd.set(db_labels[i])
                break
        # Projects DB dropdown
        proj_labels = ["(none — search all pages)"] + db_labels
        self._projects_db_dd.set_values(proj_labels)
        current_proj = (profile.get("projects_db_id") or "").replace("-", "")
        if current_proj:
            for i, db in enumerate(dbs):
                if db.id.replace("-", "") == current_proj:
                    self._projects_db_dd.set(db_labels[i])
                    break
        else:
            self._projects_db_dd.set("(none — search all pages)")
        # Default project dropdown
        titles = ["(ask each time)"] + [p.title for p in pages]
        self._default_project_dd.set_values(titles)

    def _on_target_db_change(self, value: str):
        active = self.cfg.get("active_profile", "")
        if not active or not hasattr(self, "_workspace_dbs"):
            return
        db_labels = [f"{db.icon + ' ' if db.icon else ''}{db.title}"
                      for db in self._workspace_dbs]
        try:
            idx = db_labels.index(value)
        except ValueError:
            return
        new_db_id = self._workspace_dbs[idx].id
        self.cfg["profiles"][active]["target_db_id"] = new_db_id
        save_config(self.cfg)

    def _on_projects_db_change(self, value: str):
        active = self.cfg.get("active_profile", "")
        if not active:
            return
        if value == "(none — search all pages)":
            self.cfg["profiles"][active]["projects_db_id"] = None
        elif hasattr(self, "_workspace_dbs"):
            db_labels = [f"{db.icon + ' ' if db.icon else ''}{db.title}"
                          for db in self._workspace_dbs]
            try:
                idx = db_labels.index(value)
                self.cfg["profiles"][active]["projects_db_id"] = self._workspace_dbs[idx].id
            except ValueError:
                return
        save_config(self.cfg)
        # Re-fetch projects since the source changed
        if active in self.cfg.get("profiles", {}):
            threading.Thread(
                target=self._fetch_workspace_data_thread,
                args=(self.cfg["profiles"][active],), daemon=True).start()

    def _build_row(self, parent, slug, prof, is_active):
        row = tk.Frame(parent, bg=C["card"],
                        highlightbackground=C["border_soft"],
                        highlightthickness=0)
        # Active marker dot
        dot = tk.Canvas(row, width=10, height=10, bg=C["card"],
                          highlightthickness=0)
        dot.pack(side="left", padx=(10, 8), pady=10)
        dot_fill = C["orange"] if is_active else C["card"]
        dot.create_oval(1, 1, 9, 9, fill=dot_fill,
                          outline=C["ink"], width=1.2)

        # Label + slug col
        txt = tk.Frame(row, bg=C["card"])
        txt.pack(side="left", fill="x", expand=True, pady=8)
        tk.Label(txt, text=prof.get("label", slug),
                 bg=C["card"], fg=C["ink"],
                 font=F("body", 11, "bold"), anchor="w").pack(fill="x")
        active_text = "  · active" if is_active else ""
        tk.Label(txt, text=f"{slug}{active_text}",
                 bg=C["card"], fg=C["ink3"],
                 font=F("mono", 8), anchor="w").pack(fill="x", pady=(1, 0))

        # Bind click on whole row
        for w in (row, dot, txt) + tuple(txt.winfo_children()):
            w.bind("<Button-1>", lambda e, s=slug: self._select(s))
            w.configure(cursor="hand2")
        return row

    def _paint_row(self, slug, selected):
        row = self._row_widgets.get(slug)
        if not row:
            return
        bg = C["tint_yellow"] if selected else C["card"]
        _recolor_bg(row, bg)

    def _select(self, slug):
        self._selected = slug
        for s in self._row_widgets:
            self._paint_row(s, s == slug)

    def _selected_slug(self) -> Optional[str]:
        return self._selected

    def _add(self):
        self.app.navigate("workspace_editor", slug=None)

    def _edit(self):
        slug = self._selected_slug()
        if not slug:
            return
        self.app.navigate("workspace_editor", slug=slug)

    def _delete(self):
        slug = self._selected_slug()
        if not slug:
            return
        if len(self.cfg.get("profiles", {})) <= 1:
            self.app.toast(t("settings.notion.cant_delete_last"), kind="err")
            return
        delete_profile(self.cfg, slug)
        save_config(self.cfg)
        self.refresh()

    def _set_active(self):
        slug = self._selected_slug()
        if not slug:
            return
        set_active_profile(self.cfg, slug)
        save_config(self.cfg)
        self.refresh()

    def commit(self):
        notion = self.cfg.setdefault("notion", {})
        notion["page_icon"] = self._page_icon_entry.get().strip() or "🎙️"
        # Map the (localised) dropdown label back to its slug.
        label = self._title_fmt_dd.get()
        slug = next((s for key, s in self.TITLE_FORMATS if t(key) == label),
                      "standard")
        notion["title_format"] = slug
        notion["include_raw_transcript"] = self._raw_cb.is_checked()
        v = self._default_project_dd.get().strip()
        ask_each = t("settings.notion.default_project_ask")
        notion["default_project"] = "" if v == ask_each else v
        notion["auto_publish"] = self._auto_publish_cb.is_checked()

    def _test_active(self):
        active = self.cfg.get("active_profile", "")
        if not active:
            self._account_status.config(text=t("settings.notion.no_active_err"),
                                          fg=C["err"])
            return
        profile = self.cfg.get("profiles", {}).get(active, {})
        token = profile.get("notion_token", "")
        if not token:
            self._account_status.config(text=t("settings.notion.token_missing"),
                                          fg=C["err"])
            return
        self._account_status.config(text=t("settings.notion.testing"),
                                      fg=C["ink3"])
        threading.Thread(target=self._test_thread,
                         args=(profile,), daemon=True).start()

    def _test_thread(self, profile):
        client = NotionClient(profile["notion_token"])
        result = client.test_connection()
        if result.ok:
            msg = t("settings.notion.test_ok",
                    workspace=result.workspace_name or "workspace",
                    bot=result.bot_name or "—")
            color = C["ok"]
        else:
            msg = t("settings.notion.test_err", err=result.error[:80])
            color = C["err"]
        self.after(0, lambda: self._account_status.config(text=msg, fg=color))


# ============================================================================
# Workspace editor view — in-place form
# ============================================================================

class WorkspaceEditorView(tk.Frame):
    title = "ws_editor.title.add"
    can_go_back = True

    def __init__(self, parent, app):
        super().__init__(parent, bg=C["bg_card"])
        self.app = app
        self.cfg = app.cfg
        self.slug: Optional[str] = None
        self._databases: list[DatabaseRef] = []
        self._preselect_target: Optional[str] = None
        self._preselect_projects: Optional[str] = None

        self._build()

    def _build(self):
        body = tk.Frame(self, bg=C["card"])
        body.pack(fill="both", expand=True, padx=20, pady=(8, 14))

        self._title_label = tk.Label(body, text=t("ws_editor.title.add"),
                                       bg=C["card"], fg=C["ink"],
                                       font=F("display", 18, italic=True))
        self._title_label.pack(anchor="w", pady=(0, 12))

        self._label_entry = _labeled_entry(body, t("ws_editor.label"), "")
        self._token_entry = _labeled_entry(body, t("ws_editor.token"),
                                             "", show="•")

        link = tk.Label(body,
                          text=t("ws_editor.link"),
                          bg=C["card"], fg=C["orange"],
                          font=F("mono", 9), cursor="hand2")
        link.pack(anchor="w", pady=(0, 10))
        link.bind("<Button-1>",
                   lambda e: webbrowser.open("https://www.notion.so/my-integrations"))

        test_row = tk.Frame(body, bg=C["card"])
        test_row.pack(fill="x", pady=(0, 12))
        RoundedButton(test_row, t("ws_editor.test_fetch"),
                        self._test_and_fetch,
                        kind="secondary", size="sm").pack(side="left")
        self._status = tk.Label(test_row, text="", bg=C["card"],
                                 fg=C["ink3"], font=F("mono", 9))
        self._status.pack(side="left", padx=(10, 0))

        _section_label(body, t("ws_editor.target"))
        self._target_dd = SmoothDropdown(body, values=[],
                                            placeholder=t("ws_editor.target_placeholder"),
                                            on_change=lambda v: self._on_target_change_v(v),
                                            height=34, radius=11, bg=C["card"])
        self._target_dd.pack(fill="x", pady=(0, 12))

        _section_label(body, t("ws_editor.projects"))
        self._projects_dd = SmoothDropdown(body, values=[],
                                              placeholder=t("ws_editor.projects_placeholder"),
                                              height=34, radius=11, bg=C["card"])
        self._projects_dd.pack(fill="x", pady=(0, 12))

        _section_label(body, t("ws_editor.schema"))
        sch_row = tk.Frame(body, bg=C["card"])
        sch_row.pack(fill="x", pady=(0, 14))

        tcol = tk.Frame(sch_row, bg=C["card"])
        tcol.pack(side="left", fill="x", expand=True, padx=(0, 6))
        tk.Label(tcol, text=t("ws_editor.title_prop"), bg=C["card"],
                 fg=C["ink3"],
                 font=F("mono", 8)).pack(anchor="w", pady=(0, 3))
        title_inp = SmoothInput(tcol, height=30, radius=10, bg=C["card"])
        title_inp.pack(fill="x")
        self._title_prop = title_inp.entry

        dcol = tk.Frame(sch_row, bg=C["card"])
        dcol.pack(side="left", fill="x", expand=True, padx=(6, 0))
        tk.Label(dcol, text=t("ws_editor.date_prop"), bg=C["card"],
                 fg=C["ink3"],
                 font=F("mono", 8)).pack(anchor="w", pady=(0, 3))
        date_inp = SmoothInput(dcol, height=30, radius=10, bg=C["card"])
        date_inp.pack(fill="x")
        self._date_prop = date_inp.entry

        footer = tk.Frame(body, bg=C["card"])
        footer.pack(fill="x", side="bottom", pady=(6, 0))
        RoundedButton(footer, t("btn.cancel"),
                        lambda: self.app.go_back(),
                        kind="secondary", size="md").pack(side="left")
        RoundedButton(footer, t("btn.save"),
                        self._save, kind="primary", size="md").pack(side="right")

    def on_enter(self, slug: Optional[str] = None, **_):
        """Called by navigate(...). slug=None means add-mode, slug=str means edit."""
        self.cfg = self.app.cfg
        self.slug = slug
        self._databases = []
        self._status.config(text="", fg=C["ink3"])
        self._target_dd.set_values([])
        self._projects_dd.set_values([])
        self._target_dd.set("")
        self._projects_dd.set("")

        if slug:
            self._title_label.config(text=t("ws_editor.title.edit", slug=slug))
            existing = self.cfg.get("profiles", {}).get(slug, {})
        else:
            self._title_label.config(text=t("ws_editor.title.add"))
            existing = {}

        self._label_entry.delete(0, "end")
        self._label_entry.insert(0, existing.get("label", ""))
        self._token_entry.delete(0, "end")
        self._token_entry.insert(0, existing.get("notion_token", ""))

        schema = existing.get("schema") or DEFAULT_SCHEMA
        self._title_prop.delete(0, "end")
        self._title_prop.insert(0, schema.get("title_property", "Name"))
        self._date_prop.delete(0, "end")
        self._date_prop.insert(0, schema.get("date_property", "Created Date"))

        self._preselect_target = existing.get("target_db_id")
        self._preselect_projects = existing.get("projects_db_id")

        if existing.get("notion_token"):
            self.after(120, self._test_and_fetch)

    def on_exit(self):
        pass

    def _test_and_fetch(self):
        token = self._token_entry.get().strip()
        if not token:
            self._status.config(text=t("ws_editor.err.token_first"),
                                  fg=C["err"])
            return
        self._status.config(text=t("ws_editor.testing"), fg=C["ink3"])
        threading.Thread(target=self._fetch_thread, args=(token,),
                         daemon=True).start()

    def _fetch_thread(self, token: str):
        client = NotionClient(token)
        conn = client.test_connection()
        if not conn.ok:
            self.after(0, lambda: self._status.config(
                text=f"✗ {conn.error[:60]}", fg=C["err"]))
            return
        try:
            dbs = client.list_databases()
        except Exception as e:
            self.after(0, lambda: self._status.config(
                text=f"✗ {e}", fg=C["err"]))
            return
        self.after(0, lambda: self._on_dbs_loaded(conn.workspace_name, dbs))

    def _on_dbs_loaded(self, workspace_name: str, dbs: list[DatabaseRef]):
        self._databases = dbs
        self._status.config(
            text=t("ws_editor.test_ok",
                   workspace=workspace_name or "workspace", n=len(dbs)),
            fg=C["ok"])
        self._db_labels = [f"{db.icon + ' ' if db.icon else ''}{db.title}"
                            for db in dbs]
        self._target_dd.set_values(self._db_labels)
        self._projects_dd.set_values(
            [t("ws_editor.projects_placeholder")] + self._db_labels)

        if self._preselect_target:
            for i, db in enumerate(dbs):
                if (db.id == self._preselect_target or
                        db.id.replace("-", "") == self._preselect_target.replace("-", "")):
                    self._target_dd.set(self._db_labels[i])
                    self._on_target_change_v(self._db_labels[i])
                    break
        if self._preselect_projects:
            for i, db in enumerate(dbs):
                if db.id == self._preselect_projects:
                    self._projects_dd.set(self._db_labels[i])
                    break
        else:
            self._projects_dd.set(t("ws_editor.projects_placeholder"))

    def _on_target_change_v(self, value: str):
        # Find which DB by label
        try:
            idx = self._db_labels.index(value)
        except (ValueError, AttributeError):
            return
        if idx < 0 or idx >= len(self._databases):
            return
        db = self._databases[idx]
        client = NotionClient(self._token_entry.get().strip())
        try:
            detection = client.get_db_schema(db.id)
        except Exception:
            return
        if detection.title_property:
            self._title_prop.delete(0, "end")
            self._title_prop.insert(0, detection.title_property)
        if detection.date_property:
            self._date_prop.delete(0, "end")
            self._date_prop.insert(0, detection.date_property)

    def _save(self):
        label = self._label_entry.get().strip()
        token = self._token_entry.get().strip()
        if not label or not token:
            self._status.config(text=t("ws_editor.err.required"),
                                  fg=C["err"])
            return

        target_label = self._target_dd.get()
        try:
            tgt_idx = self._db_labels.index(target_label)
        except (ValueError, AttributeError):
            self._status.config(text=t("ws_editor.err.pick_target"),
                                  fg=C["err"])
            return
        target_db_id = self._databases[tgt_idx].id

        projects_label = self._projects_dd.get()
        projects_db_id: Optional[str] = None
        if projects_label and projects_label != t("ws_editor.projects_placeholder"):
            try:
                p_idx = self._db_labels.index(projects_label)
                projects_db_id = self._databases[p_idx].id
            except (ValueError, AttributeError):
                pass

        profile = {
            "label": label,
            "notion_token": token,
            "target_db_id": target_db_id,
            "projects_db_id": projects_db_id,
            "schema": {
                "title_property": self._title_prop.get().strip() or "Name",
                "date_property": self._date_prop.get().strip() or "Created Date",
            },
        }

        if self.slug:
            self.cfg["profiles"][self.slug] = profile
        else:
            slug = _slugify(label)
            base_slug = slug
            i = 2
            while slug in self.cfg.get("profiles", {}):
                slug = f"{base_slug}-{i}"
                i += 1
            add_profile(self.cfg, slug, profile)

        save_config(self.cfg)
        self.app.on_settings_saved()
        self.app.go_back()


# ============================================================================
# LLM tab
# ============================================================================

class LLMTab(tk.Frame):
    """Provider-aware LLM config — provider picker rendered as clickable cards."""

    PROVIDERS = [
        ("lm_studio", "LM Studio",       "localhost:1234 · local",       True),
        ("ollama",    "Ollama",          "localhost:11434 · local",      True),
        ("openai",    "OpenAI",          "api.openai.com · cloud",       True),
        ("anthropic", "Anthropic",       "api.anthropic.com · cloud",    False),
        ("gemini",    "Google Gemini",   "gen language · cloud",         False),
        ("deepseek",  "DeepSeek",        "api.deepseek.com · cloud",     True),
        ("custom",    "Custom",          "OpenAI-compatible URL",        True),
    ]

    PROVIDER_URLS = {
        "lm_studio": "http://localhost:1234/v1",
        "ollama":    "http://localhost:11434/v1",
        "openai":    "https://api.openai.com/v1",
        "anthropic": "https://api.anthropic.com/v1",
        "gemini":    "https://generativelanguage.googleapis.com/v1beta",
        "deepseek":  "https://api.deepseek.com/v1",
        "custom":    "",
    }

    # Provider-specific model presets shown until user runs Test Connection
    # (then real list replaces these where available).
    PROVIDER_MODELS = {
        "lm_studio": ["auto"],
        "ollama":    ["auto"],
        "openai":    ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"],
        "anthropic": [
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022",
            "claude-3-opus-20240229",
            "claude-sonnet-4-20250514",
        ],
        "gemini": [
            "gemini-1.5-flash",
            "gemini-1.5-pro",
            "gemini-2.0-flash-exp",
        ],
        "deepseek": [
            "deepseek-chat",       # V3 — cheap + fast, best for summarisation
            "deepseek-reasoner",   # R1 — reasoning, slower + pricier
        ],
        "custom":    ["auto"],
    }

    # API key requirement copy per provider
    PROVIDER_KEY_HINTS = {
        "lm_studio": "Not required — local server.",
        "ollama":    "Not required — local server.",
        "openai":    "Required. Get one at platform.openai.com/api-keys",
        "anthropic": "Required. Get one at console.anthropic.com",
        "gemini":    "Required. Get one at aistudio.google.com/apikey",
        "deepseek":  "Required. Get one at platform.deepseek.com/api_keys",
        "custom":    "Provider-dependent.",
    }

    def __init__(self, parent, cfg: dict):
        super().__init__(parent, bg=C["card"])
        self.cfg = cfg
        llm = cfg.setdefault("llm", dict(LM_STUDIO_DEFAULTS))

        body = tk.Frame(self, bg=C["card"])
        body.pack(fill="both", expand=True, padx=12, pady=12)

        _section_label(body, t("settings.ai.provider"))
        self._provider_var = tk.StringVar(value=llm.get("provider", "lm_studio"))
        # 2-column grid of provider cards (compact)
        grid = tk.Frame(body, bg=C["card"])
        grid.pack(fill="x", pady=(0, 14))
        self._provider_cards: dict[str, SmoothCard] = {}
        for i, (slug, label, sub, supported) in enumerate(self.PROVIDERS):
            row, col = divmod(i, 2)
            cell = self._build_provider_card(grid, slug, label, sub, supported)
            cell.grid(row=row, column=col, sticky="ew", padx=(0 if col == 0 else 4),
                       pady=4)
            self._provider_cards[slug] = cell
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)
        self._paint_provider_cards()

        self._provider_hint = tk.Label(
            body, text="", bg=C["card"], fg=C["warn"],
            font=F("mono", 9), wraplength=380, justify="left")
        self._provider_hint.pack(anchor="w", pady=(0, 10))

        # Smooth inputs for URL + API key
        _section_label(body, t("settings.ai.base_url"))
        self._base_url_input = SmoothInput(body, height=36, radius=11, bg=C["card"])
        self._base_url_input.pack(fill="x", pady=(0, 10))
        self._base_url_input.set(llm.get("base_url", ""))
        self._base_url = self._base_url_input.entry  # back-compat

        _section_label(body, t("settings.ai.api_key"))
        self._api_key_input = SmoothInput(body, height=36, radius=11,
                                              show="•", bg=C["card"])
        self._api_key_input.pack(fill="x", pady=(0, 10))
        self._api_key_input.set(llm.get("api_key", "lm-studio"))
        self._api_key = self._api_key_input.entry

        _section_label(body, t("settings.ai.model"))
        # Pre-load provider-specific model list so dropdown has real options
        # on first open (instead of just ["auto"] until user runs Test).
        saved_provider = llm.get("provider", "lm_studio")
        saved_model = llm.get("model", "auto")
        init_models = list(self.PROVIDER_MODELS.get(saved_provider, ["auto"]))
        if saved_model and saved_model not in init_models:
            init_models = [saved_model] + init_models
        self._model_dd = SmoothDropdown(body, values=init_models,
                                            initial=saved_model,
                                            height=34, radius=11, bg=C["card"])
        self._model_dd.pack(fill="x", pady=(0, 8))

        test_row = tk.Frame(body, bg=C["bg_card"])
        test_row.pack(fill="x", pady=(0, 14))
        _ghost_button(test_row, t("btn.test_connection"),
                       self._test).pack(side="left", ipadx=12, ipady=6)
        self._status = tk.Label(test_row, text="", bg=C["bg_card"],
                                 fg=C["text3"], font=("Consolas", 9))
        self._status.pack(side="left", padx=(12, 0))

        # Temperature + timeout in one row
        adv = tk.Frame(body, bg=C["bg_card"])
        adv.pack(fill="x", pady=(0, 0))
        tcol = tk.Frame(adv, bg=C["bg_card"])
        tcol.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._temp_entry = _labeled_entry(
            tcol, t("settings.ai.temperature"),
            str(llm.get("temperature", 0.3)))
        ocol = tk.Frame(adv, bg=C["bg_card"])
        ocol.pack(side="left", fill="x", expand=True, padx=(8, 0))
        self._timeout_entry = _labeled_entry(
            ocol, t("settings.ai.timeout"),
            str(llm.get("timeout", 300)))

        # Sync hint with initial provider
        self._on_provider_change(None)

# (no extra hook needed)

    def _build_provider_card(self, parent, slug: str, label: str,
                               sub: str, supported: bool) -> SmoothCard:
        card = SmoothCard(parent, radius=12, padding=10, bg=C["card"])
        col = tk.Frame(card.inner, bg=C["card"])
        col.pack(fill="x")
        tk.Label(col, text=label, bg=C["card"], fg=C["ink"],
                 font=F("body", 10, "bold"),
                 anchor="w").pack(fill="x")
        tk.Label(col, text=sub, bg=C["card"], fg=C["ink3"],
                 font=F("mono", 8), anchor="w").pack(fill="x", pady=(1, 0))
        # Click to select
        for w in (card.inner, col) + tuple(col.winfo_children()):
            w.bind("<Button-1>", lambda e, s=slug: self._select_provider(s))
            w.configure(cursor="hand2")
        return card

    def _select_provider(self, slug: str):
        self._provider_var.set(slug)
        # Auto-fill URL
        url = self.PROVIDER_URLS.get(slug, "")
        if url:
            self._base_url_input.set(url)
        # Refresh model dropdown with provider-specific defaults
        models = self.PROVIDER_MODELS.get(slug, ["auto"])
        self._model_dd.set_values(models)
        # Pick first as default (preserve user's choice if still valid)
        if self._model_dd.get() not in models:
            self._model_dd.set(models[0])
        self._paint_provider_cards()
        self._update_provider_hint(slug)

    def _paint_provider_cards(self):
        active = self._provider_var.get()
        for slug, card in self._provider_cards.items():
            is_active = (slug == active)
            # Re-render the card with active bg
            card._fill = C["tint_yellow"] if is_active else C["card"]
            card._border = C["ink"]
            card._border_w = 1.5 if is_active else 1
            card._last_size = (0, 0)  # force re-render
            w = card.winfo_width()
            h = card.winfo_height()
            if w > 1 and h > 1:
                card._render_bg(w, h)
            # Repaint inner labels for active background
            new_bg = C["tint_yellow"] if is_active else C["card"]
            for child in card.inner.winfo_children():
                _recolor_bg(child, new_bg)

    def _update_provider_hint(self, slug: str):
        # All providers now have adapter support. Show API key requirement
        # so user knows what to fill in.
        key_hint = self.PROVIDER_KEY_HINTS.get(slug, "")
        self._provider_hint.config(text=t("settings.ai.api_key_hint",
                                            hint=key_hint),
                                      fg=C["ink3"])

    # Backwards-compat shim — older code paths may still reference this
    def _on_provider_change(self, _=None):
        slug = self._provider_var.get()
        self._select_provider(slug)

    def _test(self):
        self._status.config(text=t("settings.ai.testing"), fg=C["ink3"])
        provider = self._provider_var.get() or "lm_studio"
        url = self._base_url_input.get().strip()
        api_key = self._api_key_input.get().strip() or "lm-studio"
        model = self._model_dd.get().strip() or "auto"
        threading.Thread(
            target=self._test_thread,
            args=(provider, url, api_key, model),
            daemon=True).start()

    def _test_thread(self, provider: str, url: str, api_key: str, model: str):
        client = LLMClient(provider=provider, base_url=url,
                            api_key=api_key, model=model)
        result = client.test_connection()
        if result.ok:
            chat_models = [m for m in result.models
                            if "embed" not in m.lower()]
            self.after(0, lambda: self._on_test_ok(provider, chat_models))
        else:
            self.after(0, lambda: self._status.config(
                text=t("settings.ai.test_err", err=result.error[:70]),
                fg=C["err"]))

    def _on_test_ok(self, provider: str, models: list[str]):
        self._status.config(text=t("settings.ai.test_ok", n=len(models)),
                              fg=C["ok"])
        # OpenAI-compat providers (LM Studio / Ollama / OpenAI / DeepSeek /
        # Custom) expose /models and allow 'auto' first-match selection.
        # Anthropic / Gemini need an explicit model name.
        if provider in ("lm_studio", "ollama", "openai", "deepseek", "custom"):
            values = ["auto"] + models
        else:
            values = models or self.PROVIDER_MODELS.get(provider, [])
        self._model_dd.set_values(values)
        if self._model_dd.get() not in values:
            self._model_dd.set(values[0] if values else "auto")

    def commit(self):
        llm = self.cfg.setdefault("llm", {})
        llm["provider"] = self._provider_var.get() or "lm_studio"
        llm["base_url"] = self._base_url_input.get().strip()
        llm["api_key"] = self._api_key_input.get().strip() or "lm-studio"
        llm["model"] = self._model_dd.get().strip() or "auto"
        try:
            llm["temperature"] = float(self._temp_entry.get().strip())
        except ValueError:
            llm["temperature"] = 0.3
        try:
            llm["timeout"] = max(30, int(self._timeout_entry.get().strip()))
        except ValueError:
            llm["timeout"] = 300


# ============================================================================
# Whisper tab
# ============================================================================

class WhisperTab(tk.Frame):
    # Simple labels mapped to the actual Whisper param value. Internal
    # values stay technical, UI shows plain-language choices.
    MODEL_OPTIONS = [
        ("Fast — least accurate",          "small"),
        ("Balanced — recommended",         "turbo"),
        ("Accurate — slowest",             "large-v3"),
    ]
    LANG_OPTIONS = [
        ("Indonesian",                      "id"),
        ("English",                         "en"),
        ("Auto-detect",                     "auto"),
    ]
    COMPUTE_OPTIONS = [
        ("Fast — slight accuracy loss",    "int8"),
        ("Balanced — recommended",         "float16"),
        ("Maximum precision — slowest",    "float32"),
    ]
    BEAM_OPTIONS = [
        ("Quick — fastest, rougher",       1),
        ("Default — recommended",          5),
        ("Thorough — slowest, best",       10),
    ]
    DEVICE_OPTIONS = [
        ("GPU (CUDA) — fast, uses VRAM",   "cuda"),
        ("CPU — slower, no GPU conflict",  "cpu"),
    ]

    @staticmethod
    def _label_for(options, value):
        for label, v in options:
            if v == value:
                return label
        return options[0][0]

    @staticmethod
    def _value_for(options, label, default):
        for l, v in options:
            if l == label:
                return v
        return default

    def __init__(self, parent, cfg: dict):
        super().__init__(parent, bg=C["card"])
        self.cfg = cfg
        w = cfg.setdefault("whisper", {})

        body = tk.Frame(self, bg=C["card"])
        body.pack(fill="both", expand=True, padx=14, pady=14)

        # Helper: dropdown field with hint below — single column flow
        def _field(parent, label_text, hint_text, widget):
            _section_label(parent, label_text)
            widget.pack(fill="x", pady=(0, 4))
            tk.Label(parent, text=hint_text,
                     bg=C["card"], fg=C["ink3"],
                     font=F("mono", 9), anchor="w",
                     wraplength=520, justify="left").pack(
                fill="x", pady=(0, 14))

        # === Model
        model_labels = [lbl for lbl, _ in self.MODEL_OPTIONS]
        self._model_dd = SmoothDropdown(
            body, values=model_labels,
            initial=self._label_for(self.MODEL_OPTIONS, w.get("model", "turbo")),
            height=34, radius=11, bg=C["card"])
        _field(body, t("settings.whisper.model"),
               t("settings.whisper.model_hint"),
               self._model_dd)

        # === Language
        lang_labels = [lbl for lbl, _ in self.LANG_OPTIONS]
        self._lang_dd = SmoothDropdown(
            body, values=lang_labels,
            initial=self._label_for(self.LANG_OPTIONS,
                                     w.get("language") or "auto"),
            height=34, radius=11, bg=C["card"])
        _field(body, t("settings.whisper.language"),
               t("settings.whisper.language_hint"),
               self._lang_dd)

        # === Compute type
        compute_labels = [lbl for lbl, _ in self.COMPUTE_OPTIONS]
        self._compute_dd = SmoothDropdown(
            body, values=compute_labels,
            initial=self._label_for(self.COMPUTE_OPTIONS,
                                     w.get("compute_type", "float16")),
            height=34, radius=11, bg=C["card"])
        _field(body, t("settings.whisper.compute"),
               t("settings.whisper.compute_hint"),
               self._compute_dd)

        # === Beam size
        beam_labels = [lbl for lbl, _ in self.BEAM_OPTIONS]
        self._beam_dd = SmoothDropdown(
            body, values=beam_labels,
            initial=self._label_for(self.BEAM_OPTIONS,
                                     int(w.get("beam_size", 5))),
            height=34, radius=11, bg=C["card"])
        _field(body, t("settings.whisper.beam"),
               t("settings.whisper.beam_hint"),
               self._beam_dd)

        # === Hardware (GPU vs CPU)
        device_labels = [lbl for lbl, _ in self.DEVICE_OPTIONS]
        self._device_dd = SmoothDropdown(
            body, values=device_labels,
            initial=self._label_for(self.DEVICE_OPTIONS,
                                     (w.get("device") or "cuda").lower()),
            height=34, radius=11, bg=C["card"])
        _field(body, t("settings.whisper.device"),
               t("settings.whisper.device_hint"),
               self._device_dd)

        # === VAD checkbox
        vad_row = tk.Frame(body, bg=C["card"])
        vad_row.pack(fill="x", pady=(4, 4))
        self._vad_cb = SmoothCheckBox(vad_row,
                                          checked=bool(w.get("vad_filter", True)),
                                          size=18, bg=C["card"])
        self._vad_cb.pack(side="left", padx=(0, 10), anchor="n", pady=(2, 0))
        vad_col = tk.Frame(vad_row, bg=C["card"])
        vad_col.pack(side="left", fill="x", expand=True)
        tk.Label(vad_col, text=t("settings.whisper.vad"),
                 bg=C["card"], fg=C["ink"], font=F("body", 10, "bold"),
                 anchor="w").pack(fill="x")
        tk.Label(vad_col,
                 text=t("settings.whisper.vad_hint"),
                 bg=C["card"], fg=C["ink3"], font=F("mono", 9),
                 anchor="w", wraplength=520,
                 justify="left").pack(fill="x", pady=(2, 0))

    def commit(self):
        w = self.cfg.setdefault("whisper", {})
        w["model"] = self._value_for(
            self.MODEL_OPTIONS, self._model_dd.get(), "turbo")
        lang_val = self._value_for(
            self.LANG_OPTIONS, self._lang_dd.get(), "id")
        w["language"] = lang_val if lang_val != "auto" else None
        w["compute_type"] = self._value_for(
            self.COMPUTE_OPTIONS, self._compute_dd.get(), "float16")
        w["beam_size"] = self._value_for(
            self.BEAM_OPTIONS, self._beam_dd.get(), 5)
        w["device"] = self._value_for(
            self.DEVICE_OPTIONS, self._device_dd.get(), "cuda")
        w["vad_filter"] = self._vad_cb.is_checked()


# ============================================================================
# Telegram tab
# ============================================================================

class TelegramTab(tk.Frame):
    """Notifications tab — Telegram + Discord with test buttons."""

    def __init__(self, parent, cfg: dict):
        super().__init__(parent, bg=C["card"])
        self.cfg = cfg
        tg = cfg.setdefault("telegram", {})
        dc = cfg.setdefault("discord", {})

        # Scrollable body
        canvas = tk.Canvas(self, bg=C["card"], highlightthickness=0)
        canvas.pack(side="left", fill="both", expand=True)
        sb = tk.Scrollbar(self, orient="vertical", command=canvas.yview,
                           bg=C["card"], troughcolor=C["card"], bd=0, width=6)
        sb.pack(side="right", fill="y")
        canvas.configure(yscrollcommand=sb.set)
        body = tk.Frame(canvas, bg=C["card"])
        body_id = canvas.create_window((0, 0), window=body, anchor="nw")
        body.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
                     lambda e: canvas.itemconfigure(body_id, width=e.width))

        def _wheel(event):
            if event.delta:
                canvas.yview_scroll(-int(event.delta / 120), "units")
            else:
                canvas.yview_scroll(-1 if event.num == 4 else 1, "units")
        self._wheel = _wheel

        inner = tk.Frame(body, bg=C["card"])
        inner.pack(fill="both", expand=True, padx=12, pady=12)

        # === Telegram section
        _section_label(inner, t("settings.notif.telegram"))
        tg_row = tk.Frame(inner, bg=C["card"])
        tg_row.pack(fill="x", pady=(0, 8))
        self._tg_enabled_cb = SmoothCheckBox(
            tg_row, checked=bool(tg.get("enabled", False)),
            size=18, bg=C["card"])
        self._tg_enabled_cb.pack(side="left", padx=(0, 10))
        tk.Label(tg_row, text=t("settings.notif.tg_enable"),
                 bg=C["card"], fg=C["ink"],
                 font=F("body", 10, "bold")).pack(side="left")

        self._tg_token_entry = _labeled_entry(
            inner, t("settings.notif.tg_token"),
            tg.get("bot_token", ""), show="•")
        self._tg_chat_entry = _labeled_entry(
            inner, t("settings.notif.tg_chat"), tg.get("chat_id", ""))

        tg_test = tk.Frame(inner, bg=C["card"])
        tg_test.pack(fill="x", pady=(0, 6))
        RoundedButton(tg_test, t("btn.send_test"), self._test_telegram,
                       kind="secondary", size="sm").pack(side="left")
        self._tg_status = tk.Label(tg_test, text="",
                                      bg=C["card"], fg=C["ink3"],
                                      font=F("mono", 9))
        self._tg_status.pack(side="left", padx=(10, 0))

        tk.Label(inner,
                 text=t("settings.notif.tg_hint"),
                 bg=C["card"], fg=C["ink3"], font=F("mono", 9),
                 wraplength=520, justify="left",
                 anchor="w").pack(fill="x", pady=(4, 14))

        # === Discord section
        tk.Frame(inner, height=1, bg=C["border_soft"]).pack(
            fill="x", pady=(6, 12))
        _section_label(inner, t("settings.notif.discord"))
        dc_row = tk.Frame(inner, bg=C["card"])
        dc_row.pack(fill="x", pady=(0, 8))
        self._dc_enabled_cb = SmoothCheckBox(
            dc_row, checked=bool(dc.get("enabled", False)),
            size=18, bg=C["card"])
        self._dc_enabled_cb.pack(side="left", padx=(0, 10))
        tk.Label(dc_row, text=t("settings.notif.dc_enable"),
                 bg=C["card"], fg=C["ink"],
                 font=F("body", 10, "bold")).pack(side="left")

        self._dc_webhook_entry = _labeled_entry(
            inner, t("settings.notif.dc_url"),
            dc.get("webhook_url", ""), show="•")

        dc_test = tk.Frame(inner, bg=C["card"])
        dc_test.pack(fill="x", pady=(0, 6))
        RoundedButton(dc_test, t("btn.send_test"), self._test_discord,
                       kind="secondary", size="sm").pack(side="left")
        self._dc_status = tk.Label(dc_test, text="",
                                      bg=C["card"], fg=C["ink3"],
                                      font=F("mono", 9))
        self._dc_status.pack(side="left", padx=(10, 0))

        tk.Label(inner,
                 text=t("settings.notif.dc_hint"),
                 bg=C["card"], fg=C["ink3"], font=F("mono", 9),
                 wraplength=520, justify="left",
                 anchor="w").pack(fill="x", pady=(4, 14))

        self.after(50, self._bind_wheel_recursively)

    def _bind_wheel_recursively(self):
        def walk(w):
            w.bind("<MouseWheel>", self._wheel)
            w.bind("<Button-4>", self._wheel)
            w.bind("<Button-5>", self._wheel)
            for c in w.winfo_children():
                walk(c)
        walk(self)

    def _test_telegram(self):
        token = self._tg_token_entry.get().strip()
        chat = self._tg_chat_entry.get().strip()
        if not token or not chat:
            self._tg_status.config(text=t("settings.notif.tg_err.required"),
                                     fg=C["err"])
            return
        self._tg_status.config(text=t("settings.notif.tg_sending"),
                                 fg=C["ink3"])
        threading.Thread(target=self._test_tg_thread,
                         args=(token, chat), daemon=True).start()

    def _test_tg_thread(self, token, chat):
        from ..services.telegram import TelegramClient
        c = TelegramClient(bot_token=token, chat_id=chat, enabled=True)
        ok = c.send_text(t("settings.notif.test_tg_body"))
        self.after(0, lambda: self._tg_status.config(
            text=t("settings.notif.tg_ok") if ok
                  else t("settings.notif.tg_err"),
            fg=C["ok"] if ok else C["err"]))

    def _test_discord(self):
        url = self._dc_webhook_entry.get().strip()
        if not url:
            self._dc_status.config(text=t("settings.notif.dc_err.required"),
                                     fg=C["err"])
            return
        self._dc_status.config(text=t("settings.notif.dc_sending"),
                                 fg=C["ink3"])
        threading.Thread(target=self._test_dc_thread,
                         args=(url,), daemon=True).start()

    def _test_dc_thread(self, url):
        from ..services.discord import DiscordClient
        c = DiscordClient(webhook_url=url, enabled=True)
        ok = c.send_text(t("settings.notif.test_dc_body"))
        self.after(0, lambda: self._dc_status.config(
            text=t("settings.notif.dc_ok") if ok
                  else t("settings.notif.dc_err"),
            fg=C["ok"] if ok else C["err"]))

    def commit(self):
        tg = self.cfg.setdefault("telegram", {})
        tg["enabled"] = self._tg_enabled_cb.is_checked()
        tg["bot_token"] = self._tg_token_entry.get().strip()
        tg["chat_id"] = self._tg_chat_entry.get().strip()
        dc = self.cfg.setdefault("discord", {})
        dc["enabled"] = self._dc_enabled_cb.is_checked()
        dc["webhook_url"] = self._dc_webhook_entry.get().strip()


# ============================================================================
# Output tab
# ============================================================================

class OutputTab(tk.Frame):
    def __init__(self, parent, cfg: dict):
        super().__init__(parent, bg=C["card"])
        self.cfg = cfg

        body = tk.Frame(self, bg=C["card"])
        body.pack(fill="both", expand=True, padx=12, pady=12)

        _section_label(body, t("settings.output.folder"))
        path_inp = SmoothInput(body, height=34, radius=11, bg=C["card"])
        path_inp.pack(fill="x", pady=(0, 6))
        path_inp.set(cfg.get("output_dir", "./output"))
        self._path_entry = path_inp.entry

        browse_row = tk.Frame(body, bg=C["card"])
        browse_row.pack(fill="x", pady=(0, 4))
        RoundedButton(browse_row, t("btn.browse"), self._browse,
                       kind="secondary", size="sm").pack(side="left")
        tk.Label(body,
                 text=t("settings.output.folder_hint"),
                 bg=C["card"], fg=C["ink3"], font=F("mono", 9),
                 anchor="w").pack(fill="x", pady=(6, 20))

        # Auto-open Notion — SmoothCheckBox + label row
        _section_label(body, t("settings.output.after"))
        toggle_row = tk.Frame(body, bg=C["card"])
        toggle_row.pack(fill="x", pady=(0, 4))
        self._auto_open_cb = SmoothCheckBox(toggle_row,
                                                checked=bool(cfg.get("auto_open_notion", False)),
                                                size=18, bg=C["card"])
        self._auto_open_cb.pack(side="left", padx=(0, 10))
        tk.Label(toggle_row,
                 text=t("settings.output.auto_open"),
                 bg=C["card"], fg=C["ink"], font=F("body", 10),
                 anchor="w").pack(side="left", fill="x", expand=True)
        tk.Label(body,
                 text=t("settings.output.auto_open_hint"),
                 bg=C["card"], fg=C["ink3"], font=F("mono", 9),
                 wraplength=320, justify="left",
                 anchor="w").pack(fill="x", pady=(4, 20))

        # ===== Interface language =====
        # Drives UI labels, Notion headings, month abbreviations. LLM summary
        # output language is auto-detected from the transcript regardless of
        # this setting (Indonesian audio → Indonesian summary, etc.).
        _section_label(body, t("settings.output.lang"))
        self.LANG_OPTIONS = [
            (t("settings.output.lang_en"), "en"),
            (t("settings.output.lang_id"), "id"),
        ]
        lang_labels = [lbl for lbl, _ in self.LANG_OPTIONS]
        current_code = (cfg.get("language") or "en").lower()
        current_label = next(
            (lbl for lbl, code in self.LANG_OPTIONS if code == current_code),
            lang_labels[0])
        self._lang_dd = SmoothDropdown(
            body, values=lang_labels, initial=current_label,
            height=34, radius=11, bg=C["card"])
        self._lang_dd.pack(fill="x", pady=(0, 4))
        tk.Label(body,
                 text=t("settings.output.lang_hint"),
                 bg=C["card"], fg=C["ink3"], font=F("mono", 9),
                 wraplength=520, justify="left",
                 anchor="w").pack(fill="x", pady=(0, 0))

    def _browse(self):
        d = filedialog.askdirectory(title=t("file_dialog.pick_output"))
        if d:
            self._path_entry.delete(0, "end")
            self._path_entry.insert(0, d)

    def commit(self):
        self.cfg["output_dir"] = (self._path_entry.get().strip()
                                    or "./output")
        self.cfg["auto_open_notion"] = self._auto_open_cb.is_checked()
        # Language: map dropdown label back to ISO code.
        chosen_label = self._lang_dd.get()
        chosen_code = next(
            (code for lbl, code in self.LANG_OPTIONS if lbl == chosen_label),
            "en")
        self.cfg["language"] = chosen_code


# ============================================================================
# About tab — app identity, credits, links
# ============================================================================

class AboutTab(tk.Frame):
    """Static credits / about panel. No editable settings — purely
    informational (logo, version, author, tech stack, GitHub link, license).
    """

    GITHUB_URL = "https://github.com/gemrra/NoteNara"

    def __init__(self, parent, cfg: dict):
        super().__init__(parent, bg=C["card"])
        from .. import __version__

        body = tk.Frame(self, bg=C["card"])
        body.pack(fill="both", expand=True, padx=20, pady=18)

        # Logo + wordmark
        head = tk.Frame(body, bg=C["card"])
        head.pack(fill="x", pady=(4, 2))
        BrandLogo(head, size=44, bg=C["card"]).pack(side="left", padx=(0, 12))
        title_col = tk.Frame(head, bg=C["card"])
        title_col.pack(side="left", fill="x", expand=True)
        tk.Label(title_col, text="NoteNara", bg=C["card"], fg=C["ink"],
                 font=F("display", 22, italic=True),
                 anchor="w").pack(fill="x")
        tk.Label(title_col, text=t("settings.about.version", v=__version__),
                 bg=C["card"], fg=C["ink3"], font=F("mono", 9),
                 anchor="w").pack(fill="x")

        tk.Label(body, text=t("settings.about.tagline"),
                 bg=C["card"], fg=C["ink2"], font=F("body", 10),
                 anchor="w", wraplength=520, justify="left").pack(
            fill="x", pady=(10, 0))
        tk.Label(body, text=t("settings.about.made_by"),
                 bg=C["card"], fg=C["ink"], font=F("body", 11, "bold"),
                 anchor="w").pack(fill="x", pady=(8, 0))

        # Divider
        tk.Frame(body, height=1, bg=C["border_soft"]).pack(
            fill="x", pady=(16, 14))

        # Credits / tech stack
        _section_label(body, t("settings.about.credits_title"))
        tk.Label(body, text=t("settings.about.credits"),
                 bg=C["card"], fg=C["ink2"], font=F("mono", 9),
                 anchor="w", justify="left").pack(fill="x", pady=(2, 14))

        # GitHub button
        RoundedButton(body, t("settings.about.github"),
                       lambda: webbrowser.open(self.GITHUB_URL),
                       kind="secondary", size="sm").pack(anchor="w")

        # License footnote
        tk.Label(body, text=t("settings.about.license"),
                 bg=C["card"], fg=C["ink3"], font=F("mono", 9),
                 anchor="w").pack(fill="x", pady=(16, 0))

    def commit(self):
        # Nothing to persist — informational tab only.
        pass


# AppearanceTab removed — no theme switching shipped yet.
