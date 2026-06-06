"""Meeting transcription pipeline.

Chains the four services into the v1 user-flow without n8n:

    file → Whisper → save local copy → LLM summarise
                                       → Notion page
                                       → Telegram notify (optional)

Each step:
  * Updates a progress bar (0-100 across the whole pipeline)
  * Emits log lines via on_log(msg, kind)
  * Is cancellable via the shared threading.Event
  * Degrades gracefully — a missing LLM means we keep the local transcript
    rather than failing the whole run.
"""

from __future__ import annotations

import os
import threading
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .services.llm import LLMClient, SummaryResult
from .services.notion import (
    NotionClient, NotionError, CreatedPage,
    format_page_title, today_iso,
)
from .services.telegram import TelegramClient
from .services.discord import DiscordClient
from .services.whisper import WhisperService, TranscriptionCancelled, TranscriptResult


# Pipeline progress allocation — sums to 100.
PHASE_WEIGHTS = {
    "transcribe": 70,
    "save_local": 2,
    "summarize":  18,
    "notion":     7,
    "telegram":   3,
}


LogFn = Callable[[str, str], None]                 # (msg, kind)
ProgressFn = Callable[[float, str], None]          # (percent 0-100, phase label)


@dataclass
class PipelineResult:
    transcript_text: str
    transcript_path: Path
    summary: Optional[SummaryResult] = None
    notion_page: Optional[CreatedPage] = None
    telegram_sent: bool = False
    # Cumulative degradations — used by the UI to surface warnings instead of
    # claiming success when half the steps fell through.
    warnings: list[str] = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


@dataclass
class PipelineInputs:
    file_path: Path
    project: str
    materi: str
    target_db_id: str
    schema: dict[str, str]
    # User-overridable meeting date in ISO format (YYYY-MM-DD). When None,
    # the pipeline falls back to today() at publish time — preserves old
    # behaviour for callers that don't set it.
    date_iso: Optional[str] = None


