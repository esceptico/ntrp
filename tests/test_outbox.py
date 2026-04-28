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
