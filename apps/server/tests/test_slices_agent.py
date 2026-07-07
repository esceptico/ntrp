from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio

import ntrp.database as database
import ntrp.slices.agent as slice_agent_module
from ntrp.automation.models import Automation
from ntrp.automation.scheduler import Scheduler
from ntrp.automation.store import AutomationStore
from ntrp.automation.triggers import EventTrigger, TimeTrigger
from ntrp.memory.pages import parse_page
from ntrp.slices.agent import _OBSERVE_EXTRA_TOOLS, build_slice_prompt, parse_agent_ask, run_slice_agent
from ntrp.slices.asks import AskStore
from ntrp.slices.models import Slice
from ntrp.tools.executor import ToolExecutor

SLICE = Slice(key="o-1a", title="O-1A", page_path="topics/o-1a.md", autonomy="observe")
PAGE = parse_page("---\ntitle: O-1A\n---\n# O-1A\n\n## Open loops\n- Find counsel.\n")


def test_prompt_contains_page_loops_and_contract():
    p = build_slice_prompt(SLICE, PAGE, recent=[{"event": "memory_changed", "path": "topics/o-1a.md"}])
    assert "Find counsel." in p
    assert "at most ONE ask" in p
    assert "observe" in p  # contract stated to the agent


def test_parse_agent_ask_extracts_json_block_or_none():
    out = 'Reviewed the domain.\n```json\n{"ask": {"text": "Review counsel memo", "kind": "review"}}\n```'
    ask = parse_agent_ask(out)
    assert ask == {"text": "Review counsel memo", "kind": "review"}
    assert parse_agent_ask("All quiet, nothing needs the user.") is None


def test_parse_agent_ask_rejects_invalid_kind_as_silence():
    out = '```json\n{"ask": {"text": "Do the thing", "kind": "yolo"}}\n```'
    assert parse_agent_ask(out) is None


def test_parse_agent_ask_rejects_missing_text_as_silence():
    out = '```json\n{"ask": {"kind": "review"}}\n```'
    assert parse_agent_ask(out) is None


def test_parse_agent_ask_rejects_empty_text_as_silence():
    out = '```json\n{"ask": {"text": "", "kind": "review"}}\n```'
    assert parse_agent_ask(out) is None


def test_parse_agent_ask_rejects_non_str_text_as_silence():
    out = '```json\n{"ask": {"text": 42, "kind": "review"}}\n```'
    assert parse_agent_ask(out) is None


def test_parse_agent_ask_accepts_every_valid_kind():
    for kind in ("review", "decide", "act", "drift"):
        out = f'```json\n{{"ask": {{"text": "x", "kind": "{kind}"}}}}\n```'
        assert parse_agent_ask(out) == {"text": "x", "kind": kind}


def test_observe_toolset_includes_memory_write_but_excludes_bash_and_send():
    """The contract promises observe agents 'may read + update the topic
    page + ask' — regression test for the bug where auto_approve=False
    silently collapsed the toolset to read-only, excluding memory writes."""
    executor = ToolExecutor(get_services=lambda: {"memory_records"})
    tools = executor.get_tools(read_only=True, extra_names=_OBSERVE_EXTRA_TOOLS)
    names = {t["function"]["name"] for t in tools}

    assert "remember" in names  # memory-write, granted to observe
    assert "recall" in names  # read tool, granted by read_only=True
    assert "bash" not in names
    assert "send" not in names


def test_act_toolset_is_a_superset_of_observe_toolset():
    executor = ToolExecutor(get_services=lambda: {"memory_records"})
    observe_names = {
        t["function"]["name"]
        for t in executor.get_tools(read_only=True, extra_names=_OBSERVE_EXTRA_TOOLS)
    }
    act_names = {t["function"]["name"] for t in executor.get_tools()}

    assert observe_names <= act_names
    assert "bash" in act_names
    assert len(act_names) > len(observe_names)


@pytest.mark.asyncio
async def test_run_slice_agent_requests_observe_extra_tools_but_not_auto_approve(monkeypatch):
    """run_slice_agent must build a RunRequest that stays non-auto-approve
    (approvals still gate everything) while still naming the memory-write
    extras for observe mode."""
    captured = {}

    async def fake_run_agent(deps, request):
        captured["request"] = request

        class _Result:
            run_id = "r1"
            output = None

        return _Result()

    monkeypatch.setattr(slice_agent_module, "run_agent", fake_run_agent)

    class FakeAskStore:
        def upsert(self, ask):
            raise AssertionError("no ask should be upserted for a silent run")

    await run_slice_agent(deps=object(), slice=SLICE, page=PAGE, asks=FakeAskStore(), recent=[])

    request = captured["request"]
    assert request.auto_approve is False
    assert request.extra_tool_names == _OBSERVE_EXTRA_TOOLS


