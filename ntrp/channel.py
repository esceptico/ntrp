from collections import defaultdict
from collections.abc import Callable, Coroutine
from typing import Any

from ntrp.logging import get_logger

type Handler[T] = Callable[[T], Coroutine[Any, Any, None]]

_logger = get_logger(__name__)


class Channel:
    def __init__(self):
        self._handlers: dict[type, list[Handler]] = defaultdict(list)

    def subscribe[T](self, event_type: type[T], handler: Handler[T]) -> None:
        self._handlers[event_type].append(handler)

    async def publish[T](self, event: T) -> None:
        for handler in self._handlers.get(type(event), []):
            try:
                await handler(event)
            except Exception:
                _logger.exception(
                    "Event handler %s failed for %s",
                    handler.__qualname__,
                    type(event).__name__,
                )
