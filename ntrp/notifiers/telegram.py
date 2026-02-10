import aiohttp

from ntrp.logging import get_logger

_logger = get_logger(__name__)


class TelegramNotifier:
    channel = "telegram"

    def __init__(self, token: str, user_id: str):
        self._token = token
        self._user_id = user_id

    async def send(self, subject: str, body: str) -> None:
        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        text = f"<b>{subject}</b>\n\n{body}"
        payload = {"chat_id": self._user_id, "text": text, "parse_mode": "HTML"}

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    detail = await resp.text()
                    _logger.error("Telegram send failed (%d): %s", resp.status, detail)