@pytest.mark.asyncio
async def test_run_slice_agent_act_mode_requests_no_extra_tools(monkeypatch):
    """act mode already gets the full toolset via auto_approve=True, so no
    extras are needed (and RunRequest.extra_tool_names is ignored on that
    path — see runner._prepare)."""
    captured = {}

    async def fake_run_agent(deps, request):
        captured["request"] = request

        class _Result:
            run_id = "r1"
            output = None

        return _Result()

    monkeypatch.setattr(slice_agent_module, "run_agent", fake_run_agent)

    act_slice = Slice(key="o-1a", title="O-1A", page_path="topics/o-1a.md", autonomy="act")

    class FakeAskStore:
        def upsert(self, ask):
            raise AssertionError("no ask should be upserted for a silent run")

    await run_slice_agent(deps=object(), slice=act_slice, page=PAGE, asks=FakeAskStore(), recent=[])

    request = captured["request"]
    assert request.auto_approve is True
    assert request.extra_tool_names == frozenset()


@pytest_asyncio.fixture
async def store(tmp_path: Path):
    conn = await database.connect(tmp_path / "automation.db")
    s = AutomationStore(conn)
    await s.init_schema()
    yield s
    await conn.close()


def _slice_automation(task_id: str = "slice:o-1a") -> Automation:
    now = datetime.now(UTC)
    return Automation(
        task_id=task_id,
        name=task_id,
        description="Standing agent for the 'O-1A' slice",
        model=None,
        triggers=[TimeTrigger(at="06:30", days="daily"), EventTrigger(event_type="memory_changed")],
        enabled=True,
        created_at=now,
        next_run_at=now - timedelta(seconds=1),
        last_run_at=None,
        last_result=None,
        running_since=None,
        auto_approve=False,
        handler="slice_agent",
        builtin=False,
    )


@pytest.mark.asyncio
async def test_scheduler_dispatches_slice_automation_into_slice_agent_handler(store: AutomationStore):
    """The generic 'slice_agent' handler backs every slice:{key} automation; the
    scheduler must thread automation.task_id through so the shared handler can
    resolve which slice fired (mirrors AutomationRuntime._build_slice_agent_handler,
    which pulls context["task_id"] to look up the slice by key)."""
    await store.save(_slice_automation())
    calls: list[dict] = []

    async def slice_agent_handler(context: dict | None) -> str | None:
        calls.append(context)
        return "ran slice agent"

    sched = Scheduler(store=store, build_deps=lambda: None)
    sched.register_handler("slice_agent", slice_agent_handler)

    await sched._tick()
    for t in list(sched._running):
        await t

    assert len(calls) == 1
    assert calls[0]["task_id"] == "slice:o-1a"

    reloaded = await store.get("slice:o-1a")
    assert reloaded.last_result == "ran slice agent"


@pytest.mark.asyncio
async def test_two_sequential_nominations_leave_only_the_newest_active(tmp_path: Path, monkeypatch):
    """A new agent nomination must retire the slice's previous active
    source=="agent" ask (state "done") rather than piling on top of it —
    only the newest survives as active."""
    outputs = iter([
        '```json\n{"ask": {"text": "First nomination", "kind": "review"}}\n```',
        '```json\n{"ask": {"text": "Second nomination", "kind": "decide"}}\n```',
    ])

    async def fake_run_agent(deps, request):
        class _Result:
            run_id = "r1"
            output = next(outputs)

        return _Result()

    monkeypatch.setattr(slice_agent_module, "run_agent", fake_run_agent)

    asks = AskStore(tmp_path / "state.json")
    await run_slice_agent(deps=object(), slice=SLICE, page=PAGE, asks=asks, recent=[])
    await run_slice_agent(deps=object(), slice=SLICE, page=PAGE, asks=asks, recent=[])

    active = asks.list("o-1a")
    assert len(active) == 1
    assert active[0].text == "Second nomination"

    all_agent_asks = [a for a in asks.list("o-1a", include_resolved=True) if a.source == "agent"]
    assert len(all_agent_asks) == 2
    done = [a for a in all_agent_asks if a.state == "done"]
    assert len(done) == 1
    assert done[0].text == "First nomination"


def test_load_slice_context_reads_page_or_degrades(tmp_path):
    from ntrp.slices.context import load_slice_context
    from ntrp.slices.registry import SliceRegistry
    from ntrp.slices.models import Slice

    reg_path = tmp_path / "slices.json"
    SliceRegistry(reg_path).save([Slice(key="o-1a", title="O-1A", page_path="topics/o-1a.md", autonomy="observe")])
    vault = tmp_path / "memory"
    (vault / "topics").mkdir(parents=True)
    (vault / "topics" / "o-1a.md").write_text("---\ntitle: O-1A\n---\n# O-1A\n\n## Open loops\n- Find counsel.\n")

    ctx = load_slice_context(reg_path, vault, "o-1a")
    assert ctx["title"] == "O-1A"
    assert "Find counsel." in ctx["page"]

    assert load_slice_context(reg_path, vault, "nope") is None  # unknown slice → plain chat
    (vault / "topics" / "o-1a.md").unlink()
    assert load_slice_context(reg_path, vault, "o-1a") is None  # missing page → plain chat


def test_system_blocks_include_slice_block():
    from ntrp.core.prompts import build_system_blocks

    blocks = build_system_blocks(source_details={}, slice_context={"title": "O-1A", "page": "# O-1A\ncase notes"})
    joined = "\n".join(b["text"] for b in blocks)
    assert "## SLICE: O-1A" in joined
    assert "case notes" in joined
