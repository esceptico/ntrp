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
async def test_bus_registry_records_emitted_events():
    recorded = []

    async def record_event(record):
        recorded.append(record)

    registry = BusRegistry(record_event=record_event)
    bus = registry.get_or_create("sess-1")
    await bus.emit(ThinkingEvent(status="saved"))

    assert len(recorded) == 1
    assert recorded[0].seq == 1
    assert recorded[0].session_id == "sess-1"
    assert recorded[0].event.status == "saved"


@pytest.mark.asyncio
async def test_bus_registry_preserves_sequence_when_session_bus_is_recreated():
    registry = BusRegistry()
    first_bus = registry.get_or_create("sess-1")
    await first_bus.emit(ThinkingEvent(status="first"))
    assert first_bus._recent[-1].seq == 1

    registry.remove("sess-1")

    second_bus = registry.get_or_create("sess-1")
    queue = second_bus.subscribe()
    second = ThinkingEvent(status="second")
    await second_bus.emit(second)

    record = queue.get_nowait()
    assert record.seq == 2
    assert record.event == second


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
async def test_subscribe_with_replay_reports_gap_for_cursor_below_checkpoint():
    bus = SessionBus(session_id="sess-1")
    await bus.emit(ThinkingEvent(status="a"))
    await bus.emit(ThinkingEvent(status="b"))
    bus.mark_checkpoint()
    await bus.emit(ThinkingEvent(status="c"))

    subscription = bus.subscribe_with_replay(after_seq=1)
    snapshot, queue = subscription

    assert subscription.replay_gap is True
    # Only post-checkpoint events are replayed; client must reload history.
    assert _seqs(snapshot) == [3]
    assert queue.empty()


@pytest.mark.asyncio
async def test_subscribe_with_replay_reports_gap_for_future_cursor():
    bus = SessionBus(session_id="sess-1")
    await bus.emit(ThinkingEvent(status="a"))

    subscription = bus.subscribe_with_replay(after_seq=44)
    snapshot, queue = subscription

    assert subscription.replay_gap is True
    assert snapshot == []
    assert queue.empty()


def test_recreated_empty_bus_reports_gap_above_checkpoint():
    bus = SessionBus(session_id="sess-1", initial_next_seq=8, initial_checkpoint_seq=4)

    subscription = bus.subscribe_with_replay(after_seq=4)

    assert subscription.replay_gap is True
    assert subscription.snapshot == []


@pytest.mark.asyncio
async def test_subscribe_with_replay_reports_no_gap_for_satisfiable_cursor():
    bus = SessionBus(session_id="sess-1")
    await bus.emit(ThinkingEvent(status="a"))
    await bus.emit(ThinkingEvent(status="b"))
    await bus.emit(ThinkingEvent(status="c"))

    subscription = bus.subscribe_with_replay(after_seq=1)
    snapshot, queue = subscription

    assert subscription.replay_gap is False
    assert _seqs(snapshot) == [2, 3]
    assert queue.empty()


@pytest.mark.asyncio
async def test_subscribe_with_replay_reports_no_gap_without_cursor():
    bus = SessionBus(session_id="sess-1")
    await bus.emit(ThinkingEvent(status="a"))
    bus.mark_checkpoint()
    await bus.emit(ThinkingEvent(status="b"))

    subscription = bus.subscribe_with_replay()
    snapshot, queue = subscription

    assert subscription.replay_gap is False
    # Without cursor, only post-checkpoint events are replayed (the live
    # tail). Pre-checkpoint events are on disk and the client is expected
    # to reach those via the history endpoint.
    assert _seqs(snapshot) == [2]
    assert queue.empty()


@pytest.mark.asyncio
async def test_subscribe_with_replay_no_gap_for_cursor_at_or_above_checkpoint():
    """The fast-path tab-switch case: client comes back with a cursor
    that's >= the latest checkpoint. We just ship the buffered tail and
    don't force a history reload, even though a checkpoint fired while
    the client was away."""
    bus = SessionBus(session_id="sess-1")
    await bus.emit(ThinkingEvent(status="a"))
    await bus.emit(ThinkingEvent(status="b"))
    bus.mark_checkpoint()  # checkpoint at seq=2
    await bus.emit(ThinkingEvent(status="c"))
    await bus.emit(ThinkingEvent(status="d"))

    # Cursor at the checkpoint: smooth replay, no gap.
    subscription = bus.subscribe_with_replay(after_seq=2)
    assert subscription.replay_gap is False
    assert _seqs(subscription.snapshot) == [3, 4]

    # Cursor above the checkpoint: same.
    subscription = bus.subscribe_with_replay(after_seq=3)
    assert subscription.replay_gap is False
    assert _seqs(subscription.snapshot) == [4]


@pytest.mark.asyncio
async def test_mark_checkpoint_keeps_events_in_buffer():
    """Unlike the prior clear_buffer behavior, mark_checkpoint leaves the
    buffer intact. This lets clients with cursors right at the checkpoint
    see the pre-checkpoint events in their queue (they won't, because the
    snapshot filters by max(after_seq, checkpoint_seq), but emit() to
    existing subscribers is unaffected and the deque retains everything
    until it overflows)."""
    bus = SessionBus(session_id="sess-1")
    await bus.emit(ThinkingEvent(status="a"))
    await bus.emit(ThinkingEvent(status="b"))
    bus.mark_checkpoint()
    await bus.emit(ThinkingEvent(status="c"))

    assert _seqs(list(bus._recent)) == [1, 2, 3]
    assert bus.checkpoint_seq == 2


@pytest.mark.asyncio
async def test_existing_subscribers_keep_receiving_after_checkpoint():
    """mark_checkpoint only affects future subscribers' replay snapshot
    boundary; live subscribers' queues are not touched."""
    bus = SessionBus(session_id="sess-1")
    queue = bus.subscribe()
    await bus.emit(ThinkingEvent(status="one"))
    bus.mark_checkpoint()
    await bus.emit(ThinkingEvent(status="two"))

    assert queue.get_nowait().event.status == "one"
    assert queue.get_nowait().event.status == "two"


@pytest.mark.asyncio
async def test_emit_checkpoint_subscribe_invariant():
    """A new subscriber attached after a checkpoint only sees post-
    checkpoint events in its replay snapshot. Pre-checkpoint events are
    in the buffer but filtered out — the client is expected to fetch
    them via history."""
    bus = SessionBus(session_id="sess-1")

    await bus.emit(ThinkingEvent(status="step1-a"))
    await bus.emit(ThinkingEvent(status="step1-b"))
    bus.mark_checkpoint()
    e3 = ThinkingEvent(status="step2-a")
    await bus.emit(e3)

    snapshot, _q = bus.subscribe_with_replay()
    assert _seqs(snapshot) == [3]
    assert _events(snapshot) == [e3]


@pytest.mark.asyncio
async def test_bus_registry_preserves_checkpoint_seq_across_recreation():
    registry = BusRegistry()
    bus = registry.get_or_create("sess-1")
    await bus.emit(ThinkingEvent(status="a"))
    await bus.emit(ThinkingEvent(status="b"))
    bus.mark_checkpoint()
    assert bus.checkpoint_seq == 2

    registry.remove("sess-1")
    recreated = registry.get_or_create("sess-1")
    assert recreated.checkpoint_seq == 2
    # next_seq is also preserved.
    assert recreated.next_seq == 3


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
