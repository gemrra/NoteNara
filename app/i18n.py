"""Centralised i18n strings for NoteNara.

Two languages are supported: ``en`` (default) and ``id``. Callers use
``t("section.key")`` to look up the active-language string; all strings live
in a single dict so adding a new language is one entry away.

Locale is set once at app startup from ``cfg['language']`` via
``set_locale()``. The UI exposes a dropdown that updates the config — change
takes effect on next app restart so we don't have to rebuild already-rendered
widgets.

Why a flat dict instead of gettext/Babel:
- Project is small (~30 user-facing strings), gettext infra overkill
- Tk widgets read strings at construction; rebuilding the tree on locale
  change is more code than just asking the user to restart
- Easy to grep / diff strings across languages when there are only two
"""
from __future__ import annotations

_DEFAULT_LANG = "en"
_current_lang = _DEFAULT_LANG


# ---------------------------------------------------------------------------
# String table
# ---------------------------------------------------------------------------

STRINGS: dict[str, dict[str, str]] = {
    "en": {
        # ----- App UI -----
        "file_dialog.title":            "Choose audio / video",
        "file_dialog.all_files":        "All files",
        "preview.ornament.summary":     "summary",
        "preview.ornament.key_points":  "key points · {n}",
        "preview.ornament.action_items": "action items · {n}",
        "preview.ornament.raw":         "raw transcript",
        "markdown.heading.summary":     "## Summary",
        "markdown.heading.key_points":  "## Key points",
        "markdown.heading.action_items": "## Action items",
        "notion_setup.label.topic":     "Topic",
        "notion_setup.error.no_topic":  "Topic is required.",
        "notion_setup.error.no_workspace": "Choose a workspace first.",

        # ----- Notion page headings -----
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
            "3. summary: STRING, 3-5 sentences — what was discussed + outcome "
            "/ conclusion.\n\n"
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
            "[LLM failed to produce valid JSON — try running again, increase "
            "max_tokens, or switch to a larger model.]"
        ),

        # ----- Date / months -----
        "date.month_abbrs": "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec",
    },

    "id": {
        # ----- App UI -----
        "file_dialog.title":            "Pilih audio / video",
        "file_dialog.all_files":        "Semua file",
        "preview.ornament.summary":     "ringkasan",
        "preview.ornament.key_points":  "key points · {n}",
        "preview.ornament.action_items": "action items · {n}",
        "preview.ornament.raw":         "raw transcript",
        "markdown.heading.summary":     "## Ringkasan",
        "markdown.heading.key_points":  "## Key points",
        "markdown.heading.action_items": "## Action items",
        "notion_setup.label.topic":     "Topik / materi",
        "notion_setup.error.no_topic":  "Topik / materi belum diisi.",
        "notion_setup.error.no_workspace": "Pilih workspace dulu.",

        # ----- Notion page headings -----
        "notion.heading.summary":       "📋 Ringkasan",
        "notion.heading.key_points":    "💬 Inti Diskusi",
        "notion.heading.action_items":  "✅ Action Items",
        "notion.heading.raw_transcript": "📝 Raw Transcript",

        # ----- LLM prompts -----
        "llm.system_prompt": (
            "Kamu adalah notulen meeting profesional. Tugas kamu adalah "
            "membaca transcript meeting dan menghasilkan ringkasan yang rapi "
            "dan terstruktur. Selalu balas HANYA dengan JSON valid sesuai "
            "skema yang diminta — tanpa markdown, tanpa backtick, tanpa "
            "komentar.\n\n"
            "PENTING: tulis summary, key_points, dan action_items dalam "
            "BAHASA YANG SAMA dengan transcript. Kalau transcript Bahasa "
            "Indonesia, balas dalam Bahasa Indonesia. Kalau Bahasa Inggris, "
            "balas dalam Bahasa Inggris. Jangan diterjemahkan."
        ),
        "llm.user_template": (
            "Topik meeting: {materi}\n"
            "Project: {project}\n\n"
            "Transcript:\n{transcript}\n\n"
            "Tugas: analisis transcript di atas dan keluarkan ringkasan "
            "dalam JSON.\n\n"
            "Aturan strict:\n"
            "1. key_points: array of STRING. Bisa 2 sampai 15+ item — ikutin "
            "isi meeting. JANGAN dipaksa jadi 3.\n"
            "2. action_items: array of STRING (BUKAN object / dict). Tiap "
            "item berupa satu kalimat: 'Deskripsi task - PIC (kalau "
            "disebutkan)'. Contoh benar: 'Buat draft kontrak - Mas Danar'. "
            "Kalau gak ada task, kasih array kosong [].\n"
            "3. summary: STRING, 3-5 kalimat — apa yang dibahas + hasil / "
            "kesimpulan.\n\n"
            "Ikuti bahasa transcript (jangan diterjemahkan). Balas HANYA "
            "dengan JSON valid (tanpa markdown, tanpa backtick, tanpa prose "
            "tambahan). Struktur:\n"
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
            "Tulis ringkasan akhir dalam BAHASA YANG SAMA dengan ringkasan "
            "per-bagian — jangan diterjemahkan.\n\n"
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
            "[LLM gagal menghasilkan JSON valid — coba run ulang, tingkatkan "
            "max_tokens, atau pakai model lebih besar.]"
        ),

        # ----- Date / months -----
        "date.month_abbrs": "Jan Feb Mar Apr Mei Jun Jul Agu Sep Okt Nov Des",
    },
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def set_locale(lang: str) -> None:
    """Set the active language. Falls back to default if lang unknown.

    Call this once at startup after loading the config. Changing it later
    works but already-built Tk widgets won't update — restart needed for
    a clean swap.
    """
    global _current_lang
    _current_lang = lang if lang in STRINGS else _DEFAULT_LANG


def get_locale() -> str:
    return _current_lang


def supported_locales() -> list[str]:
    return list(STRINGS.keys())


def t(key: str, **kwargs: object) -> str:
    """Lookup ``key`` in the active language. Falls back to ``en`` then key.

    Supports ``str.format`` substitution: ``t("preview.ornament.key_points", n=5)``.
    """
    table = STRINGS.get(_current_lang, STRINGS[_DEFAULT_LANG])
    s = table.get(key) or STRINGS[_DEFAULT_LANG].get(key, key)
    if kwargs:
        try:
            return s.format(**kwargs)
        except (KeyError, IndexError):
            return s
    return s


def months() -> list[str]:
    """Twelve month abbreviations in the active language."""
    return t("date.month_abbrs").split()
