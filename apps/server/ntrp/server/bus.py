import asyncio
import json
from collections import deque
from collections.abc import Awaitable, Callable
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


def stream_record_to_sse_string(session_id: str, record: StreamRecord, *, replay: bool = False) -> str:
    sse = record.event.to_sse()
    payload = json.loads(sse["data"])
    payload["seq"] = record.seq
    payload["session_id"] = record.session_id
    if replay:
        payload["replay"] = True
    return f"id: {record.seq}\nevent: {sse['event']}\ndata: {json.dumps(payload)}\n\n"


@dataclass
class SessionBus:
    session_id: str
    subscriber_queue_size: int = SSE_QUEUE_MAXSIZE
    initial_next_seq: InitVar[int] = 1
    initial_checkpoint_seq: InitVar[int] = 0
    record_event: Callable[[StreamRecord], Awaitable[None]] | None = None
    _subscribers: list[asyncio.Queue[StreamRecord | None]] = field(default_factory=list)
    _next_seq: int = field(default=1, init=False)
    # Highest seq that has been persisted to disk via session_service.save().
    # The buffer keeps every event regardless; this watermark just tells
    # reconnecting clients which side of the disk/buffer boundary their
    # cursor falls on. A cursor < _checkpoint_seq means the client missed
    # state that's now only on disk → stream_reset → history reload. A
    # cursor >= _checkpoint_seq means a clean buffered replay is enough.
    _checkpoint_seq: int = field(default=0, init=False)
    # Live replay buffer. Bounded by RECENT_BUFFER_MAX; oldest evicts on
    # overflow. Unlike the prior design, we don't clear at checkpoint —
    # so a fast reconnect after a step boundary stays in the buffered-
    # replay path instead of triggering a stream_reset + history reload.
    _recent: deque[StreamRecord] = field(default_factory=lambda: deque(maxlen=RECENT_BUFFER_MAX))

    def __post_init__(self, initial_next_seq: int, initial_checkpoint_seq: int) -> None:
        self._next_seq = initial_next_seq
        self._checkpoint_seq = initial_checkpoint_seq

    @property
    def next_seq(self) -> int:
        return self._next_seq

    @property
    def checkpoint_seq(self) -> int:
        return self._checkpoint_seq

    async def emit(self, event: SSEEvent) -> None:
        record = StreamRecord(seq=self._next_seq, session_id=self.session_id, event=event)
        self._next_seq += 1
        self._recent.append(record)
        if self.record_event:
            await self.record_event(record)
        for queue in tuple(self._subscribers):
            try:
                queue.put_nowait(record)
            except asyncio.QueueFull:
                self._close_slow_subscriber(queue)

    def mark_checkpoint(self) -> None:
        """Record that every event up to the latest emitted seq is now
        persisted to disk by the chat service. Reconnecting clients with
        a cursor below this point will be served a stream_reset so they
        rehydrate from history instead of the buffer (which may have
        evicted those events, and even if not, replaying them would
        double-apply over the freshly loaded history)."""
        self._checkpoint_seq = self._next_seq - 1

    def subscribe_with_replay(
        self, after_seq: int | None = None
    ) -> ReplaySubscription:
        """Atomically snapshot the replay buffer AND register a live queue.
        emit() never awaits, so no event can interleave between snapshot and
        queue registration.

        Replay snapshot only includes events with `seq > _checkpoint_seq`
        — events at or below the checkpoint are on disk and the client is
        expected to fetch them via the history endpoint, not replay."""
        live_floor = max(after_seq if after_seq is not None else 0, self._checkpoint_seq)
        snapshot = [record for record in self._recent if record.seq > live_floor]
        replay_gap = self._has_replay_gap(after_seq) if after_seq is not None else False
        queue: asyncio.Queue[StreamRecord | None] = asyncio.Queue(maxsize=self.subscriber_queue_size)
        self._subscribers.append(queue)
        return ReplaySubscription(snapshot=snapshot, queue=queue, replay_gap=replay_gap)

    def _has_replay_gap(self, after_seq: int) -> bool:
        newest_seq = self._next_seq - 1
        if after_seq > newest_seq:
            return True
        if after_seq < self._checkpoint_seq:
            return True
        # Buffer eviction can in theory leave a gap above the checkpoint
        # if a single step emits more events than RECENT_BUFFER_MAX. In
        # practice steps are far smaller than that, but we guard anyway.
        if self._recent and after_seq < self._recent[0].seq - 1:
            return True
        return False

    def subscribe(self) -> asyncio.Queue[StreamRecord | None]:
        """Live-only subscription — for feeds that don't replay (e.g. the
        global automation stream)."""
        queue: asyncio.Queue[StreamRecord | None] = asyncio.Queue(maxsize=self.subscriber_queue_size)
        self._subscribers.append(queue)
        return queue

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
    def __init__(
        self,
        *,
        record_event: Callable[[StreamRecord], Awaitable[None]] | None = None,
    ):
        self._buses: dict[str, SessionBus] = {}
        self._next_seq_by_session: dict[str, int] = {}
        self._checkpoint_seq_by_session: dict[str, int] = {}
        self._record_event = record_event

    def get_or_create(self, session_id: str) -> SessionBus:
        if session_id not in self._buses:
            self._buses[session_id] = SessionBus(
                session_id=session_id,
                initial_next_seq=self._next_seq_by_session.get(session_id, 1),
                initial_checkpoint_seq=self._checkpoint_seq_by_session.get(session_id, 0),
                record_event=self._record_event,
            )
        return self._buses[session_id]

    def remember_session_cursor(
        self,
        session_id: str,
        *,
        next_seq: int,
        checkpoint_seq: int | None = None,
    ) -> None:
        if session_id in self._buses:
            return
        self._next_seq_by_session[session_id] = max(next_seq, self._next_seq_by_session.get(session_id, 1))
        if checkpoint_seq is not None:
            self._checkpoint_seq_by_session[session_id] = max(
                checkpoint_seq,
                self._checkpoint_seq_by_session.get(session_id, 0),
            )

    def get(self, session_id: str) -> SessionBus | None:
        return self._buses.get(session_id)

    def remove(self, session_id: str) -> None:
        bus = self._buses.pop(session_id, None)
        if bus:
            self._next_seq_by_session[session_id] = bus.next_seq
            self._checkpoint_seq_by_session[session_id] = bus.checkpoint_seq

    def close_all_sync(self) -> None:
        for bus in self._buses.values():
            self._next_seq_by_session[bus.session_id] = bus.next_seq
            self._checkpoint_seq_by_session[bus.session_id] = bus.checkpoint_seq
            bus.close_all_sync()

    async def close_all(self) -> None:
        self.close_all_sync()
        self._buses.clear()
