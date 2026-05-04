from collections.abc import Awaitable, Callable
from dataclasses import replace
from typing import Any

from ntrp.agent.model_request import ModelRequest, ModelRequestNext
from ntrp.core.compactor import Compactor
from ntrp.events.sse import CompactionFinishedEvent, CompactionStartedEvent


class CompactionModelRequestMiddleware:
    def __init__(
        self,
        compactor: Compactor | None = None,
        on_compact: Callable[[], None] | None = None,
        emit: Callable[[Any], Awaitable[None]] | None = None,
        run_id: str = "",
    ):
        self.compactor = compactor
        self.on_compact = on_compact
        self.emit = emit
        self.run_id = run_id

    async def __call__(self, request: ModelRequest, next_request: ModelRequestNext) -> ModelRequest:
        prepared = await next_request(request)
        if not self.compactor:
            return prepared

        last_input_tokens = prepared.previous_response.usage.input_tokens if prepared.previous_response else None

        # Pre-check so we only emit start/finish around an *actual* compaction.
        # `should_compact` is optional on the Compactor protocol; fall back to
        # the silent path when a compactor doesn't expose it.
        should = bool(getattr(self.compactor, "should_compact", lambda *_: False)(
            prepared.messages, prepared.model, last_input_tokens,
        ))

        if should and self.emit:
            await self.emit(CompactionStartedEvent(run_id=self.run_id))

        compacted = await self.compactor.maybe_compact(prepared.messages, prepared.model, last_input_tokens)

        if compacted is None:
            return prepared

        if self.emit:
            await self.emit(
                CompactionFinishedEvent(
                    run_id=self.run_id,
                    messages_before=len(prepared.messages),
                    messages_after=len(compacted),
                )
            )

        if self.on_compact:
            self.on_compact()
        return replace(prepared, messages=compacted)
