"""Notion API client.

Replaces the n8n nodes for fetching projects and creating the meeting page.
Each method maps to a real REST call against api.notion.com — the integration
token is per-workspace, so a single LLMClient instance scopes to one Notion
workspace and one Notion-Version.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Any, Optional

import requests


NOTION_VERSION = "2022-06-28"
API = "https://api.notion.com/v1"

# Notion's text blocks have a 2000-char rich_text content limit per chunk —
# 1900 leaves headroom for ellipsis-style formatting we might add later.
NOTION_TEXT_CHUNK = 1900


@dataclass
class DatabaseRef:
    id: str
    title: str
    icon: Optional[str] = None


@dataclass
class PageRef:
    id: str
    title: str


@dataclass
class SchemaDetection:
    title_property: Optional[str] = None
    date_property: Optional[str] = None
    all_properties: dict[str, str] = field(default_factory=dict)  # name -> type

    @property
    def is_valid(self) -> bool:
        # Title is required by Notion; date we can synthesise if missing.
        return self.title_property is not None


@dataclass
class ConnectionResult:
    ok: bool
    workspace_name: str = ""
    bot_name: str = ""
    error: str = ""


@dataclass
class CreatedPage:
    id: str
    url: str


class NotionError(RuntimeError):
    def __init__(self, status: int, message: str):
        super().__init__(f"Notion API {status}: {message}")
        self.status = status


class NotionClient:
    """Per-workspace Notion REST client. Cheap to construct; no I/O until called."""

    def __init__(self, token: str, timeout: int = 15):
        self.token = (token or "").strip()
        self.timeout = timeout

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        }

    # ---------- low-level ----------

    def _request(self, method: str, path: str, **kw) -> dict[str, Any]:
        url = f"{API}{path}"
        try:
            r = requests.request(method, url, headers=self._headers,
                                  timeout=self.timeout, **kw)
        except requests.exceptions.RequestException as e:
            raise NotionError(0, str(e)) from e
        if r.status_code >= 400:
            try:
                msg = r.json().get("message", r.text)
            except Exception:
                msg = r.text[:200]
            raise NotionError(r.status_code, msg)
        return r.json()

    # ---------- connection ----------

    def test_connection(self) -> ConnectionResult:
        """Hit /users/me to validate the token. Returns user/workspace metadata."""
        if not self.token:
            return ConnectionResult(ok=False, error="Token kosong.")
        try:
            data = self._request("GET", "/users/me")
        except NotionError as e:
            return ConnectionResult(ok=False, error=str(e))
        bot = (data.get("bot") or {})
        owner = (bot.get("owner") or {})
        return ConnectionResult(
            ok=True,
            workspace_name=bot.get("workspace_name") or owner.get("workspace_name", ""),
            bot_name=data.get("name", ""),
        )

    # ---------- discovery ----------

    def list_databases(self) -> list[DatabaseRef]:
        """Search every database the integration has access to.

        Used by the Settings dialog to populate the "target database" picker.
        """
        body = {
            "filter": {"property": "object", "value": "database"},
            "page_size": 100,
        }
        data = self._request("POST", "/search", json=body)
        out: list[DatabaseRef] = []
        for db in data.get("results", []):
            if db.get("object") != "database":
                continue
            title = "".join(
                t.get("plain_text", "") for t in (db.get("title") or [])
            ).strip()
            icon_obj = db.get("icon") or {}
            icon = icon_obj.get("emoji") if icon_obj.get("type") == "emoji" else None
            out.append(DatabaseRef(
                id=db["id"],
                title=title or "(untitled)",
                icon=icon,
            ))
        out.sort(key=lambda d: d.title.lower())
        return out

    def get_db_schema(self, db_id: str) -> SchemaDetection:
        """Fetch DB and auto-detect title + date property names.

        If a DB has multiple date properties we pick the first one — the user
        can override the schema in the workspace editor.
        """
        data = self._request("GET", f"/databases/{db_id}")
        props = data.get("properties", {}) or {}
        detection = SchemaDetection()
        for name, p in props.items():
            ptype = (p or {}).get("type", "")
            detection.all_properties[name] = ptype
            if ptype == "title" and detection.title_property is None:
                detection.title_property = name
            if ptype == "date" and detection.date_property is None:
                detection.date_property = name
        return detection

    def list_pages_in_db(self, db_id: str) -> list[PageRef]:
        """Query pages in a database — used when projects_db_id is set."""
        body: dict[str, Any] = {"page_size": 100}
        data = self._request("POST", f"/databases/{db_id}/query", json=body)
        return _extract_pages(data.get("results", []))

    def search_pages_excluding_db(self, exclude_db_id: str) -> list[PageRef]:
        """Fallback project source: every page the integration sees minus the target DB.

        Mirrors v1's behavior so the migration is a no-op for existing users.
        """
        body = {
            "filter": {"property": "object", "value": "page"},
            "page_size": 100,
        }
        data = self._request("POST", "/search", json=body)
        exclude_clean = (exclude_db_id or "").replace("-", "")
        pages: list[PageRef] = []
        for page in data.get("results", []):
            if page.get("object") != "page":
                continue
            parent = (page.get("parent") or {})
            parent_db = (parent.get("database_id") or "").replace("-", "")
            if exclude_clean and parent_db == exclude_clean:
                continue
            ref = _page_ref(page)
            if ref:
                pages.append(ref)
        # De-dupe by title (keeps v1 behavior)
        seen: set[str] = set()
        unique: list[PageRef] = []
        for p in pages:
            if p.title in seen:
                continue
            seen.add(p.title)
            unique.append(p)
        unique.sort(key=lambda p: p.title.lower())
        return unique

    # ---------- meeting page creation ----------

    def create_meeting_page(
        self,
        db_id: str,
        schema: dict[str, str],
        title: str,
        date_iso: str,
        summary: str,
        key_points: list[str],
        action_items: list[str],
        transcript: str,
    ) -> CreatedPage:
        """Create a meeting note page using the structure from the v1 n8n flow.

        Layout:
            🎙 (icon)
            ## 📋 Ringkasan       → paragraphs
            ---
            ## 💬 Inti Diskusi    → bulleted list
            ---
            ## ✅ Action Items     → to-do checkboxes
            ---
            ▸ 📝 Raw Transcript    → toggle containing the full transcript
        """
        title_prop = schema.get("title_property") or "Name"
        date_prop = schema.get("date_property") or "Created Date"

        properties: dict[str, Any] = {
            title_prop: {"title": [{"type": "text", "text": {"content": title[:2000]}}]},
        }
        if date_prop:
            properties[date_prop] = {"date": {"start": date_iso}}

        children: list[dict[str, Any]] = []
        children.append(_heading_2("📋 Ringkasan"))
        children.extend(_paragraph_blocks(summary or "-"))
        children.append(_divider())

        children.append(_heading_2("💬 Inti Diskusi"))
        if key_points:
            children.extend(_bulleted_blocks(key_points))
        else:
            children.extend(_paragraph_blocks("-"))
        children.append(_divider())

        children.append(_heading_2("✅ Action Items"))
        if action_items:
            children.extend(_todo_blocks(action_items))
        else:
            children.extend(_paragraph_blocks("-"))
        children.append(_divider())

        children.append(_transcript_toggle(transcript or "-"))

        body = {
            "parent": {"database_id": db_id},
            "icon": {"type": "emoji", "emoji": "🎙️"},
            "properties": properties,
            "children": children,
        }
        data = self._request("POST", "/pages", json=body)
        return CreatedPage(id=data["id"], url=data.get("url", ""))


# ---------- Notion block helpers ----------

def _rich_text(content: str) -> list[dict[str, Any]]:
    return [{"type": "text", "text": {"content": content}}]


def _heading_2(text: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "heading_2",
        "heading_2": {
            "rich_text": [
                {"type": "text", "text": {"content": text}, "annotations": {"bold": True}}
            ]
        },
    }


def _divider() -> dict[str, Any]:
    return {"object": "block", "type": "divider", "divider": {}}


def _paragraph_blocks(text: str) -> list[dict[str, Any]]:
    """Chunk long text into Notion-friendly paragraph blocks."""
    if not text:
        return [{"object": "block", "type": "paragraph",
                 "paragraph": {"rich_text": _rich_text("-")}}]
    blocks: list[dict[str, Any]] = []
    remaining = text
    while remaining:
        chunk, remaining = remaining[:NOTION_TEXT_CHUNK], remaining[NOTION_TEXT_CHUNK:]
        blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": _rich_text(chunk)},
        })
    return blocks


def _bulleted_blocks(items: list[str]) -> list[dict[str, Any]]:
    return [{
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": _rich_text(str(item)[:NOTION_TEXT_CHUNK])},
    } for item in items]


def _todo_blocks(items: list[str]) -> list[dict[str, Any]]:
    return [{
        "object": "block",
        "type": "to_do",
        "to_do": {
            "rich_text": _rich_text(str(item)[:NOTION_TEXT_CHUNK]),
            "checked": False,
        },
    } for item in items]


def _transcript_toggle(transcript: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "toggle",
        "toggle": {
            "rich_text": [{
                "type": "text",
                "text": {"content": "📝 Raw Transcript"},
                "annotations": {"bold": True, "color": "gray"},
            }],
            "children": _paragraph_blocks(transcript),
        },
    }


def _extract_pages(results: list[dict[str, Any]]) -> list[PageRef]:
    pages = []
    for page in results:
        ref = _page_ref(page)
        if ref:
            pages.append(ref)
    pages.sort(key=lambda p: p.title.lower())
    return pages


def _page_ref(page: dict[str, Any]) -> Optional[PageRef]:
    props = page.get("properties") or {}
    title = None
    for _, p in props.items():
        if (p or {}).get("type") == "title":
            title = "".join(t.get("plain_text", "") for t in (p.get("title") or []))
            break
    if not title or not title.strip():
        return None
    return PageRef(id=page["id"], title=title.strip())


def today_iso() -> str:
    return datetime.date.today().isoformat()


def format_page_title(project: str, materi: str, date_iso: str) -> str:
    """Page title: "[Project — ]Materi — DD Mon YYYY".

    Project is optional — when empty the title collapses to "Materi — Date"
    instead of leaving a leading "— ".
    """
    try:
        d = datetime.date.fromisoformat(date_iso)
        # Indonesian month abbreviations — matches v1 locale 'id-ID' output
        months = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun",
                  "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]
        date_label = f"{d.day:02d} {months[d.month - 1]} {d.year}"
    except (ValueError, IndexError):
        date_label = date_iso
    parts = [p for p in (project.strip() if project else "", materi.strip(), date_label) if p]
    return " — ".join(parts)
