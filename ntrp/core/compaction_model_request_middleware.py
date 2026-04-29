from dataclasses import replace

from ntrp.agent.model_request import ModelRequest, ModelRequestNext
from ntrp.core.compactor import Compactor


class CompactionModelRequestMiddleware:
    def __init__(
        self,
        compactor: Compactor | None = None,
    ):
        self.compactor = compactor

    async def __call__(self, request: ModelRequest, next_request: ModelRequestNext) -> ModelRequest:
        prepared = await next_request(request)
        if not self.compactor:
            return prepared

        last_input_tokens = prepared.previous_response.usage.input_tokens if prepared.previous_response else None
        compacted = await self.compactor.maybe_compact(prepared.messages, prepared.model, last_input_tokens)
        if compacted is None:
            return prepared

        return replace(prepared, messages=compacted)
