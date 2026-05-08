import asyncio
import json
from collections import deque
from dataclasses import InitVar, dataclass, field

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
    session_id: str
    event: SSEEvent


@dataclass(frozen=True, slots=True)
class ReplaySubscription:
    snapshot: list[StreamRecord]
    queue: asyncio.Queue[StreamRecord | None]
    replay_gap: bool = False

    def __iter__(self):
        yield self.snapshot
        yield self.queue


def stream_record_to_sse_string(session_id: str, record: StreamRecord) -> str:
    sse = record.event.to_sse()
    payload = json.loads(sse["data"])
    payload["seq"] = record.seq
    payload["session_id"] = record.session_id
    return f"id: {record.seq}\nevent: {sse['event']}\ndata: {json.dumps(payload)}\n\n"


@dataclass
class SessionBus:
    session_id: str
    subscriber_queue_size: int = SSE_QUEUE_MAXSIZE
    initial_next_seq: InitVar[int] = 1
    _subscribers: list[asyncio.Queue[StreamRecord | None]] = field(default_factory=list)
    _next_seq: int = field(default=1, init=False)
    # Replay buffer for events emitted since the last `clear_buffer()`.
    # Paired with checkpoint saves: every `on_step_finish` (and the final
    # save in chat.py) commits messages to disk and then wipes this. So
    # disk holds everything up to the last checkpoint and the buffer
    # holds everything since — together they reconstruct current state
    # without overlap, no cursor needed.
    _recent: deque[StreamRecord] = field(default_factory=lambda: deque(maxlen=RECENT_BUFFER_MAX))

    def __post_init__(self, initial_next_seq: int) -> None:
        self._next_seq = initial_next_seq

    @property
    def next_seq(self) -> int:
        return self._next_seq

    async def emit(self, event: SSEEvent) -> None:
        record = StreamRecord(seq=self._next_seq, session_id=self.session_id, event=event)
        self._next_seq += 1
        self._recent.append(record)
        for queue in tuple(self._subscribers):
            try:
                queue.put_nowait(record)
            except asyncio.QueueFull:
                self._close_slow_subscriber(queue)

    def subscribe_with_replay(
        self, after_seq: int | None = None
    ) -> ReplaySubscription:
        """Atomically snapshot the replay buffer AND register a live queue.
        emit() never awaits, so no event can interleave between snapshot and
        queue registration."""
        if after_seq is None:
            snapshot = list(self._recent)
            replay_gap = False
        else:
            snapshot = [record for record in self._recent if record.seq > after_seq]
            replay_gap = self._has_replay_gap(after_seq)
        queue: asyncio.Queue[StreamRecord | None] = asyncio.Queue(maxsize=self.subscriber_queue_size)
        self._subscribers.append(queue)
        return ReplaySubscription(snapshot=snapshot, queue=queue, replay_gap=replay_gap)

    def _has_replay_gap(self, after_seq: int) -> bool:
        if self._recent:
            return after_seq < self._recent[0].seq - 1
        return after_seq < self._next_seq - 1

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
        self._next_seq_by_session: dict[str, int] = {}

    def get_or_create(self, session_id: str) -> SessionBus:
        if session_id not in self._buses:
            self._buses[session_id] = SessionBus(
                session_id=session_id,
                initial_next_seq=self._next_seq_by_session.get(session_id, 1),
            )
        return self._buses[session_id]

    def get(self, session_id: str) -> SessionBus | None:
        return self._buses.get(session_id)

    def remove(self, session_id: str) -> None:
        bus = self._buses.pop(session_id, None)
        if bus:
            self._next_seq_by_session[session_id] = bus.next_seq

    def close_all_sync(self) -> None:
        for bus in self._buses.values():
            self._next_seq_by_session[bus.session_id] = bus.next_seq
            bus.close_all_sync()

    async def close_all(self) -> None:
        self.close_all_sync()
        self._buses.clear()
