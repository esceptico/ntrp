"""Read-only tools that expose recent chat sessions to the agent.

Built for cross-session pattern detection — e.g. an audit automation that
runs weekly, scans recent sessions, and proposes automations/skills based
on what the user actually repeats. The agent gets enough to identify
patterns without dumping every byte of history into context.

Two tools:
- `list_recent_sessions` — index of sessions: id, name, when, message count.
- `read_session` — messages for one session, with content trimmed by default
  so a single huge session can't blow the context window.
"""

from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, Field

from ntrp.tools.core import ToolResult, tool
from ntrp.tools.core.context import ToolExecution

# How aggressively to trim each message's content when summarizing a session.
# Tool calls and large tool results are the worst offenders — a single bash
# output can be tens of KB. The default keeps the structure intact while
# capping each line, and `full_content=True` opts in to untrimmed bodies.
_DEFAULT_CONTENT_CHARS = 400
_MAX_CONTENT_CHARS = 4_000
_DEFAULT_LIST_LIMIT = 20
_MAX_LIST_LIMIT = 100
_DEFAULT_MESSAGE_LIMIT = 50
_MAX_MESSAGE_LIMIT = 200


class ListRecentSessionsInput(BaseModel):
    limit: int = Field(
        default=_DEFAULT_LIST_LIMIT,
        ge=1,
        le=_MAX_LIST_LIMIT,
        description=f"Max sessions to return (default {_DEFAULT_LIST_LIMIT}, max {_MAX_LIST_LIMIT}). Most recent first.",
    )
    within_days: int | None = Field(
        default=None,
        ge=1,
        le=365,
        description=(
            "Only return sessions with activity in the last N days. Omit to "
            "use limit alone. Useful for periodic audits ('last 7 days')."
        ),
    )


class ReadSessionInput(BaseModel):
    session_id: str = Field(description="The session_id from list_recent_sessions.")
    limit: int = Field(
        default=_DEFAULT_MESSAGE_LIMIT,
        ge=1,
        le=_MAX_MESSAGE_LIMIT,
        description=(
            f"Max messages to return (default {_DEFAULT_MESSAGE_LIMIT}, max "
            f"{_MAX_MESSAGE_LIMIT}). Messages are returned oldest-first."
        ),
    )
    content_chars: int = Field(
        default=_DEFAULT_CONTENT_CHARS,
        ge=50,
        le=_MAX_CONTENT_CHARS,
        description=(
            f"Truncate each message's content body to this many chars "
            f"(default {_DEFAULT_CONTENT_CHARS}, max {_MAX_CONTENT_CHARS}). "
            "Keeps a long session readable without blowing context."
        ),
    )
    role_filter: str | None = Field(
        default=None,
        description=(
            "Comma-separated roles to include, e.g. 'user' for just the "
            "prompts, or 'user,assistant' to drop tool noise. Omit for all."
        ),
    )


# --- Helpers ---


def _content_to_text(raw) -> str:
    """Normalize a stored message content into plain text. Messages can be
    a string, a list of content blocks (text/image/tool_result), or a dict —
    flatten to a single string the agent can scan."""
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list):
        parts: list[str] = []
        for block in raw:
            if isinstance(block, dict):
                if block.get("type") == "text" and block.get("text"):
                    parts.append(block["text"])
                elif block.get("type") == "tool_use" and block.get("name"):
                    parts.append(f"[tool_use: {block['name']}]")
                elif block.get("type") == "tool_result":
                    inner = block.get("content")
                    parts.append(f"[tool_result: {_content_to_text(inner)[:120]}]")
                elif block.get("type") == "image":
                    parts.append("[image]")
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    if isinstance(raw, dict):
        return _content_to_text(raw.get("content"))
    return str(raw)


def _truncate(text: str, max_chars: int) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def _parse_when(raw) -> datetime | None:
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=UTC)
    if isinstance(raw, str):
        try:
            dt = datetime.fromisoformat(raw)
            return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
        except ValueError:
            return None
    return None


def _format_when(raw) -> str:
    dt = _parse_when(raw)
    if dt is None:
        return str(raw)
    return dt.strftime("%Y-%m-%d %H:%M")


