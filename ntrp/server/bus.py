import asyncio
from dataclasses import dataclass, field

from ntrp.events.sse import SSEEvent


@dataclass
class SessionBus:
    session_id: str
    _subscribers: list[asyncio.Queue[SSEEvent | None]] = field(default_factory=list)

    async def emit(self, event: SSEEvent) -> None:
        for queue in self._subscribers:
            await queue.put(event)

    def subscribe(self) -> asyncio.Queue[SSEEvent | None]:
        queue: asyncio.Queue[SSEEvent | None] = asyncio.Queue()
        self._subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[SSEEvent | None]) -> None:
        try:
            self._subscribers.remove(queue)
        except ValueError:
            pass


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

    def close_all_sync(self) -> None:
        for bus in self._buses.values():
            for queue in bus._subscribers:
                queue.put_nowait(None)

    async def close_all(self) -> None:
        self.close_all_sync()
        self._buses.clear()
