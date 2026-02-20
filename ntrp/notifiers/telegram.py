from typing import Any

import aiohttp
import markdown as md

from ntrp.notifiers.base import Notifier


def _md_to_html(text: str) -> str:
    converter = md.Markdown(extensions=["extra"])
    html = converter.convert(text)
    html = html.replace("<p>", "").replace("</p>", "\n").strip()
    return html


def _escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class TelegramNotifier(Notifier):
    channel = "telegram"

    @classmethod
    def from_config(cls, config: dict, runtime: Any) -> "TelegramNotifier":
        return cls(runtime=runtime, user_id=config["user_id"])

    def __init__(self, runtime: Any, user_id: str):
        self._runtime = runtime
        self._user_id = user_id

    async def send(self, subject: str, body: str) -> None:
        token = self._runtime.config.telegram_bot_token
        if not token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN not set in config")

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        text = f"<b>{_escape_html(subject)}</b>\n\n{_md_to_html(body)}"
        payload = {"chat_id": self._user_id, "text": text, "parse_mode": "HTML"}

        async with aiohttp.ClientSession() as session, session.post(url, json=payload) as resp:
            if resp.status != 200:
                detail = await resp.text()
                raise RuntimeError(f"Telegram send failed ({resp.status}): {detail}")
