"""Discord webhook notification service — optional.

Discord webhooks are dead simple — POST a JSON `{"content": "..."}` to the
webhook URL. No bot token, no chat ID. Create one in Discord:
  Channel → Settings → Integrations → Webhooks → New Webhook → Copy URL
"""

from __future__ import annotations

import requests


class DiscordClient:
    """Send a formatted notification to a Discord channel via webhook.

    Args:
        webhook_url: full webhook URL from Discord channel settings.
        enabled: when False, send() is a no-op (pipeline calls it blindly).
        timeout: per-request HTTP timeout.
    """

    def __init__(self, webhook_url: str = "",
                 enabled: bool = False,
                 timeout: int = 10):
        self.webhook_url = (webhook_url or "").strip()
        self.enabled = enabled and bool(self.webhook_url)
        self.timeout = timeout

    def send_meeting_notification(
        self,
        title: str,
        summary_short: str,
        page_url: str,
        n_actions: int,
    ) -> bool:
        if not self.enabled:
            return False
        n_word = "item" if n_actions == 1 else "items"
        content = (
            f"🎙️  **Meeting notes saved!**\n"
            f"📁  **{title}**\n\n"
            f"📋  {summary_short}\n\n"
            f"✅  **{n_actions} action {n_word}**\n"
            f"🔗  {page_url}"
        )
        return self._post({"content": content})

    def send_text(self, text: str) -> bool:
        if not self.enabled:
            return False
        return self._post({"content": text})

    def _post(self, body: dict) -> bool:
        try:
            r = requests.post(self.webhook_url, json=body, timeout=self.timeout)
        except requests.exceptions.RequestException:
            return False
        return r.status_code < 400
