import asyncio
from datetime import UTC, datetime, timedelta

from ntrp.channel import Channel
from ntrp.constants import (
    MONITOR_CALENDAR_DAYS,
    MONITOR_CALENDAR_LIMIT,
    MONITOR_DEFAULT_LEAD_MINUTES,
    MONITOR_POLL_INTERVAL,
)
from ntrp.events.triggers import EventApproaching
from ntrp.logging import get_logger
from ntrp.monitor.store import MonitorStateStore
from ntrp.sources.base import CalendarSource

_logger = get_logger(__name__)
_STATE_NAMESPACE = "monitor.calendar.notified"


class CalendarMonitor:
    """Polls calendar data and publishes EventApproaching trigger events."""

    def __init__(self, source: CalendarSource, state_store: MonitorStateStore):
        self._source = source
        self._state_store = state_store
        self._channel: Channel | None = None
        self._task: asyncio.Task | None = None
        self._notified_at: dict[str, datetime] = {}

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
        await self._restore_state()
        await self._loop()

    async def _loop(self) -> None:
        while True:
            events = await asyncio.to_thread(self._poll)
            if self._channel:
                for event in events:
                    self._channel.publish(event)
            await self._persist_state()
            await asyncio.sleep(MONITOR_POLL_INTERVAL)

    def _poll(self) -> list[EventApproaching]:
        now = datetime.now(UTC)
        horizon = now + timedelta(minutes=MONITOR_DEFAULT_LEAD_MINUTES)
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

            notify_key = self._notify_key(item.source_id, item.metadata.get("calendar_id"), start)
            if notify_key in self._notified_at:
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
            self._notified_at[notify_key] = now
            _logger.info("Event approaching: %s in %d min", item.title, minutes_until)

        self._prune_notified(now)
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

    @staticmethod
    def _notify_key(event_id: str, calendar_id: str | None, start: datetime) -> str:
        calendar = (calendar_id or "primary").lower()
        return f"{calendar}:{event_id}:{start.isoformat()}"

    def _prune_notified(self, now: datetime) -> None:
        cutoff = now - timedelta(days=2)
        self._notified_at = {k: seen_at for k, seen_at in self._notified_at.items() if seen_at >= cutoff}

    async def _restore_state(self) -> None:
        payload = await self._state_store.get_state(_STATE_NAMESPACE)
        restored: dict[str, datetime] = {}
        for key, raw_ts in payload.items():
            if not isinstance(raw_ts, str):
                continue
            try:
                ts = datetime.fromisoformat(raw_ts)
            except ValueError:
                continue
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
            restored[key] = ts.astimezone(UTC)
        self._notified_at = restored
        self._prune_notified(datetime.now(UTC))

    async def _persist_state(self) -> None:
        payload = {key: seen_at.isoformat() for key, seen_at in self._notified_at.items()}
        await self._state_store.set_state(_STATE_NAMESPACE, payload)
