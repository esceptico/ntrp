from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio

import ntrp.database as database
from ntrp.automation.scheduler import Scheduler
from ntrp.automation.service import AutomationService
from ntrp.automation.store import AutomationStore


@pytest_asyncio.fixture
async def store(tmp_path: Path):
    conn = await database.connect(tmp_path / "automation.db")
    s = AutomationStore(conn)
    await s.init_schema()
    yield s
    await conn.close()


@pytest_asyncio.fixture
async def service(store: AutomationStore):
    sched = Scheduler(store=store, build_deps=lambda: None)
    return AutomationService(store=store, scheduler=sched)


# ---------------- store-level: try_claim_idempotency ----------------


@pytest.mark.asyncio
async def test_global_claim_first_succeeds_second_fails(store: AutomationStore):
    assert await store.try_claim_idempotency(
        scope="global", key="item-42", automation_task_id="child-a"
    )
    assert not await store.try_claim_idempotency(
        scope="global", key="item-42", automation_task_id="child-b"
    )


@pytest.mark.asyncio
async def test_global_claim_ignores_parent(store: AutomationStore):
    # Global scope: same key conflicts regardless of which parent.
    assert await store.try_claim_idempotency(
        scope="global", key="news-7", automation_task_id="child-a"
    )
    assert not await store.try_claim_idempotency(
        scope="global", key="news-7", automation_task_id="child-b"
    )


@pytest.mark.asyncio
async def test_run_claim_first_succeeds_second_fails(store: AutomationStore):
    fire_at = datetime(2026, 5, 13, 10, 0, tzinfo=UTC).isoformat()
    assert await store.try_claim_idempotency(
        scope="run",
        key="item-1",
        parent_automation_id="watcher",
        parent_fire_at=fire_at,
        automation_task_id="child-a",
    )
    assert not await store.try_claim_idempotency(
        scope="run",
        key="item-1",
        parent_automation_id="watcher",
        parent_fire_at=fire_at,
        automation_task_id="child-b",
    )


@pytest.mark.asyncio
async def test_run_claim_different_fire_at_succeeds(store: AutomationStore):
    # Run scope: claim namespace resets per fire.
    fire1 = datetime(2026, 5, 13, 10, 0, tzinfo=UTC).isoformat()
    fire2 = datetime(2026, 5, 13, 11, 0, tzinfo=UTC).isoformat()
    assert await store.try_claim_idempotency(
        scope="run",
        key="item-1",
        parent_automation_id="watcher",
        parent_fire_at=fire1,
        automation_task_id="child-a",
    )
    assert await store.try_claim_idempotency(
        scope="run",
        key="item-1",
        parent_automation_id="watcher",
        parent_fire_at=fire2,
        automation_task_id="child-b",
    )


@pytest.mark.asyncio
async def test_attempt_claim_first_succeeds_second_fails(store: AutomationStore):
    fire_at = datetime(2026, 5, 13, 10, 0, tzinfo=UTC).isoformat()
    assert await store.try_claim_idempotency(
        scope="attempt",
        key="item-1",
        parent_automation_id="watcher",
        parent_fire_at=fire_at,
        attempt_n=0,
        automation_task_id="child-a",
    )
    assert not await store.try_claim_idempotency(
        scope="attempt",
        key="item-1",
        parent_automation_id="watcher",
        parent_fire_at=fire_at,
        attempt_n=0,
        automation_task_id="child-b",
    )


@pytest.mark.asyncio
async def test_attempt_claim_different_attempt_succeeds(store: AutomationStore):
    fire_at = datetime(2026, 5, 13, 10, 0, tzinfo=UTC).isoformat()
    assert await store.try_claim_idempotency(
        scope="attempt",
        key="item-1",
        parent_automation_id="watcher",
        parent_fire_at=fire_at,
        attempt_n=0,
        automation_task_id="child-a",
    )
    assert await store.try_claim_idempotency(
        scope="attempt",
        key="item-1",
        parent_automation_id="watcher",
        parent_fire_at=fire_at,
        attempt_n=1,
        automation_task_id="child-b",
    )


# ---------------- validation ----------------


@pytest.mark.asyncio
async def test_global_with_parent_raises(store: AutomationStore):
    with pytest.raises(ValueError):
        await store.try_claim_idempotency(
            scope="global",
            key="k",
            parent_automation_id="watcher",
            automation_task_id="c",
        )


@pytest.mark.asyncio
async def test_global_with_fire_at_raises(store: AutomationStore):
    with pytest.raises(ValueError):
        await store.try_claim_idempotency(
            scope="global",
            key="k",
            parent_fire_at="2026-05-13T10:00:00+00:00",
            automation_task_id="c",
        )


@pytest.mark.asyncio
async def test_global_with_attempt_n_raises(store: AutomationStore):
    with pytest.raises(ValueError):
        await store.try_claim_idempotency(
            scope="global",
            key="k",
            attempt_n=0,
            automation_task_id="c",
        )


