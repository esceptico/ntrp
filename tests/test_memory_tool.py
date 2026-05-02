from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from ntrp.context.models import SessionState
from ntrp.memory.models import Fact, FactContext, FactKind, FactLifetime, Observation, SourceType
from ntrp.tools.core.context import BackgroundTaskRegistry, IOBridge, RunContext, ToolContext, ToolExecution
from ntrp.tools.core.registry import ToolRegistry
from ntrp.tools.memory import RecallInput, RememberInput, recall, remember


class FakeMemory:
    def __init__(self):
        self.kwargs = None

    async def remember(self, **kwargs):
        self.kwargs = kwargs
        fact = SimpleNamespace(text=kwargs["text"], kind=kwargs["kind"], lifetime=kwargs["lifetime"])
        return SimpleNamespace(fact=fact, entities_extracted=kwargs["entity_names"] or [])


def _execution(memory) -> ToolExecution:
    ctx = ToolContext(
        session_state=SessionState(session_id="test", started_at=datetime.now(UTC)),
        registry=ToolRegistry(),
        run=RunContext(run_id="run-1"),
        io=IOBridge(),
        services={"memory": memory},
        background_tasks=BackgroundTaskRegistry(session_id="test"),
    )
    return ToolExecution(tool_id="t1", tool_name="remember", ctx=ctx)


@pytest.mark.asyncio
async def test_remember_tool_passes_typed_metadata():
    memory = FakeMemory()

    result = await remember(
        _execution(memory),
        RememberInput(
            fact="User prefers typed memory facts",
            kind=FactKind.PREFERENCE,
            lifetime=FactLifetime.TEMPORARY,
            salience=1,
            confidence=0.8,
            entities=["User"],
            source="chat:test",
            happened_at="2026-05-01T10:00:00+00:00",
            expires_at="2026-06-01T10:00:00+00:00",
        ),
    )

    assert memory.kwargs["text"] == "User prefers typed memory facts"
    assert memory.kwargs["source_type"] == SourceType.CHAT
    assert memory.kwargs["kind"] == FactKind.PREFERENCE
    assert memory.kwargs["lifetime"] == FactLifetime.TEMPORARY
    assert memory.kwargs["salience"] == 1
    assert memory.kwargs["confidence"] == 0.8
    assert memory.kwargs["entity_names"] == ["User"]
    assert memory.kwargs["happened_at"] == datetime(2026, 5, 1, 10, tzinfo=UTC)
    assert memory.kwargs["expires_at"] == datetime(2026, 6, 1, 10, tzinfo=UTC)
    assert "Kind: preference" in result.content
    assert "Lifetime: temporary" in result.content


@pytest.mark.asyncio
async def test_recall_tool_uses_observations_as_model_facing_layer():
    now = datetime.now(UTC)
    fact = Fact(
        id=4,
        text="User said raw facts are noisy",
        embedding=None,
        source_type=SourceType.CHAT,
        source_ref=None,
        happened_at=None,
        created_at=now,
        last_accessed_at=now,
        access_count=0,
        consolidated_at=None,
    )
    observation = Observation(
        id=7,
        summary="User wants prompt memory to use consolidated observations",
        embedding=None,
        evidence_count=1,
        source_fact_ids=[fact.id],
        history=[],
        created_at=now,
        updated_at=now,
        last_accessed_at=now,
        access_count=0,
    )

    class Memory:
        recorded = None
        reinforced = None

        async def inspect_recall(self, *, query: str, limit: int):
            return FactContext(
                facts=[fact],
                observations=[observation],
                bundled_sources={observation.id: [fact]},
            )

        async def record_context_access(self, **kwargs):
            self.recorded = kwargs

        async def reinforce_accessed_memory(self, **kwargs):
            self.reinforced = kwargs

    memory = Memory()

    result = await recall(_execution(memory), RecallInput(query="memory quality"))

    assert "consolidated observations" in result.content
    assert "raw facts are noisy" not in result.content
    assert result.preview == "1 patterns, 0 facts"
    assert memory.recorded["injected_fact_ids"] == []
    assert memory.recorded["injected_observation_ids"] == [observation.id]
    assert memory.recorded["bundled_fact_ids"] == [fact.id]
