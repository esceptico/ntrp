from dataclasses import dataclass

from ntrp.agent.types.stop import StopReason
from ntrp.agent.types.usage import Usage


@dataclass(frozen=True)
class TextDelta:
    content: str


@dataclass(frozen=True)
class TextBlock:
    content: str


@dataclass(frozen=True)
class ToolStarted:
    tool_id: str
    name: str
    args: dict
    display_name: str = ""


@dataclass(frozen=True)
class ToolCompleted:
    tool_id: str
    name: str
    result: str
    preview: str
    duration_ms: int = 0
    is_error: bool = False
    data: dict | None = None
    display_name: str = ""


@dataclass(frozen=True)
class Result:
    text: str
    stop_reason: StopReason
    steps: int
    usage: Usage
