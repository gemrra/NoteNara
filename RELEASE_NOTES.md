# NoteNara v2.1.0 — Windows bundle

A self-contained Windows build. **No Python install, no `pip`, no CUDA toolkit required** — just download, extract, and run.

## Download & run

1. Download `NoteNara-v2.1.0-win64.zip` below.
2. Extract it anywhere (e.g. `C:\NoteNara` or your Desktop).
3. Double-click **`NoteNara.exe`** inside the extracted folder.

That's it — the app launches. GPU transcription works out of the box if you have an NVIDIA card; otherwise switch to CPU in Settings → Transcription → Hardware.

> **Windows SmartScreen** may warn on first launch because the build isn't code-signed. Click **More info → Run anyway**.

## What's in the package

The download is ~1.3 GB zipped (~2.1 GB extracted) because it's fully self-contained — nothing gets installed on your system:

- **Embedded Python runtime** — no Python install needed.
- **Whisper engine** — faster-whisper + CTranslate2 (the speech-to-text backend).
- **NVIDIA CUDA runtime** — cublas + cuDNN DLLs (~1.9 GB of the size). This is what makes GPU transcription work **without installing the CUDA Toolkit**.
- **Media decoding** — PyAV / FFmpeg bindings for mp4 / mkv / mov / etc.
- **UI + integrations** — Notion, Telegram, Discord, and all 6 LLM provider adapters.

The Whisper model (~1.5 GB) is the only piece not bundled — it downloads on first transcription into a `models/` folder next to the app.

## What you still need to set up (one-time, ~5 minutes)

NoteNara orchestrates your own accounts — it doesn't ship with any:

- **An LLM** — pick one:
  - **Cloud (easiest):** get an API key from OpenAI, DeepSeek, Anthropic, or Google Gemini, and paste it in Settings → AI Model. DeepSeek is the cheapest (~$0.01 per meeting).
  - **Local (private, free):** install [LM Studio](https://lmstudio.ai), load a chat model (Qwen 2.5 7B Instruct recommended), click "Start Server".
- **Notion (optional)** — only if you want auto-publish. Create an integration at [notion.so/my-integrations](https://www.notion.so/my-integrations), share your target database with it, paste the token in Settings → Workspaces. If you just want a text summary, skip Notion and use **Save as .txt** instead.

## First transcription

The Whisper model (~1.5 GB) downloads automatically the first time you transcribe, into a `models/` folder next to the .exe. Subsequent runs are instant.

## Notes

- All your data (config, transcripts, logs, models) lives next to the .exe — nothing is written to AppData or the registry. Delete the folder to uninstall completely.
- Your config (API keys, Notion tokens) stays local in `meeting_app_config.json`.
- UI available in English and Bahasa Indonesia (Settings → Output → Interface language).
