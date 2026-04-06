from ntrp.agent import CompletionResponse, StepConfig
from ntrp.channel import Channel
from ntrp.core.compactor import Compactor
from ntrp.events.internal import ContextCompressed


class NtrpCompactionHook:
    def __init__(
        self,
        channel: Channel,
        session_id: str,
        model: str,
        compactor: Compactor | None = None,
        is_root: bool = True,
    ):
        self.channel = channel
        self.session_id = session_id
        self.model = model
        self.compactor = compactor
        self.is_root = is_root

    async def prepare_step(
        self,
        step: int,
        messages: list[dict],
        last_response: CompletionResponse | None,
    ) -> StepConfig | None:
        if not self.compactor:
            return None

        last_input_tokens = last_response.usage.input_tokens if last_response else None

        before = len(messages)
        compacted = await self.compactor.maybe_compact(messages, self.model, last_input_tokens)
        if compacted is None:
            return None

        if self.is_root:
            kept_tail = len(compacted) - 2
            discarded = tuple(messages[1 : before - kept_tail])
            self.channel.publish(ContextCompressed(messages=discarded, session_id=self.session_id))

        return StepConfig(messages=compacted)
