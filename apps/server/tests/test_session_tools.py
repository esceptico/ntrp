"""Tests for the read-only sessions tools (`list_recent_sessions`,
`read_session`) used by cross-session audit automations."""

from datetime import UTC, datetime, timedelta

import pytest

from ntrp.context.models import SessionState
from ntrp.tools.core.context import (
    BackgroundTaskRegistry,
    IOBridge,
    RunContext,
    ToolContext,
    ToolExecution,
)
from ntrp.tools.core.registry import ToolRegistry
from ntrp.tools.sessions import (
    ListRecentSessionsInput,
    ReadSessionInput,
    list_recent_sessions,
    read_session,
)


class _StubSessionService:
    """Just enough of the SessionService surface to drive the tools.
    Lets us assert what the tool actually returned without spinning up a
    real session store."""

    def __init__(self, sessions: list[dict], messages: dict[str, list[dict]] | None = None):
        self._sessions = sessions
        self._messages = messages or {}

    async def list_sessions(self, limit: int = 20) -> list[dict]:
        return list(self._sessions[:limit])

    async def list_messages(self, session_id: str, limit: int = 100) -> dict:
        msgs = self._messages.get(session_id, [])
        return {"messages": list(msgs[:limit])}


def _make_execution(services: dict | None = None) -> ToolExecution:
    ctx = ToolContext(
        session_state=SessionState(session_id="cur", started_at=datetime.now(UTC)),
        registry=ToolRegistry(),
        run=RunContext(run_id="run-1"),
        io=IOBridge(),
        background_tasks=BackgroundTaskRegistry(session_id="cur"),
        services=services or {},
    )
    return ToolExecution(tool_id="t1", tool_name="test", ctx=ctx)


@pytest.mark.asyncio
async def test_list_recent_sessions_returns_formatted_list():
    now = datetime.now(UTC)
    service = _StubSessionService(
        sessions=[
            {
                "session_id": "20260510_120000_000",
                "name": "Daily standup",
                "started_at": (now - timedelta(hours=2)).isoformat(),
                "last_activity": (now - timedelta(hours=1)).isoformat(),
                "message_count": 12,
            },
            {
                "session_id": "20260509_090000_000",
                "name": None,
                "started_at": (now - timedelta(days=1)).isoformat(),
                "last_activity": (now - timedelta(days=1)).isoformat(),
                "message_count": 4,
            },
        ]
    )
    execution = _make_execution(services={"session": service})

    result = await list_recent_sessions(execution, ListRecentSessionsInput(limit=20))

    assert not result.is_error
    assert "20260510_120000_000" in result.content
    assert "Daily standup" in result.content
    assert "(untitled)" in result.content  # falls back when name is None
    assert "12 msgs" in result.content


@pytest.mark.asyncio
async def test_list_recent_sessions_filters_by_within_days():
    now = datetime.now(UTC)
    service = _StubSessionService(
        sessions=[
            {
                "session_id": "recent",
                "name": "Today",
                "last_activity": (now - timedelta(hours=2)).isoformat(),
                "message_count": 5,
            },
            {
                "session_id": "old",
                "name": "Last month",
                "last_activity": (now - timedelta(days=20)).isoformat(),
                "message_count": 3,
            },
        ]
    )
    execution = _make_execution(services={"session": service})

    result = await list_recent_sessions(
        execution, ListRecentSessionsInput(limit=20, within_days=7)
    )

    assert "recent" in result.content
    assert "old" not in result.content


@pytest.mark.asyncio
async def test_list_recent_sessions_missing_service_is_error():
    execution = _make_execution(services={})  # session service absent

    result = await list_recent_sessions(execution, ListRecentSessionsInput())

    assert result.is_error
    assert "unavailable" in result.content.lower()


@pytest.mark.asyncio
async def test_read_session_truncates_long_content():
    long_body = "x" * 1000
    service = _StubSessionService(
        sessions=[],
        messages={
            "s1": [
                {"role": "user", "content": "Hello, can you summarize my emails?"},
                {"role": "assistant", "content": long_body},
            ]
        },
    )
    execution = _make_execution(services={"session": service})

    result = await read_session(
        execution, ReadSessionInput(session_id="s1", content_chars=100)
    )

    assert not result.is_error
    assert "[user]" in result.content
    assert "[assistant]" in result.content
    # Long body should have been trimmed with an ellipsis marker.
    assert "…" in result.content
    # And it shouldn't carry the full original.
    assert long_body not in result.content


@pytest.mark.asyncio
async def test_read_session_role_filter():
    service = _StubSessionService(
        sessions=[],
        messages={
            "s1": [
                {"role": "user", "content": "prompt"},
                {"role": "assistant", "content": "answer"},
                {"role": "tool", "content": "tool output", "name": "bash"},
            ]
        },
    )
    execution = _make_execution(services={"session": service})

    result = await read_session(
        execution, ReadSessionInput(session_id="s1", role_filter="user")
    )

    assert "[user]" in result.content
    assert "[assistant]" not in result.content
    assert "[tool" not in result.content


@pytest.mark.asyncio
async def test_read_session_handles_structured_content_blocks():
    service = _StubSessionService(
        sessions=[],
        messages={
            "s1": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Look at this image"},
                        {"type": "image", "source": {}},
                    ],
                },
                {
                    "role": "assistant",
                    "content": [
                        {"type": "tool_use", "name": "bash", "input": {}},
                    ],
                },
            ]
        },
    )
    execution = _make_execution(services={"session": service})

    result = await read_session(execution, ReadSessionInput(session_id="s1"))

    assert "Look at this image" in result.content
    assert "[image]" in result.content
    assert "[tool_use: bash]" in result.content
