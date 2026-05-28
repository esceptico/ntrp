from datetime import UTC, datetime

import pytest

import ntrp.tools.memory as memory_tools
from ntrp.context.models import ProjectContext, SessionState
from ntrp.memory.activation import MemoryActivationBundle, MemoryActivationCandidate
from ntrp.tools.core.context import BackgroundTaskRegistry, IOBridge, RunContext, ToolContext, ToolExecution
from ntrp.tools.core.registry import ToolRegistry


class _FakeRetrieval:
    class _Conn:
        async def commit(self):
            return None

    def __init__(self, bundle: MemoryActivationBundle):
        self.bundle = bundle
        self.requests = []
        self.conn = self._Conn()

    async def search(self, request):
        self.requests.append(request)
        return self.bundle


def _bundle(
    *,
    query: str = "user prefs",
    prompt_context: str = "",
    candidates: list[MemoryActivationCandidate] | None = None,
) -> MemoryActivationBundle:
    return MemoryActivationBundle(
        query=query,
        scope="project:proj-1",
        kinds=None,
        used_chars=len(prompt_context),
        candidates=candidates or [],
        prompt_context=prompt_context,
    )


def _execution(
    *,
    tool_id: str = "tool-call-1",
    project: ProjectContext | None = None,
    retrieval: _FakeRetrieval | None = None,
) -> ToolExecution:
    ctx = ToolContext(
        session_state=SessionState(session_id="session-1", started_at=datetime.now(UTC)),
        registry=ToolRegistry(),
        run=RunContext(run_id="run-1"),
        io=IOBridge(),
        services={"memory_retrieval": retrieval or _FakeRetrieval(_bundle())},
        project=project,
        background_tasks=BackgroundTaskRegistry(session_id="session-1"),
    )
    return ToolExecution(tool_id=tool_id, tool_name="recall", ctx=ctx)


@pytest.mark.asyncio
async def test_recall_tool_passes_runtime_context_to_activation():
    candidate = MemoryActivationCandidate(
        item_id="42",
        kind="claim",
        content="User likes concise answers",
        score=0.91,
        score_breakdown={"fts": 1.0},
        reasons=["fts_match"],
        confidence=0.9,
        scope="project:proj-1",
        tags=["preference"],
        source_refs=[{"id": "knowledge:1"}],
        valid_from="2026-01-01T00:00:00+00:00",
        invalid_at=None,
        created_at="2026-01-01T00:00:00+00:00",
    )
    retrieval = _FakeRetrieval(_bundle(prompt_context="MEMORY CONTEXT", candidates=[candidate]))
    execution = _execution(
        tool_id="recall-call-1",
        project=ProjectContext(project_id="proj-1", name="Project", knowledge_scope="project:proj-1"),
        retrieval=retrieval,
    )

    result = await memory_tools.recall(execution, memory_tools.RecallInput(query="user prefs"))

    assert result.content == "MEMORY CONTEXT"
    assert result.data is not None
    activation_bundle = result.data["activation_bundle"]
    assert activation_bundle["candidates"][0]["item_id"] == "42"
    assert activation_bundle["candidates"][0]["kind"] == "claim"
    request = retrieval.requests[0]
    assert request.task == "recall_tool"
    assert request.task_id == "recall-call-1"
    assert request.session_id == "session-1"
    assert request.run_id == "run-1"
    assert request.surface == "tool"
    assert request.scope == "project:proj-1"
    assert request.record_access is True


@pytest.mark.asyncio
async def test_forget_tool_passes_runtime_context_to_activation():
    retrieval = _FakeRetrieval(_bundle(query="stale pref"))
    execution = _execution(tool_id="forget-call-1", retrieval=retrieval)
    execution.tool_name = "forget"

    result = await memory_tools.forget(execution, memory_tools.ForgetInput(query="stale pref"))

    assert result.preview == "Archived 0"
    request = retrieval.requests[0]
    assert request.task == "forget_tool"
    assert request.task_id == "forget-call-1"
    assert request.session_id == "session-1"
    assert request.run_id == "run-1"
    assert request.surface == "tool"
    assert request.limit == 20


class _FakeItemsRepo:
    def __init__(self):
        self.inserted: list = []

    async def insert_item(self, item):
        self.inserted.append(item)
        return "item-xyz"


class _FakeEmbedder:
    async def embed_one(self, text: str):
        return [0.1, 0.2, 0.3]


@pytest.mark.asyncio
async def test_remember_writes_memory_item_as_user_authored_claim():
    project = ProjectContext(
        project_id="proj-1",
        name="proj",
        knowledge_scope="project:proj-1",
    )
    items = _FakeItemsRepo()
    embedder = _FakeEmbedder()
    execution = _execution(project=project, retrieval=None)
    execution.ctx.services["memory_items"] = items
    execution.ctx.services["embedder"] = embedder

    args = memory_tools.RememberInput(
        fact="user prefers casual tone",
        kind="preference",
        salience=1,
        confidence=0.9,
        entities=["User"],
        source="session:abc",
    )
    result = await memory_tools.remember(execution, args)

    assert result.preview == "user prefers casual tone"
    assert len(items.inserted) == 1
    rec = items.inserted[0]
    assert rec.content == "user prefers casual tone"
    assert rec.kind == "claim"
    assert rec.provenance == "user_authored"
    assert rec.scope == "project:proj-1"
    assert rec.confidence == 0.9
    assert "kind:preference" in rec.tags
    assert "salience:1" in rec.tags
    assert "entity:User" in rec.tags
    assert rec.source_refs == [{"kind": "user", "ref": "session:abc"}]
    assert rec.embedding is not None
