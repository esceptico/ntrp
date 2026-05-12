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


@pytest_asyncio.fixture
async def store(tmp_path: Path):
    conn = await database.connect(tmp_path / "automation.db")
    s = AutomationStore(conn)
    await s.init_schema()
    yield s
    await conn.close()


def _loop(
    task_id: str = "loop-1",
    *,
    session_id: str = "sess-1",
    prompt: str = "check CI",
    every: str = "5m",
    max_iterations: int | None = None,
    iteration_count: int = 0,
    next_run_at: datetime | None = None,
) -> Automation:
    now = datetime.now(UTC)
    return Automation(
        task_id=task_id,
        name=f"Loop: {prompt[:40]}",
        description=prompt,
        model=None,
        triggers=[TimeTrigger(every=every)],
        enabled=True,
        created_at=now,
        next_run_at=next_run_at or (now - timedelta(seconds=1)),
        last_run_at=None,
        last_result=None,
        running_since=None,
        writable=True,
        kind="loop",
        target_session_id=session_id,
        loop_prompt=prompt,
        max_iterations=max_iterations,
        iteration_count=iteration_count,
    )


def _make_scheduler(store: AutomationStore) -> tuple[Scheduler, list[Automation]]:
    dispatched: list[Automation] = []

    async def dispatcher(auto: Automation) -> str | None:
        dispatched.append(auto)
        return "fake-run-id"

    sched = Scheduler(store=store, build_deps=lambda: None)
    sched.set_loop_dispatcher(dispatcher)
    return sched, dispatched


@pytest.mark.asyncio
async def test_scheduler_dispatches_due_loop(store: AutomationStore):
    await store.save(_loop())
    sched, dispatched = _make_scheduler(store)

    await sched._tick()
    # Loops fire asynchronously through _start_run → _run_and_finalize.
    # Drain the scheduler's tracked tasks.
    for t in list(sched._running):
        await t

    assert len(dispatched) == 1
    assert dispatched[0].task_id == "loop-1"
    assert dispatched[0].loop_prompt == "check CI"

    reloaded = await store.get("loop-1")
    assert reloaded.iteration_count == 1
    assert reloaded.enabled is True
    assert reloaded.next_run_at is not None and reloaded.next_run_at > datetime.now(UTC)


@pytest.mark.asyncio
async def test_max_iterations_disables_loop(store: AutomationStore):
    await store.save(_loop(max_iterations=2, iteration_count=1))
    sched, dispatched = _make_scheduler(store)

    await sched._tick()
    for t in list(sched._running):
        await t

    assert len(dispatched) == 1
    reloaded = await store.get("loop-1")
    assert reloaded.iteration_count == 2
    assert reloaded.enabled is False


@pytest.mark.asyncio
async def test_loop_without_dispatcher_raises(store: AutomationStore):
    await store.save(_loop())
    sched = Scheduler(store=store, build_deps=lambda: None)  # no dispatcher

    await sched._tick()
    for t in list(sched._running):
        await t

    # Loop run failed (no dispatcher); iteration_count untouched, next_run advanced.
    reloaded = await store.get("loop-1")
    assert reloaded.iteration_count == 0


@pytest.mark.asyncio
async def test_create_loop_via_service_stores_correctly(store: AutomationStore):
    sched, _ = _make_scheduler(store)
    svc = AutomationService(store=store, scheduler=sched)

    loop = await svc.create_loop(
        session_id="sess-1",
        prompt="watch CI",
        every="5m",
        max_iterations=10,
        stop_when="when green",
    )

    assert loop.kind == "loop"
    assert loop.target_session_id == "sess-1"
    assert loop.loop_prompt == "watch CI"
    assert loop.max_iterations == 10
    assert loop.stop_when == "when green"
    assert loop.triggers[0].params()["every"] == "5m"

    loops = await svc.list_loops_by_session("sess-1")
    assert [a.task_id for a in loops] == [loop.task_id]


@pytest.mark.asyncio
async def test_create_loop_rejects_empty_prompt(store: AutomationStore):
    sched, _ = _make_scheduler(store)
    svc = AutomationService(store=store, scheduler=sched)

    with pytest.raises(ValueError, match="prompt"):
        await svc.create_loop(session_id="s", prompt="   ", every="5m")


@pytest.mark.asyncio
async def test_max_iterations_loop_clears_next_run_at(store: AutomationStore):
    # Fire the final iteration of a 2-iter loop. After it, the loop should
    # be disabled AND next_run_at should be None (no future countdown for
    # a loop that will never fire again).
    await store.save(_loop(max_iterations=2, iteration_count=1))
    sched, dispatched = _make_scheduler(store)

    await sched._tick()
    for t in list(sched._running):
        await t

    assert len(dispatched) == 1
    reloaded = await store.get("loop-1")
    assert reloaded.enabled is False
    assert reloaded.next_run_at is None


@pytest.mark.asyncio
async def test_aged_out_loop_clears_next_run_at(store: AutomationStore):
    old = datetime.now(UTC) - timedelta(days=8)
    loop = Automation(
        task_id="loop-old",
        name="x",
        description="x",
        model=None,
        triggers=[TimeTrigger(every="5m")],
        enabled=True,
        created_at=old,
        next_run_at=datetime.now(UTC) - timedelta(seconds=1),
        last_run_at=None,
        last_result=None,
        running_since=None,
        writable=True,
        kind="loop",
        target_session_id="sess",
        loop_prompt="check x",
        max_age_days=7,
    )
    await store.save(loop)
    sched, _ = _make_scheduler(store)

    await sched._tick()
    for t in list(sched._running):
        await t

    reloaded = await store.get("loop-old")
    assert reloaded.enabled is False
    assert reloaded.next_run_at is None


@pytest.mark.asyncio
async def test_aged_out_loop_disables_without_firing(store: AutomationStore):
    # Loop created 8 days ago, max_age_days=7 → aged out.
    old = datetime.now(UTC) - timedelta(days=8)
    loop = Automation(
        task_id="loop-old",
        name="x",
        description="x",
        model=None,
        triggers=[TimeTrigger(every="5m")],
        enabled=True,
        created_at=old,
        next_run_at=datetime.now(UTC) - timedelta(seconds=1),
        last_run_at=None,
        last_result=None,
        running_since=None,
        writable=True,
        kind="loop",
        target_session_id="sess",
        loop_prompt="check x",
        max_age_days=7,
    )
    await store.save(loop)
    sched, dispatched = _make_scheduler(store)

    await sched._tick()
    for t in list(sched._running):
        await t

    assert dispatched == []  # never dispatched
    reloaded = await store.get("loop-old")
    assert reloaded.enabled is False
    assert reloaded.iteration_count == 0
