from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PendingToolCall:
    tool_call: Any
    name: str
    args: dict


@dataclass(frozen=True)
class ToolExecutionResult:
    call: PendingToolCall
    content: str
    preview: str
    duration_ms: int
    is_error: bool = False
    data: dict | None = None