class MeetingPipeline:
    """Orchestrates a single transcription run.

    A pipeline instance is **stateless across runs** — construct fresh services
    once at app startup, then call .run(...) per meeting. The Whisper service
    keeps its model loaded across calls (that's the whole point of caching it).
    """

    def __init__(
        self,
        whisper: WhisperService,
        llm: LLMClient,
        notion: NotionClient,
        telegram: TelegramClient,
        output_dir: Path,
        discord: Optional["DiscordClient"] = None,
    ):
        self.whisper = whisper
        self.llm = llm
        self.notion = notion
        self.telegram = telegram
        self.discord = discord  # optional; constructed default-disabled if None
        self.output_dir = output_dir

    def run(
        self,
        inputs: PipelineInputs,
        on_progress: Optional[ProgressFn] = None,
        on_log: Optional[LogFn] = None,
        cancel_event: Optional[threading.Event] = None,
    ) -> PipelineResult:
        log = on_log or (lambda m, k: None)
        progress = _make_phase_progress(on_progress, PHASE_WEIGHTS)
        cancel = cancel_event or threading.Event()

        # ----- 1. Transcribe -----
        progress.start("transcribe", "Loading model…")
        log(f"Transcribing → {inputs.file_path.name}", "info")
        transcript = self.whisper.transcribe(
            inputs.file_path,
            on_progress=lambda pct, phase: progress.update("transcribe", pct, phase),
            cancel_event=cancel,
        )
        log(
            f"Transcript ready · {len(transcript.text)} chars · "
            f"{transcript.language} ({transcript.language_probability:.0%})",
            "ok",
        )
        progress.complete("transcribe")
        _check_cancel(cancel)

        # ----- 2. Save local copy -----
        progress.start("save_local", "Saving local copy…")
        transcript_path = self._save_transcript(inputs.file_path, transcript)
        log(f"Saved local copy → {transcript_path.name}", "info")
        progress.complete("save_local")
        _check_cancel(cancel)

        result = PipelineResult(
            transcript_text=transcript.text,
            transcript_path=transcript_path,
        )

        return self._publish_phases(
            transcript_text=transcript.text,
            inputs=inputs,
            result=result,
            progress=progress,
            log=log,
            cancel=cancel,
        )

    # ----------------------------------------------------------------
    # New v2-flow methods: split into transcribe-only and publish-only so
    # the UI can show a preview between the two stages.
    # ----------------------------------------------------------------

    def transcribe_and_summarize(
        self,
        file_path: Path,
        materi_hint: str = "",
        on_progress: Optional[ProgressFn] = None,
        on_log: Optional[LogFn] = None,
        cancel_event: Optional[threading.Event] = None,
    ) -> dict:
        """Run Whisper + save local + LLM summarise. Skip Notion/Telegram.

        Returns a dict with: transcript_text, transcript_path, summary, warnings.
        summary may be None if the LLM was unavailable — caller decides what
        to do (caller usually shows the local transcript anyway).
        """
        log = on_log or (lambda m, k: None)
        # Reweight phases since publish steps are skipped.
        weights = {"transcribe": 78, "save_local": 2, "summarize": 20}
        progress = _make_phase_progress(on_progress, weights)
        cancel = cancel_event or threading.Event()
        warnings: list[str] = []

        # 1. Transcribe
        progress.start("transcribe", "Loading model…")
        log(f"Transcribing → {file_path.name}", "info")
        transcript = self.whisper.transcribe(
            file_path,
            on_progress=lambda pct, phase: progress.update("transcribe", pct, phase),
            cancel_event=cancel,
        )
        log(
            f"Transcript ready · {len(transcript.text)} chars · "
            f"{transcript.language} ({transcript.language_probability:.0%})",
            "ok",
        )
        progress.complete("transcribe")
        _check_cancel(cancel)

        # 2. Save local
        progress.start("save_local", "Saving local copy…")
        transcript_path = self._save_transcript(file_path, transcript)
        log(f"Saved local copy → {transcript_path.name}", "info")
        progress.complete("save_local")
        _check_cancel(cancel)

        # 2b. Empty transcript guard — if Whisper produced no text there is
        # nothing to summarise. This is almost always a media problem (no
        # audio track / silent recording / all-silence VAD), NOT an LLM
        # problem. Surface it clearly instead of calling the LLM with an
        # empty prompt and reporting a misleading "LLM unreachable".
        if not transcript.text.strip():
            msg = ("No speech found in the audio — the recording may have no "
                   "audio track, be silent, or contain only noise/music. "
                   "Check that the file actually has someone speaking.")
            log(msg, "warn")
            warnings.append(msg)
            progress.start("summarize", "No speech detected")
            progress.complete("summarize")
            return {
                "transcript_text": transcript.text,
                "transcript_path": transcript_path,
                "summary": None,
                "warnings": warnings,
                "empty_transcript": True,
            }

        # 3. Summarise (or skip gracefully if LLM is down)
        summary = None
        try:
            model = self.llm.resolve_model()
            log(f"Asking LLM ({model})…", "info")
        except Exception as e:
            msg = f"LLM unavailable · {e}"
            log(msg, "err")
            warnings.append(msg)
            progress.start("summarize", "Skipping summary (LLM down)")
            progress.complete("summarize")
            return {
                "transcript_text": transcript.text,
                "transcript_path": transcript_path,
                "summary": None,
                "warnings": warnings,
            }

        progress.start("summarize", "Summarising…")
        try:
            summary = self.llm.summarize_transcript(
                transcript=transcript.text,
                materi=materi_hint,
                project="",
                on_log=log,
            )
            log(f"Summary ready · {len(summary.key_points)} points · "
                f"{len(summary.action_items)} actions", "ok")
        except Exception as e:
            msg = f"LLM summarisation failed · {e}"
            log(msg, "err")
            warnings.append(msg)
        progress.complete("summarize")

        return {
            "transcript_text": transcript.text,
            "transcript_path": transcript_path,
            "summary": summary,
            "warnings": warnings,
        }

    def publish_to_notion(
        self,
        transcript_text: str,
        summary: SummaryResult,
        inputs: PipelineInputs,
        on_progress: Optional[ProgressFn] = None,
        on_log: Optional[LogFn] = None,
    ) -> dict:
        """Take an already-computed summary (possibly edited) and push to Notion + Telegram.

        Returns: notion_page (CreatedPage or None), telegram_sent (bool), warnings (list[str]).
        """
        log = on_log or (lambda m, k: None)
        weights = {"notion": 75, "telegram": 25}
        progress = _make_phase_progress(on_progress, weights)

        # Use a throwaway result object to reuse the existing safe helpers.
        result = PipelineResult(transcript_text=transcript_text, transcript_path=None)
        result.summary = summary

        progress.start("notion", "Creating Notion page…")
        page = self._create_notion_page_safely(transcript_text, summary, inputs,
                                                  log, result)
        result.notion_page = page
        progress.complete("notion")

        progress.start("telegram", "Notifying Telegram…")
        telegram_sent = self._notify_telegram_safely(page, summary, inputs, log)
        progress.complete("telegram")

        return {
            "notion_page": page,
            "telegram_sent": telegram_sent,
            "warnings": result.warnings,
        }

    def publish_existing_transcript(
        self,
        transcript_text: str,
        transcript_path: Path,
        inputs: PipelineInputs,
        on_progress: Optional[ProgressFn] = None,
        on_log: Optional[LogFn] = None,
        cancel_event: Optional[threading.Event] = None,
    ) -> PipelineResult:
        """Retry the LLM → Notion → Telegram steps without re-transcribing.

        Used by the Resend button when transcript is already saved on disk but
        a downstream step (most commonly LLM timeout) failed on the first run.
        Progress is rescaled to 100% across just the publish phases so the bar
        still fills the full width.
        """
        log = on_log or (lambda m, k: None)
        # Rescale progress so publish phases alone sum to 100.
        publish_weights = {"summarize": 65, "notion": 25, "telegram": 10}
        progress = _make_phase_progress(on_progress, publish_weights)
        cancel = cancel_event or threading.Event()

        result = PipelineResult(
            transcript_text=transcript_text,
            transcript_path=transcript_path,
        )
        log(f"Resending → {transcript_path.name}", "info")
        return self._publish_phases(
            transcript_text=transcript_text,
            inputs=inputs,
            result=result,
            progress=progress,
            log=log,
            cancel=cancel,
        )

    def _publish_phases(
        self,
        transcript_text: str,
        inputs: PipelineInputs,
        result: PipelineResult,
        progress: "_make_phase_progress",
        log: LogFn,
        cancel: threading.Event,
    ) -> PipelineResult:
        """Steps 3-5 of the pipeline: summarize → notion → telegram."""

        # ----- 3. Summarize via LLM -----
        # Log which model was actually picked so users can tell whether 'auto'
        # selected the small chat model or e.g. the 35B variant.
        try:
            model = self.llm.resolve_model()
            log(f"Asking LLM ({model})…", "info")
        except Exception as e:
            log(f"LLM unavailable · {e}", "err")
            model = None

        progress.start("summarize", "Asking LLM for summary…")
        summary = (self._summarize_safely(transcript_text, inputs, log, result)
                    if model is not None else None)
        result.summary = summary
        progress.complete("summarize")
        _check_cancel(cancel)

        # ----- 4. Create Notion page -----
        progress.start("notion", "Creating Notion page…")
        page = self._create_notion_page_safely(transcript_text, summary, inputs, log, result)
        result.notion_page = page
        progress.complete("notion")
        _check_cancel(cancel)

        # ----- 5. Telegram notify -----
        progress.start("telegram", "Notifying Telegram…")
        result.telegram_sent = self._notify_telegram_safely(
            page, summary, inputs, log)
        progress.complete("telegram")

        return result

    # ---------- step helpers ----------

    def _save_transcript(self, file_path: Path, transcript: TranscriptResult) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        base = file_path.stem
        out_path = self.output_dir / f"{base}_transcript.txt"
        # Paragraph-formatted version, with timestamps for the longer-form view.
        paragraphs = transcript.to_paragraphs(paragraph_gap_s=2.0)
        out_path.write_text("\n\n".join(paragraphs), encoding="utf-8")
        return out_path

    def _summarize_safely(
        self,
        transcript_text: str,
        inputs: PipelineInputs,
        log: LogFn,
        result: PipelineResult,
    ) -> Optional[SummaryResult]:
        try:
            summary = self.llm.summarize_transcript(
                transcript=transcript_text,
                materi=inputs.materi,
                project=inputs.project,
                on_log=log,
            )
            log(
                f"Summary ready · {len(summary.key_points)} key points · "
                f"{len(summary.action_items)} action items",
                "ok",
            )
            if summary.truncated:
                msg = "LLM input was truncated — transcript exceeded max_chars"
                log(msg, "warn")
                result.warnings.append(msg)
            return summary
        except Exception as e:
            msg = f"LLM summarisation failed · {e}"
            log(msg, "err")
            result.warnings.append(msg)
            return None

    def _create_notion_page_safely(
        self,
        transcript_text: str,
        summary: Optional[SummaryResult],
        inputs: PipelineInputs,
        log: LogFn,
        result: PipelineResult,
    ) -> Optional[CreatedPage]:
        if summary is None:
            msg = "Skipping Notion — no summary to publish."
            log(msg, "warn")
            result.warnings.append(msg)
            return None
        if not inputs.target_db_id:
            msg = "Skipping Notion — no target database configured."
            log(msg, "warn")
            result.warnings.append(msg)
            return None

        date_iso = inputs.date_iso or today_iso()
        title = format_page_title(inputs.project, inputs.materi, date_iso)
        try:
            page = self.notion.create_meeting_page(
                db_id=inputs.target_db_id,
                schema=inputs.schema,
                title=title,
                date_iso=date_iso,
                summary=summary.summary,
                key_points=summary.key_points,
                action_items=summary.action_items,
                transcript=transcript_text,
            )
            log(f"Notion page created → {page.url}", "ok")
            return page
        except NotionError as e:
            msg = f"Notion error · {e}"
            log(msg, "err")
            result.warnings.append(msg)
            return None
        except Exception as e:
            msg = f"Notion publish failed · {e}"
            log(msg, "err")
            result.warnings.append(f"{msg}\n{traceback.format_exc()}")
            return None

    def _notify_telegram_safely(
        self,
        page: Optional[CreatedPage],
        summary: Optional[SummaryResult],
        inputs: PipelineInputs,
        log: LogFn,
    ) -> bool:
        """Sends to Telegram AND Discord (if enabled). Returns True if either fired."""
        if page is None or summary is None:
            return False
        date_iso = inputs.date_iso or today_iso()
        title = format_page_title(inputs.project, inputs.materi, date_iso)
        summary_short = summary.summary[:200]
        any_sent = False

        # Telegram
        if self.telegram.enabled:
            ok = self.telegram.send_meeting_notification(
                title=title, summary_short=summary_short,
                page_url=page.url,
                n_actions=len(summary.action_items))
            log("Telegram sent." if ok else "Telegram send failed.",
                "ok" if ok else "warn")
            any_sent = any_sent or ok

        # Discord
        if self.discord is not None and self.discord.enabled:
            ok = self.discord.send_meeting_notification(
                title=title, summary_short=summary_short,
                page_url=page.url,
                n_actions=len(summary.action_items))
            log("Discord sent." if ok else "Discord send failed.",
                "ok" if ok else "warn")
            any_sent = any_sent or ok

        return any_sent


# ---------- progress helper ----------

class _make_phase_progress:
    """Tiny adapter mapping per-phase progress (0-100) to a global percent.

    The weights dict scopes which phases are part of "100%" — for the full
    pipeline we pass PHASE_WEIGHTS; for the resend path we pass a smaller
    subset so the bar still fills the full width.
    """

    def __init__(self, on_progress: Optional[ProgressFn],
                  weights: Optional[dict] = None):
        self.on_progress = on_progress
        self.weights = weights if weights is not None else PHASE_WEIGHTS
        self.completed = 0.0  # cumulative percent already done

    def start(self, phase: str, label: str) -> None:
        if self.on_progress:
            self.on_progress(self.completed, label)

    def update(self, phase: str, sub_pct: float, label: str) -> None:
        if not self.on_progress:
            return
        weight = self.weights.get(phase, 0)
        pct = self.completed + (sub_pct / 100.0) * weight
        self.on_progress(min(100.0, pct), label)

    def complete(self, phase: str) -> None:
        self.completed += self.weights.get(phase, 0)
        if self.on_progress:
            self.on_progress(min(100.0, self.completed), "")


def _check_cancel(cancel: threading.Event) -> None:
    if cancel.is_set():
        raise TranscriptionCancelled()
