from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio

import ntrp.database as database
import ntrp.tools.research as research_module
from ntrp.agent import SharedLedger
from ntrp.context.models import SessionState
from ntrp.context.store import SessionStore
from ntrp.core.spawner import SpawnResult
from ntrp.tools.core.context import BackgroundTaskRegistry, IOBridge, RunContext, ToolContext, ToolExecution
from ntrp.tools.core.registry import ToolRegistry
from ntrp.tools.executor import ToolExecutor


@pytest_asyncio.fixture
async def session_store(tmp_path: Path):
    conn = await database.connect(tmp_path / "sessions.db")
    read_conn = await database.connect(tmp_path / "sessions.db", readonly=True)
    store = SessionStore(conn, read_conn)
    await store.init_schema()
    yield store
    await read_conn.close()
    await conn.close()


SCRATCHPAD_TOOL_NAMES = {
    "write_research_artifact",
    "append_research_artifact",
    "read_research_artifact",
    "list_research_artifacts",
}


def test_scratchpad_tools_are_research_only():
    from ntrp.integrations.core import CORE_INTEGRATIONS

    assert set(research_module.RESEARCH_AGENT_TOOLS) >= SCRATCHPAD_TOOL_NAMES
    main_tool_names = {name for integ in CORE_INTEGRATIONS for name in integ.tools}
    assert not (SCRATCHPAD_TOOL_NAMES & main_tool_names)


@pytest.mark.asyncio
async def test_research_offers_scratchpad_and_returns_artifact_manifest(session_store: SessionStore):
    captured = {}
    registry = ToolExecutor().registry

    async def spawn_fn(ctx, task, **kwargs):
        captured.update(kwargs)
        await session_store.put_research_artifact(scope_id="research-1", path="inv.md", content="big inventory")
        return SpawnResult(text="done")

    ctx = _context(SharedLedger(), registry=registry, spawn_fn=spawn_fn)
    ctx.services["store"] = session_store
    execution = ToolExecution(tool_id="research-1", tool_name="research", ctx=ctx)

    result = await research_module.research(execution, research_module.ResearchInput(task="x", depth="normal"))

    tool_names = {schema["function"]["name"] for schema in captured["tools"]}
    assert tool_names >= SCRATCHPAD_TOOL_NAMES
    assert result.data is not None
    assert result.data["artifacts"] == [{"path": "inv.md", "bytes": len(b"big inventory"), "preview": "big inventory"}]


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
        return SpawnResult(
            text="done",
            child_run_id="agent-research-1",
            parent_tool_call_id="research-1",
            agent_type="research",
            wait=True,
            status="completed",
        )

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
    assert captured["agent_type"] == "research"
    assert captured["wait"] is True
    assert result.data is not None
    assert result.data["child_agent"] == {
        "child_run_id": "agent-research-1",
        "parent_tool_call_id": "research-1",
        "agent_type": "research",
        "wait": True,
        "status": "completed",
    }
    assert (
        set(captured["extra_tools"])
        == {
            "research_note",
            "research_outline",
            "research_cover",
        }
        | SCRATCHPAD_TOOL_NAMES
    )
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
