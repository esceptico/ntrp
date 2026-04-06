from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from ntrp.agent.types.config import StepConfig
from ntrp.agent.types.llm import CompletionResponse

PrepareStepFn = Callable[[int, list[dict], CompletionResponse | None], Awaitable[StepConfig | None]]
OnResponseFn = Callable[[CompletionResponse], Awaitable[None]]
OnStepFinishFn = Callable[[int, CompletionResponse, list[dict]], Awaitable[None]]
OnErrorFn = Callable[[Exception], Awaitable[None]]
OnFinishFn = Callable[[str, int, list[dict]], Awaitable[None]]
GetPendingMessagesFn = Callable[[], Awaitable[list[dict]]]


@dataclass
class AgentHooks:
    prepare_step: PrepareStepFn | None = None
    on_response: OnResponseFn | None = None
    on_step_finish: OnStepFinishFn | None = None
    on_error: OnErrorFn | None = None
    on_finish: OnFinishFn | None = None
    get_pending_messages: GetPendingMessagesFn | None = None
