"""
Server-Sent Event types for ntrp's chat stream.

The wire format follows the AG-UI protocol (https://ag-ui-protocol.com)
where applicable. Canonical event types are uppercase per AG-UI spec; the
remaining ntrp-specific events (approval, background tasks, automations,
etc.) ride on the same channel as snake_case named non-canonical events.

Every event includes a `timestamp` (Unix milliseconds) on the wire so
clients can compute per-event timing without a local clock.
"""

import json
import time
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from uuid import uuid4

from ntrp.agent import (
    ReasoningBlock,
    ReasoningDelta,
    ReasoningEnded,
    ReasoningStarted,
    TextBlock,
    TextDelta,
    ToolCompleted,
    ToolStarted,
)


class EventType(StrEnum):
    # ─── AG-UI canonical events (uppercase) ────────────────────────────
    RUN_STARTED = "RUN_STARTED"
    RUN_FINISHED = "RUN_FINISHED"
    RUN_ERROR = "RUN_ERROR"

    TEXT_MESSAGE_START = "TEXT_MESSAGE_START"
    TEXT_MESSAGE_CONTENT = "TEXT_MESSAGE_CONTENT"
    TEXT_MESSAGE_END = "TEXT_MESSAGE_END"

    TOOL_CALL_START = "TOOL_CALL_START"
    TOOL_CALL_ARGS = "TOOL_CALL_ARGS"
    TOOL_CALL_END = "TOOL_CALL_END"
    TOOL_CALL_RESULT = "TOOL_CALL_RESULT"

    REASONING_START = "REASONING_START"
    REASONING_MESSAGE_START = "REASONING_MESSAGE_START"
    REASONING_MESSAGE_CONTENT = "REASONING_MESSAGE_CONTENT"
    REASONING_MESSAGE_END = "REASONING_MESSAGE_END"
    REASONING_END = "REASONING_END"

    # ─── ntrp-specific events (snake_case, non-canonical) ──────────────
    THINKING = "thinking"
    APPROVAL_NEEDED = "approval_needed"
    QUESTION = "question"
    BACKGROUND_TASK = "background_task"
    RUN_CANCELLED = "run_cancelled"
    RUN_BACKGROUNDED = "run_backgrounded"
    MESSAGE_INGESTED = "message_ingested"
    AUTOMATION_PROGRESS = "automation_progress"
    AUTOMATION_FINISHED = "automation_finished"
    COMPACTION_STARTED = "compaction_started"
    COMPACTION_FINISHED = "compaction_finished"


def _now_ms() -> int:
    return int(time.time() * 1000)


@dataclass(frozen=True)
class SSEEvent:
    type: EventType
    timestamp: int = field(default_factory=_now_ms)

    def to_sse(self) -> dict:
        data = asdict(self)
        data["type"] = self.type.value
        return {"event": self.type.value, "data": json.dumps(data)}

    def to_sse_string(self) -> str:
        sse = self.to_sse()
        return f"event: {sse['event']}\ndata: {sse['data']}\n\n"


# ─── Run lifecycle ───────────────────────────────────────────────────


@dataclass(frozen=True)
class RunStartedEvent(SSEEvent):
    type: EventType = field(default=EventType.RUN_STARTED, init=False)
    session_id: str = ""
    run_id: str = ""
    integrations: list[str] = field(default_factory=list)
    integration_errors: dict[str, str] = field(default_factory=dict)
    skip_approvals: bool = False
    session_name: str = ""


@dataclass(frozen=True)
class RunFinishedEvent(SSEEvent):
    type: EventType = field(default=EventType.RUN_FINISHED, init=False)
    run_id: str = ""
    usage: dict = field(default_factory=dict)


@dataclass(frozen=True)
class RunErrorEvent(SSEEvent):
    type: EventType = field(default=EventType.RUN_ERROR, init=False)
    message: str = ""
    recoverable: bool = False


# ─── Text messages (AG-UI Start / Content / End) ─────────────────────


@dataclass(frozen=True)
class TextMessageStartEvent(SSEEvent):
    type: EventType = field(default=EventType.TEXT_MESSAGE_START, init=False)
    message_id: str = ""
    role: str = "assistant"


@dataclass(frozen=True)
class TextMessageContentEvent(SSEEvent):
    type: EventType = field(default=EventType.TEXT_MESSAGE_CONTENT, init=False)
    message_id: str = ""
    delta: str = ""
    depth: int = 0
    parent_id: str | None = None


@dataclass(frozen=True)
class TextMessageEndEvent(SSEEvent):
    type: EventType = field(default=EventType.TEXT_MESSAGE_END, init=False)
    message_id: str = ""
    content: str = ""  # cumulative final text, optional convenience for clients


# ─── Tool calls (AG-UI Start / Args / End / Result) ──────────────────


