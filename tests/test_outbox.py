from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio

import ntrp.database as database
from ntrp.agent import Usage
from ntrp.events.internal import RunCompleted
from ntrp.outbox import (
    OUTBOX_FACT_INDEX_DELETE,
    OUTBOX_FACT_INDEX_UPSERT,
    OUTBOX_MEMORY_INDEX_CLEAR,
    OUTBOX_RUN_COMPLETED,
    OutboxStore,
    OutboxWorker,
    run_completed_from_payload,
)


def _run_completed(run_id: str = "run-1") -> RunCompleted:
    return RunCompleted(
        run_id=run_id,
        session_id="session-1",
        messages=(
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "done"},
        ),
        usage=Usage(prompt_tokens=3, completion_tokens=5, cache_read_tokens=7, cache_write_tokens=11),
        result="done",
    )


@pytest_asyncio.fixture
async def outbox_store(tmp_path: Path):
    conn = await database.connect(tmp_path / "outbox.db")
    store = OutboxStore(conn)
    await store.init_schema()
    yield store
    await conn.close()


@pytest.mark.asyncio
async def test_enqueue_run_completed_is_idempotent_and_claims_payload(outbox_store: OutboxStore):
    event = _run_completed()

    assert await outbox_store.enqueue_run_completed(event) is True
    assert await outbox_store.enqueue_run_completed(event) is False

    claimed = await outbox_store.claim_batch(worker_id="test-worker", limit=10)

    assert len(claimed) == 1
    assert claimed[0].event_type == OUTBOX_RUN_COMPLETED
    assert claimed[0].attempts == 1
    restored = run_completed_from_payload(claimed[0].payload)
    assert restored == event

    await outbox_store.mark_completed(claimed[0].id)
    assert await outbox_store.claim_batch(worker_id="test-worker", limit=10) == []


@pytest.mark.asyncio
async def test_enqueue_memory_index_events_allow_repeated_updates(outbox_store: OutboxStore):
    assert await outbox_store.enqueue_fact_index_upsert(10, "first") is True
    assert await outbox_store.enqueue_fact_index_upsert(10, "second") is True
    assert await outbox_store.enqueue_fact_index_delete(10) is True
    assert await outbox_store.enqueue_memory_index_clear() is True

    claimed = await outbox_store.claim_batch(worker_id="test-worker", limit=10)

    assert [event.event_type for event in claimed] == [
        OUTBOX_FACT_INDEX_UPSERT,
        OUTBOX_FACT_INDEX_UPSERT,
        OUTBOX_FACT_INDEX_DELETE,
        OUTBOX_MEMORY_INDEX_CLEAR,
    ]
    assert claimed[0].payload == {"fact_id": 10, "text": "first"}
    assert claimed[1].payload == {"fact_id": 10, "text": "second"}
    assert claimed[2].payload == {"fact_id": 10}
    assert claimed[3].payload == {}


@pytest.mark.asyncio
async def test_status_reports_backlog_and_dead_letters(outbox_store: OutboxStore):
    await outbox_store.enqueue_run_completed(_run_completed())
    await outbox_store.enqueue(
        event_type="custom.scheduled",
        payload={"value": 1},
        idempotency_key="custom.scheduled:1",
        available_at=datetime.now(UTC) + timedelta(hours=1),
    )

    claimed = await outbox_store.claim_batch(worker_id="test-worker", limit=1)
    await outbox_store.mark_failed(claimed[0].id, error="bad payload", retry_at=None, dead=True)

    status = await outbox_store.get_status(now=datetime.now(UTC))

    assert status["total"] == 2
    assert status["ready"] == 0
    assert status["scheduled"] == 1
    assert status["by_status"] == {
        "pending": 1,
        "running": 0,
        "completed": 0,
        "dead": 1,
    }
    assert status["by_event_type"][OUTBOX_RUN_COMPLETED]["dead"] == 1
    assert status["by_event_type"]["custom.scheduled"]["pending"] == 1
    assert status["next_pending_available_at"] is not None
    assert status["newest_dead_updated_at"] is not None
    assert len(status["recent_dead"]) == 1

    dead = status["recent_dead"][0]
    assert dead["id"] == claimed[0].id
    assert dead["event_type"] == OUTBOX_RUN_COMPLETED
    assert dead["aggregate_type"] == "run"
    assert dead["aggregate_id"] == "run-1"
    assert dead["attempts"] == 1
    assert dead["last_error"] == "bad payload"
    assert dead["created_at"] is not None
    assert dead["updated_at"] is not None


