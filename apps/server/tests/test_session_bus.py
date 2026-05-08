import pytest

from ntrp.events.sse import ThinkingEvent
from ntrp.server.bus import BusRegistry, SessionBus


def _seqs(records):
    return [record.seq for record in records]


def _events(records):
    return [record.event for record in records]


@pytest.mark.asyncio
async def test_session_bus_closes_slow_subscriber_without_blocking_fast_one():
    bus = SessionBus(session_id="sess-1", subscriber_queue_size=2)
    slow = bus.subscribe()
    fast = bus.subscribe()

    first = ThinkingEvent(status="one")
    second = ThinkingEvent(status="two")
    third = ThinkingEvent(status="three")

    await bus.emit(first)
    assert fast.get_nowait().event == first

    await bus.emit(second)
    assert fast.get_nowait().event == second

    await bus.emit(third)

    assert slow not in bus._subscribers
    assert slow.get_nowait() is None
    assert fast.get_nowait().event == third


def test_bus_registry_close_all_handles_full_subscriber_queues():
    registry = BusRegistry()
    bus = registry.get_or_create("sess-1")
    queue = bus.subscribe()

    for i in range(bus.subscriber_queue_size):
        queue.put_nowait(ThinkingEvent(status=str(i)))

    registry.close_all_sync()

    assert queue.get_nowait() is None
    assert bus._subscribers == []


@pytest.mark.asyncio
async def test_subscribe_with_replay_returns_buffered_records_to_new_subscribers():
    bus = SessionBus(session_id="sess-1")
    a, b, c = ThinkingEvent(status="a"), ThinkingEvent(status="b"), ThinkingEvent(status="c")
    await bus.emit(a)
    await bus.emit(b)
    await bus.emit(c)

    snapshot, queue = bus.subscribe_with_replay()
    assert _seqs(snapshot) == [1, 2, 3]
    assert _events(snapshot) == [a, b, c]
    # The queue is for events emitted AFTER subscribe, not the buffer.
    assert queue.empty()

    # Live event after subscribe lands on the queue, not the snapshot.
    d = ThinkingEvent(status="d")
    await bus.emit(d)
    record = queue.get_nowait()
    assert record.seq == 4
    assert record.event == d


@pytest.mark.asyncio
async def test_subscribe_with_replay_after_seq_returns_only_later_records():
    bus = SessionBus(session_id="sess-1")
    await bus.emit(ThinkingEvent(status="a"))
    await bus.emit(ThinkingEvent(status="b"))
    await bus.emit(ThinkingEvent(status="c"))

    snapshot, queue = bus.subscribe_with_replay(after_seq=1)

    assert _seqs(snapshot) == [2, 3]
    assert [record.event.status for record in snapshot] == ["b", "c"]
    assert queue.empty()


@pytest.mark.asyncio
async def test_clear_buffer_drops_replay_state_without_resetting_sequence():
    """Buffer is wiped at every checkpoint save so disk and buffer never
    overlap. After clear, new subscribers get no replay — only live."""
    bus = SessionBus(session_id="sess-1")
    await bus.emit(ThinkingEvent(status="before-save"))

    bus.clear_buffer()  # checkpoint just saved messages to disk

    snapshot, queue = bus.subscribe_with_replay()
    assert snapshot == []
    after = ThinkingEvent(status="after-save")
    await bus.emit(after)
    record = queue.get_nowait()
    assert record.seq == 2
    assert record.event == after


@pytest.mark.asyncio
async def test_existing_subscribers_keep_receiving_after_clear_buffer():
    """clear_buffer only affects the replay snapshot for FUTURE subscribers;
    live subscribers' queues are not touched."""
    bus = SessionBus(session_id="sess-1")
    queue = bus.subscribe()
    await bus.emit(ThinkingEvent(status="one"))
    bus.clear_buffer()
    await bus.emit(ThinkingEvent(status="two"))

    assert queue.get_nowait().event.status == "one"
    assert queue.get_nowait().event.status == "two"


@pytest.mark.asyncio
async def test_emit_save_clear_subscribe_invariant():
    """The 'no overlap' invariant: events emitted before the checkpoint
    only appear on disk, events emitted after only appear in the buffer.
    Reconnects compose the two without seeing duplicates."""
    bus = SessionBus(session_id="sess-1")

    # Step 1: events fly during a step.
    await bus.emit(ThinkingEvent(status="step1-a"))
    await bus.emit(ThinkingEvent(status="step1-b"))

    # Checkpoint fires: caller saves messages to disk, then wipes buffer.
    bus.clear_buffer()

    # Step 2: more events.
    e3 = ThinkingEvent(status="step2-a")
    await bus.emit(e3)

    # New subscriber gets ONLY the post-clear events.
    snapshot, _q = bus.subscribe_with_replay()
    assert _seqs(snapshot) == [3]
    assert _events(snapshot) == [e3]


@pytest.mark.asyncio
async def test_buffer_overflow_drops_oldest_silently():
    """The deque's maxlen is sized to cover a single research turn's worth
    of nested events. If a run somehow blows past that, the oldest entries
    are dropped silently — replay sees only the tail. Documented behavior;
    the bump from 2k to 10k makes this rare in practice but the failure
    mode (orphaned tool-call events on the client) is on us if it hits."""
    from ntrp.server.bus import RECENT_BUFFER_MAX

    bus = SessionBus(session_id="sess-1")
    overflow = RECENT_BUFFER_MAX + 50
    for i in range(overflow):
        await bus.emit(ThinkingEvent(status=f"e{i}"))

    snapshot, _q = bus.subscribe_with_replay()
    assert len(snapshot) == RECENT_BUFFER_MAX
    # Oldest events are gone; tail is preserved.
    assert snapshot[0].event.status == f"e{overflow - RECENT_BUFFER_MAX}"
    assert snapshot[-1].event.status == f"e{overflow - 1}"
