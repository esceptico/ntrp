from collections.abc import Awaitable, Callable

from evals.assertions import EventAssertions

SendFn = Callable[[str], Awaitable[list[dict]]]


class RuntimeCase:
    def __init__(self, send_fn: SendFn):
        self._send_fn = send_fn

    async def send(self, prompt: str) -> EventAssertions:
        events = await self._send_fn(prompt)
        return EventAssertions(events)
