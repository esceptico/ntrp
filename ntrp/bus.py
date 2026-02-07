from collections import defaultdict
from collections.abc import Callable, Coroutine
from typing import Any

type Handler[T] = Callable[[T], Coroutine[Any, Any, None]]


# TODO: use queue for better concurrency control?
class EventBus:
    def __init__(self):
        self._handlers: dict[type, list[Handler]] = defaultdict(list)

    def subscribe[T](self, event_type: type[T], handler: Handler[T]) -> None:
        self._handlers[event_type].append(handler)

    async def publish[T](self, event: T) -> None:
        for handler in self._handlers.get(type(event), []):
            await handler(event)
