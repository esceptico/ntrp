import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from ntrp.constants import (
    OUTBOX_BATCH_SIZE,
    OUTBOX_MAX_RETRIES,
    OUTBOX_POLL_INTERVAL,
    OUTBOX_RETRY_BASE_SECONDS,
    OUTBOX_RETRY_MAX_SECONDS,
    OUTBOX_STALE_LOCK_SECONDS,
)
from ntrp.logging import get_logger
from ntrp.outbox.models import OutboxEvent
from ntrp.outbox.store import OutboxStore

_logger = get_logger(__name__)

OutboxHandler = Callable[[OutboxEvent], Awaitable[None]]


class OutboxWorker:
    def __init__(
        self,
        store: OutboxStore,
        *,
        worker_id: str | None = None,
        batch_size: int = OUTBOX_BATCH_SIZE,
        poll_interval: float = OUTBOX_POLL_INTERVAL,
        max_retries: int = OUTBOX_MAX_RETRIES,
        retry_base_seconds: int = OUTBOX_RETRY_BASE_SECONDS,
        retry_max_seconds: int = OUTBOX_RETRY_MAX_SECONDS,
        stale_lock_seconds: int = OUTBOX_STALE_LOCK_SECONDS,
    ):
        self.store = store
        self.worker_id = worker_id or f"outbox-{uuid4().hex[:8]}"
        self.batch_size = batch_size
        self.poll_interval = poll_interval
        self.max_retries = max_retries
        self.retry_base_seconds = retry_base_seconds
        self.retry_max_seconds = retry_max_seconds
        self.stale_lock_seconds = stale_lock_seconds
        self._handlers: dict[str, OutboxHandler] = {}
        self._task: asyncio.Task | None = None

    def register_handler(self, event_type: str, handler: OutboxHandler) -> None:
        self._handlers[event_type] = handler

    def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._loop())
        _logger.info("Outbox worker started", worker_id=self.worker_id)

    async def stop(self) -> None:
        if not self._task:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
        _logger.info("Outbox worker stopped", worker_id=self.worker_id)

    async def _loop(self) -> None:
        try:
            locked_before = datetime.now(UTC) - timedelta(seconds=self.stale_lock_seconds)
            released = await self.store.release_stale_running(locked_before)
            if released:
                _logger.info("Released stale outbox rows", count=released)
        except Exception:
            _logger.exception("Failed to release stale outbox rows")

        while True:
            try:
                processed = await self.process_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                _logger.exception("Outbox processing failed")
                processed = False
            if not processed:
                await asyncio.sleep(self.poll_interval)

    async def process_once(self) -> bool:
        events = await self.store.claim_batch(worker_id=self.worker_id, limit=self.batch_size)
        for event in events:
            await self._dispatch(event)
        return bool(events)

    async def _dispatch(self, event: OutboxEvent) -> None:
        handler = self._handlers.get(event.event_type)
        if not handler:
            await self._mark_failed(event, f"No outbox handler registered for {event.event_type}")
            return

        try:
            await handler(event)
        except Exception as exc:
            _logger.exception("Outbox handler failed", event_id=event.id, event_type=event.event_type)
            await self._mark_failed(event, f"{type(exc).__name__}: {exc}")
            return

        await self.store.mark_completed(event.id)

    async def _mark_failed(self, event: OutboxEvent, error: str) -> None:
        if event.attempts >= self.max_retries:
            await self.store.mark_failed(event.id, error=error, retry_at=None, dead=True)
            _logger.error(
                "Outbox event moved to dead state",
                event_id=event.id,
                event_type=event.event_type,
                attempts=event.attempts,
            )
            return

        retry_at = datetime.now(UTC) + timedelta(seconds=self._retry_delay_seconds(event.attempts))
        await self.store.mark_failed(event.id, error=error, retry_at=retry_at)

    def _retry_delay_seconds(self, attempts: int) -> int:
        delay = self.retry_base_seconds * (2 ** max(attempts - 1, 0))
        return min(self.retry_max_seconds, delay)