def _format_call(name: str, args: dict) -> str:
    if not args:
        return f"{name}()"
    parts = [f"{k}={v!r}" for k, v in sorted(args.items())]
    return f"{name}({', '.join(parts)})"


@dataclass(frozen=True)
class ToolCallStartEvent(SSEEvent):
    type: EventType = field(default=EventType.TOOL_CALL_START, init=False)
    tool_call_id: str = ""
    tool_call_name: str = ""
    parent_message_id: str | None = None
    display_name: str = ""
    description: str = ""  # human-readable preview of the call
    depth: int = 0
    parent_id: str | None = None
    kind: str = "tool"


@dataclass(frozen=True)
class ToolCallArgsEvent(SSEEvent):
    type: EventType = field(default=EventType.TOOL_CALL_ARGS, init=False)
    tool_call_id: str = ""
    delta: str = ""  # JSON-encoded args (ntrp emits atomically, so single delta)
    depth: int = 0
    parent_id: str | None = None


@dataclass(frozen=True)
class ToolCallEndEvent(SSEEvent):
    type: EventType = field(default=EventType.TOOL_CALL_END, init=False)
    tool_call_id: str = ""
    depth: int = 0
    parent_id: str | None = None


@dataclass(frozen=True)
class ToolCallResultEvent(SSEEvent):
    type: EventType = field(default=EventType.TOOL_CALL_RESULT, init=False)
    tool_call_id: str = ""
    role: str = "tool"
    content: str = ""
    preview: str = ""
    duration_ms: int = 0
    data: dict | None = None
    display_name: str = ""
    name: str = ""  # tool name, convenience
    depth: int = 0
    parent_id: str | None = None
    kind: str = "tool"
    is_error: bool = False


# ─── Reasoning (AG-UI Start / Content / End + outer Start/End) ───────


@dataclass(frozen=True)
class ReasoningStartEvent(SSEEvent):
    type: EventType = field(default=EventType.REASONING_START, init=False)
    message_id: str = ""
    depth: int = 0
    parent_id: str | None = None


@dataclass(frozen=True)
class ReasoningMessageStartEvent(SSEEvent):
    type: EventType = field(default=EventType.REASONING_MESSAGE_START, init=False)
    message_id: str = ""
    role: str = "reasoning"
    depth: int = 0
    parent_id: str | None = None


@dataclass(frozen=True)
class ReasoningMessageContentEvent(SSEEvent):
    type: EventType = field(default=EventType.REASONING_MESSAGE_CONTENT, init=False)
    message_id: str = ""
    delta: str = ""
    depth: int = 0
    parent_id: str | None = None


@dataclass(frozen=True)
class ReasoningMessageEndEvent(SSEEvent):
    type: EventType = field(default=EventType.REASONING_MESSAGE_END, init=False)
    message_id: str = ""
    depth: int = 0
    parent_id: str | None = None


@dataclass(frozen=True)
class ReasoningEndEvent(SSEEvent):
    type: EventType = field(default=EventType.REASONING_END, init=False)
    message_id: str = ""
    depth: int = 0
    parent_id: str | None = None


# ─── ntrp-specific (non-canonical) events ─────────────────────────────


@dataclass(frozen=True)
class ThinkingEvent(SSEEvent):
    type: EventType = field(default=EventType.THINKING, init=False)
    status: str = ""


@dataclass(frozen=True)
class ApprovalNeededEvent(SSEEvent):
    type: EventType = field(default=EventType.APPROVAL_NEEDED, init=False)
    tool_id: str = ""
    name: str = ""
    path: str | None = None
    diff: str | None = None
    content_preview: str | None = None


@dataclass(frozen=True)
class QuestionEvent(SSEEvent):
    type: EventType = field(default=EventType.QUESTION, init=False)
    question: str = ""
    tool_id: str = ""


@dataclass(frozen=True)
class BackgroundTaskEvent(SSEEvent):
    type: EventType = field(default=EventType.BACKGROUND_TASK, init=False)
    task_id: str = ""
    command: str = ""
    status: str = ""  # "started", "completed", "failed", "cancelled", "activity"
    detail: str | None = None


@dataclass(frozen=True)
class RunCancelledEvent(SSEEvent):
    type: EventType = field(default=EventType.RUN_CANCELLED, init=False)
    run_id: str = ""


@dataclass(frozen=True)
class RunBackgroundedEvent(SSEEvent):
    type: EventType = field(default=EventType.RUN_BACKGROUNDED, init=False)
    run_id: str = ""


@dataclass(frozen=True)
class MessageIngestedEvent(SSEEvent):
    type: EventType = field(default=EventType.MESSAGE_INGESTED, init=False)
    client_id: str = ""
    run_id: str = ""


@dataclass(frozen=True)
class AutomationProgressEvent(SSEEvent):
    type: EventType = field(default=EventType.AUTOMATION_PROGRESS, init=False)
    task_id: str = ""
    status: str = ""


