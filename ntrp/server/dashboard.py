import time
from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ntrp.constants import CONSOLIDATION_INTERVAL
from ntrp.events.internal import ConsolidationCompleted, FactCreated, RunCompleted, RunStarted, ToolExecuted

if TYPE_CHECKING:
    from ntrp.server.runtime import Runtime

TOOL_HISTORY_SIZE = 20
TOKEN_HISTORY_SIZE = 60
RECENT_FACTS_SIZE = 3


@dataclass
class ToolRecord:
    name: str
    duration_ms: int
    depth: int
    ts: float
    error: bool


@dataclass
class TokenRecord:
    prompt: int
    completion: int
    ts: float


class DashboardCollector:
    def __init__(self):
        self.started_at: float = time.time()
        self.total_runs: int = 0
        self.active_runs: int = 0

        self.total_prompt_tokens: int = 0
        self.total_completion_tokens: int = 0
        self.token_history: deque[TokenRecord] = deque(maxlen=TOKEN_HISTORY_SIZE)
        self.tool_history: deque[ToolRecord] = deque(maxlen=TOOL_HISTORY_SIZE)
        self.tool_stats: dict[str, dict[str, int]] = {}

        self.recent_facts: deque[dict] = deque(maxlen=RECENT_FACTS_SIZE)
        self.last_consolidation_at: float | None = None

    async def on_tool_executed(self, event: ToolExecuted) -> None:
        self.tool_history.append(ToolRecord(event.name, event.duration_ms, event.depth, time.time(), event.is_error))
        stats = self.tool_stats.setdefault(event.name, {"count": 0, "total_ms": 0, "error_count": 0})
        stats["count"] += 1
        stats["total_ms"] += event.duration_ms
        if event.is_error:
            stats["error_count"] += 1

    async def on_run_completed(self, event: RunCompleted) -> None:
        self.total_runs += 1
        self.active_runs = max(0, self.active_runs - 1)
        self.total_prompt_tokens += event.usage.prompt_tokens
        self.total_completion_tokens += event.usage.completion_tokens
        self.token_history.append(TokenRecord(event.usage.prompt_tokens, event.usage.completion_tokens, time.time()))

    async def on_run_started(self, _event: RunStarted) -> None:
        self.active_runs += 1

    async def on_consolidation_completed(self, event: ConsolidationCompleted) -> None:
        self.last_consolidation_at = time.time()

    async def on_fact_created(self, event: FactCreated) -> None:
        self.recent_facts.append({"id": event.fact_id, "text": event.text[:80], "ts": time.time()})

    async def snapshot(self, runtime: "Runtime") -> dict:
        now = time.time()

        system = {
            "uptime_seconds": int(now - self.started_at),
            "model": runtime.config.chat_model,
            "memory_model": runtime.config.memory_model,
            "sources": runtime.get_available_sources(),
            "source_errors": runtime.get_source_errors(),
        }

        tokens = {
            "total_prompt": self.total_prompt_tokens,
            "total_completion": self.total_completion_tokens,
            "history": [{"prompt": t.prompt, "completion": t.completion, "ts": t.ts} for t in self.token_history],
        }

        agent = {
            "active_runs": self.active_runs,
            "total_runs": self.total_runs,
            "recent_tools": [
                {"name": t.name, "duration_ms": t.duration_ms, "depth": t.depth, "ts": t.ts, "error": t.error}
                for t in self.tool_history
            ],
            "tool_stats": {
                name: {
                    "count": s["count"],
                    "avg_ms": s["total_ms"] // max(s["count"], 1),
                    "error_count": s["error_count"],
                }
                for name, s in self.tool_stats.items()
            },
        }

        indexer_progress = runtime.indexer.progress
        schedule_tasks = None
        if runtime.schedule_service:
            schedule_tasks = await runtime.schedule_service.list_all()

        memory_stats = None
        memory_consolidating = False
        memory_unconsolidated = 0
        if runtime.memory_service:
            memory_stats = await runtime.memory_service.stats()
            memory_unconsolidated = await runtime.memory_service.count_unconsolidated()
            memory_consolidating = runtime.memory_service.is_consolidating

        background = {
            "indexer": {
                "status": indexer_progress.status.value,
                "progress_done": indexer_progress.done,
                "progress_total": indexer_progress.total,
                "error": runtime.indexer.error,
            },
            "scheduler": {
                "running": runtime.schedule_service.is_running if runtime.schedule_service else False,
                "active_task": None,
                "total_scheduled": 0,
                "enabled_count": 0,
                "next_run_at": None,
            },
            "consolidation": {
                "running": memory_consolidating,
                "interval_seconds": CONSOLIDATION_INTERVAL,
            },
        }

        if memory_stats:
            memory = {
                "enabled": True,
                **memory_stats,
                "unconsolidated": memory_unconsolidated,
                "consolidation_running": memory_consolidating,
                "last_consolidation_at": self.last_consolidation_at,
                "recent_facts": list(self.recent_facts),
            }
        else:
            memory = {
                "enabled": False,
                "fact_count": 0,
                "observation_count": 0,
                "unconsolidated": 0,
                "consolidation_running": False,
                "last_consolidation_at": None,
                "recent_facts": [],
            }

        if schedule_tasks is not None:
            enabled = [t for t in schedule_tasks if t.enabled]
            running = [t for t in schedule_tasks if t.running_since]
            next_runs = [t.next_run_at.timestamp() for t in enabled if t.next_run_at]
            background["scheduler"] = {
                "running": runtime.schedule_service.is_running if runtime.schedule_service else False,
                "active_task": running[0].description[:60] if running else None,
                "total_scheduled": len(schedule_tasks),
                "enabled_count": len(enabled),
                "next_run_at": min(next_runs) if next_runs else None,
            }

        return {
            "system": system,
            "tokens": tokens,
            "agent": agent,
            "memory": memory,
            "background": background,
        }
