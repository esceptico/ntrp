from ntrp.agent import CompletionResponse, StepConfig
from ntrp.core.compactor import Compactor


class NtrpCompactionHook:
    def __init__(
        self,
        model: str,
        compactor: Compactor | None = None,
    ):
        self.model = model
        self.compactor = compactor

    async def prepare_step(
        self,
        step: int,
        messages: list[dict],
        last_response: CompletionResponse | None,
    ) -> StepConfig | None:
        if not self.compactor:
            return None

        last_input_tokens = last_response.usage.input_tokens if last_response else None

        compacted = await self.compactor.maybe_compact(messages, self.model, last_input_tokens)
        if compacted is None:
            return None

        return StepConfig(messages=compacted)
