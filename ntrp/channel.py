import asyncio
from collections import defaultdict
from collections.abc import Callable, Coroutine
from typing import Any

from ntrp.constants import CHANNEL_DISPATCH_WORKERS
from ntrp.logging import get_logger

type Handler[T] = Callable[[T], Coroutine[Any, Any, None]]

_logger = get_logger(__name__)


class Channel:
    """Fire-and-forget pub/sub bus.

    - subscribe(EventType, handler) — register an async handler, called once at setup.
    - publish(event) — notify all subscribers, returns immediately.
      Handlers run as independent background tasks. No ordering guarantees.
      Errors are logged, never propagated.
    """

    def __init__(self) -> None:
        self._handlers: dict[type, list[Handler]] = defaultdict(list)
        self._queue: asyncio.Queue[tuple[Handler[Any], Any]] = asyncio.Queue()
        self._workers: set[asyncio.Task] = set()

    def subscribe[T](self, event_type: type[T], handler: Handler[T]) -> None:
        self._handlers[event_type].append(handler)

    def unsubscribe[T](self, event_type: type[T], handler: Handler[T]) -> None:
        handlers = self._handlers.get(event_type)
        if handlers:
            try:
                handlers.remove(handler)
            except ValueError:
                pass

    def publish[T](self, event: T) -> None:
        if not self._ensure_workers():
            return
        handlers = tuple(self._handlers.get(type(event), ()))
        if not handlers:
            return

        for handler in handlers:
            self._queue.put_nowait((handler, event))

    async def _run[T](self, handler: Handler[T], event: T) -> None:
        try:
            await handler(event)
        except Exception:
            _logger.exception(
                "Event handler %s failed for %s",
                handler.__qualname__,
                type(event).__name__,
            )

    def _ensure_workers(self) -> bool:
        if self._workers:
            return True
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            _logger.warning("Channel.publish called without a running event loop; event dropped")
            return False
        for _ in range(CHANNEL_DISPATCH_WORKERS):
            task = loop.create_task(self._worker_loop())
            self._workers.add(task)
            task.add_done_callback(self._workers.discard)
        return True

    async def _worker_loop(self) -> None:
        while True:
            handler, event = await self._queue.get()
            try:
                await self._run(handler, event)
            finally:
                self._queue.task_done()
