from dataclasses import dataclass
from enum import StrEnum

from ntrp.agent.types.tool_call import ToolCall
from ntrp.agent.types.usage import Usage


class Role(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class FinishReason(StrEnum):
    STOP = "stop"
    TOOL_CALLS = "tool_calls"
    LENGTH = "length"
    CONTENT_FILTER = "content_filter"


@dataclass(frozen=True)
class Message:
    role: Role
    content: str | None
    tool_calls: list[ToolCall] | None
    reasoning_content: str | None


@dataclass(frozen=True)
class Choice:
    message: Message
    finish_reason: FinishReason | None


@dataclass(frozen=True)
class CompletionResponse:
    choices: list[Choice]
    usage: Usage
    model: str
