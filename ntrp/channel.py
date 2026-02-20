import asyncio
from collections import defaultdict
from collections.abc import Callable, Coroutine
from typing import Any

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
        for handler in self._handlers.get(type(event), []):
            asyncio.create_task(self._run(handler, event))

    async def _run[T](self, handler: Handler[T], event: T) -> None:
        try:
            await handler(event)
        except Exception:
            _logger.exception(
                "Event handler %s failed for %s",
                handler.__qualname__,
                type(event).__name__,
            )
