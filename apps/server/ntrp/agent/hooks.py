from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from ntrp.agent.types.llm import CompletionResponse

OnResponseFn = Callable[[CompletionResponse], Awaitable[None]]
OnStepFinishFn = Callable[[int, CompletionResponse, list[dict]], Awaitable[None]]
OnErrorFn = Callable[[Exception], Awaitable[None]]
OnFinishFn = Callable[[str, int, list[dict]], Awaitable[None]]
GetPendingMessagesFn = Callable[[], Awaitable[list[dict]]]
# Awaited at each step boundary; blocks while the run is paused, returns
# immediately otherwise. Cancellation (task.cancel) still interrupts the wait.
WaitWhilePausedFn = Callable[[], Awaitable[None]]


@dataclass
class AgentHooks:
    on_response: OnResponseFn | None = None
    on_step_finish: OnStepFinishFn | None = None
    on_error: OnErrorFn | None = None
    on_finish: OnFinishFn | None = None
    get_pending_messages: GetPendingMessagesFn | None = None
    wait_while_paused: WaitWhilePausedFn | None = None
