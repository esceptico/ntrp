from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio

import ntrp.database as database
from ntrp.automation.models import Automation
from ntrp.automation.scheduler import Scheduler
from ntrp.automation.store import AutomationStore
from ntrp.automation.triggers import EventTrigger, TimeTrigger
from ntrp.memory.pages import parse_page
from ntrp.slices.agent import build_slice_prompt, parse_agent_ask
from ntrp.slices.models import Slice

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
