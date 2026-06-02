# NoteNara

Local meeting transcription app for Windows. Drop an audio/video recording, get it auto-transcribed with **Whisper turbo** (CUDA or CPU), summarized by an LLM of your choice — local (**LM Studio**, **Ollama**) or cloud (**OpenAI**, **Anthropic**, **Gemini**, **DeepSeek**) — and auto-published to **Notion** as a structured meeting note with key points and action items.

**Local-first by default.** No API key required when using LM Studio. Your transcripts never leave your machine until you choose to publish them. Cloud LLMs are optional for deeper reasoning.

**Bilingual UI.** Switch between English and Bahasa Indonesia from Settings → Output. The LLM summary stays in the language of the audio regardless of UI choice.

---

## ✨ Features

- **Whisper turbo on CUDA** — transcribe a 1-hour meeting in ~3 minutes on a mid-range GPU. CPU fallback when no NVIDIA card is available.
- **6 LLM providers** — LM Studio, Ollama, OpenAI, Anthropic, Google Gemini, DeepSeek, or any Custom OpenAI-compatible endpoint.
- **Language-aware prompting** — the LLM keeps summary, key points, and action items in the same language as the transcript (Indonesian audio → Indonesian summary, English audio → English summary). No translation, no mismatched output.
- **Auto-publish to Notion** — fully structured page with summary, key points, action items, and an optional collapsed raw transcript block.
- **Save as `.txt`** — one-click export of the edited summary to a plain text file (opens in Notepad / your default editor). Use this when you don't need Notion.
- **Multi-workspace** — switch between Notion workspaces (e.g., Personal / Client A / Client B) without re-configuring.
- **Optional notifications** — push summaries to **Telegram** (bot) or **Discord** (webhook) when each meeting is finished.
- **Drag & drop UI** — not a technical tool; just drop a file. Smooth retro editorial design built with Tkinter + Pillow.
- **In-app log viewer** — daily rotating log file under `logs/` and a "View log" button in the app for quick triage.
- **Cancellable + retry-friendly** — the pipeline degrades gracefully (LLM unreachable? The transcript is still saved locally and can be retried).

---

## 📋 Prerequisites

| | |
|---|---|
| **OS** | Windows 10 / 11 (tested). Linux / macOS likely works but paths may need adjustment. |
| **Python** | 3.10+ (3.12 recommended). |
| **GPU** | NVIDIA with CUDA 12.x for Whisper turbo. If you don't have a GPU, switch to CPU in Settings → Transcription → Hardware. |
| **ffmpeg** | Required for video container support. Install and add to PATH. |
| **LM Studio** | https://lmstudio.ai — optional, only if you want to run the LLM locally. Load a chat model (Qwen 2.5 7B Instruct works well). |
| **Notion** | Create an integration at https://www.notion.so/my-integrations and share your target database with it. |

---

## 🚀 Installation

**Quick start (Windows):**

```powershell
git clone https://github.com/gemarafi66-svg/NoteNara.git
cd NoteNara
install_deps.bat
```

`install_deps.bat` checks that Python is available, creates a venv, and installs every dependency including the CUDA runtime libraries (`nvidia-cublas-cu12`, `nvidia-cudnn-cu12`). Total install ~2 GB; the script takes 5–10 minutes on a normal internet connection.

**Manual install (if you prefer):**

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Optional: build a standalone launcher

The default launcher is `NoteNara.bat`. To get a real `NoteNara.exe` with the proper taskbar icon and AppUserModelID grouping:

```powershell
pip install pyinstaller pywin32
python -m PyInstaller --onefile --windowed --icon=app\assets\NoteNara.ico --name=NoteNara --distpath=. --workpath=build --specpath=build --noconfirm launcher.py
Remove-Item build -Recurse -Force
python make-shortcut.py  # generates NoteNara.lnk with the AppUserModelID property set
```

---

## 🎬 First Run

```powershell
.\NoteNara.bat
```

Or double-click `NoteNara.exe` if you've built it.

