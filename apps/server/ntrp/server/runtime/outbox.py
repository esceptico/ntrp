from datetime import UTC, datetime

from ntrp.automation.scheduler import Scheduler
from ntrp.automation.store import AutomationStore
from ntrp.outbox import (
    OUTBOX_FACT_INDEX_DELETE,
    OUTBOX_FACT_INDEX_UPSERT,
    OUTBOX_MEMORY_INDEX_CLEAR,
    OUTBOX_RUN_COMPLETED,
    OutboxEvent,
    OutboxWorker,
    fact_deleted_from_payload,
    fact_updated_from_payload,
    run_completed_from_payload,
)
from ntrp.outbox.store import OutboxStore
from ntrp.server.indexer import Indexer


class RuntimeOutbox:
    def __init__(
        self,
        *,
        outbox_store: OutboxStore,
        automation_store: AutomationStore,
        scheduler: Scheduler,
        indexer: Indexer | None,
    ):
        self.worker = OutboxWorker(outbox_store)
        self.outbox_store = outbox_store
        self.automation_store = automation_store
        self.scheduler = scheduler
        self.indexer = indexer
        self._register_handlers()

    def start(self) -> None:
        self.worker.start()

    async def stop(self) -> None:
        await self.worker.stop()

    def _register_handlers(self) -> None:
        self.worker.register_handler(OUTBOX_RUN_COMPLETED, self._on_run_completed)
        self.worker.register_handler(OUTBOX_FACT_INDEX_UPSERT, self._on_fact_upserted)
        self.worker.register_handler(OUTBOX_FACT_INDEX_DELETE, self._on_fact_deleted)
        self.worker.register_handler(OUTBOX_MEMORY_INDEX_CLEAR, self._on_memory_cleared)

    async def _on_run_completed(self, event: OutboxEvent) -> None:
        run_completed = run_completed_from_payload(event.payload)
        if run_completed.messages:
            await self.automation_store.record_chat_extraction_activity(
                run_completed.session_id,
                run_completed.messages,
                datetime.now(UTC),
            )
        await self.scheduler.handle_run_completed(run_completed)

    async def _on_fact_upserted(self, event: OutboxEvent) -> None:
        if not self.indexer:
            return
        fact = fact_updated_from_payload(event.payload)
        await self.indexer.index.upsert(
            source="memory",
            source_id=f"fact:{fact.fact_id}",
            title=fact.text[:50],
            content=fact.text,
        )

    async def _on_fact_deleted(self, event: OutboxEvent) -> None:
        if not self.indexer:
            return
        fact = fact_deleted_from_payload(event.payload)
        await self.indexer.index.delete("memory", f"fact:{fact.fact_id}")

    async def _on_memory_cleared(self, _event: OutboxEvent) -> None:
        if self.indexer:
            await self.indexer.index.clear_source("memory")

    async def get_status(self) -> dict:
        worker_running = self.worker.is_running
        return {
            "status": "running" if worker_running else "stopped",
            "worker": {
                "running": worker_running,
                "worker_id": self.worker.worker_id,
            },
            "events": await self.outbox_store.get_status(),
        }

    async def get_health(self) -> dict:
        status = await self.get_status()
        events = status.get("events", {})
        by_status = events.get("by_status", {})
        return {
            "worker_running": status.get("worker", {}).get("running", False),
            "pending": by_status.get("pending", 0),
            "ready": events.get("ready", 0),
            "running": by_status.get("running", 0),
            "dead": by_status.get("dead", 0),
        }

    async def replay_dead_events(self, event_ids: list[int]) -> dict:
        result = await self.outbox_store.replay_dead(event_ids)
        return {"status": "queued" if result["replayed"] else "unchanged", **result}

    async def prune_completed(self, *, before: datetime, limit: int) -> dict:
        deleted = await self.outbox_store.prune_completed(before=before, limit=limit)
        return {
            "status": "deleted",
            "deleted": deleted,
            "before": before.isoformat(),
            "limit": limit,
        }
