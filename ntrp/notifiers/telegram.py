import aiohttp
import markdown as md

from ntrp.logging import get_logger

_logger = get_logger(__name__)

_converter = md.Markdown(extensions=["extra"])


def _md_to_html(text: str) -> str:
    _converter.reset()
    html = _converter.convert(text)
    # strip wrapping <p> tags for flat messages
    html = html.replace("<p>", "").replace("</p>", "\n").strip()
    return html


def _escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class TelegramNotifier:
    channel = "telegram"

    def __init__(self, token: str, user_id: str):
        self._token = token
        self._user_id = user_id

    async def send(self, subject: str, body: str) -> None:
        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        text = f"<b>{_escape_html(subject)}</b>\n\n{_md_to_html(body)}"
        payload = {"chat_id": self._user_id, "text": text, "parse_mode": "HTML"}

        async with aiohttp.ClientSession() as session, session.post(url, json=payload) as resp:
            if resp.status != 200:
                detail = await resp.text()
                _logger.error("Telegram send failed (%d): %s", resp.status, detail)
