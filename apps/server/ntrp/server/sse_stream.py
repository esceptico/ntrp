import asyncio
import json
import time
from collections.abc import AsyncGenerator, Callable, Iterable

from ntrp.events.sse import KeepaliveEvent, SSEEvent, StreamResetEvent
from ntrp.server.bus import SessionBus, StreamRecord, stream_record_to_sse_string

ShouldEmit = Callable[[SSEEvent], bool]


def keepalive_chunk(session_id: str, latest_seq: int) -> str:
    event = KeepaliveEvent(session_id=session_id, latest_seq=latest_seq)
    sse = event.to_sse()
    payload = {
        **json.loads(sse["data"]),
        "seq": latest_seq,
        "session_id": session_id,
    }
    return f"id: {latest_seq}\nevent: {sse['event']}\ndata: {json.dumps(payload)}\n\n"


def reset_chunk(session_id: str, reason: str, seq: int) -> str:
    reset_record = StreamRecord(
        seq=max(0, seq),
        session_id=session_id,
        event=StreamResetEvent(reason=reason),
    )
    return stream_record_to_sse_string(session_id, reset_record)


async def replay_records(
    session_id: str,
    records: Iterable[StreamRecord],
    *,
    should_emit: ShouldEmit,
) -> AsyncGenerator[str]:
    for record in records:
        if not should_emit(record.event):
            continue
        yield stream_record_to_sse_string(session_id, record, replay=True)
        await asyncio.sleep(0)


async def live_records(
    *,
    bus: SessionBus,
    queue: asyncio.Queue[StreamRecord | None],
    session_id: str,
    should_emit: ShouldEmit,
    keepalive_interval: float,
    replay_upper_seq: int | None = None,
) -> AsyncGenerator[str]:
    last_event_at = time.monotonic()

    while True:
        try:
            record = await asyncio.wait_for(queue.get(), timeout=0.5)
        except TimeoutError:
            if time.monotonic() - last_event_at >= keepalive_interval:
                last_event_at = time.monotonic()
                yield keepalive_chunk(session_id, bus.next_seq - 1)
            continue

        if record is None:
            break

        if (
            replay_upper_seq is not None
            and record.seq <= replay_upper_seq
            and not isinstance(record.event, StreamResetEvent)
        ):
            continue

        event = record.event
        if not should_emit(event):
            last_event_at = time.monotonic()
            continue

        last_event_at = time.monotonic()
        yield stream_record_to_sse_string(session_id, record)
        if isinstance(event, StreamResetEvent):
            break
        await asyncio.sleep(0)
