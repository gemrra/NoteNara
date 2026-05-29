"""Telegram notification service — optional.

Replaces the n8n Telegram Notify node. The pipeline calls send() unconditionally;
if the client was constructed disabled, the call is a silent no-op so the rest
of the pipeline keeps flowing.
"""

from __future__ import annotations

import requests


class TelegramClient:
    """Send formatted meeting notifications via the Telegram Bot API.

    Args:
        bot_token: Bot token from @BotFather
        chat_id:   Target chat (your own user ID for personal notifications)
        enabled:   When False, send() is a no-op — set this from config so
                   pipeline code doesn't need its own conditional.
    """

    def __init__(self, bot_token: str = "", chat_id: str = "",
                 enabled: bool = False, timeout: int = 10):
        self.bot_token = (bot_token or "").strip()
        self.chat_id = (chat_id or "").strip()
        self.enabled = enabled and bool(self.bot_token) and bool(self.chat_id)
        self.timeout = timeout

    def send_meeting_notification(
        self,
        title: str,
        summary_short: str,
        page_url: str,
        n_actions: int,
    ) -> bool:
        """Send the standard meeting summary message. Returns False if disabled or failed."""
        if not self.enabled:
            return False

        text = (
            f"🎙️ *Meeting notes saved!*\n\n"
            f"📁 *{_escape_md(title)}*\n\n"
            f"📋 {_escape_md(summary_short)}...\n\n"
            f"✅ *{n_actions} action item{'s' if n_actions != 1 else ''}*\n\n"
            f"🔗 {page_url}"
        )
        return self._send_message(text, parse_mode="Markdown")

    def send_text(self, text: str) -> bool:
        """Send a plain text message — used for ad-hoc errors or status."""
        if not self.enabled:
            return False
        return self._send_message(text, parse_mode=None)

    def _send_message(self, text: str, parse_mode: str | None) -> bool:
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload: dict[str, str | int] = {"chat_id": self.chat_id, "text": text}
        if parse_mode:
            payload["parse_mode"] = parse_mode
        try:
            r = requests.post(url, json=payload, timeout=self.timeout)
        except requests.exceptions.RequestException:
            return False
        return r.status_code < 400


# Telegram Markdown (v1) only requires escaping a small set of chars in *text*
# positions (asterisk would terminate the bold span). We pre-process the
# user-supplied bits before injecting them into the template.
_MD_ESCAPE = str.maketrans({"*": "\\*", "_": "\\_", "`": "\\`", "[": "\\["})


def _escape_md(s: str) -> str:
    return (s or "").translate(_MD_ESCAPE)
