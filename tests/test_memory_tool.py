from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from ntrp.context.models import SessionState
from ntrp.memory.models import FactKind, SourceType
from ntrp.tools.core.context import BackgroundTaskRegistry, IOBridge, RunContext, ToolContext, ToolExecution
from ntrp.tools.core.registry import ToolRegistry
from ntrp.tools.memory import RememberInput, remember


class FakeMemory:
    def __init__(self):
        self.kwargs = None

    async def remember(self, **kwargs):
        self.kwargs = kwargs
        fact = SimpleNamespace(text=kwargs["text"], kind=kwargs["kind"])
        return SimpleNamespace(fact=fact, entities_extracted=kwargs["entity_names"] or [])


def _execution(memory: FakeMemory) -> ToolExecution:
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
    assert memory.kwargs["salience"] == 1
    assert memory.kwargs["confidence"] == 0.8
    assert memory.kwargs["entity_names"] == ["User"]
    assert memory.kwargs["happened_at"] == datetime(2026, 5, 1, 10, tzinfo=UTC)
    assert memory.kwargs["expires_at"] == datetime(2026, 6, 1, 10, tzinfo=UTC)
    assert "Kind: preference" in result.content
