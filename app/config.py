"""Config v2 schema, load/save, and v1 → v2 migration.

Schema v2:
{
  "version": 2,
  "active_profile": "personal",
  "llm": {
    "provider": "lm_studio" | "ollama" | "custom",
    "base_url": "http://localhost:1234/v1",
    "model": "auto",
    "api_key": "lm-studio",
    "max_context": null,           # null = auto-detect from /v1/models
    "temperature": 0.3
  },
  "whisper": {
    "model": "turbo",
    "language": "id",
    "compute_type": "float16",
    "beam_size": 5,
    "vad_filter": true
  },
  "telegram": {
    "enabled": false,
    "bot_token": "",
    "chat_id": ""
  },
  "output_dir": "./output",         # relative paths resolved against BASE_DIR
  "profiles": {
    "<slug>": {
      "label": str,
      "notion_token": str,
      "target_db_id": str,          # required to be a useful profile
      "projects_db_id": str | null, # null = search all pages excluding target_db
      "schema": {
        "title_property": "Name",
        "date_property": "Created Date"
      }
    }
  }
}
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from .constants import BASE_DIR, CONFIG_PATH, LEGACY_NOTES_DB_ID

CURRENT_VERSION = 2

LM_STUDIO_DEFAULTS = {
    "provider": "lm_studio",
    "base_url": "http://localhost:1234/v1",
    "model": "auto",
    "api_key": "lm-studio",
    "max_context": None,
    "temperature": 0.3,
    "timeout": 300,
}

WHISPER_DEFAULTS = {
    "model": "turbo",
    "language": "id",
    "compute_type": "float16",
    "beam_size": 5,
    "vad_filter": True,
    # "cuda" uses GPU (fast but contends with LM Studio for VRAM).
    # "cpu" uses CPU only — slower but no GPU conflict.
    "device": "cuda",
}

TELEGRAM_DEFAULTS = {
    "enabled": False,
    "bot_token": "",
    "chat_id": "",
}

DISCORD_DEFAULTS = {
    "enabled": False,
    "webhook_url": "",
}

DEFAULT_SCHEMA = {
    "title_property": "Name",
    "date_property": "Created Date",
}


def empty_config() -> dict[str, Any]:
    """A v2 config with no profiles — what a brand-new install gets."""
    return {
        "version": CURRENT_VERSION,
        "active_profile": "",
        "llm": dict(LM_STUDIO_DEFAULTS),
        "whisper": dict(WHISPER_DEFAULTS),
        "telegram": dict(TELEGRAM_DEFAULTS),
        "discord": dict(DISCORD_DEFAULTS),
        "output_dir": "./output",
        # When True, pipeline opens the Notion page in browser on success.
        # When False, the main UI shows a clickable "Open page" button instead.
        "auto_open_notion": False,
        # "light" or "dark". Light is default to match the editorial mockup.
        "theme": "light",
        "profiles": {},
    }


def load_config() -> dict[str, Any]:
    """Load config from disk, migrating v1 → v2 if needed.

    Returns a v2-shaped dict. If the file doesn't exist, returns empty_config().
    """
    if not CONFIG_PATH.exists():
        return empty_config()

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (json.JSONDecodeError, OSError):
        # Corrupt or unreadable — fall back to empty rather than crash.
        return empty_config()

    if not isinstance(raw, dict):
        return empty_config()

    version = raw.get("version")
    if version == CURRENT_VERSION:
        return _ensure_shape(raw)
    if version is None and "notion_token" in raw:
        migrated = migrate_v1_to_v2(raw)
        # Backup the old file and write the migrated config.
        backup_path = CONFIG_PATH.with_suffix(CONFIG_PATH.suffix + ".v1.bak")
        try:
            shutil.copy2(CONFIG_PATH, backup_path)
        except OSError:
            pass
        save_config(migrated)
        return migrated

    # Unknown version — preserve what we can.
    return _ensure_shape(raw)


def save_config(cfg: dict[str, Any]) -> None:
    """Write config atomically to disk."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = CONFIG_PATH.with_suffix(CONFIG_PATH.suffix + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    tmp_path.replace(CONFIG_PATH)


