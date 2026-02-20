from typing import TYPE_CHECKING

from ntrp.events.internal import (
    ConsolidationCompleted,
    FactCreated,
    FactDeleted,
    FactUpdated,
    MemoryCleared,
    RunCompleted,
    RunStarted,
    SourceChanged,
    ToolExecuted,
)
from ntrp.sources.base import Indexable

if TYPE_CHECKING:
    from ntrp.server.runtime import Runtime


async def _on_fact_upserted(runtime: "Runtime", event: FactCreated | FactUpdated) -> None:
    await runtime.indexer.index.upsert(
        source="memory",
        source_id=f"fact:{event.fact_id}",
        title=event.text[:50],
        content=event.text,
    )


async def _on_fact_deleted(runtime: "Runtime", event: FactDeleted) -> None:
    await runtime.indexer.index.delete("memory", f"fact:{event.fact_id}")


async def _on_memory_cleared(runtime: "Runtime", _event: MemoryCleared) -> None:
    await runtime.indexer.index.clear_source("memory")


async def _on_source_changed(runtime: "Runtime", event: SourceChanged) -> None:
    name = event.source_name
    source = runtime.source_mgr.sources.get(name)
    if source and isinstance(source, Indexable):
        runtime.indexables[name] = source
        runtime.start_indexing()
    elif source is None:
        runtime.indexables.pop(name, None)
        await runtime.indexer.index.clear_source(name)


def wire_events(runtime: "Runtime") -> None:
    ch = runtime.channel

    # Dashboard
    ch.subscribe(ToolExecuted, runtime.dashboard.on_tool_executed)
    ch.subscribe(RunStarted, runtime.dashboard.on_run_started)
    ch.subscribe(RunCompleted, runtime.dashboard.on_run_completed)
    ch.subscribe(FactCreated, runtime.dashboard.on_fact_created)
    ch.subscribe(ConsolidationCompleted, runtime.dashboard.on_consolidation_completed)

    # Memory → search index bridge
    ch.subscribe(FactCreated, lambda e: _on_fact_upserted(runtime, e))
    ch.subscribe(FactUpdated, lambda e: _on_fact_upserted(runtime, e))
    ch.subscribe(FactDeleted, lambda e: _on_fact_deleted(runtime, e))
    ch.subscribe(MemoryCleared, lambda e: _on_memory_cleared(runtime, e))

    # Source changes → reindex
    ch.subscribe(SourceChanged, lambda e: _on_source_changed(runtime, e))