@pytest.mark.asyncio
async def test_run_without_fire_at_raises(store: AutomationStore):
    with pytest.raises(ValueError):
        await store.try_claim_idempotency(
            scope="run",
            key="k",
            parent_automation_id="watcher",
            automation_task_id="c",
        )


@pytest.mark.asyncio
async def test_run_without_parent_raises(store: AutomationStore):
    with pytest.raises(ValueError):
        await store.try_claim_idempotency(
            scope="run",
            key="k",
            parent_fire_at="2026-05-13T10:00:00+00:00",
            automation_task_id="c",
        )


@pytest.mark.asyncio
async def test_run_with_attempt_n_raises(store: AutomationStore):
    with pytest.raises(ValueError):
        await store.try_claim_idempotency(
            scope="run",
            key="k",
            parent_automation_id="watcher",
            parent_fire_at="2026-05-13T10:00:00+00:00",
            attempt_n=0,
            automation_task_id="c",
        )


@pytest.mark.asyncio
async def test_attempt_without_attempt_n_raises(store: AutomationStore):
    with pytest.raises(ValueError):
        await store.try_claim_idempotency(
            scope="attempt",
            key="k",
            parent_automation_id="watcher",
            parent_fire_at="2026-05-13T10:00:00+00:00",
            automation_task_id="c",
        )


@pytest.mark.asyncio
async def test_unknown_scope_raises(store: AutomationStore):
    with pytest.raises(ValueError):
        await store.try_claim_idempotency(
            scope="bogus",
            key="k",
            automation_task_id="c",
        )


# ---------------- list_claims_for_parent ----------------


@pytest.mark.asyncio
async def test_list_claims_for_parent(store: AutomationStore):
    fire_at = datetime(2026, 5, 13, 10, 0, tzinfo=UTC).isoformat()
    await store.try_claim_idempotency(
        scope="run",
        key="item-1",
        parent_automation_id="watcher",
        parent_fire_at=fire_at,
        automation_task_id="child-a",
    )
    await store.try_claim_idempotency(
        scope="run",
        key="item-2",
        parent_automation_id="watcher",
        parent_fire_at=fire_at,
        automation_task_id="child-b",
    )
    # Different parent — should not appear.
    await store.try_claim_idempotency(
        scope="run",
        key="item-3",
        parent_automation_id="other-watcher",
        parent_fire_at=fire_at,
        automation_task_id="child-c",
    )

    claims = await store.list_claims_for_parent("watcher")
    keys = {c["key"] for c in claims}
    assert keys == {"item-1", "item-2"}


# ---------------- service integration ----------------


@pytest.mark.asyncio
async def test_create_with_idempotency_key_returns_none_on_repeat(service: AutomationService):
    first = await service.create(
        name="watch-item-1",
        description="poke item 1",
        trigger_type="time",
        at="09:00",
        idempotency_key="item-1",
        idempotency_scope="global",
    )
    assert first is not None
    assert first.idempotency_key == "item-1"
    assert first.idempotency_scope == "global"

    second = await service.create(
        name="watch-item-1-again",
        description="poke item 1 again",
        trigger_type="time",
        at="09:00",
        idempotency_key="item-1",
        idempotency_scope="global",
    )
    assert second is None


@pytest.mark.asyncio
async def test_create_run_scope_isolated_per_fire(service: AutomationService):
    fire1 = datetime(2026, 5, 13, 10, 0, tzinfo=UTC).isoformat()
    fire2 = datetime(2026, 5, 13, 11, 0, tzinfo=UTC).isoformat()

    a = await service.create(
        name="child-a",
        description="x",
        trigger_type="time",
        at="09:00",
        idempotency_key="item-1",
        idempotency_scope="run",
        parent_automation_id="watcher",
        parent_fire_at=fire1,
    )
    dup = await service.create(
        name="child-a-dup",
        description="x",
        trigger_type="time",
        at="09:00",
        idempotency_key="item-1",
        idempotency_scope="run",
        parent_automation_id="watcher",
        parent_fire_at=fire1,
    )
    b = await service.create(
        name="child-a-fire2",
        description="x",
        trigger_type="time",
        at="09:00",
        idempotency_key="item-1",
        idempotency_scope="run",
        parent_automation_id="watcher",
        parent_fire_at=fire2,
    )
    assert a is not None
    assert dup is None
    assert b is not None


@pytest.mark.asyncio
async def test_create_loop_with_idempotency(service: AutomationService):
    first = await service.create_loop(
        session_id="sess-1",
        prompt="watch CI",
        every="5m",
        idempotency_key="ci-loop",
        idempotency_scope="global",
    )
    assert first is not None
    second = await service.create_loop(
        session_id="sess-1",
        prompt="watch CI again",
        every="5m",
        idempotency_key="ci-loop",
        idempotency_scope="global",
    )
    assert second is None
