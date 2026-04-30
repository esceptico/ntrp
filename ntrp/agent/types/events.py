from dataclasses import dataclass

from ntrp.agent.types.stop import StopReason
from ntrp.agent.types.usage import Usage


@dataclass(frozen=True, kw_only=True)
class AgentEventBase:
    depth: int = 0
    parent_id: str | None = None


@dataclass(frozen=True, kw_only=True)
class TextDelta(AgentEventBase):
    content: str


@dataclass(frozen=True, kw_only=True)
class TextBlock(AgentEventBase):
    content: str


@dataclass(frozen=True, kw_only=True)
class ReasoningBlock(AgentEventBase):
    content: str


@dataclass(frozen=True, kw_only=True)
class ReasoningStarted(AgentEventBase):
    message_id: str


@dataclass(frozen=True, kw_only=True)
class ReasoningDelta(AgentEventBase):
    message_id: str
    content: str


@dataclass(frozen=True, kw_only=True)
class ReasoningEnded(AgentEventBase):
    message_id: str


@dataclass(frozen=True, kw_only=True)
class ToolStarted(AgentEventBase):
    tool_id: str
    name: str
    args: dict
    display_name: str


@dataclass(frozen=True, kw_only=True)
class ToolCompleted(AgentEventBase):
    tool_id: str
    name: str
    result: str
    preview: str
    duration_ms: int
    is_error: bool
    data: dict | None
    display_name: str


@dataclass(frozen=True)
class Result:
    text: str
    stop_reason: StopReason
    steps: int
    usage: Usage
