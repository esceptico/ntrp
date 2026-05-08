import asyncio
from collections import deque
from dataclasses import dataclass, field

from ntrp.events.sse import SSEEvent

SSE_QUEUE_MAXSIZE = 256
# Sized for a single research turn that fans out to ~150 nested tool
# calls (each emits START + ARGS + END + RESULT = 4 events, plus text
# deltas). Below this, an overflowing run loses early TOOL_CALL_START
# events; the client then sees orphaned ARGS/END/RESULT and the tool
# silently disappears from the activity panel. ~10k events × ~200B =
# ~2MB per active session, which is fine for a single-user app.
RECENT_BUFFER_MAX = 10000


@dataclass(frozen=True, slots=True)
class StreamRecord:
    seq: int
    event: SSEEvent


@dataclass
class SessionBus:
    session_id: str
    subscriber_queue_size: int = SSE_QUEUE_MAXSIZE
    _subscribers: list[asyncio.Queue[StreamRecord | None]] = field(default_factory=list)
    _next_seq: int = field(default=1, init=False)
    # Replay buffer for events emitted since the last `clear_buffer()`.
    # Paired with checkpoint saves: every `on_step_finish` (and the final
    # save in chat.py) commits messages to disk and then wipes this. So
    # disk holds everything up to the last checkpoint and the buffer
    # holds everything since — together they reconstruct current state
    # without overlap, no cursor needed.
    _recent: deque[StreamRecord] = field(default_factory=lambda: deque(maxlen=RECENT_BUFFER_MAX))

    async def emit(self, event: SSEEvent) -> None:
        record = StreamRecord(seq=self._next_seq, event=event)
        self._next_seq += 1
        self._recent.append(record)
        for queue in tuple(self._subscribers):
            try:
                queue.put_nowait(record)
            except asyncio.QueueFull:
                self._close_slow_subscriber(queue)

    def subscribe_with_replay(
        self, after_seq: int | None = None
    ) -> tuple[list[StreamRecord], asyncio.Queue[StreamRecord | None]]:
        """Atomically snapshot the replay buffer AND register a live queue.
        emit() never awaits, so no event can interleave between snapshot and
        queue registration."""
        if after_seq is None:
            snapshot = list(self._recent)
        else:
            snapshot = [record for record in self._recent if record.seq > after_seq]
        queue: asyncio.Queue[StreamRecord | None] = asyncio.Queue(maxsize=self.subscriber_queue_size)
        self._subscribers.append(queue)
        return snapshot, queue

    def subscribe(self) -> asyncio.Queue[StreamRecord | None]:
        """Live-only subscription — for feeds that don't replay (e.g. the
        global automation stream)."""
        queue: asyncio.Queue[StreamRecord | None] = asyncio.Queue(maxsize=self.subscriber_queue_size)
        self._subscribers.append(queue)
        return queue

    def clear_buffer(self) -> None:
        """Drop every buffered event. Called by the chat service right
        after each checkpoint save so the buffer never holds events that
        are also on disk (which would re-apply on reconnect)."""
        self._recent.clear()

    def unsubscribe(self, queue: asyncio.Queue[StreamRecord | None]) -> None:
        try:
            self._subscribers.remove(queue)
        except ValueError:
            pass

    def close_all_sync(self) -> None:
        for queue in tuple(self._subscribers):
            self.unsubscribe(queue)
            self._close_queue(queue)

    def _close_slow_subscriber(self, queue: asyncio.Queue[StreamRecord | None]) -> None:
        self.unsubscribe(queue)
        self._close_queue(queue)

    @staticmethod
    def _close_queue(queue: asyncio.Queue[StreamRecord | None]) -> None:
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
