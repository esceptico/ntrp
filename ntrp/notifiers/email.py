import asyncio
from collections.abc import Callable

from ntrp.logging import get_logger

_logger = get_logger(__name__)


class EmailNotifier:
    channel = "email"

    def __init__(self, gmail: Callable):
        self._gmail = gmail

    async def send(self, subject: str, body: str) -> None:
        source = self._gmail()
        if not source:
            _logger.warning("Email notifier: gmail source unavailable")
            return

        accounts = source.list_accounts()
        if not accounts:
            _logger.warning("Email notifier: no gmail accounts configured")
            return

        await asyncio.to_thread(
            source.send_email,
            account=accounts[0],
            to=accounts[0],
            subject=subject,
            body=body,
            html=True,
        )
