import json
from dataclasses import asdict, dataclass, field
from enum import StrEnum


class EventType(StrEnum):
    """Types of events the server can emit."""

    # Agent state
    THINKING = "thinking"
    TEXT = "text"

    # Tool handling
    TOOL_CALL = "tool_call"  # Tool being called
    TOOL_RESULT = "tool_result"  # Result from tool

    # Approvals
    APPROVAL_NEEDED = "approval_needed"  # Write operation needs approval

    # User interaction
    QUESTION = "question"  # Agent asking user a question (free-form)
    CHOICE = "choice"  # Agent asking user to pick from options

    # Session
    SESSION_INFO = "session_info"

    # Completion
    DONE = "done"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass
class SSEEvent:
    type: EventType

    def to_sse(self) -> dict:
        data = asdict(self)
        data["type"] = self.type.value
        return {"event": self.type.value, "data": json.dumps(data)}

    def to_sse_string(self) -> str:
        sse = self.to_sse()
        return f"event: {sse['event']}\ndata: {sse['data']}\n\n"


@dataclass
class ThinkingEvent(SSEEvent):
    type: EventType = field(default=EventType.THINKING, init=False)
    status: str = ""


@dataclass
class TextEvent(SSEEvent):
    type: EventType = field(default=EventType.TEXT, init=False)
    content: str = ""


def _format_call(name: str, args: dict) -> str:
    if not args:
        return f"{name}()"
    parts = [f"{k}={v!r}" for k, v in sorted(args.items())]
    return f"{name}({', '.join(parts)})"


@dataclass
class ToolCallEvent(SSEEvent):
    type: EventType = field(default=EventType.TOOL_CALL, init=False)
    tool_id: str
    name: str
    args: dict
    depth: int = 0  # 0 = top-level, >0 = subagent
    parent_id: str = ""  # Parent tool_call_id for grouping subagent calls
    description: str = field(init=False)

    def __post_init__(self):
        self.description = _format_call(self.name, self.args)


@dataclass
class ToolResultEvent(SSEEvent):
    type: EventType = field(default=EventType.TOOL_RESULT, init=False)
    tool_id: str
    name: str
    result: str
    preview: str
    depth: int = 0
    parent_id: str = ""
    duration_ms: int = 0
    metadata: dict | None = None


@dataclass
class ApprovalNeededEvent(SSEEvent):
    type: EventType = field(default=EventType.APPROVAL_NEEDED, init=False)
    tool_id: str = ""
    name: str = ""
    # For file operations
    path: str | None = None
    diff: str | None = None
    content_preview: str | None = None


@dataclass
class QuestionEvent(SSEEvent):
    type: EventType = field(default=EventType.QUESTION, init=False)
    question: str = ""
    tool_id: str = ""  # For tracking



@dataclass
class ChoiceEvent(SSEEvent):
    type: EventType = field(default=EventType.CHOICE, init=False)
    question: str = ""
    options: list[dict] = field(default_factory=list)  # List of {id, label, description?}
    allow_multiple: bool = False  # Single vs multi-select
    tool_id: str = ""


@dataclass
class SessionInfoEvent(SSEEvent):
    type: EventType = field(default=EventType.SESSION_INFO, init=False)
    session_id: str = ""
    run_id: str = ""
    sources: list[str] = field(default_factory=list)
    source_errors: dict[str, str] = field(default_factory=dict)
    skip_approvals: bool = False


@dataclass
class DoneEvent(SSEEvent):
    type: EventType = field(default=EventType.DONE, init=False)
    run_id: str = ""
    usage: dict = field(default_factory=dict)  # {"prompt": N, "completion": N}


@dataclass
class ErrorEvent(SSEEvent):
    type: EventType = field(default=EventType.ERROR, init=False)
    message: str = ""
    recoverable: bool = False


@dataclass
class CancelledEvent(SSEEvent):
    type: EventType = field(default=EventType.CANCELLED, init=False)
    run_id: str = ""