# --- Executors ---


async def list_recent_sessions(
    execution: ToolExecution, args: ListRecentSessionsInput
) -> ToolResult:
    svc = execution.ctx.services.get("session")
    if svc is None:
        return ToolResult(content="Session service unavailable.", preview="Unavailable", is_error=True)

    sessions = await svc.list_sessions(limit=args.limit * 2 if args.within_days else args.limit)

    if args.within_days is not None:
        cutoff = datetime.now(UTC) - timedelta(days=args.within_days)
        sessions = [
            s for s in sessions
            if (when := _parse_when(s.get("last_activity"))) is not None and when >= cutoff
        ]
    sessions = sessions[: args.limit]

    if not sessions:
        return ToolResult(content="No sessions found.", preview="0 sessions")

    lines: list[str] = []
    for s in sessions:
        sid = s.get("session_id", "?")
        name = (s.get("name") or "(untitled)").strip()
        when = _format_when(s.get("last_activity") or s.get("started_at"))
        count = s.get("message_count", 0)
        lines.append(f"- {sid} · {name} · {when} · {count} msgs")

    return ToolResult(
        content="\n".join(lines),
        preview=f"{len(sessions)} sessions",
    )


async def read_session(execution: ToolExecution, args: ReadSessionInput) -> ToolResult:
    svc = execution.ctx.services.get("session")
    if svc is None:
        return ToolResult(content="Session service unavailable.", preview="Unavailable", is_error=True)

    roles: set[str] | None = None
    if args.role_filter:
        roles = {r.strip().lower() for r in args.role_filter.split(",") if r.strip()}

    try:
        page = await svc.list_messages(args.session_id, limit=args.limit)
    except Exception as e:
        return ToolResult(
            content=f"Failed to read session {args.session_id}: {e}",
            preview="Read failed",
            is_error=True,
        )

    raw_messages = page.get("messages") if isinstance(page, dict) else page
    if not raw_messages:
        return ToolResult(
            content=f"No messages in session {args.session_id}.",
            preview="0 messages",
        )

    lines: list[str] = []
    kept = 0
    for msg in raw_messages:
        role = (msg.get("role") or "").lower()
        if roles is not None and role not in roles:
            continue
        body = _truncate(_content_to_text(msg.get("content")), args.content_chars)
        # Tool messages carry the tool name on the role/metadata; surface it
        # so the agent can spot patterns like "always runs gh + bash".
        tool_name = msg.get("name") or msg.get("tool_name")
        prefix = f"{role}" + (f"({tool_name})" if tool_name and role == "tool" else "")
        if body:
            lines.append(f"[{prefix}] {body}")
        else:
            lines.append(f"[{prefix}]")
        kept += 1

    if not kept:
        return ToolResult(
            content=f"No messages matched filter in session {args.session_id}.",
            preview="0 matched",
        )

    return ToolResult(
        content="\n".join(lines),
        preview=f"{kept} of {len(raw_messages)} messages",
    )


# --- Tool registration ---

LIST_RECENT_SESSIONS_DESCRIPTION = (
    "List recent chat sessions (most recent first) with id, name, last "
    "activity, and message count. Read-only. Use to find sessions worth "
    "inspecting before calling read_session. Useful for cross-session "
    "pattern detection (audit automations, propose-* skills running in "
    "a scheduled context with no current conversation)."
)

READ_SESSION_DESCRIPTION = (
    "Read messages from a specific session by session_id. Content is "
    "truncated per message to keep context manageable; raise "
    "content_chars (up to 4000) for fuller bodies. Use role_filter='user' "
    "to scan only user prompts when looking for patterns. Read-only."
)


list_recent_sessions_tool = tool(
    display_name="ListRecentSessions",
    description=LIST_RECENT_SESSIONS_DESCRIPTION,
    input_model=ListRecentSessionsInput,
    requires={"session"},
    execute=list_recent_sessions,
)

read_session_tool = tool(
    display_name="ReadSession",
    description=READ_SESSION_DESCRIPTION,
    input_model=ReadSessionInput,
    requires={"session"},
    execute=read_session,
)
