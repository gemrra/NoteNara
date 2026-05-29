"""Whisper transcription service.

Wraps faster-whisper with:
- Lazy-loaded, cached model (loaded once per app session)
- VAD tuning that suppresses the "looping phrase" hallucination (e.g. the
  "Tengah Tengah Tengah" loop we saw in v1 output) — the key knob is
  condition_on_previous_text=False, which stops a bad guess at one silence
  point from poisoning every chunk that follows.
- Progress callback with percent + phase, driven by segment.end / duration
- Cancellation support via threading.Event
- Robust CUDA DLL discovery (globs nvidia/*/bin instead of hardcoded paths)
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from ..constants import DEFAULT_MODEL_DIR, VENV_NVIDIA_DIR


# ---------- CUDA setup ----------

_cuda_setup_done = False


def setup_cuda_dlls() -> list[Path]:
    """Add bundled nvidia CUDA DLL directories to the process search path.

    Returns the list of directories that were registered. Idempotent.
    """
    global _cuda_setup_done
    if _cuda_setup_done:
        return []

    added: list[Path] = []
    if not VENV_NVIDIA_DIR.exists():
        _cuda_setup_done = True
        return added

    # Walk nvidia/<pkg>/bin for every installed CUDA wheel (cublas, cudnn, ...)
    for pkg_dir in VENV_NVIDIA_DIR.iterdir():
        bin_dir = pkg_dir / "bin"
        if not bin_dir.is_dir():
            continue
        os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")
        try:
            os.add_dll_directory(str(bin_dir))  # type: ignore[attr-defined]
        except (AttributeError, OSError):
            pass
        added.append(bin_dir)

    _cuda_setup_done = True
    return added


# ---------- Result types ----------

@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str


@dataclass
class TranscriptResult:
    text: str
    segments: list[TranscriptSegment]
    language: str
    language_probability: float
    duration: float

    def to_paragraphs(self, paragraph_gap_s: float = 2.0) -> list[str]:
        """Group segments into paragraphs when there's a silence gap between them.

        Default 2s gap is a natural turn boundary in conversational meetings.
        """
        if not self.segments:
            return [self.text]
        paragraphs: list[list[str]] = [[]]
        last_end = self.segments[0].start
        for seg in self.segments:
            if seg.start - last_end > paragraph_gap_s and paragraphs[-1]:
                paragraphs.append([])
            paragraphs[-1].append(seg.text.strip())
            last_end = seg.end
        return [" ".join(p).strip() for p in paragraphs if p]


# ---------- Errors ----------

class TranscriptionCancelled(Exception):
    """Raised when the caller cancels via the threading.Event."""


# ---------- Service ----------

ProgressFn = Callable[[float, str], None]


class WhisperService:
    """Lazy-loading, cached Whisper transcription service.

    The model is loaded the first time `transcribe()` is called (or explicitly
    via `ensure_loaded()`) and reused for every subsequent call — eliminating
    the 5-10 second reload that v1 incurred per transcription.
    """

    def __init__(
        self,
        model_name: str = "turbo",
        compute_type: str = "float16",
        device: str = "cuda",
        model_dir: Optional[Path] = None,
        beam_size: int = 5,
        vad_filter: bool = True,
    ):
        self.model_name = model_name
        self.compute_type = compute_type
        self.device = device
        self.model_dir = Path(model_dir) if model_dir else DEFAULT_MODEL_DIR
        self.beam_size = beam_size
        self.vad_filter = vad_filter

        self._model = None
        self._load_lock = threading.Lock()

    def ensure_loaded(self, on_progress: Optional[ProgressFn] = None) -> None:
        """Load the model if it isn't already. Safe to call from any thread.

        Loading from disk/network to VRAM can take 10-60 seconds (longer if
        GPU memory is contended with another app like LM Studio). A heartbeat
        thread updates the phase label every 2 seconds so the user knows the
        app is alive, not frozen.
        """
        if self._model is not None:
            return
        with self._load_lock:
            if self._model is not None:
                return
            if on_progress:
                on_progress(0.0, f"Loading Whisper {self.model_name}…")

            import time
            stop_hb = threading.Event()
            start_t = time.time()

            def heartbeat():
                while not stop_hb.wait(2):
                    elapsed = int(time.time() - start_t)
                    if on_progress:
                        msg = f"Loading Whisper {self.model_name}… {elapsed}s"
                        if elapsed >= 30:
                            msg += " (check GPU memory — close LM Studio?)"
                        on_progress(0.0, msg)

            hb = threading.Thread(target=heartbeat, daemon=True)
            hb.start()

            try:
                setup_cuda_dlls()
                from faster_whisper import WhisperModel
                self._model = WhisperModel(
                    self.model_name,
                    device=self.device,
                    compute_type=self.compute_type,
                    download_root=str(self.model_dir),
                )
            finally:
                stop_hb.set()

    def transcribe(
        self,
        file_path: str | Path,
        language: str = "id",
        on_progress: Optional[ProgressFn] = None,
        cancel_event: Optional[threading.Event] = None,
    ) -> TranscriptResult:
        """Transcribe an audio/video file.

        Args:
            file_path: Path to the input media.
            language: ISO 639-1 language hint, or None for auto-detect.
            on_progress: Callback(percent, phase). Percent is 0-100.
            cancel_event: If set during streaming, raises TranscriptionCancelled.
        """
        self.ensure_loaded(on_progress)
        assert self._model is not None

        if on_progress:
            on_progress(0.0, "Starting transcription…")

        segments_iter, info = self._model.transcribe(
            str(file_path),
            language=language,
            beam_size=self.beam_size,
            vad_filter=self.vad_filter,
            # --- Hallucination suppression ---
            # Without this, Whisper feeds its own previous output back as
            # context, so one bad guess at a silence becomes a runaway loop.
            condition_on_previous_text=False,
            # Whisper's own silence detector — independent of VAD filter
            no_speech_threshold=0.6,
            # Tighter VAD: shorter silence threshold = fewer fake "music" bridges
            vad_parameters={"min_silence_duration_ms": 500, "threshold": 0.5},
        )

        duration = float(info.duration) or 1.0
        segments: list[TranscriptSegment] = []
        for seg in segments_iter:
            if cancel_event is not None and cancel_event.is_set():
                raise TranscriptionCancelled()
            segments.append(TranscriptSegment(
                start=float(seg.start),
                end=float(seg.end),
                text=seg.text,
            ))
            if on_progress:
                pct = min(100.0, (seg.end / duration) * 100.0)
                on_progress(pct, f"Transcribing… {pct:.0f}%")

        text = " ".join(s.text.strip() for s in segments).strip()

        if on_progress:
            on_progress(100.0, "Transcription complete.")

        return TranscriptResult(
            text=text,
            segments=segments,
            language=info.language,
            language_probability=float(info.language_probability),
            duration=duration,
        )
