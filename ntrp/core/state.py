from collections.abc import Awaitable, Callable
from enum import StrEnum


class AgentState(StrEnum):
    IDLE = "idle"
    THINKING = "thinking"
    TOOL_CALL = "tool_call"
    RESPONDING = "responding"


StateCallback = Callable[[AgentState], Awaitable[None]]
