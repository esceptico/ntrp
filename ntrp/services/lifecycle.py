import asyncio
from typing import TYPE_CHECKING

from ntrp.channel import Channel
from ntrp.sources.base import Indexable
from ntrp.events import (
    ConsolidationCompleted,
    ContextCompressed,
    FactCreated,
    FactDeleted,
    FactUpdated,
    MemoryCleared,
    RunCompleted,
    RunStarted,
    ScheduleCompleted,
    SourceChanged,
    ToolExecuted,
)
from ntrp.memory.chat_extraction import make_chat_extraction_handler
from ntrp.notifiers import make_schedule_dispatcher

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
    async with runtime._config_lock:
        runtime.rebuild_executor()
    name = event.source_name
    source = runtime.source_mgr.sources.get(name)
    if source and isinstance(source, Indexable):
        runtime.indexables[name] = source
        runtime.start_indexing()
    elif name in runtime.indexables and source is None:
        runtime.indexables.pop(name)
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

    # Source changes → rebuild executor + reindex
    ch.subscribe(SourceChanged, lambda e: _on_source_changed(runtime, e))

    # Schedule notifications
    ch.subscribe(ScheduleCompleted, make_schedule_dispatcher(lambda: runtime.notifiers))

    # Auto-extract facts from compressed context
    ch.subscribe(
        ContextCompressed,
        make_chat_extraction_handler(lambda: runtime.memory, runtime.config.memory_model),
    )
