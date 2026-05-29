"""Centralised i18n strings for NoteNara.

Two languages: ``en`` (default) and ``id``. Callers use ``t("section.key")``
to look up the active-language string; all strings live in a single dict so
adding a new language is one entry away.

Locale is set once at app startup from ``cfg['language']`` via
``set_locale()``. The UI exposes a dropdown that updates the config — change
takes effect on next restart since already-built Tk widgets keep their
construction-time text.
"""
from __future__ import annotations

_DEFAULT_LANG = "en"
_current_lang = _DEFAULT_LANG


STRINGS: dict[str, dict[str, str]] = {
    "en": {
        # ----- common buttons -----
        "btn.save":             "Save",
        "btn.cancel":           "Cancel",
        "btn.back":              "Back",
        "btn.delete":           "Delete",
        "btn.edit":             "Edit",
        "btn.add":              "Add",
        "btn.set_active":       "Set Active",
        "btn.test_connection":  "Test connection",
        "btn.send_test":        "Send test message",
        "btn.browse":           "Browse folder…",
        "btn.copy_markdown":    "Copy markdown",
        "btn.copy_plain":       "Copy plain",
        "btn.copy_link":        "Copy link",
        "btn.view_log":         "View log",
        "btn.send_to_notion":   "Send to Notion  →",
        "btn.publish":          "Publish to Notion",
        "btn.publishing":       "Publishing…",
        "btn.open_in_notion":   "Open in Notion  ↗",
        "btn.back_to_home":     "← Back to home",
        "btn.start_transcription": "Start transcription  →",
        "btn.get_started":      "Get started  →",
        "btn.skip":             "Skip",
        "btn.add_workspace":    "+ Add workspace",

        # ----- app chrome -----
        "chrome.settings.title": "Settings",

        # ----- main view -----
        "main.tagline":         "Drop a recording — get a clean summary in seconds. Local & private.",
        "main.dropzone.title":  "Drop a recording",
        "main.dropzone.subtitle": "or click to browse",
        "main.ornament.recent": "recent",
        "main.recent.empty":    "No recent transcriptions yet.",
        "main.recent.open":     "Open",
        "main.file.remove":     "Remove",
        "main.cancel_processing": "Cancel",

        # ----- welcome view -----
        "welcome.welcome_to":   "Welcome to",
        "welcome.step1.title":  "Drop your meeting recording",
        "welcome.step1.desc":   "audio · video — mp4, mp3, wav, m4a, mov…",
        "welcome.step2.title":  "Review the auto-summary",
        "welcome.step2.desc":   "edit anything before publishing",
        "welcome.step3.title":  "Copy it — or send it to Notion",
        "welcome.step3.desc":   "workspace setup is asked on demand",

        # ----- preview view -----
        "preview.title":            "Review",
        "preview.meta_format":      "{chars} chars  ·  {kp} key points  ·  {ai} action items",
        "preview.truncated":        "truncated",
        "preview.no_summary":       "No summary available (LLM unreachable).",
        "preview.no_summary_hint":  "The transcript is saved locally. Open Settings → AI model to fix the connection, then try again.",
        "preview.ornament.summary": "summary",
        "preview.ornament.key_points":   "key points · {n}",
        "preview.ornament.action_items": "action items · {n}",
        "preview.ornament.raw":     "raw transcript",
        "preview.raw.full_link":    "full → {name}",

        # ----- markdown export -----
        "markdown.heading.summary":     "## Summary",
        "markdown.heading.key_points":  "## Key points",
        "markdown.heading.action_items": "## Action items",

        # ----- notion setup view -----
        "notion_setup.title":       "Send to Notion",
        "notion_setup.crumb":       "workspace · target · project · topic",
        "notion_setup.workspace":   "Workspace",
        "notion_setup.workspace_placeholder": "Select workspace…",
        "notion_setup.target_db":   "Target database",
        "notion_setup.target_db_empty": "(no database configured)",
        "notion_setup.project":     "Project   optional",
        "notion_setup.project_none": "(no project)",
        "notion_setup.topic":       "Topic",
        "notion_setup.date":        "Meeting date   YYYY-MM-DD",
        "notion_setup.date_invalid": "Invalid date — using today instead.",
        "notion_setup.preview_label": "PAGE TITLE PREVIEW",
        "notion_setup.empty_title": "(empty title)",
        "notion_setup.publishing":  "Publishing to Notion…",
        "notion_setup.err.no_topic": "Topic is required.",
        "notion_setup.err.no_workspace": "Choose a workspace first.",
        "notion_setup.err.projects_fail": "Projects fetch failed: {msg}",

        # ----- done view -----
        "done.title":               "Saved to Notion",
        "done.meta_format":         "{kp} key points · {ai} action items",
        "done.page_title_label":    "PAGE TITLE",

        # ----- file picker / dialogs -----
        "file_dialog.title":        "Choose audio / video",
        "file_dialog.all_files":    "All files",
        "file_dialog.pick_output":  "Pick output folder",

        # ----- phase chip / progress -----
        "phase.loading_services":   "Loading services…",
        "phase.starting":            "Starting…",
        "phase.loading_whisper":    "Loading Whisper {name}…",
        "phase.loading_whisper_t":  "Loading Whisper {name}… {sec}s",
        "phase.loading_whisper_hint": "Loading Whisper {name}… {sec}s (check GPU memory — close LM Studio?)",
        "phase.transcribing":       "Transcribing… {pct:.0f}%",
        "phase.transcription_done": "Transcription complete.",

        # ----- log widget -----
        "log.header":               "LOG",
        "log.stdout":               "STDOUT",
        "log.clear":                "clear",
        "log.open":                 "open log",
        "log.lines":                "{n} line{s}",
        "log.awaiting":             "awaiting input…",

        # ----- settings: sidebar tabs -----
        "settings.tab.notion":          "Notion",
        "settings.tab.ai":              "AI model",
        "settings.tab.transcription":   "Transcription",
        "settings.tab.notifications":   "Notifications",
        "settings.tab.output":          "Output",

        # ----- settings: Notion tab -----
        "settings.notion.workspaces":   "Workspaces",
        "settings.notion.workspaces_hint": "Each workspace = one Notion integration token + its target DB.",
        "settings.notion.empty":        "No workspaces yet. Click + Add to create one.",
        "settings.notion.page_format":  "Page format",
        "settings.notion.page_format_hint": "How meeting pages look when published.",
        "settings.notion.page_icon":    "PAGE ICON",
        "settings.notion.title_format": "TITLE FORMAT",
        "settings.notion.include_raw":  "Include raw transcript (collapsed toggle)",
        "settings.notion.include_raw_hint": "Off = lighter page, transcript stays as local .txt only.",
        "settings.notion.active_dbs":   "Active workspace databases",
        "settings.notion.active_dbs_hint": "Where meeting notes get published + where project list is sourced from.",
        "settings.notion.target_db_label": "TARGET DATABASE  (notes get created here)",
        "settings.notion.projects_db_label": "PROJECTS DATABASE  (optional — source for project list)",
        "settings.notion.projects_db_none": "(none — search all pages)",
        "settings.notion.defaults":     "Defaults",
        "settings.notion.defaults_hint": "Pre-fill the publish form so each meeting is quicker.",
        "settings.notion.default_project": "DEFAULT PROJECT",
        "settings.notion.default_project_ask": "(ask each time)",
        "settings.notion.default_project_hint": "'(ask each time)' = pick per meeting.",
        "settings.notion.auto_publish":     "Skip preview, auto-publish to Notion",
        "settings.notion.auto_publish_hint": "One-click meeting → page. You trust the LLM.",
        "settings.notion.active":       "Active workspace",
        "settings.notion.test_hint":    "Click 'Test connection' to verify.",
        "settings.notion.no_active":    "No active workspace",
        "settings.notion.cant_delete_last": "Can't delete the last workspace.",
        "settings.notion.test_ok":      "✓ Connected · {workspace} · bot: {bot}",
        "settings.notion.test_err":     "✗ {err}",
        "settings.notion.no_active_err": "No active workspace.",
        "settings.notion.token_missing": "Token missing.",
        "settings.notion.testing":      "Testing…",
        "settings.notion.title_fmt.standard":   "Project — Materi — Date",
        "settings.notion.title_fmt.simple":     "Materi — Date",
        "settings.notion.title_fmt.date_first": "Date · Materi",

        # ----- settings: workspace editor -----
        "ws_editor.title.add":          "Add workspace",
        "ws_editor.title.edit":         "Edit workspace — {slug}",
        "ws_editor.label":              "Label",
        "ws_editor.token":              "Notion integration token",
        "ws_editor.link":               "🔗  notion.so/my-integrations",
        "ws_editor.test_fetch":         "Test & fetch databases",
        "ws_editor.target":             "Target database — where meeting notes go",
        "ws_editor.target_placeholder": "(test connection first)",
        "ws_editor.projects":           "Projects database — optional",
        "ws_editor.projects_placeholder": "(none — search all pages)",
        "ws_editor.schema":             "Schema mapping — auto-detected",
        "ws_editor.title_prop":         "TITLE",
        "ws_editor.date_prop":          "DATE",
        "ws_editor.err.token_first":    "Enter a token first.",
        "ws_editor.err.required":       "Label and token are required.",
        "ws_editor.err.pick_target":    "Pick a target database.",
        "ws_editor.testing":            "Testing…",
        "ws_editor.test_ok":            "✓ {workspace} · {n} db(s)",

        # ----- settings: AI / LLM tab -----
        "settings.ai.provider":         "Provider",
        "settings.ai.base_url":         "Base URL",
        "settings.ai.api_key":          "API key   only for cloud providers",
        "settings.ai.model":            "Model",
        "settings.ai.temperature":      "Temperature (0-1)",
        "settings.ai.timeout":          "Timeout (seconds)",
        "settings.ai.api_key_hint":     "API key: {hint}",
        "settings.ai.testing":          "Testing…",
        "settings.ai.test_ok":          "✓ Connected · {n} model(s)",
        "settings.ai.test_err":         "✗ {err}",
        "settings.ai.no_models":        "No chat-capable models found (only embeddings).",

        # ----- settings: Whisper tab -----
        "settings.whisper.model":               "Model",
        "settings.whisper.model_hint":          "Transcription engine size. Larger = more accurate but slower and uses more GPU memory.",
        "settings.whisper.language":            "Audio language",
        "settings.whisper.language_hint":       "Tell Whisper which language the meeting is in. 'Auto-detect' guesses from the first few seconds.",
        "settings.whisper.compute":             "Number precision",
        "settings.whisper.compute_hint":        "How precisely the model does math. Lower precision = faster, uses less VRAM. 'Balanced' works for most GPUs.",
        "settings.whisper.beam":                "Decode quality",
        "settings.whisper.beam_hint":           "How hard Whisper searches for the best transcription. 'Thorough' costs ~2× time vs 'Quick' but catches harder words.",
        "settings.whisper.device":              "Hardware",
        "settings.whisper.device_hint":         "Use GPU for speed, or switch to CPU if Whisper hangs at 'Loading services…' (usually because LM Studio is holding your VRAM). CPU forces int8 precision automatically.",
        "settings.whisper.vad":                 "Skip silence (recommended)",
        "settings.whisper.vad_hint":            "Removes quiet gaps before transcribing — prevents the model from inventing repeating phrases on silence.",

        # ----- settings: notifications tab -----
        "settings.notif.telegram":              "Telegram",
        "settings.notif.tg_enable":             "Enable Telegram notifications",
        "settings.notif.tg_token":              "Bot token",
        "settings.notif.tg_chat":               "Chat ID",
        "settings.notif.tg_hint":               "@BotFather to create a bot + grab token. DM the bot, then @userinfobot to get your chat ID.",
        "settings.notif.tg_err.required":       "Token + Chat ID required.",
        "settings.notif.tg_sending":            "Sending…",
        "settings.notif.tg_ok":                 "✓ Sent — check your chat.",
        "settings.notif.tg_err":                "✗ Failed — check token / chat ID.",
        "settings.notif.test_tg_body":          "🎉 Test from NoteNara — your Telegram setup works!",
        "settings.notif.discord":               "Discord",
        "settings.notif.dc_enable":             "Enable Discord webhook",
        "settings.notif.dc_url":                "Webhook URL",
        "settings.notif.dc_hint":               "Channel → Settings → Integrations → Webhooks → New Webhook → Copy URL.",
        "settings.notif.dc_err.required":       "Webhook URL required.",
        "settings.notif.dc_sending":            "Sending…",
        "settings.notif.dc_ok":                 "✓ Sent — check your channel.",
        "settings.notif.dc_err":                "✗ Failed — check webhook URL.",
        "settings.notif.test_dc_body":          "🎉 **Test from NoteNara** — your Discord webhook works!",

        # ----- settings: output tab -----
        "settings.output.folder":               "Transcript output folder",
        "settings.output.folder_hint":          "Relative paths resolve against the project root.",
        "settings.output.after":                "After-completion",
        "settings.output.auto_open":            "Auto-open Notion page in browser when done",
        "settings.output.auto_open_hint":       "When off, a clickable button appears in the main view so you can open the page manually.",
        "settings.output.lang":                 "Interface language",
        "settings.output.lang_hint":            "Changes the app UI + Notion page headings. Meeting summary itself still follows the audio language. Restart NoteNara to apply.",
        "settings.output.lang_en":              "English",
        "settings.output.lang_id":              "Bahasa Indonesia",

        # ----- Notion page headings (what shows on the published page) -----
        "notion.heading.summary":       "📋 Summary",
        "notion.heading.key_points":    "💬 Key Points",
        "notion.heading.action_items":  "✅ Action Items",
        "notion.heading.raw_transcript": "📝 Raw Transcript",

        # ----- LLM prompts -----
        "llm.system_prompt": (
            "You are a professional meeting notes assistant. Your job is to "
            "read a meeting transcript and produce a clean, structured "
            "summary. Always respond ONLY with valid JSON matching the "
            "requested schema — no markdown, no backticks, no commentary.\n\n"
            "IMPORTANT: write the summary, key_points, and action_items in "
            "the SAME LANGUAGE as the transcript. If the transcript is in "
            "Indonesian, respond in Indonesian. If it is in English, respond "
            "in English. Do not translate."
        ),
        "llm.user_template": (
            "Meeting topic: {materi}\n"
            "Project: {project}\n\n"
            "Transcript:\n{transcript}\n\n"
            "Task: analyse the transcript above and output a summary as JSON.\n\n"
            "Strict rules:\n"
            "1. key_points: array of STRING. Can be 2 to 15+ items — follow "
            "what the meeting actually covered. DO NOT force exactly 3.\n"
            "2. action_items: array of STRING (NOT object / dict). Each item "
            "is one sentence: 'Task description - PIC (if mentioned)'. "
            "Correct example: 'Draft the contract - Danar'. If there are no "
            "tasks, return an empty array [].\n"
            "3. summary: STRING, 3-5 sentences — what was discussed + "
            "outcome / conclusion.\n\n"
            "Match the language of the transcript (do not translate). "
            "Respond ONLY with valid JSON (no markdown, no backticks, no "
            "extra prose). Structure:\n"
            "{{\n"
            "  \"summary\": \"...\",\n"
            "  \"key_points\": [\"...\", \"...\"],\n"
            "  \"action_items\": [\"... - PIC\", \"...\"]\n"
            "}}"
        ),
        "llm.merge_prompt": (
            "Below are section-by-section summaries from one long meeting. "
            "Task: produce ONE final summary (3-5 sentences) that combines "
            "all sections into a coherent narrative.\n\n"
            "Write the final summary in the SAME LANGUAGE as the section "
            "summaries — do not translate.\n\n"
            "Section summaries:\n{partials}\n\n"
            "Respond ONLY with JSON (no markdown):\n"
            "{{\"summary\": \"...\"}}"
        ),
        "llm.placeholder.not_specified": "(not specified)",
        "llm.error.all_chunks_failed": (
            "[All chunks failed — try running again or switch to a larger "
            "model.]"
        ),
        "llm.error.invalid_json": (
            "[LLM failed to produce valid JSON — try running again, "
            "increase max_tokens, or switch to a larger model.]"
        ),

        # ----- months (used by Notion page title + recent list) -----
        "date.month_abbrs": "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec",
    },

    "id": {
        # ----- common buttons -----
        "btn.save":             "Simpan",
        "btn.cancel":           "Batal",
        "btn.back":              "Kembali",
        "btn.delete":           "Hapus",
        "btn.edit":             "Edit",
        "btn.add":              "Tambah",
        "btn.set_active":       "Jadikan Aktif",
        "btn.test_connection":  "Test koneksi",
        "btn.send_test":        "Kirim test",
        "btn.browse":           "Pilih folder…",
        "btn.copy_markdown":    "Salin markdown",
        "btn.copy_plain":       "Salin teks polos",
        "btn.copy_link":        "Salin link",
        "btn.view_log":         "Lihat log",
        "btn.send_to_notion":   "Kirim ke Notion  →",
        "btn.publish":          "Publish ke Notion",
        "btn.publishing":       "Mengirim…",
        "btn.open_in_notion":   "Buka di Notion  ↗",
        "btn.back_to_home":     "← Kembali ke beranda",
        "btn.start_transcription": "Mulai transkripsi  →",
        "btn.get_started":      "Mulai  →",
        "btn.skip":             "Lewati",
        "btn.add_workspace":    "+ Tambah workspace",

        # ----- app chrome -----
        "chrome.settings.title": "Pengaturan",

        # ----- main view -----
        "main.tagline":         "Drop recording — dapet ringkasan rapi dalam hitungan detik. Lokal & privat.",
        "main.dropzone.title":  "Drop recording",
        "main.dropzone.subtitle": "atau klik untuk pilih",
        "main.ornament.recent": "terakhir",
        "main.recent.empty":    "Belum ada transkripsi.",
        "main.recent.open":     "Buka",
        "main.file.remove":     "Hapus",
        "main.cancel_processing": "Batal",

        # ----- welcome view -----
        "welcome.welcome_to":   "Selamat datang di",
        "welcome.step1.title":  "Drop recording meeting kamu",
        "welcome.step1.desc":   "audio · video — mp4, mp3, wav, m4a, mov…",
        "welcome.step2.title":  "Review auto-summary",
        "welcome.step2.desc":   "edit apa pun sebelum di-publish",
        "welcome.step3.title":  "Salin — atau kirim ke Notion",
        "welcome.step3.desc":   "setup workspace ditanya pas dibutuhin",

        # ----- preview view -----
        "preview.title":            "Review",
        "preview.meta_format":      "{chars} char  ·  {kp} key points  ·  {ai} action items",
        "preview.truncated":        "terpotong",
        "preview.no_summary":       "Ringkasan tidak tersedia (LLM tidak terjangkau).",
        "preview.no_summary_hint":  "Transkrip tersimpan lokal. Buka Settings → AI model untuk perbaiki koneksi, lalu coba lagi.",
        "preview.ornament.summary": "ringkasan",
        "preview.ornament.key_points":   "key points · {n}",
        "preview.ornament.action_items": "action items · {n}",
        "preview.ornament.raw":     "raw transcript",
        "preview.raw.full_link":    "lengkap → {name}",

        # ----- markdown export -----
        "markdown.heading.summary":     "## Ringkasan",
        "markdown.heading.key_points":  "## Key Points",
        "markdown.heading.action_items": "## Action Items",

        # ----- notion setup view -----
        "notion_setup.title":       "Kirim ke Notion",
        "notion_setup.crumb":       "workspace · target · project · topik",
        "notion_setup.workspace":   "Workspace",
        "notion_setup.workspace_placeholder": "Pilih workspace…",
        "notion_setup.target_db":   "Database tujuan",
        "notion_setup.target_db_empty": "(belum ada database)",
        "notion_setup.project":     "Project   opsional",
        "notion_setup.project_none": "(tanpa project)",
        "notion_setup.topic":       "Topik / materi",
        "notion_setup.date":        "Tanggal meeting   YYYY-MM-DD",
        "notion_setup.date_invalid": "Format tanggal salah — pakai tanggal hari ini.",
        "notion_setup.preview_label": "PREVIEW JUDUL HALAMAN",
        "notion_setup.empty_title": "(judul kosong)",
        "notion_setup.publishing":  "Mengirim ke Notion…",
        "notion_setup.err.no_topic": "Topik / materi belum diisi.",
        "notion_setup.err.no_workspace": "Pilih workspace dulu.",
        "notion_setup.err.projects_fail": "Gagal ambil projects: {msg}",

        # ----- done view -----
        "done.title":               "Tersimpan di Notion",
        "done.meta_format":         "{kp} key points · {ai} action items",
        "done.page_title_label":    "JUDUL HALAMAN",

        # ----- file picker / dialogs -----
        "file_dialog.title":        "Pilih audio / video",
        "file_dialog.all_files":    "Semua file",
        "file_dialog.pick_output":  "Pilih folder output",

        # ----- phase chip / progress -----
        "phase.loading_services":   "Memuat services…",
        "phase.starting":            "Memulai…",
        "phase.loading_whisper":    "Memuat Whisper {name}…",
        "phase.loading_whisper_t":  "Memuat Whisper {name}… {sec}d",
        "phase.loading_whisper_hint": "Memuat Whisper {name}… {sec}d (cek GPU memory — tutup LM Studio?)",
        "phase.transcribing":       "Transkripsi… {pct:.0f}%",
        "phase.transcription_done": "Transkripsi selesai.",

        # ----- log widget -----
        "log.header":               "LOG",
        "log.stdout":               "STDOUT",
        "log.clear":                "bersihkan",
        "log.open":                 "buka log",
        "log.lines":                "{n} baris",
        "log.awaiting":             "menunggu input…",

        # ----- settings: sidebar tabs -----
        "settings.tab.notion":          "Notion",
        "settings.tab.ai":              "Model AI",
        "settings.tab.transcription":   "Transkripsi",
        "settings.tab.notifications":   "Notifikasi",
        "settings.tab.output":          "Output",

        # ----- settings: Notion tab -----
        "settings.notion.workspaces":   "Workspaces",
        "settings.notion.workspaces_hint": "Tiap workspace = satu integration token Notion + target DB-nya.",
        "settings.notion.empty":        "Belum ada workspace. Klik + Tambah untuk bikin.",
        "settings.notion.page_format":  "Format halaman",
        "settings.notion.page_format_hint": "Tampilan meeting page pas dipublish.",
        "settings.notion.page_icon":    "ICON HALAMAN",
        "settings.notion.title_format": "FORMAT JUDUL",
        "settings.notion.include_raw":  "Sertakan raw transcript (toggle collapse)",
        "settings.notion.include_raw_hint": "Off = halaman lebih ringan, transkrip tetep ke-save lokal sebagai .txt.",
        "settings.notion.active_dbs":   "Database workspace aktif",
        "settings.notion.active_dbs_hint": "Tempat meeting notes di-publish + sumber list project.",
        "settings.notion.target_db_label": "DATABASE TUJUAN  (catatan dibuat di sini)",
        "settings.notion.projects_db_label": "DATABASE PROJECTS  (opsional — sumber list project)",
        "settings.notion.projects_db_none": "(tanpa — cari di semua page)",
        "settings.notion.defaults":     "Default",
        "settings.notion.defaults_hint": "Pre-fill form publish biar tiap meeting lebih cepet.",
        "settings.notion.default_project": "PROJECT DEFAULT",
        "settings.notion.default_project_ask": "(tanya tiap kali)",
        "settings.notion.default_project_hint": "'(tanya tiap kali)' = pilih per meeting.",
        "settings.notion.auto_publish":     "Skip preview, auto-publish ke Notion",
        "settings.notion.auto_publish_hint": "One-click meeting → page. Lu percaya sama LLM.",
        "settings.notion.active":       "Workspace aktif",
        "settings.notion.test_hint":    "Klik 'Test koneksi' untuk verifikasi.",
        "settings.notion.no_active":    "Belum ada workspace aktif",
        "settings.notion.cant_delete_last": "Workspace terakhir gak bisa dihapus.",
        "settings.notion.test_ok":      "✓ Terkoneksi · {workspace} · bot: {bot}",
        "settings.notion.test_err":     "✗ {err}",
        "settings.notion.no_active_err": "Belum ada workspace aktif.",
        "settings.notion.token_missing": "Token kosong.",
        "settings.notion.testing":      "Mengetes…",
        "settings.notion.title_fmt.standard":   "Project — Materi — Tanggal",
        "settings.notion.title_fmt.simple":     "Materi — Tanggal",
        "settings.notion.title_fmt.date_first": "Tanggal · Materi",

        # ----- settings: workspace editor -----
        "ws_editor.title.add":          "Tambah workspace",
        "ws_editor.title.edit":         "Edit workspace — {slug}",
        "ws_editor.label":              "Label",
        "ws_editor.token":              "Integration token Notion",
        "ws_editor.link":               "🔗  notion.so/my-integrations",
        "ws_editor.test_fetch":         "Test & ambil databases",
        "ws_editor.target":             "Database tujuan — tempat meeting notes",
        "ws_editor.target_placeholder": "(test koneksi dulu)",
        "ws_editor.projects":           "Database projects — opsional",
        "ws_editor.projects_placeholder": "(tanpa — cari di semua page)",
        "ws_editor.schema":             "Mapping schema — auto-detect",
        "ws_editor.title_prop":         "JUDUL",
        "ws_editor.date_prop":          "TANGGAL",
        "ws_editor.err.token_first":    "Isi token dulu.",
        "ws_editor.err.required":       "Label dan token wajib diisi.",
        "ws_editor.err.pick_target":    "Pilih database tujuan.",
        "ws_editor.testing":            "Mengetes…",
        "ws_editor.test_ok":            "✓ {workspace} · {n} db",

        # ----- settings: AI / LLM tab -----
        "settings.ai.provider":         "Provider",
        "settings.ai.base_url":         "Base URL",
        "settings.ai.api_key":          "API key   untuk cloud provider aja",
        "settings.ai.model":            "Model",
        "settings.ai.temperature":      "Temperature (0-1)",
        "settings.ai.timeout":          "Timeout (detik)",
        "settings.ai.api_key_hint":     "API key: {hint}",
        "settings.ai.testing":          "Mengetes…",
        "settings.ai.test_ok":          "✓ Terkoneksi · {n} model",
        "settings.ai.test_err":         "✗ {err}",
        "settings.ai.no_models":        "Gak ada model chat (cuma embedding).",

        # ----- settings: Whisper tab -----
        "settings.whisper.model":               "Model",
        "settings.whisper.model_hint":          "Ukuran engine transkripsi. Lebih besar = lebih akurat tapi lebih lambat + makan GPU memory.",
        "settings.whisper.language":            "Bahasa audio",
        "settings.whisper.language_hint":       "Kasih tau Whisper bahasa meeting-nya. 'Auto-detect' nebak dari beberapa detik awal.",
        "settings.whisper.compute":             "Presisi angka",
        "settings.whisper.compute_hint":        "Seberapa presisi model itung. Presisi lebih rendah = lebih cepet, lebih hemat VRAM. 'Balanced' cocok buat kebanyakan GPU.",
        "settings.whisper.beam":                "Kualitas decode",
        "settings.whisper.beam_hint":           "Seberapa keras Whisper nyari transkripsi terbaik. 'Thorough' makan ~2× waktu vs 'Quick' tapi nangkep kata-kata yang lebih susah.",
        "settings.whisper.device":              "Hardware",
        "settings.whisper.device_hint":         "Pake GPU buat cepet, atau switch ke CPU kalau Whisper hang di 'Loading services…' (biasanya gara-gara LM Studio nahan VRAM lu). CPU auto-pake int8 precision.",
        "settings.whisper.vad":                 "Skip silence (recommended)",
        "settings.whisper.vad_hint":            "Hapus gap diem sebelum transkripsi — cegah model bikin frase repetitif pas silence.",

        # ----- settings: notifications tab -----
        "settings.notif.telegram":              "Telegram",
        "settings.notif.tg_enable":             "Aktifkan notifikasi Telegram",
        "settings.notif.tg_token":              "Bot token",
        "settings.notif.tg_chat":               "Chat ID",
        "settings.notif.tg_hint":               "@BotFather buat bikin bot + ambil token. DM bot-nya, terus @userinfobot buat dapet chat ID.",
        "settings.notif.tg_err.required":       "Token + Chat ID wajib.",
        "settings.notif.tg_sending":            "Mengirim…",
        "settings.notif.tg_ok":                 "✓ Terkirim — cek chat lu.",
        "settings.notif.tg_err":                "✗ Gagal — cek token / chat ID.",
        "settings.notif.test_tg_body":          "🎉 Test dari NoteNara — setup Telegram lu berhasil!",
        "settings.notif.discord":               "Discord",
        "settings.notif.dc_enable":             "Aktifkan webhook Discord",
        "settings.notif.dc_url":                "Webhook URL",
        "settings.notif.dc_hint":               "Channel → Settings → Integrations → Webhooks → New Webhook → Copy URL.",
        "settings.notif.dc_err.required":       "Webhook URL wajib.",
        "settings.notif.dc_sending":            "Mengirim…",
        "settings.notif.dc_ok":                 "✓ Terkirim — cek channel lu.",
        "settings.notif.dc_err":                "✗ Gagal — cek webhook URL.",
        "settings.notif.test_dc_body":          "🎉 **Test dari NoteNara** — webhook Discord lu berhasil!",

        # ----- settings: output tab -----
        "settings.output.folder":               "Folder output transcript",
        "settings.output.folder_hint":          "Path relatif di-resolve dari project root.",
        "settings.output.after":                "Setelah selesai",
        "settings.output.auto_open":            "Buka Notion page otomatis di browser pas selesai",
        "settings.output.auto_open_hint":       "Kalau off, tombol clickable muncul di main view biar lu bisa buka manual.",
        "settings.output.lang":                 "Bahasa interface",
        "settings.output.lang_hint":            "Ngubah UI app + heading Notion page. Ringkasan meeting tetep ngikut bahasa audio. Restart NoteNara biar berlaku.",
        "settings.output.lang_en":              "English",
        "settings.output.lang_id":              "Bahasa Indonesia",

        # ----- Notion page headings -----
        "notion.heading.summary":       "📋 Ringkasan",
        "notion.heading.key_points":    "💬 Inti Diskusi",
        "notion.heading.action_items":  "✅ Action Items",
        "notion.heading.raw_transcript": "📝 Raw Transcript",

        # ----- LLM prompts -----
        "llm.system_prompt": (
            "Kamu adalah notulen meeting profesional. Tugas kamu adalah "
            "membaca transcript meeting dan menghasilkan ringkasan yang "
            "rapi dan terstruktur. Selalu balas HANYA dengan JSON valid "
            "sesuai skema yang diminta — tanpa markdown, tanpa backtick, "
            "tanpa komentar.\n\n"
            "PENTING: tulis summary, key_points, dan action_items dalam "
            "BAHASA YANG SAMA dengan transcript. Kalau transcript Bahasa "
            "Indonesia, balas dalam Bahasa Indonesia. Kalau Bahasa "
            "Inggris, balas dalam Bahasa Inggris. Jangan diterjemahkan."
        ),
        "llm.user_template": (
            "Topik meeting: {materi}\n"
            "Project: {project}\n\n"
            "Transcript:\n{transcript}\n\n"
            "Tugas: analisis transcript di atas dan keluarkan ringkasan "
            "dalam JSON.\n\n"
            "Aturan strict:\n"
            "1. key_points: array of STRING. Bisa 2 sampai 15+ item — "
            "ikutin isi meeting. JANGAN dipaksa jadi 3.\n"
            "2. action_items: array of STRING (BUKAN object / dict). Tiap "
            "item berupa satu kalimat: 'Deskripsi task - PIC (kalau "
            "disebutkan)'. Contoh benar: 'Buat draft kontrak - Mas Danar'. "
            "Kalau gak ada task, kasih array kosong [].\n"
            "3. summary: STRING, 3-5 kalimat — apa yang dibahas + hasil / "
            "kesimpulan.\n\n"
            "Ikuti bahasa transcript (jangan diterjemahkan). Balas HANYA "
            "dengan JSON valid (tanpa markdown, tanpa backtick, tanpa "
            "prose tambahan). Struktur:\n"
            "{{\n"
            "  \"summary\": \"...\",\n"
            "  \"key_points\": [\"...\", \"...\"],\n"
            "  \"action_items\": [\"... - PIC\", \"...\"]\n"
            "}}"
        ),
        "llm.merge_prompt": (
            "Berikut ringkasan per-bagian dari satu meeting yang panjang. "
            "Tugas: buat SATU ringkasan akhir (3-5 kalimat) yang "
            "menggabungkan semuanya menjadi narasi koheren.\n\n"
            "Tulis ringkasan akhir dalam BAHASA YANG SAMA dengan "
            "ringkasan per-bagian — jangan diterjemahkan.\n\n"
            "Ringkasan per-bagian:\n{partials}\n\n"
            "Balas HANYA dengan JSON (tanpa markdown):\n"
            "{{\"summary\": \"...\"}}"
        ),
        "llm.placeholder.not_specified": "(tidak disebutkan)",
        "llm.error.all_chunks_failed": (
            "[Semua chunk gagal — coba run ulang atau pakai model lebih "
            "besar.]"
        ),
        "llm.error.invalid_json": (
            "[LLM gagal menghasilkan JSON valid — coba run ulang, "
            "tingkatkan max_tokens, atau pakai model lebih besar.]"
        ),

        # ----- months -----
        "date.month_abbrs": "Jan Feb Mar Apr Mei Jun Jul Agu Sep Okt Nov Des",
    },
}


def set_locale(lang: str) -> None:
    """Set the active language. Falls back to default if lang unknown."""
    global _current_lang
    _current_lang = lang if lang in STRINGS else _DEFAULT_LANG


def get_locale() -> str:
    return _current_lang


def supported_locales() -> list[str]:
    return list(STRINGS.keys())


def t(key: str, **kwargs: object) -> str:
    """Lookup ``key`` in active language. Falls back to ``en`` then key."""
    table = STRINGS.get(_current_lang, STRINGS[_DEFAULT_LANG])
    s = table.get(key) or STRINGS[_DEFAULT_LANG].get(key, key)
    if kwargs:
        try:
            return s.format(**kwargs)
        except (KeyError, IndexError):
            return s
    return s


def months() -> list[str]:
    """Twelve month abbreviations in active language."""
    return t("date.month_abbrs").split()