@dataclass(frozen=True)
class AutomationFinishedEvent(SSEEvent):
    type: EventType = field(default=EventType.AUTOMATION_FINISHED, init=False)
    task_id: str = ""
    result: str | None = None


@dataclass(frozen=True)
class CompactionStartedEvent(SSEEvent):
    type: EventType = field(default=EventType.COMPACTION_STARTED, init=False)
    run_id: str = ""


@dataclass(frozen=True)
class CompactionFinishedEvent(SSEEvent):
    type: EventType = field(default=EventType.COMPACTION_FINISHED, init=False)
    run_id: str = ""
    messages_before: int = 0
    messages_after: int = 0


# ─── Aliases (back-compat for existing imports) ───────────────────────

# Older code may import ToolCallEvent / ToolResultEvent / TextEvent /
# TextDeltaEvent. Map them to the AG-UI start/result/content equivalents
# so callers don't break. New code should prefer the canonical names above.
ToolCallEvent = ToolCallStartEvent
ToolResultEvent = ToolCallResultEvent
TextEvent = TextMessageContentEvent
TextDeltaEvent = TextMessageContentEvent


# ─── Conversion from agent events to AG-UI SSE ────────────────────────


def agent_events_to_sse(event) -> tuple[SSEEvent, ...]:
    """Convert an ntrp.agent event to one or more SSEEvents.

    For tool calls we emit the full AG-UI start/args/end triplet; ntrp
    produces tool calls atomically (the model isn't streaming arguments
    token-by-token), so the args delta carries the full JSON payload.
    """
    base = {"depth": event.depth, "parent_id": event.parent_id}
    match event:
        case TextDelta():
            # We don't have an explicit "text started" agent event, so the
            # client synthesises a START on first CONTENT; we just emit the
            # streaming delta.
            return (
                TextMessageContentEvent(
                    message_id=getattr(event, "message_id", "") or "",
                    delta=event.content,
                    **base,
                ),
            )
        case TextBlock():
            # TextBlock is the cumulative-final text for a step; the streaming
            # TextDelta events already carried every chunk over the wire, so
            # re-emitting here would just duplicate the message client-side.
            # Other (non-SSE) consumers of agent events can still use
            # TextBlock — it's only this conversion that drops it.
            return ()
        case ReasoningBlock():
            message_id = f"reasoning-{uuid4().hex[:10]}"
            content = event.content.strip()
            return (
                ReasoningStartEvent(message_id=message_id, **base),
                ReasoningMessageStartEvent(message_id=message_id, **base),
                ReasoningMessageContentEvent(message_id=message_id, delta=content, **base),
                ReasoningMessageEndEvent(message_id=message_id, **base),
                ReasoningEndEvent(message_id=message_id, **base),
            )
        case ReasoningStarted():
            return (
                ReasoningStartEvent(message_id=event.message_id, **base),
                ReasoningMessageStartEvent(message_id=event.message_id, **base),
            )
        case ReasoningDelta():
            return (ReasoningMessageContentEvent(message_id=event.message_id, delta=event.content, **base),)
        case ReasoningEnded():
            return (
                ReasoningMessageEndEvent(message_id=event.message_id, **base),
                ReasoningEndEvent(message_id=event.message_id, **base),
            )
        case ToolStarted():
            description = _format_call(event.display_name or event.name, event.args)
            args_json = json.dumps(event.args) if event.args else "{}"
            return (
                ToolCallStartEvent(
                    tool_call_id=event.tool_id,
                    tool_call_name=event.name,
                    display_name=event.display_name,
                    description=description,
                    depth=event.depth,
                    parent_id=event.parent_id,
                    kind=event.kind,
                ),
                ToolCallArgsEvent(
                    tool_call_id=event.tool_id,
                    delta=args_json,
                    depth=event.depth,
                    parent_id=event.parent_id,
                ),
                ToolCallEndEvent(
                    tool_call_id=event.tool_id,
                    depth=event.depth,
                    parent_id=event.parent_id,
                ),
            )
        case ToolCompleted():
            return (
                ToolCallResultEvent(
                    tool_call_id=event.tool_id,
                    name=event.name,
                    content=event.result,
                    preview=event.preview,
                    duration_ms=event.duration_ms,
                    data=event.data,
                    display_name=event.display_name,
                    depth=event.depth,
                    parent_id=event.parent_id,
                    kind=event.kind,
                    is_error=event.is_error,
                ),
            )
    return ()


def agent_event_to_sse(event) -> "SSEEvent | None":
    events = agent_events_to_sse(event)
    # Returns the lead/canonical event when one or more are produced. For
    # tool calls (start/args/end triplet) the START event is the
    # informative one for callers that just want a single event handle.
    return events[0] if events else None
