from dataclasses import dataclass


@dataclass(frozen=True)
class FunctionCall:
    name: str
    arguments: str


@dataclass(frozen=True)
class ToolCall:
    id: str
    type: str  # always "function"
    function: FunctionCall
    thought_signature: str | None = None


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int
    completion_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int


@dataclass(frozen=True)
class Message:
    role: str
    content: str | None
    tool_calls: list[ToolCall] | None
    reasoning_content: str | None


@dataclass(frozen=True)
class Choice:
    message: Message
    finish_reason: str | None


@dataclass(frozen=True)
class CompletionResponse:
    choices: list[Choice]
    usage: Usage
    model: str
