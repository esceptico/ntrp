import asyncio
from dataclasses import dataclass, field

from ntrp.events.sse import SSEEvent

SSE_QUEUE_MAXSIZE = 256


@dataclass
class SessionBus:
    session_id: str
    subscriber_queue_size: int = SSE_QUEUE_MAXSIZE
    _subscribers: list[asyncio.Queue[SSEEvent | None]] = field(default_factory=list)

    async def emit(self, event: SSEEvent) -> None:
        for queue in tuple(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                self._close_slow_subscriber(queue)

    def subscribe(self) -> asyncio.Queue[SSEEvent | None]:
        queue: asyncio.Queue[SSEEvent | None] = asyncio.Queue(maxsize=self.subscriber_queue_size)
        self._subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[SSEEvent | None]) -> None:
        try:
            self._subscribers.remove(queue)
        except ValueError:
            pass

    def close_all_sync(self) -> None:
        for queue in tuple(self._subscribers):
            self.unsubscribe(queue)
            self._close_queue(queue)

    def _close_slow_subscriber(self, queue: asyncio.Queue[SSEEvent | None]) -> None:
        self.unsubscribe(queue)
        self._close_queue(queue)

    @staticmethod
    def _close_queue(queue: asyncio.Queue[SSEEvent | None]) -> None:
        while True:
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        queue.put_nowait(None)


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
            bus.close_all_sync()

    async def close_all(self) -> None:
        self.close_all_sync()
        self._buses.clear()
