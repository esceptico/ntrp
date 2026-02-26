import asyncio
from datetime import UTC, datetime, timedelta

from ntrp.channel import Channel
from ntrp.constants import (
    MONITOR_CALENDAR_DAYS,
    MONITOR_CALENDAR_LIMIT,
    MONITOR_EVENT_APPROACHING_HORIZON_MINUTES,
    MONITOR_POLL_INTERVAL,
)
from ntrp.events.triggers import EventApproaching
from ntrp.logging import get_logger
from ntrp.monitor.store import MonitorStateStore
from ntrp.sources.base import CalendarSource

_logger = get_logger(__name__)


class CalendarMonitor:
    """Polls calendar data and publishes EventApproaching trigger events."""

    def __init__(self, source: CalendarSource, state_store: MonitorStateStore):
        self._source = source
        self._state_store = state_store
        self._channel: Channel | None = None
        self._task: asyncio.Task | None = None

    def start(self, channel: Channel) -> None:
        if self._task is not None and not self._task.done():
            return
        self._channel = channel
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        finally:
            self._task = None

    async def _run(self) -> None:
        await self._loop()

    async def _loop(self) -> None:
        while True:
            events = await asyncio.to_thread(self._poll)
            if self._channel:
                for event in events:
                    self._channel.publish(event)
            await asyncio.sleep(MONITOR_POLL_INTERVAL)

    def _poll(self) -> list[EventApproaching]:
        now = datetime.now(UTC)
        horizon = now + timedelta(minutes=MONITOR_EVENT_APPROACHING_HORIZON_MINUTES)
        events: list[EventApproaching] = []

        try:
            items = self._source.get_upcoming(days=MONITOR_CALENDAR_DAYS, limit=MONITOR_CALENDAR_LIMIT)
        except (OSError, ValueError) as e:
            _logger.warning("Failed to fetch upcoming calendar events: %s", e)
            return events
        except Exception:
            _logger.exception("Unexpected error while polling upcoming calendar events")
            return events

        for item in items:
            start = self._parse_start(item.metadata.get("start"))
            if start is None or start < now or start > horizon:
                continue

            minutes_until = max(0, int((start - now).total_seconds() / 60))
            event = EventApproaching(
                event_id=item.source_id,
                summary=item.title,
                start=start,
                minutes_until=minutes_until,
                location=item.metadata.get("location"),
                attendees=tuple(item.metadata.get("attendees", [])),
            )
            events.append(event)
            _logger.info("Event approaching: %s in %d min", item.title, minutes_until)

        return events

    @staticmethod
    def _parse_start(raw_start: str | None) -> datetime | None:
        if not raw_start:
            return None
        try:
            start = datetime.fromisoformat(raw_start)
        except ValueError:
            return None
        if start.tzinfo is None:
            return start.replace(tzinfo=UTC)
        return start.astimezone(UTC)
