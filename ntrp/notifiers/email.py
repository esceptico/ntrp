import asyncio
from collections.abc import Callable

from ntrp.logging import get_logger

_logger = get_logger(__name__)


class EmailNotifier:
    channel = "email"

    def __init__(self, gmail: Callable, from_account: str, to_address: str):
        self._gmail = gmail
        self._from_account = from_account
        self._to_address = to_address

    async def send(self, subject: str, body: str) -> None:
        source = self._gmail()
        if not source:
            _logger.warning("Email notifier: gmail source unavailable")
            return

        await asyncio.to_thread(
            source.send_email,
            account=self._from_account,
            to=self._to_address,
            subject=subject,
            body=body,
            html=True,
        )
