import json
from datetime import UTC, datetime

import pytest

from ntrp.agent import ReasoningContentDelta, ReasoningDelta
from ntrp.context.models import SessionState
from ntrp.core import spawner as spawner_module
from ntrp.core.spawner import create_spawn_fn
from ntrp.events.sse import ReasoningMessageContentEvent, agent_events_to_sse
from ntrp.tools.core.context import BackgroundTaskRegistry, IOBridge, RunContext, ToolContext
from tests.helpers import make_executor, make_text_response


def test_reasoning_sse_preserves_nested_scope():
    (event,) = agent_events_to_sse(
        ReasoningDelta(depth=1, parent_id="call-research", message_id="reasoning-1", content="internal thought")
    )

    assert isinstance(event, ReasoningMessageContentEvent)
    assert event.depth == 1
    assert event.parent_id == "call-research"

    data = json.loads(event.to_sse()["data"])
    assert data["depth"] == 1
    assert data["parent_id"] == "call-research"


@pytest.mark.asyncio
async def test_research_child_reasoning_is_not_emitted_to_parent(monkeypatch):
    prompt_cache_keys = []

    class FakeLLM:
        async def stream(self, messages, model, tools, tool_choice=None, reasoning_effort=None, prompt_cache_key=None):
            prompt_cache_keys.append(prompt_cache_key)
            yield ReasoningContentDelta("internal research thought")
            yield make_text_response("child answer", model=model)

    monkeypatch.setattr(spawner_module, "llm_client", FakeLLM())

    emitted = []

    async def emit(event):
        emitted.append(event)

    executor = make_executor()
    ctx = ToolContext(
        session_state=SessionState(session_id="test", started_at=datetime.now(UTC)),
        registry=executor.registry,
        run=RunContext(run_id="run-1", current_depth=0, max_depth=3),
        io=IOBridge(emit=emit),
        background_tasks=BackgroundTaskRegistry(session_id="test"),
    )

    spawn = create_spawn_fn(executor=executor, model="test-model", max_depth=3, current_depth=0)
    result = await spawn(
        ctx,
        "research task",
        system_prompt="research system",
        tools=[],
        parent_id="call-research",
        timeout=1,
    )

    assert result == "child answer"
    assert emitted == []
    assert len(prompt_cache_keys) == 1
    assert prompt_cache_keys[0].startswith("test::")
