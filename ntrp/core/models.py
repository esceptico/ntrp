from dataclasses import dataclass
from typing import Any


@dataclass
class PendingToolCall:
    tool_call: Any
    name: str
    args: dict


@dataclass
class ToolExecutionResult:
    call: PendingToolCall
    content: str
    preview: str
    metadata: dict | None
    duration_ms: int
