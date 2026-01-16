from collections.abc import Awaitable, Callable
from enum import Enum


class AgentState(Enum):
    IDLE = "idle"
    THINKING = "thinking"
    TOOL_CALL = "tool_call"
    RESPONDING = "responding"
    ERROR = "error"


# Callback type for state changes
StateCallback = Callable[[AgentState], Awaitable[None]]
