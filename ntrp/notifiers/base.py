from typing import Protocol


class Notifier(Protocol):
    channel: str

    async def send(self, subject: str, body: str) -> None: ...