On first launch the app will:
1. Detect that no config exists and show a welcome wizard.
2. Click "Add workspace →" to enter:
   - **Label** (workspace name, e.g., "Personal" / "Acme Client")
   - **Notion integration token** (from https://www.notion.so/my-integrations)
   - Click "Test & fetch databases" — the app will pull every database your integration has access to.
   - Pick a **Target database** (where meeting notes will be created).
   - Optionally pick a **Projects database** (if you keep a separate database for projects; otherwise the app will search across all pages).
3. Save and you're ready to go.

The Settings dialog (gear icon, top-right) lets you configure:
- **Workspaces** — add / edit / delete profiles, set the active one, configure page format and default project.
- **AI Model** — provider (LM Studio / Ollama / OpenAI / Anthropic / Gemini / DeepSeek / Custom), base URL, model, API key.
- **Transcription** — Whisper model size, audio language, compute precision, decode quality, GPU/CPU hardware.
- **Notifications** — Telegram bot and Discord webhook, with test-send buttons.
- **Output** — transcript output folder, auto-open Notion toggle, **interface language** (English / Bahasa Indonesia).

---

## 💡 How to use

1. Make sure your LLM provider is ready (LM Studio running on port 1234, or an API key configured in Settings).
2. Drag & drop a meeting recording onto the drop zone, or click to pick a file.
3. Click **Start transcription**. The progress bar updates per phase in real time.
4. When transcribe + summarize finishes, a **Review** page opens where you can edit the summary, key points, and action items.
5. From here you have a few options in the footer:
   - **Copy markdown** — copy the formatted summary to clipboard.
   - **Save as .txt** — write a plain text copy of the summary to your output folder and open it in Notepad / your default editor. Use this when you just want a file, no Notion.
   - **Send to Notion →** — fill in workspace, project, topic, and meeting date (auto-filled from the file's modification time), then **Publish**.

---

## 🛠 Troubleshooting

**"Library cublas64_12.dll is not found"**  
CUDA libraries are missing. Run `pip install nvidia-cublas-cu12 nvidia-cudnn-cu12`, or switch to CPU mode in Settings → Transcription → Hardware → "CPU".

**"Can't reach http://localhost:1234/v1"**  
LM Studio isn't running, or no model is loaded. Open LM Studio, pick a model, and click "Start Server".

**Whisper stuck at "Loading services…" for a long time**  
GPU VRAM contention with LM Studio (both apps competing for VRAM). Either close LM Studio before transcribing, or switch Whisper to CPU mode in Settings.

**"Failed to load · check token"**  
The Notion integration token is wrong, or the database hasn't been shared with the integration. In Notion: open the database → "..." → "Add connections" → pick your integration.

**"No chat-capable models found (only embeddings)"**  
LM Studio only has an embedding model loaded. Load a chat model (search for Qwen 2.5 or Llama 3.2 in LM Studio).

**Looping phrase hallucination (e.g., "Tengah Tengah Tengah")**  
v2 disables `condition_on_previous_text` and tunes VAD to prevent this. If it still happens, try setting Decode quality to "Thorough" in Settings → Transcription.

**Long meeting (>1 hour) — LLM summary gets cut off**  
Map-reduce chunking kicks in automatically for long transcripts. If you still see truncation, increase the LM Studio context length to 32768+, or switch to DeepSeek / Anthropic (128K+ context).

**Taskbar icon reverts to the Python feather after pinning**  
Use `NoteNara.lnk` (not the `.exe` directly) to pin to the taskbar. The shortcut has the AppUserModelID property set so Windows keeps the NoteNara icon consistent.

---

## 📦 File layout

```
NoteNara/
├── meeting_app.py                # entrypoint (thin)
├── launcher.py                   # source for NoteNara.exe (PyInstaller)
├── make-shortcut.py              # generates NoteNara.lnk with AppUserModelID
├── meeting_app_config.json       # your config (gitignored — contains tokens!)
├── meeting_app_config.example.json
├── requirements.txt
├── NoteNara.bat                  # debug launcher (console visible)
├── install_deps.bat
├── app/
│   ├── config.py                 # v2 schema + migration
│   ├── constants.py              # paths, palette
│   ├── i18n.py                   # EN / ID translation strings
│   ├── pipeline.py               # orchestrator
│   ├── assets/                   # logo PNGs, .ico, SVG sources
│   ├── services/
│   │   ├── whisper.py            # cached model, VAD-tuned
│   │   ├── llm.py                # multi-provider (OpenAI / Anthropic / Gemini / DeepSeek)
│   │   ├── notion.py             # workspace + page client
│   │   ├── telegram.py           # bot notifications
│   │   └── discord.py            # webhook notifications
│   └── ui/
│       ├── app.py                # main App (chrome + views)
│       ├── widgets.py            # ProgressBar, PhaseChip, TerminalLog
│       ├── smooth.py             # PIL-rendered widgets (BrandLogo, SmoothCard, RoundedButton, ...)
│       ├── retro.py              # mockup-faithful widgets (RetroDropZone, FileCard, RecentList)
│       └── settings.py           # tabbed settings dialog
├── input/                        # your media files (gitignored)
├── output/                       # generated transcripts (gitignored)
├── logs/                         # daily rotating logs (gitignored)
└── models/                       # Whisper model cache (gitignored)
```

---

## 🔧 Tech stack

- **faster-whisper** 1.2.1 — Whisper inference (CTranslate2)
- **tkinterdnd2** — drag & drop in Tk
- **Pillow** — PIL rendering for smooth antialiased widgets
- **requests** — HTTP only; no SDK bloat
- LM Studio / Ollama / OpenAI / DeepSeek / Custom expose an **OpenAI-compatible API** — a single client handles all of them
- Anthropic and Gemini have native adapters with their own request schemas
- Notion **REST API v1** (Notion-Version: 2022-06-28)
- Telegram **Bot API** + Discord **Webhooks**

No heavy non-ML dependencies. The project is ~3k lines of Python plus a venv that's mostly NVIDIA CUDA DLLs.

---

## 📄 License

MIT — see [LICENSE](LICENSE). You're free to use, modify, and redistribute, including commercially, as long as the copyright notice stays in the source. No warranty.
