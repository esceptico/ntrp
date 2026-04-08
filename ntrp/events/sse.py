import json
from dataclasses import asdict, dataclass, field
from enum import StrEnum

from ntrp.agent import TextBlock, TextDelta, ToolCompleted, ToolStarted


class EventType(StrEnum):
    THINKING = "thinking"
    TEXT = "text"
    TEXT_DELTA = "text_delta"
    TEXT_MESSAGE_START = "text_message_start"
    TEXT_MESSAGE_END = "text_message_end"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    APPROVAL_NEEDED = "approval_needed"
    QUESTION = "question"
    RUN_STARTED = "run_started"
    BACKGROUND_TASK = "background_task"
    RUN_FINISHED = "run_finished"
    RUN_ERROR = "run_error"
    RUN_CANCELLED = "run_cancelled"
    RUN_BACKGROUNDED = "run_backgrounded"


@dataclass(frozen=True)
class SSEEvent:
    type: EventType

    def to_sse(self) -> dict:
        data = asdict(self)
        data["type"] = self.type.value
        return {"event": self.type.value, "data": json.dumps(data)}

    def to_sse_string(self) -> str:
        sse = self.to_sse()
        return f"event: {sse['event']}\ndata: {sse['data']}\n\n"


@dataclass(frozen=True)
class ThinkingEvent(SSEEvent):
    type: EventType = field(default=EventType.THINKING, init=False)
    status: str


@dataclass(frozen=True)
class TextEvent(SSEEvent):
    type: EventType = field(default=EventType.TEXT, init=False)
    content: str
    depth: int = 0
    parent_id: str | None = None


@dataclass(frozen=True)
class TextDeltaEvent(SSEEvent):
    type: EventType = field(default=EventType.TEXT_DELTA, init=False)
    content: str
    depth: int = 0
    parent_id: str | None = None


def _format_call(name: str, args: dict) -> str:
    if not args:
        return f"{name}()"
    parts = [f"{k}={v!r}" for k, v in sorted(args.items())]
    return f"{name}({', '.join(parts)})"


@dataclass(frozen=True)
class ToolCallEvent(SSEEvent):
    type: EventType = field(default=EventType.TOOL_CALL, init=False)
    tool_id: str
    name: str
    args: dict
    depth: int = 0
    parent_id: str | None = None
    display_name: str = ""

    def to_sse(self) -> dict:
        data = asdict(self)
        data["type"] = self.type.value
        data["description"] = _format_call(self.display_name, self.args)
        return {"event": self.type.value, "data": json.dumps(data)}


@dataclass(frozen=True)
class ToolResultEvent(SSEEvent):
    type: EventType = field(default=EventType.TOOL_RESULT, init=False)
    tool_id: str
    name: str
    result: str
    preview: str
    depth: int = 0
    parent_id: str | None = None
    duration_ms: int = 0
    data: dict | None = None
    display_name: str = ""


@dataclass(frozen=True)
class ApprovalNeededEvent(SSEEvent):
    type: EventType = field(default=EventType.APPROVAL_NEEDED, init=False)
    tool_id: str
    name: str
    # For file operations
    path: str | None = None
    diff: str | None = None
    content_preview: str | None = None


@dataclass(frozen=True)
class QuestionEvent(SSEEvent):
    type: EventType = field(default=EventType.QUESTION, init=False)
    question: str
    tool_id: str


@dataclass(frozen=True)
class RunStartedEvent(SSEEvent):
    type: EventType = field(default=EventType.RUN_STARTED, init=False)
    session_id: str
    run_id: str
    integrations: list[str] = field(default_factory=list)
    integration_errors: dict[str, str] = field(default_factory=dict)
    skip_approvals: bool = False
    session_name: str = ""


@dataclass(frozen=True)
class BackgroundTaskEvent(SSEEvent):
    type: EventType = field(default=EventType.BACKGROUND_TASK, init=False)
    task_id: str
    command: str
    status: str  # "started", "completed", "failed", "cancelled", "activity"
    detail: str | None = None


@dataclass(frozen=True)
class RunFinishedEvent(SSEEvent):
    type: EventType = field(default=EventType.RUN_FINISHED, init=False)
    run_id: str
    usage: dict = field(default_factory=dict)  # {"prompt": N, "completion": N}


@dataclass(frozen=True)
class RunErrorEvent(SSEEvent):
    type: EventType = field(default=EventType.RUN_ERROR, init=False)
    message: str
    recoverable: bool = False


@dataclass(frozen=True)
class RunCancelledEvent(SSEEvent):
    type: EventType = field(default=EventType.RUN_CANCELLED, init=False)
    run_id: str


@dataclass(frozen=True)
class RunBackgroundedEvent(SSEEvent):
    type: EventType = field(default=EventType.RUN_BACKGROUNDED, init=False)
    run_id: str


@dataclass(frozen=True)
class TextMessageStartEvent(SSEEvent):
    type: EventType = field(default=EventType.TEXT_MESSAGE_START, init=False)
    message_id: str
    role: str = "assistant"


@dataclass(frozen=True)
class TextMessageEndEvent(SSEEvent):
    type: EventType = field(default=EventType.TEXT_MESSAGE_END, init=False)
    message_id: str


def agent_event_to_sse(event) -> "SSEEvent | None":
    """Convert an ntrp.agent event to an SSEEvent."""
    base = {"depth": event.depth, "parent_id": event.parent_id}
    match event:
        case TextDelta():
            return TextDeltaEvent(content=event.content, **base)
        case TextBlock():
            return TextEvent(content=event.content, **base)
        case ToolStarted():
            return ToolCallEvent(
                tool_id=event.tool_id,
                name=event.name,
                args=event.args,
                display_name=event.display_name,
                **base,
            )
        case ToolCompleted():
            return ToolResultEvent(
                tool_id=event.tool_id,
                name=event.name,
                result=event.result,
                preview=event.preview,
                duration_ms=event.duration_ms,
                data=event.data,
                display_name=event.display_name,
                **base,
            )
    return None
