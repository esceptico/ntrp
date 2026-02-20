import asyncio
from typing import Any

from ntrp.notifiers.base import Notifier


class EmailNotifier(Notifier):
    channel = "email"

    @classmethod
    def from_config(cls, config: dict, runtime: Any) -> "EmailNotifier":
        return cls(runtime=runtime, from_account=config["from_account"], to_address=config["to_address"])

    def __init__(self, runtime: Any, from_account: str, to_address: str):
        self._runtime = runtime
        self._from_account = from_account
        self._to_address = to_address

    async def send(self, subject: str, body: str) -> None:
        gmail = self._runtime.source_mgr.sources.get("gmail")
        if not gmail:
            raise RuntimeError("Gmail source not available")

        await asyncio.to_thread(
            gmail.send_email,
            account=self._from_account,
            to=self._to_address,
            subject=subject,
            body=body,
            html=True,
        )