def migrate_v1_to_v2(old: dict[str, Any]) -> dict[str, Any]:
    """Upgrade a v1 config (single notion_token) into a v2 config with one profile.

    v1 shape: {"notion_token": "ntn_..."}
    The existing user's target DB defaults to LEGACY_NOTES_DB_ID so behavior is preserved.
    """
    cfg = empty_config()
    token = (old.get("notion_token") or "").strip()

    if token:
        cfg["active_profile"] = "personal"
        cfg["profiles"]["personal"] = {
            "label": "Personal Workspace",
            "notion_token": token,
            "target_db_id": LEGACY_NOTES_DB_ID,
            "projects_db_id": None,
            "schema": dict(DEFAULT_SCHEMA),
        }
    return cfg


def _ensure_shape(cfg: dict[str, Any]) -> dict[str, Any]:
    """Backfill missing top-level keys so callers can rely on the shape."""
    base = empty_config()

    out = {**base, **cfg}
    out["llm"] = {**base["llm"], **(cfg.get("llm") or {})}
    out["whisper"] = {**base["whisper"], **(cfg.get("whisper") or {})}
    out["telegram"] = {**base["telegram"], **(cfg.get("telegram") or {})}
    out["discord"] = {**base["discord"], **(cfg.get("discord") or {})}
    out["auto_open_notion"] = bool(cfg.get("auto_open_notion", False))

    profiles = cfg.get("profiles") or {}
    cleaned: dict[str, Any] = {}
    for slug, profile in profiles.items():
        if not isinstance(profile, dict):
            continue
        cleaned[slug] = {
            "label": profile.get("label") or slug,
            "notion_token": profile.get("notion_token", ""),
            "target_db_id": profile.get("target_db_id", ""),
            "projects_db_id": profile.get("projects_db_id") or None,
            "schema": {**DEFAULT_SCHEMA, **(profile.get("schema") or {})},
        }
    out["profiles"] = cleaned

    if cleaned and (not out["active_profile"] or out["active_profile"] not in cleaned):
        out["active_profile"] = next(iter(cleaned))

    return out


# ---------- Profile helpers ----------

def get_active_profile(cfg: dict[str, Any]) -> dict[str, Any] | None:
    """Return the active profile dict, or None if no profiles configured."""
    slug = cfg.get("active_profile")
    if not slug:
        return None
    return cfg.get("profiles", {}).get(slug)


def set_active_profile(cfg: dict[str, Any], slug: str) -> None:
    """Set active profile by slug. Raises KeyError if slug doesn't exist."""
    if slug not in cfg.get("profiles", {}):
        raise KeyError(f"No profile with slug {slug!r}")
    cfg["active_profile"] = slug


def add_profile(cfg: dict[str, Any], slug: str, profile: dict[str, Any]) -> None:
    """Add a profile. Sets it as active if it's the first one."""
    cfg.setdefault("profiles", {})[slug] = profile
    if not cfg.get("active_profile"):
        cfg["active_profile"] = slug


def delete_profile(cfg: dict[str, Any], slug: str) -> None:
    """Delete a profile. If it was active, falls back to first remaining profile."""
    cfg.get("profiles", {}).pop(slug, None)
    if cfg.get("active_profile") == slug:
        cfg["active_profile"] = next(iter(cfg.get("profiles", {})), "")


def resolve_output_dir(cfg: dict[str, Any]) -> Path:
    """Resolve the configured output_dir to an absolute Path."""
    raw = cfg.get("output_dir") or "./output"
    p = Path(raw)
    if not p.is_absolute():
        p = BASE_DIR / p
    return p


def is_first_run(cfg: dict[str, Any]) -> bool:
    """True if the config has no workspace profiles — i.e. user should see the wizard."""
    return not cfg.get("profiles")


def apply_theme_from_cfg(cfg: dict[str, Any]) -> None:
    """Apply the configured theme to the runtime palette before UI builds."""
    from .constants import apply_theme
    theme = (cfg.get("theme") or "light").lower()
    apply_theme(dark=(theme == "dark"))
