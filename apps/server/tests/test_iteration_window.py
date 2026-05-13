"""Bounded history window for iteration-mode loops.

When a loop fires in `read_history=True` mode it re-enters the target
session. To keep the prompt context bounded for long-running monitors we
cap prior history to LOOP_ITERATION_HISTORY_WINDOW messages — preserving
the system message at index 0 and keeping the most recent tail.

Trimming is runtime-only — disk history is untouched.
"""

from datetime import UTC, datetime

import pytest

from ntrp.constants import LOOP_ITERATION_HISTORY_WINDOW
from ntrp.context.models import SessionData, SessionState
from ntrp.core.factory import AgentConfig
from ntrp.server.state import RunRegistry
from ntrp.services.chat import ChatDeps, _loop_task_id_from_client_id, prepare_chat


def _make_history(n: int, *, with_system: bool = True) -> list[dict]:
    msgs: list[dict] = []
    if with_system:
        msgs.append({"role": "system", "content": "you are helpful"})
    for i in range(n):
        role = "user" if i % 2 == 0 else "assistant"
        msgs.append({"role": role, "content": f"msg-{i}"})
    return msgs


class _StubExecutor:
    def __init__(self) -> None:
        from ntrp.tools.core.registry import ToolRegistry

        self.registry = ToolRegistry()
        self.tool_services: dict[str, object] = {}

    def get_tools(self) -> list[dict]:
        return []


class _StubSessionService:
    def __init__(self, messages: list[dict], session_id: str = "sess-1") -> None:
        self._messages = messages
        self._session_id = session_id
        self.save_progress_calls: list[list[dict]] = []

    async def load(self, session_id: str | None = None) -> SessionData | None:
        state = SessionState(
            session_id=session_id or self._session_id,
            started_at=datetime.now(UTC),
        )
        return SessionData(state=state, messages=list(self._messages))

    def create(
        self,
        name: str | None = None,
        session_type: str = "chat",
        origin_automation_id: str | None = None,
    ) -> SessionState:
        return SessionState(
            session_id=self._session_id,
            started_at=datetime.now(UTC),
            name=name,
        )

    async def save_progress(self, session_state, messages: list[dict]) -> None:
        self.save_progress_calls.append(list(messages))


def _make_deps(session_service: _StubSessionService) -> ChatDeps:
    return ChatDeps(
        chat_model="gpt-5.2",
        agent_config=AgentConfig(
            model="gpt-5.2",
            research_model=None,
            max_depth=1,
            deferred_tools=False,
        ),
        executor=_StubExecutor(),
        session_service=session_service,
        run_registry=RunRegistry(),
        available_integrations=[],
        integration_errors={},
    )


def _split_history(messages: list[dict]) -> tuple[list[dict], list[dict], dict]:
    """Returns (system, prior_history, fresh_user_message)."""
    system = [m for m in messages if m.get("role") == "system"]
    user_added = messages[-1]
    middle = messages[len(system) : -1]
    return system, middle, user_added


def test_loop_iteration_history_window_constant_exists():
    # Sanity check that the budget is what the design calls for. If this
    # ever changes intentionally, update the test consciously.
    assert LOOP_ITERATION_HISTORY_WINDOW == 50


@pytest.mark.asyncio
async def test_loop_iteration_trims_history_to_window():
    # 60 prior messages (system + 60). Loop fire should leave system + last 50
    # prior msgs + the fresh user prompt = 52 entries.
    history = _make_history(60)
    svc = _StubSessionService(history)
    deps = _make_deps(svc)

    client_id = "loop:loop-shy-otter:7"
    ctx = await prepare_chat(
        deps,
        message="iteration prompt",
        skip_approvals=None,
        session_id="sess-1",
        client_id=client_id,
        loop_task_id=_loop_task_id_from_client_id(client_id),
    )

    system, prior, user_msg = _split_history(ctx.run.messages)
    assert len(system) == 1
    assert len(prior) == LOOP_ITERATION_HISTORY_WINDOW
    # Kept the tail, not the head.
    assert prior[0]["content"] == "msg-10"
    assert prior[-1]["content"] == "msg-59"
    # The fresh loop-dispatched message is appended after the trimmed tail.
    assert user_msg["role"] == "user"
    assert user_msg.get("is_meta") is True
    assert user_msg["client_id"] == "loop:loop-shy-otter:7"


@pytest.mark.asyncio
async def test_loop_iteration_under_window_keeps_all_history():
    # 30 prior messages — below the cap → no trimming.
    history = _make_history(30)
    svc = _StubSessionService(history)
    deps = _make_deps(svc)

    client_id = "loop:loop-a:1"
    ctx = await prepare_chat(
        deps,
        message="iter",
        skip_approvals=None,
        session_id="sess-1",
        client_id=client_id,
        loop_task_id=_loop_task_id_from_client_id(client_id),
    )

    system, prior, _ = _split_history(ctx.run.messages)
    assert len(system) == 1
    assert len(prior) == 30
    assert prior[0]["content"] == "msg-0"
    assert prior[-1]["content"] == "msg-29"


@pytest.mark.asyncio
async def test_non_loop_chat_does_not_trim_history():
    # 60 prior messages but no loop client_id → full history visible.
    history = _make_history(60)
    svc = _StubSessionService(history)
    deps = _make_deps(svc)

    ctx = await prepare_chat(
        deps,
        message="hi there",
        skip_approvals=False,
        session_id="sess-1",
        client_id="user-cid-42",
    )

    system, prior, user_msg = _split_history(ctx.run.messages)
    assert len(system) == 1
    assert len(prior) == 60
    assert prior[0]["content"] == "msg-0"
    assert prior[-1]["content"] == "msg-59"
    # Not flagged as meta — this is a real user message.
    assert "is_meta" not in user_msg


@pytest.mark.asyncio
async def test_loop_iteration_preserves_system_after_trim():
    # System message must survive even when the tail is trimmed aggressively.
    history = _make_history(60)
    # Make the system message recognizable so we can assert it's the same one.
    history[0]["content"] = "SENTINEL-SYSTEM-PROMPT"
    svc = _StubSessionService(history)
    deps = _make_deps(svc)

    client_id = "loop:loop-b:99"
    ctx = await prepare_chat(
        deps,
        message="iter",
        skip_approvals=None,
        session_id="sess-1",
        client_id=client_id,
        loop_task_id=_loop_task_id_from_client_id(client_id),
    )

    # The system message is rebuilt by _prepare_messages from system_blocks,
    # so the *content* won't match the sentinel — but it must still be
    # present at index 0 and the trimmed tail must not contain a leftover
    # system row.
    assert ctx.run.messages[0]["role"] == "system"
    other_systems = [m for m in ctx.run.messages[1:] if m.get("role") == "system"]
    assert other_systems == []
    # And the prior-history portion is exactly the cap.
    _, prior, _ = _split_history(ctx.run.messages)
    assert len(prior) == LOOP_ITERATION_HISTORY_WINDOW
