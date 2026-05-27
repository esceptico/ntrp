from datetime import UTC, datetime

import pytest

import ntrp.tools.research as research_module
from ntrp.agent import SharedLedger
from ntrp.context.models import SessionState
from ntrp.core.spawner import SpawnResult
from ntrp.memory.activation import MemoryActivationBundle
from ntrp.tools.core.context import BackgroundTaskRegistry, IOBridge, RunContext, ToolContext, ToolExecution
from ntrp.tools.core.registry import ToolRegistry
from ntrp.tools.executor import ToolExecutor


class _FakeMemoryRetrieval:
    def __init__(self, bundle: MemoryActivationBundle):
        self.bundle = bundle
        self.requests = []

    async def search(self, request):
        self.requests.append(request)
        return self.bundle


def _context(
    ledger: SharedLedger | None = None,
    *,
    registry: ToolRegistry | None = None,
    spawn_fn=None,
    research_scope_id: str | None = None,
) -> ToolContext:
    registry = registry or ToolRegistry()
    ctx = ToolContext(
        session_state=SessionState(session_id="test", started_at=datetime.now(UTC)),
        registry=registry,
        run=RunContext(run_id="run-1", current_depth=0, max_depth=3, research_scope_id=research_scope_id),
        io=IOBridge(),
        background_tasks=BackgroundTaskRegistry(session_id="test"),
        ledger=ledger,
    )
    ctx.spawn_fn = spawn_fn
    return ctx


def test_default_agent_tool_schemas_hide_research_ledger_helpers():
    tool_names = {schema["function"]["name"] for schema in ToolExecutor().get_tools()}

    assert "research" in tool_names
    assert "research_note" not in tool_names
    assert "research_outline" not in tool_names
    assert "research_cover" not in tool_names


@pytest.mark.asyncio
async def test_research_spawns_child_with_research_ledger_helpers():
    captured = {}
    registry = ToolExecutor().registry
    ledger = SharedLedger()

    async def spawn_fn(ctx, task, **kwargs):
        captured.update(kwargs)
        return SpawnResult(text="done")

    execution = ToolExecution(
        tool_id="research-1",
        tool_name="research",
        ctx=_context(ledger, registry=registry, spawn_fn=spawn_fn),
    )

    result = await research_module.research(
        execution,
        research_module.ResearchInput(task="inspect research behavior", depth="normal"),
    )

    tool_names = {schema["function"]["name"] for schema in captured["tools"]}
    assert result.content == "done"
    assert "research_note" in tool_names
    assert "research_outline" in tool_names
    assert "research_cover" in tool_names
    assert set(captured["extra_tools"]) == {"research_note", "research_outline", "research_cover"}
    assert captured["research_scope_id"] == "research-1"


@pytest.mark.asyncio
async def test_nested_research_still_passes_ledger_helper_schemas():
    captured = {}
    registry = ToolExecutor().registry.copy_with(research_module.RESEARCH_AGENT_TOOLS)
    ledger = SharedLedger()

    async def spawn_fn(ctx, task, **kwargs):
        captured.update(kwargs)
        return SpawnResult(text="done")

    execution = ToolExecution(
        tool_id="research-nested",
        tool_name="research",
        ctx=_context(ledger, registry=registry, spawn_fn=spawn_fn, research_scope_id="research-parent"),
    )

    result = await research_module.research(
        execution,
        research_module.ResearchInput(task="inspect nested research behavior", depth="normal"),
    )

    tool_names = {schema["function"]["name"] for schema in captured["tools"]}
    assert result.content == "done"
    assert "research_note" in tool_names
    assert "research_outline" in tool_names
    assert "research_cover" in tool_names
    assert captured["extra_tools"] == {}
    assert captured["research_scope_id"] == "research-nested"


@pytest.mark.asyncio
async def test_research_note_records_fact_in_shared_ledger():
    assert hasattr(research_module, "research_note")
    ledger = SharedLedger()
    execution = ToolExecution(tool_id="note-1", tool_name="research_note", ctx=_context(ledger))

    result = await research_module.research_note(
        execution,
        research_module.ResearchNoteInput(
            kind="fact",
            claim="ntrp research agents can spawn child agents.",
            source="apps/server/ntrp/tools/research.py",
            quote="Spawn a research agent",
        ),
    )

    assert result.preview == "Recorded fact"
    assert [note.kind for note in ledger.notes] == ["fact"]
    assert ledger.notes[0].source == "apps/server/ntrp/tools/research.py"


