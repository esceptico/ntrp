from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio

import ntrp.database as database
from ntrp.automation.models import Automation
from ntrp.automation.scheduler import Scheduler
from ntrp.automation.service import AutomationService
from ntrp.automation.store import AutomationStore
from ntrp.automation.triggers import TimeTrigger
from ntrp.context.models import SessionState
from ntrp.services.chat import _loop_task_id_from_client_id
from ntrp.tools.automation import (
    CreateAutomationInput,
    CreateLoopInput,
    LoopDoneInput,
    ScheduleWakeupInput,
    create_automation,
    create_loop,
    loop_done,
    schedule_wakeup,
)
from ntrp.tools.core.context import (
    BackgroundTaskRegistry,
    IOBridge,
    RunContext,
    ToolContext,
    ToolExecution,
)
from ntrp.tools.core.registry import ToolRegistry


@pytest_asyncio.fixture
async def store_and_svc(tmp_path: Path):
    conn = await database.connect(tmp_path / "automation.db")
    store = AutomationStore(conn)
    await store.init_schema()
    sched = Scheduler(store=store, build_deps=lambda: None)
    svc = AutomationService(store=store, scheduler=sched)
    now = datetime.now(UTC)
    loop = Automation(
        task_id="loop-1",
        name="x",
        description="x",
        model=None,
        triggers=[TimeTrigger(every="5m")],
        enabled=True,
        created_at=now,
        next_run_at=now + timedelta(minutes=5),
        last_run_at=None,
        last_result=None,
        running_since=None,
        writable=True,
        kind="loop",
        target_session_id="sess-1",
        loop_prompt="watch CI",
    )
    await store.save(loop)
    try:
        yield store, svc
    finally:
        await conn.close()


def _execution(svc: AutomationService, loop_task_id: str | None) -> ToolExecution:
    ctx = ToolContext(
        session_state=SessionState(session_id="sess-1", started_at=datetime.now(UTC)),
        registry=ToolRegistry(),
        run=RunContext(run_id="run-1", loop_task_id=loop_task_id),
        io=IOBridge(),
        services={"automation": svc},
        background_tasks=BackgroundTaskRegistry(session_id="sess-1"),
    )
    return ToolExecution(tool_id="t1", tool_name="schedule_wakeup", ctx=ctx)


def test_loop_task_id_parsing():
    assert _loop_task_id_from_client_id("loop:loop-shy-otter:3") == "loop-shy-otter"
    # task_id can itself contain dashes; only the trailing iter is stripped.
    assert _loop_task_id_from_client_id("loop:loop-a-b-c:42") == "loop-a-b-c"
    assert _loop_task_id_from_client_id(None) is None
    assert _loop_task_id_from_client_id("user-1234") is None
    # Malformed: no iter suffix.
    assert _loop_task_id_from_client_id("loop:onlytaskid") is None


@pytest.mark.asyncio
async def test_schedule_wakeup_updates_next_run(store_and_svc):
    store, svc = store_and_svc
    execution = _execution(svc, loop_task_id="loop-1")

    before = datetime.now(UTC)
    result = await schedule_wakeup(execution, ScheduleWakeupInput(delay_seconds=300))
    assert not result.is_error

    loop = await store.get("loop-1")
    assert loop.next_run_at is not None
    # next_run_at should be ~now + 300s
    delta = (loop.next_run_at - before).total_seconds()
    assert 295 <= delta <= 305


@pytest.mark.asyncio
async def test_schedule_wakeup_refuses_outside_loop(store_and_svc):
    _, svc = store_and_svc
    execution = _execution(svc, loop_task_id=None)

    result = await schedule_wakeup(execution, ScheduleWakeupInput(delay_seconds=60))
    assert result.is_error
    assert "loop" in result.content.lower()


@pytest.mark.asyncio
async def test_loop_done_disables_loop(store_and_svc):
    store, svc = store_and_svc
    execution = _execution(svc, loop_task_id="loop-1")

    result = await loop_done(execution, LoopDoneInput(reason="CI green"))
    assert not result.is_error

    loop = await store.get("loop-1")
    assert loop.enabled is False


@pytest.mark.asyncio
async def test_loop_done_refuses_outside_loop(store_and_svc):
    _, svc = store_and_svc
    execution = _execution(svc, loop_task_id=None)

    result = await loop_done(execution, LoopDoneInput(reason="x"))
    assert result.is_error


def test_schedule_wakeup_input_enforces_min_delay():
    import pydantic

    with pytest.raises(pydantic.ValidationError):
        ScheduleWakeupInput(delay_seconds=59)


# --- create_automation / create_loop tool wiring for channel-aware fields ---


@pytest.mark.asyncio
async def test_create_automation_idempotency_claim_dedupes(store_and_svc):
    _, svc = store_and_svc
    execution = _execution(svc, loop_task_id=None)

    args = CreateAutomationInput(
        name="daily brief",
        description="post the morning brief",
        trigger_type="time",
        at="09:00",
    )

    first = await create_automation(
        execution,
        args.model_copy(update={"idempotency_key": "daily-brief-1", "idempotency_scope": "global"}),
    )
    assert not first.is_error
    assert "Created" in first.content or "created" in first.content.lower()

    second = await create_automation(
        execution,
        args.model_copy(update={"idempotency_key": "daily-brief-1", "idempotency_scope": "global"}),
    )
    assert not second.is_error
    assert "Skipped" in second.content


@pytest.mark.asyncio
async def test_create_automation_passes_thread_id_and_read_history(store_and_svc):
    store, svc = store_and_svc
    execution = _execution(svc, loop_task_id=None)

    args = CreateAutomationInput(
        name="thread automation",
        description="post into a specific thread",
        trigger_type="time",
        every="1h",
    )
    result = await create_automation(
        execution,
        args.model_copy(update={"thread_id": "sess-target", "read_history": True}),
    )
    assert not result.is_error

    rows = await store.list_all()
    created = next(a for a in rows if a.name == "thread automation")
    assert created.thread_id == "sess-target"
    assert created.read_history is True


@pytest.mark.asyncio
async def test_create_automation_defaults_parent_from_loop_ctx(store_and_svc):
    store, svc = store_and_svc
    execution = _execution(svc, loop_task_id="loop-1")

    args = CreateAutomationInput(
        name="child auto",
        description="from loop",
        trigger_type="time",
        every="2h",
    )
    result = await create_automation(execution, args)
    assert not result.is_error

    rows = await store.list_all()
    child = next(a for a in rows if a.name == "child auto")
    assert child.parent_automation_id == "loop-1"


@pytest.mark.asyncio
async def test_create_loop_infers_parent_from_loop_ctx(store_and_svc):
    store, svc = store_and_svc
    execution = _execution(svc, loop_task_id="loop-1")

    result = await create_loop(
        execution,
        CreateLoopInput(prompt="watch CI again", every="5m"),
    )
    assert not result.is_error

    rows = await store.list_all()
    child = next(a for a in rows if a.loop_prompt == "watch CI again")
    assert child.parent_automation_id == "loop-1"


@pytest.mark.asyncio
async def test_create_loop_explicit_parent_overrides_ctx(store_and_svc):
    store, svc = store_and_svc
    execution = _execution(svc, loop_task_id="loop-1")

    result = await create_loop(
        execution,
        CreateLoopInput(
            prompt="watch CI yet again",
            every="5m",
            parent_automation_id="explicit-parent",
        ),
    )
    assert not result.is_error

    rows = await store.list_all()
    child = next(a for a in rows if a.loop_prompt == "watch CI yet again")
    assert child.parent_automation_id == "explicit-parent"