@pytest.mark.asyncio
async def test_replay_dead_resets_event_for_processing(outbox_store: OutboxStore):
    await outbox_store.enqueue_run_completed(_run_completed())
    claimed = await outbox_store.claim_batch(worker_id="test-worker", limit=1)
    await outbox_store.mark_failed(claimed[0].id, error="bad payload", retry_at=None, dead=True)

    result = await outbox_store.replay_dead([claimed[0].id, 999])

    assert result == {
        "requested": [claimed[0].id, 999],
        "replayed": [claimed[0].id],
        "missing": [999],
        "skipped": [],
    }

    replayed = await outbox_store.claim_batch(worker_id="test-worker", limit=1)
    assert len(replayed) == 1
    assert replayed[0].id == claimed[0].id
    assert replayed[0].status == "running"
    assert replayed[0].attempts == 1
    assert replayed[0].last_error is None


@pytest.mark.asyncio
async def test_replay_dead_skips_non_dead_events(outbox_store: OutboxStore):
    await outbox_store.enqueue_run_completed(_run_completed())
    row = (await outbox_store.conn.execute_fetchall("SELECT id FROM outbox_events"))[0]

    result = await outbox_store.replay_dead([row["id"]])

    assert result == {
        "requested": [row["id"]],
        "replayed": [],
        "missing": [],
        "skipped": [{"id": row["id"], "status": "pending"}],
    }


@pytest.mark.asyncio
async def test_prune_completed_deletes_only_old_completed_rows_up_to_limit(outbox_store: OutboxStore):
    for run_id in ("old-1", "old-2", "new-1"):
        await outbox_store.enqueue_run_completed(_run_completed(run_id))
        claimed = await outbox_store.claim_batch(worker_id="test-worker", limit=1)
        await outbox_store.mark_completed(claimed[0].id)

    old = datetime.now(UTC) - timedelta(days=30)
    new = datetime.now(UTC)
    await outbox_store.conn.execute(
        "UPDATE outbox_events SET updated_at = ? WHERE aggregate_id IN ('old-1', 'old-2')",
        (old.isoformat(),),
    )
    await outbox_store.conn.execute(
        "UPDATE outbox_events SET updated_at = ? WHERE aggregate_id = 'new-1'",
        (new.isoformat(),),
    )
    await outbox_store.conn.commit()

    cutoff = datetime.now(UTC) - timedelta(days=7)

    assert await outbox_store.prune_completed(before=cutoff, limit=1) == 1

    rows = await outbox_store.conn.execute_fetchall("SELECT aggregate_id FROM outbox_events ORDER BY aggregate_id")
    assert [row["aggregate_id"] for row in rows] == ["new-1", "old-2"]

    assert await outbox_store.prune_completed(before=cutoff, limit=10) == 1
    rows = await outbox_store.conn.execute_fetchall("SELECT aggregate_id FROM outbox_events ORDER BY aggregate_id")
    assert [row["aggregate_id"] for row in rows] == ["new-1"]


@pytest.mark.asyncio
async def test_worker_dispatches_and_marks_completed(outbox_store: OutboxStore):
    event = _run_completed()
    await outbox_store.enqueue_run_completed(event)
    handled: list[RunCompleted] = []

    async def handle(row):
        handled.append(run_completed_from_payload(row.payload))

    worker = OutboxWorker(outbox_store, worker_id="test-worker")
    worker.register_handler(OUTBOX_RUN_COMPLETED, handle)

    assert await worker.process_once() is True
    assert handled == [event]
    assert await outbox_store.claim_batch(worker_id="test-worker", limit=10) == []


@pytest.mark.asyncio
async def test_worker_retries_then_dead_letters(outbox_store: OutboxStore):
    await outbox_store.enqueue_run_completed(_run_completed())

    async def fail(_row):
        raise RuntimeError("boom")

    worker = OutboxWorker(
        outbox_store,
        worker_id="test-worker",
        max_retries=2,
        retry_base_seconds=0,
        retry_max_seconds=0,
    )
    worker.register_handler(OUTBOX_RUN_COMPLETED, fail)

    assert await worker.process_once() is True
    assert await worker.process_once() is True
    assert await worker.process_once() is False

    rows = await outbox_store.conn.execute_fetchall("SELECT status, attempts, last_error FROM outbox_events")
    assert len(rows) == 1
    assert rows[0]["status"] == "dead"
    assert rows[0]["attempts"] == 2
    assert "RuntimeError: boom" in rows[0]["last_error"]
