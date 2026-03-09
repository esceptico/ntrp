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
        self.shutdown_event: asyncio.Event = asyncio.Event()
        self._active_streams: int = 0
        self._all_streams_done: asyncio.Event = asyncio.Event()
        self._all_streams_done.set()

    def stream_started(self) -> None:
        self._active_streams += 1
        self._all_streams_done.clear()

    def stream_stopped(self) -> None:
        self._active_streams -= 1
        if self._active_streams == 0:
            self._all_streams_done.set()

    async def wait_streams_done(self, timeout: float = 2.0) -> None:
        try:
            await asyncio.wait_for(self._all_streams_done.wait(), timeout)
        except TimeoutError:
            pass

    def get_or_create(self, session_id: str) -> SessionBus:
        if session_id not in self._buses:
            self._buses[session_id] = SessionBus(session_id=session_id)
        return self._buses[session_id]

    def get(self, session_id: str) -> SessionBus | None:
        return self._buses.get(session_id)

    def remove(self, session_id: str) -> None:
        self._buses.pop(session_id, None)
