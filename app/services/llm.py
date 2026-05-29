"""Local LLM client — talks to OpenAI-compatible servers (LM Studio, Ollama).

Replaces the Gemini API node from the v1 n8n flow. By targeting the
OpenAI-compatible chat-completions endpoint, the same client code drives:
  - LM Studio  (default, http://localhost:1234/v1)
  - Ollama     (http://localhost:11434/v1)
  - Any other compatible runtime (vLLM, llama.cpp server, etc.)

We use plain `requests` instead of the openai SDK so installing the app
doesn't pull a heavy transitive dependency tree.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import requests


@dataclass
class SummaryResult:
    summary: str
    key_points: list[str]
    action_items: list[str]
    raw: str = ""                  # raw assistant text, for debug / display
    truncated: bool = False        # True if transcript was chunked


@dataclass
class ConnectionResult:
    ok: bool
    models: list[str] = field(default_factory=list)
    error: str = ""


class LLMClient:
    """OpenAI-compatible chat-completions client for local LLM servers.

    Args:
        base_url: e.g. "http://localhost:1234/v1" — should NOT include /chat/completions
        model: model name as the server reports it, or "auto" to pick the first one
        api_key: ignored by most local runtimes; OpenAI SDK requires a non-empty value
        temperature: 0.3 is a good default for summarization (factual, not creative)
        timeout: per-request HTTP timeout in seconds
    """

    def __init__(
        self,
        base_url: str = "http://localhost:1234/v1",
        model: str = "auto",
        api_key: str = "lm-studio",
        temperature: float = 0.3,
        timeout: int = 300,
        max_tokens: int = 2000,
        chunk_chars: int = 6000,
        provider: str = "lm_studio",
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key or "lm-studio"
        self.temperature = temperature
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.chunk_chars = chunk_chars
        # Provider: lm_studio | ollama | openai | anthropic | gemini |
        #           deepseek | custom
        # LM Studio / Ollama / OpenAI / DeepSeek / Custom all use OpenAI-
        # compatible API (Authorization: Bearer + /chat/completions schema).
        # Anthropic + Gemini have their own request schemas → routed via
        # _complete() dispatcher.
        self.provider = provider

        self._resolved_model: Optional[str] = None

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    # ---------- Connection / discovery ----------

    def test_connection(self) -> ConnectionResult:
        """Provider-aware connection probe."""
        if self.provider == "anthropic":
            return self._test_anthropic()
        if self.provider == "gemini":
            return self._test_gemini()
        return self._test_openai_compat()

    def _test_openai_compat(self) -> ConnectionResult:
        try:
            r = requests.get(
                f"{self.base_url}/models",
                headers=self._headers,
                timeout=5,
            )
            r.raise_for_status()
            data = r.json()
            models = [m["id"] for m in data.get("data", []) if "id" in m]
            return ConnectionResult(ok=True, models=models)
        except requests.exceptions.ConnectionError:
            return ConnectionResult(
                ok=False,
                error=f"Can't reach {self.base_url}.")
        except requests.exceptions.HTTPError as e:
            return ConnectionResult(ok=False, error=f"HTTP {e.response.status_code}")
        except Exception as e:
            return ConnectionResult(ok=False, error=str(e))

    def _test_anthropic(self) -> ConnectionResult:
        # Anthropic has no list-models endpoint. Send a 1-token ping.
        try:
            r = requests.post(
                f"{self.base_url}/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": self.model or "claude-3-5-sonnet-20241022",
                    "max_tokens": 1,
                    "messages": [{"role": "user", "content": "."}],
                },
                timeout=8)
            if r.status_code == 401:
                return ConnectionResult(ok=False, error="Invalid API key (401)")
            if r.status_code >= 400:
                msg = r.json().get("error", {}).get("message", r.text[:80])
                return ConnectionResult(ok=False, error=f"HTTP {r.status_code}: {msg}")
            # Anthropic doesn't expose model list — hardcode current options
            return ConnectionResult(ok=True, models=[
                "claude-3-5-sonnet-20241022",
                "claude-3-5-haiku-20241022",
                "claude-3-opus-20240229",
                "claude-sonnet-4-20250514",
            ])
        except Exception as e:
            return ConnectionResult(ok=False, error=str(e))

    def _test_gemini(self) -> ConnectionResult:
        try:
            r = requests.get(
                f"{self.base_url}/models?key={self.api_key}",
                timeout=5)
            r.raise_for_status()
            data = r.json()
            # Filter to generative models only
            models = [
                m["name"].split("/")[-1]
                for m in data.get("models", [])
                if "generateContent" in m.get("supportedGenerationMethods", [])
            ]
            return ConnectionResult(ok=True, models=models)
        except requests.exceptions.HTTPError as e:
            return ConnectionResult(ok=False, error=f"HTTP {e.response.status_code}")
        except Exception as e:
            return ConnectionResult(ok=False, error=str(e))

    def resolve_model(self) -> str:
        """Resolve self.model. Cloud providers (Anthropic/Gemini) require an
        explicit model name. LM Studio / Ollama / OpenAI / Custom accept
        'auto' which picks the first chat-capable model from /v1/models.
        """
        if self._resolved_model:
            return self._resolved_model
        if self.model and self.model != "auto":
            self._resolved_model = self.model
            return self._resolved_model
        # Anthropic + Gemini: no auto, require explicit model
        if self.provider == "anthropic":
            self._resolved_model = "claude-3-5-sonnet-20241022"
            return self._resolved_model
        if self.provider == "gemini":
            self._resolved_model = "gemini-1.5-flash"
            return self._resolved_model
        # OpenAI-compat: discover via /models
        result = self.test_connection()
        if not result.ok or not result.models:
            raise RuntimeError(
                result.error or "No models available on the LLM server.")
        chat_models = [m for m in result.models if not _looks_like_embedding(m)]
        if not chat_models:
            raise RuntimeError(
                "No chat-capable models found (only embeddings).")
        self._resolved_model = chat_models[0]
        return self._resolved_model

    # ---------- Summarization ----------

    SYSTEM_PROMPT = (
        "You are a professional meeting notes assistant. Your job is to read "
        "a meeting transcript and produce a clean, structured summary. "
        "Always respond ONLY with valid JSON matching the requested schema — "
        "no markdown, no backticks, no commentary.\n\n"
        "IMPORTANT: write the summary, key_points, and action_items in the "
        "SAME LANGUAGE as the transcript. If the transcript is in Indonesian, "
        "respond in Indonesian. If it is in English, respond in English. "
        "Do not translate."
    )

    USER_TEMPLATE = (
        "Meeting topic: {materi}\n"
        "Project: {project}\n\n"
        "Transcript:\n{transcript}\n\n"
        "Task: analyse the transcript above and output a summary as JSON.\n\n"
        "Strict rules:\n"
        "1. key_points: array of STRING. Can be 2 to 15+ items — follow what "
        "the meeting actually covered. DO NOT force exactly 3.\n"
        "2. action_items: array of STRING (NOT object / dict). Each item is "
        "one sentence: 'Task description - PIC (if mentioned)'. "
        "Correct example: 'Draft the contract - Danar'. If there are no "
        "tasks, return an empty array [].\n"
        "3. summary: STRING, 3-5 sentences — what was discussed + outcome / "
        "conclusion.\n\n"
        "Match the language of the transcript (do not translate). "
        "Respond ONLY with valid JSON (no markdown, no backticks, no extra "
        "prose). Structure:\n"
        "{{\n"
        "  \"summary\": \"...\",\n"
        "  \"key_points\": [\"...\", \"...\"],\n"
        "  \"action_items\": [\"... - PIC\", \"...\"]\n"
        "}}"
    )

    def summarize_transcript(
        self,
        transcript: str,
        materi: str = "",
        project: str = "",
        max_chars: int = 200_000,
        on_log: Optional[Callable[[str, str], None]] = None,
    ) -> SummaryResult:
        """Summarise a meeting transcript, chunking automatically when needed.

        Short transcripts (≤ chunk_chars) go through a single LLM call. Longer
        ones are split into overlapping chunks, summarised individually, then
        merged. The merge step uses the LLM again over the concatenated partial
        summaries — far less risky than feeding the model the full transcript,
        because the inputs are now ~hundreds of chars each, not thousands.
        """
        log = on_log or (lambda m, k: None)
        truncated = len(transcript) > max_chars
        body = transcript[:max_chars] if truncated else transcript

        if len(body) <= self.chunk_chars:
            return self._summarize_chunk(body, materi, project, truncated=truncated)

        chunks = _split_into_chunks(body, self.chunk_chars, overlap=200)
        log(f"Transcript long ({len(body)} chars) — chunking into {len(chunks)} parts",
            "info")

        partials: list[SummaryResult] = []
        for i, chunk in enumerate(chunks, 1):
            log(f"Summarising chunk {i}/{len(chunks)}…", "info")
            try:
                partial = self._summarize_chunk(chunk, materi, project,
                                                  section_hint=f"bagian {i}/{len(chunks)}")
                partials.append(partial)
            except Exception as e:
                log(f"Chunk {i} failed · {e}", "warn")

        if not partials:
            return SummaryResult(
                summary="[All chunks failed — try running again or switch to a larger model.]",
                key_points=[], action_items=[], truncated=truncated,
            )

        return self._merge_partials(partials, materi, project, log,
                                     truncated=truncated)

    # ---------- private helpers ----------

    def _summarize_chunk(
        self,
        chunk_text: str,
        materi: str,
        project: str,
        section_hint: str = "",
        truncated: bool = False,
    ) -> SummaryResult:
        """One LLM call over a single chunk of transcript."""
        model = self.resolve_model()
        # Reuse the main user template; section_hint is appended to materi so
        # the model knows this isn't the full meeting (helps it avoid claiming
        # final conclusions on a partial slice).
        materi_label = f"{materi} [{section_hint}]" if section_hint else materi
        payload = {
            "model": model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "messages": [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": self.USER_TEMPLATE.format(
                    materi=materi_label or "(not specified)",
                    project=project or "(not specified)",
                    transcript=chunk_text,
                )},
            ],
        }
        content = self._post_chat(payload)
        parsed = _parse_summary_json(content)
        return SummaryResult(
            summary=str(parsed.get("summary", "")).strip(),
            key_points=[_format_point(x) for x in (parsed.get("key_points") or [])
                         if _format_point(x)],
            action_items=[_format_action(x) for x in (parsed.get("action_items") or [])
                           if _format_action(x)],
            raw=content,
            truncated=truncated,
        )

    MERGE_PROMPT = (
        "Below are section-by-section summaries from one long meeting. "
        "Task: produce ONE final summary (3-5 sentences) that combines all "
        "sections into a coherent narrative.\n\n"
        "Write the final summary in the SAME LANGUAGE as the section "
        "summaries — do not translate.\n\n"
        "Section summaries:\n{partials}\n\n"
        "Respond ONLY with JSON (no markdown):\n"
        "{{\"summary\": \"...\"}}"
    )

    def _merge_partials(
        self,
        partials: list[SummaryResult],
        materi: str,
        project: str,
        log: Callable[[str, str], None],
        truncated: bool,
    ) -> SummaryResult:
        # Dedupe key_points and action_items by lowercased text — order-preserving.
        merged_points: list[str] = []
        merged_actions: list[str] = []
        seen_p: set[str] = set()
        seen_a: set[str] = set()
        for p in partials:
            for kp in p.key_points:
                k = kp.lower().strip()
                if k and k not in seen_p:
                    seen_p.add(k)
                    merged_points.append(kp)
            for a in p.action_items:
                k = a.lower().strip()
                if k and k not in seen_a:
                    seen_a.add(k)
                    merged_actions.append(a)

        # Final summary: ask LLM to merge the partial summaries. If that fails,
        # fall back to concatenating them.
        partials_text = "\n\n".join(
            f"[Bagian {i+1}] {p.summary}" for i, p in enumerate(partials) if p.summary
        )

        final_summary = ""
        if partials_text:
            try:
                payload = {
                    "model": self.resolve_model(),
                    "temperature": self.temperature,
                    "max_tokens": 800,
                    "messages": [
                        {"role": "system", "content": self.SYSTEM_PROMPT},
                        {"role": "user", "content": self.MERGE_PROMPT.format(
                            partials=partials_text)},
                    ],
                }
                content = self._post_chat(payload)
                parsed = _parse_summary_json(content)
                final_summary = str(parsed.get("summary", "")).strip()
            except Exception as e:
                log(f"Summary merge failed · {e} — falling back to concat",
                    "warn")

        if not final_summary:
            final_summary = " ".join(p.summary for p in partials if p.summary)

        return SummaryResult(
            summary=final_summary,
            key_points=merged_points,
            action_items=merged_actions,
            raw="",  # raw doesn't apply to merged result
            truncated=truncated,
        )

    def _post_chat(self, payload: dict) -> str:
        """Dispatcher → uses provider-specific adapter.

        payload is OpenAI-style {model, messages, max_tokens, temperature}.
        Each adapter translates to its native schema.
        """
        if self.provider == "anthropic":
            return self._anthropic_complete(payload)
        if self.provider == "gemini":
            return self._gemini_complete(payload)
        return self._openai_complete(payload)

    def _openai_complete(self, payload: dict) -> str:
        """LM Studio / Ollama / OpenAI / Custom — all OpenAI-compatible."""
        try:
            r = requests.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers,
                json=payload,
                timeout=self.timeout,
            )
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"LLM request failed: {e}") from e
        r.raise_for_status()
        data = r.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise RuntimeError(f"Unexpected LLM response shape: {data!r}") from e

    def _anthropic_complete(self, payload: dict) -> str:
        """Anthropic Messages API. System message extracted; user/assistant
        messages mapped 1:1. https://docs.anthropic.com/en/api/messages
        """
        system = ""
        msgs = []
        for m in payload.get("messages", []):
            if m["role"] == "system":
                system = m["content"]
            else:
                msgs.append({"role": m["role"], "content": m["content"]})

        body: dict[str, Any] = {
            "model": payload.get("model") or self.model,
            "max_tokens": payload.get("max_tokens", self.max_tokens),
            "temperature": payload.get("temperature", self.temperature),
            "messages": msgs,
        }
        if system:
            body["system"] = system

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        try:
            r = requests.post(
                f"{self.base_url}/messages",
                headers=headers,
                json=body,
                timeout=self.timeout,
            )
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Anthropic request failed: {e}") from e
        r.raise_for_status()
        data = r.json()
        try:
            # Response: {"content": [{"type":"text","text":"..."}], ...}
            for part in data.get("content", []):
                if part.get("type") == "text":
                    return part.get("text", "")
            return ""
        except (KeyError, IndexError, TypeError) as e:
            raise RuntimeError(
                f"Unexpected Anthropic response: {data!r}") from e

    def _gemini_complete(self, payload: dict) -> str:
        """Google Generative Language API (Gemini).
        https://ai.google.dev/api/generate-content
        """
        model = payload.get("model") or self.model
        contents = []
        sys_msg = ""
        for m in payload.get("messages", []):
            if m["role"] == "system":
                sys_msg = m["content"]
                continue
            role = "user" if m["role"] == "user" else "model"
            contents.append({
                "role": role,
                "parts": [{"text": m["content"]}],
            })

        body: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": payload.get("max_tokens", self.max_tokens),
                "temperature": payload.get("temperature", self.temperature),
            },
        }
        if sys_msg:
            body["systemInstruction"] = {"parts": [{"text": sys_msg}]}

        url = (f"{self.base_url}/models/{model}:generateContent"
               f"?key={self.api_key}")
        try:
            r = requests.post(
                url,
                headers={"content-type": "application/json"},
                json=body,
                timeout=self.timeout,
            )
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Gemini request failed: {e}") from e
        r.raise_for_status()
        data = r.json()
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as e:
            raise RuntimeError(f"Unexpected Gemini response: {data!r}") from e


_EMBEDDING_HINTS = ("embed", "embedding", "bge-", "e5-")


def _looks_like_embedding(name: str) -> bool:
    n = name.lower()
    return any(h in n for h in _EMBEDDING_HINTS)


_DECODER = json.JSONDecoder()


def _split_into_chunks(text: str, chunk_chars: int, overlap: int = 200) -> list[str]:
    """Split text into chunks of at most `chunk_chars`, with small overlap.

    Tries to break at paragraph boundaries (double-newline) first, then sentence
    boundaries (". "), then a hard char split. Overlap helps the next chunk
    pick up mid-sentence context the previous one ended on.
    """
    if len(text) <= chunk_chars:
        return [text]
    chunks: list[str] = []
    pos = 0
    while pos < len(text):
        end = min(pos + chunk_chars, len(text))
        if end < len(text):
            # Prefer paragraph break in the last 30% of the window
            window_start = pos + int(chunk_chars * 0.7)
            for sep in ("\n\n", ". ", "; ", ", "):
                split_at = text.rfind(sep, window_start, end)
                if split_at != -1:
                    end = split_at + len(sep)
                    break
        chunks.append(text[pos:end])
        if end >= len(text):
            break
        pos = max(pos + 1, end - overlap)
    return chunks


def _iter_valid_json_objects(text: str):
    """Yield every JSON object that the standard decoder can parse from `text`.

    Walks each `{` candidate and tries raw_decode there. Used instead of a
    custom balanced-brace scanner because small models often leave strings
    unterminated mid-loop — depth tracking on raw chars then gets stuck inside
    a never-closed string. raw_decode just gives up on malformed prefixes and
    we move on to the next `{`.
    """
    pos = 0
    while pos < len(text):
        next_open = text.find("{", pos)
        if next_open < 0:
            return
        try:
            obj, end = _DECODER.raw_decode(text, next_open)
            yield obj
            pos = end
        except json.JSONDecodeError:
            pos = next_open + 1


def _repair_json(text: str) -> str:
    """Fix the JSON glitches local models commonly emit.

    - Trailing commas before `]` / `}` — invalid in spec but every JS-trained
      model loves them.
    - Smart quotes from rich-text training data — replace with ASCII quotes.
    - Code fences mid-text (not just edges).
    """
    # Strip any backtick fences anywhere in the text (mid-text fences happen
    # when the model rambles before/after the JSON).
    text = re.sub(r"```(?:json)?", "", text, flags=re.IGNORECASE)
    text = text.replace("```", "")
    # Smart quotes → ASCII
    text = (text.replace("“", '"').replace("”", '"')
                 .replace("‘", "'").replace("’", "'"))
    # Trailing commas before close bracket
    text = re.sub(r",\s*([\]}])", r"\1", text)
    return text


def _parse_summary_json(text: str) -> dict[str, Any]:
    """Tolerant JSON parser for LLM output.

    Strategy:
      1. Strip leading/trailing code fences → json.loads
      2. Repair common errors (smart quotes, trailing commas) → json.loads
      3. Iterate balanced {...} blocks → try each in order, return first valid
         one that looks like a summary (has at least one of our expected keys)
      4. Same block iteration, with repairs applied
      5. Give up: return a truncated-text summary + empty lists

    Order matters: we want the FIRST valid summary object, not the largest,
    because small models sometimes loop and emit many truncated objects.
    """
    text = (text or "").strip()
    if not text:
        return {}

    expected_keys = {"summary", "key_points", "action_items"}

    def _is_summary_shape(d: Any) -> bool:
        return isinstance(d, dict) and bool(expected_keys & set(d.keys()))

    # Pass 1+2: try the whole text (fence-stripped, then repaired)
    fence_stripped = re.sub(r"^```(?:json)?\s*|\s*```$", "",
                              text, flags=re.IGNORECASE)
    for cand in (fence_stripped, _repair_json(fence_stripped)):
        try:
            data = json.loads(cand)
            if _is_summary_shape(data):
                return data
        except json.JSONDecodeError:
            pass

    # Pass 3: iterate valid JSON objects in the text, return the first that
    # looks like a summary. Skips broken/loopy prefixes the model emitted.
    for data in _iter_valid_json_objects(text):
        if _is_summary_shape(data):
            return data

    # Pass 4: try again after a repair pass (smart quotes, trailing commas)
    repaired = _repair_json(text)
    if repaired != text:
        for data in _iter_valid_json_objects(repaired):
            if _is_summary_shape(data):
                return data

    # Give up — truncate text so we don't dump a 50kB blob into Notion.
    truncated_text = text if len(text) < 1500 else text[:1500] + "\n…(truncated)"
    return {
        "summary": (
            "[LLM failed to produce valid JSON — try running again, "
            "increase max_tokens, or switch to a larger model.]\n\n"
            + truncated_text
        ),
        "key_points": [],
        "action_items": [],
    }


def _format_point(item: Any) -> str:
    """Coerce a key_point item to a clean string regardless of shape."""
    if item is None:
        return ""
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        # Sometimes wrapped as {point: ...} or {topic: ...} or {text: ...}
        for key in ("point", "topic", "text", "description", "title"):
            if key in item and item[key]:
                return str(item[key]).strip()
        # Fallback: join values
        return " ".join(str(v) for v in item.values() if v).strip()
    return str(item).strip()


def _format_action(item: Any) -> str:
    """Coerce an action_item to "task - PIC" string regardless of shape.

    Models often produce {task, PIC} objects despite being asked for strings;
    rather than fight them, we accept and reformat. Handles a few common key
    name variants (task/description/action, PIC/owner/assignee).
    """
    if item is None:
        return ""
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        task = ""
        for key in ("task", "description", "action", "title", "text"):
            if key in item and item[key]:
                task = str(item[key]).strip()
                break
        pic = ""
        for key in ("PIC", "pic", "owner", "assignee", "responsible", "person"):
            if key in item and item[key]:
                pic = str(item[key]).strip()
                break
        if task and pic:
            return f"{task} - {pic}"
        if task:
            return task
        # Fallback: pretty join
        return " - ".join(str(v) for v in item.values() if v).strip()
    return str(item).strip()
