import pytest

from ntrp.events.sse import ThinkingEvent
from ntrp.server.bus import BusRegistry, SessionBus


@pytest.mark.asyncio
async def test_session_bus_closes_slow_subscriber_without_blocking_fast_one():
    bus = SessionBus(session_id="sess-1", subscriber_queue_size=2)
    slow = bus.subscribe()
    fast = bus.subscribe()

    first = ThinkingEvent(status="one")
    second = ThinkingEvent(status="two")
    third = ThinkingEvent(status="three")

    await bus.emit(first)
    assert fast.get_nowait() == first

    await bus.emit(second)
    assert fast.get_nowait() == second

    await bus.emit(third)

    assert slow not in bus._subscribers
    assert slow.get_nowait() is None
    assert fast.get_nowait() == third


def test_bus_registry_close_all_handles_full_subscriber_queues():
    registry = BusRegistry()
    bus = registry.get_or_create("sess-1")
    queue = bus.subscribe()

    for i in range(bus.subscriber_queue_size):
        queue.put_nowait(ThinkingEvent(status=str(i)))

    registry.close_all_sync()

    assert queue.get_nowait() is None
    assert bus._subscribers == []
