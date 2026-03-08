import asyncio
from dataclasses import dataclass, field

from ntrp.events.sse import SSEEvent


@dataclass
class SessionBus:
    session_id: str
    _queue: asyncio.Queue[SSEEvent | None] = field(default_factory=asyncio.Queue)

    async def emit(self, event: SSEEvent) -> None:
        await self._queue.put(event)

    async def get(self, timeout: float = 0.5) -> SSEEvent | None:
        try:
            return await asyncio.wait_for(self._queue.get(), timeout=timeout)
        except TimeoutError:
            return None


class BusRegistry:
    def __init__(self):
        self._buses: dict[str, SessionBus] = {}

    def get_or_create(self, session_id: str) -> SessionBus:
        if session_id not in self._buses:
            self._buses[session_id] = SessionBus(session_id=session_id)
        return self._buses[session_id]

    def get(self, session_id: str) -> SessionBus | None:
        return self._buses.get(session_id)

    def remove(self, session_id: str) -> None:
        self._buses.pop(session_id, None)
