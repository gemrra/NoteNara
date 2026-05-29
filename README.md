# NoteNara

Local meeting transcription app untuk Windows. Drop audio/video meeting, otomatis di-transcribe pakai **Whisper turbo** (CUDA atau CPU), di-summarize sama LLM (lokal lewat **LM Studio**/**Ollama** atau cloud — **OpenAI**, **Anthropic**, **Gemini**, **DeepSeek**), terus auto-publish ke **Notion** sebagai meeting notes lengkap dengan key points + action items.

**Local-first by default.** Gak butuh API key kalo pakai LM Studio. Transcript kamu gak keluar dari mesin sampai kamu sendiri yang publish ke Notion. Cloud LLM optional buat reasoning yang lebih dalam.

---

## ✨ Features

- **Whisper turbo on CUDA** — transcribe meeting 1 jam dalam ~3 menit di GPU mid-range. CPU fallback otomatis kalo gak ada NVIDIA.
- **6 LLM providers** — LM Studio, Ollama, OpenAI, Anthropic, Google Gemini, DeepSeek, atau Custom OpenAI-compatible endpoint
- **Indonesian-aware prompt** — summary, key points, action items keluar dalam bahasa Indonesia
- **Auto-publish Notion** — meeting notes lengkap (ringkasan, key points, action items, raw transcript di toggle)
- **Multi-workspace** — switch antara Notion workspace (Personal / Client A / Client B) tanpa setup ulang
- **Optional notifications** — kirim summary ke **Telegram** (bot) atau **Discord** (webhook) pas meeting kelar
- **Drag & drop UI** — bukan teknikal tool, tinggal drop file. Smooth retro editorial style.
- **In-app log viewer** — daily rotating log file di `logs/`, tombol "View log" di app
- **Cancellable + retry-friendly** — pipeline graceful kalo ada step yang gagal (LLM down? transcript tetep ke-save lokal)

---

## 📋 Prerequisites

| | |
|---|---|
| **OS** | Windows 10/11 (tested) — Linux/Mac probably works, paths perlu adjustment |
| **Python** | 3.10+ (3.12 recommended) |
| **GPU** | NVIDIA dengan CUDA 12.x untuk Whisper turbo. Kalo gak ada GPU, switch ke CPU di Settings → Transcription → Hardware. |
| **ffmpeg** | Buat video container support — install dan add ke PATH |
| **LM Studio** | https://lmstudio.ai — opsional, kalo mau LLM lokal. Load satu chat model (Qwen 2.5 7B Instruct recommended). |
| **Notion** | Bikin integration di https://www.notion.so/my-integrations dan share database ke integration tsb |

---

## 🚀 Installation

```powershell
git clone https://github.com/gemarafi66-svg/NoteNara.git
cd NoteNara

python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

`requirements.txt` udah include `nvidia-cublas-cu12` + `nvidia-cudnn-cu12` jadi CUDA langsung jalan. Total install size ~2 GB.

### Optional: build standalone launcher

Default launcher adalah `NoteNara.bat`. Buat dapet `NoteNara.exe` dengan icon proper di taskbar:

```powershell
pip install pyinstaller pywin32
python -m PyInstaller --onefile --windowed --icon=app\assets\NoteNara.ico --name=NoteNara --distpath=. --workpath=build --specpath=build --noconfirm launcher.py
Remove-Item build -Recurse -Force
python make-shortcut.py  # generates NoteNara.lnk with proper AppUserModelID
```

---

## 🎬 First Run

```powershell
.\NoteNara.bat
```

Atau dobel-klik `NoteNara.exe` kalo udah di-build.

Pas pertama dibuka, app bakal:
1. Detect kalo belum ada config → munculin wizard welcome screen
2. Klik "Add workspace →" buat input:
   - **Label** (nama workspace, misal "Personal" / "Acme Client")
   - **Notion integration token** (dari https://www.notion.so/my-integrations)
   - Klik "Test & fetch databases" → bakal nge-pull list semua DB yang share ke integration kamu
   - Pilih **Target database** (DB tempat meeting notes akan dibuat)
   - Optionally pilih **Projects database** (kalo punya DB khusus list project, kalo gak — app bakal search all pages)
3. Save → langsung bisa pakai

Settings (gear icon, top-right) buat ngubah:
- **Workspaces** — add/edit/delete profile, set active, page format, default project
- **AI Model** — provider (LM Studio/Ollama/OpenAI/Anthropic/Gemini/DeepSeek/Custom), base URL, model, API key
- **Transcription** — Whisper model size, bahasa, compute precision, decode quality, GPU/CPU hardware
- **Notifications** — Telegram bot + Discord webhook, dengan test send button
- **Output** — folder transcript file, auto-open Notion toggle

---

## 💡 How to use

1. Pastiin LLM provider lu siap (LM Studio jalan di port 1234, atau API key set di Settings)
2. Drag & drop video/audio meeting ke drop zone, atau klik pilih file
3. Klik **Start transcription** → progress bar update real-time per fase
4. Setelah transcribe + summarize selesai → **Review page** muncul, lu bisa edit summary/key points/action items
5. Klik **Send to Notion** → pilih workspace, project, topic, **meeting date** (auto-detect dari file mtime)
6. Klik **Publish** → done, halaman Notion otomatis kebuka

---

## 🛠 Troubleshooting

**"Library cublas64_12.dll is not found"**
CUDA libraries belum installed. Run `pip install nvidia-cublas-cu12 nvidia-cudnn-cu12`. Atau switch ke CPU mode di Settings → Transcription → Hardware → "CPU".

**"Can't reach http://localhost:1234/v1"**
LM Studio belum jalan, atau model belum di-load. Buka LM Studio, pilih model, klik "Start Server".

**Whisper stuck di "Loading services…" lama banget**
GPU VRAM contention sama LM Studio (sama-sama rebutan VRAM). Solusi: close LM Studio dulu sebelum transcribe, atau switch Whisper ke CPU mode di Settings.

**"Failed to load · check token"**
Notion integration token salah, atau database belum di-share ke integration. Di Notion: buka database → "..." → "Add connections" → pilih integration kamu.

**"No chat-capable models found (only embeddings)"**
LM Studio cuma punya embedding model loaded. Load chat model (cari Qwen 2.5 / Llama 3.2 di LM Studio search).

**"Tengah Tengah Tengah" hallucination muncul lagi**
v2 udah pake `condition_on_previous_text=False` plus VAD tuning. Kalo masih muncul, di Settings → Transcription → Decode quality coba ganti ke "Thorough".

**Long meeting (>1 jam) — LLM summary dipotong**
Map-reduce chunking otomatis aktif buat transcript panjang. Kalo masih kepotong, naikin LM Studio context length ke 32768+, atau pake DeepSeek/Anthropic yang max context-nya 128K+.

**Taskbar icon balik ke Python feather setelah pin**
Use `NoteNara.lnk` (bukan .exe langsung) buat pin ke taskbar. .lnk udah punya `AppUserModelID` property yang bikin Windows konsisten pake icon NoteNara.

---

## 📦 File layout

```
NoteNara/
├── meeting_app.py                # entrypoint (thin)
├── launcher.py                   # source for NoteNara.exe (PyInstaller)
├── make-shortcut.py              # generates NoteNara.lnk with AppUserModelID
├── meeting_app_config.json       # your config (gitignored — has tokens!)
├── meeting_app_config.example.json
├── requirements.txt
├── NoteNara.bat                  # debug launcher (console visible)
├── install_deps.bat
├── app/
│   ├── config.py                 # v2 schema + migration
│   ├── constants.py              # paths, palette
│   ├── pipeline.py               # orchestrator
│   ├── assets/                   # logo PNGs, ico, SVG sources
│   ├── services/
│   │   ├── whisper.py            # cached model, VAD-tuned
│   │   ├── llm.py                # multi-provider (OpenAI/Anthropic/Gemini/DeepSeek)
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
- LM Studio / Ollama / OpenAI / DeepSeek / Custom expose **OpenAI-compatible API** — one client handles them
- Anthropic + Gemini have native adapters with their own request schemas
- Notion **REST API v1** (Notion-Version: 2022-06-28)
- Telegram **Bot API** + Discord **Webhooks**

No heavy non-ML deps. The whole project is ~3k lines of Python + a venv yang mostly nvidia CUDA DLLs.