@pytest.mark.asyncio
async def test_research_outline_and_cover_track_gap_notes():
    assert hasattr(research_module, "research_outline")
    assert hasattr(research_module, "research_cover")
    ledger = SharedLedger()

    await research_module.research_outline(
        ToolExecution(tool_id="outline-1", tool_name="research_outline", ctx=_context(ledger)),
        research_module.ResearchOutlineInput(sections=["Repo state", "Prompt behavior"]),
    )
    result = await research_module.research_cover(
        ToolExecution(tool_id="cover-1", tool_name="research_cover", ctx=_context(ledger)),
        research_module.ResearchCoverInput(
            section="Repo state",
            source="apps/server/ntrp/tools/research.py",
        ),
    )

    report = ledger.coverage_report()
    gaps = ledger.add_coverage_gap_notes()

    assert result.preview == "Coverage 50%"
    assert report is not None
    assert report.gaps == ["Prompt behavior"]
    assert [note.what_missing for note in gaps] == ["No source covered outline section: Prompt behavior"]


@pytest.mark.asyncio
async def test_research_outline_coverage_is_scoped_per_research_agent():
    ledger = SharedLedger()

    await research_module.research_outline(
        ToolExecution(
            tool_id="outline-1",
            tool_name="research_outline",
            ctx=_context(ledger, research_scope_id="research-a"),
        ),
        research_module.ResearchOutlineInput(sections=["Repo state", "Prompt behavior"]),
    )
    await research_module.research_outline(
        ToolExecution(
            tool_id="outline-2",
            tool_name="research_outline",
            ctx=_context(ledger, research_scope_id="research-b"),
        ),
        research_module.ResearchOutlineInput(sections=["Vault notes"]),
    )
    await research_module.research_cover(
        ToolExecution(
            tool_id="cover-1",
            tool_name="research_cover",
            ctx=_context(ledger, research_scope_id="research-a"),
        ),
        research_module.ResearchCoverInput(section="Repo state", source="apps/server/ntrp/tools/research.py"),
    )

    report_a = ledger.coverage_report(scope="research-a")
    report_b = ledger.coverage_report(scope="research-b")
    assert report_a is not None
    assert report_b is not None
    assert report_a.gaps == ["Prompt behavior"]
    assert report_b.gaps == ["Vault notes"]


@pytest.mark.asyncio
async def test_research_prompt_names_note_and_coverage_tools():
    ledger = SharedLedger()
    await ledger.register("other-research", "inspect existing behavior", depth="normal")
    ctx = _context(ledger)

    prompt = await research_module._build_research_prompt(ctx, "normal", 2, "research-1")

    assert "research_note" in prompt
    assert "research_outline" in prompt
    assert "research_cover" in prompt
    assert "facts, dead ends, contradictions, and gaps" in prompt
    assert "Do not hide unsupported claims" in prompt


@pytest.mark.asyncio
async def test_research_prompt_memory_activation_records_runtime_context():
    retrieval = _FakeMemoryRetrieval(
        MemoryActivationBundle(
            query="user identity preferences current projects",
            scope=None,
            kinds=None,
            used_chars=0,
            candidates=[],
            prompt_context="",
        )
    )
    ctx = _context()
    ctx.services["memory_retrieval"] = retrieval

    await research_module._build_research_prompt(ctx, depth="quick", remaining_depth=2, tool_id="research-call-1")

    request = retrieval.requests[0]
    assert request.task == "research_context"
    assert request.task_id == "research-call-1"
    assert request.session_id == "test"
    assert request.run_id == "run-1"
    assert request.surface == "prompt"
    assert request.record_access is True


@pytest.mark.asyncio
async def test_research_prompt_injects_memory_context_without_auto_skill_telemetry():
    class AccessEvents:
        def __init__(self):
            self.calls = []

        async def create(self, **kwargs):
            self.calls.append(kwargs)
            return kwargs

    class MemoryService:
        def __init__(self):
            self.access_events = AccessEvents()

    # Slice 7 will rebuild automatic skill activation. Slice 3 retrieval returns no skills_to_use.
    retrieval = _FakeMemoryRetrieval(
        MemoryActivationBundle(
            query="audit the memory loop research path",
            scope=None,
            kinds=None,
            used_chars=44,
            candidates=[],
            usage_event_id=456,
            prompt_context="<facts>remember source-backed research claims</facts>",
        )
    )
    memory = MemoryService()
    ctx = _context()
    ctx.services["memory_retrieval"] = retrieval
    ctx.services["memory"] = memory

    prompt = await research_module._build_research_prompt(
        ctx,
        depth="quick",
        remaining_depth=2,
        tool_id="research-call-2",
        task="audit the memory loop research path",
    )

    request = retrieval.requests[0]
    assert request.query == "audit the memory loop research path"
    assert request.task == "research_context"
    assert request.task_id == "research-call-2"
    assert request.session_id == "test"
    assert request.run_id == "run-1"
    assert request.surface == "prompt"

    assert "<facts>remember source-backed research claims</facts>" in prompt
    assert "<activated_skills>" not in prompt
    assert memory.access_events.calls == []
