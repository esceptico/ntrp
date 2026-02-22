import asyncio
from dataclasses import dataclass


@dataclass
class ExploreEntry:
    task: str
    depth: str
    status: str  # "active" | "done"


class ExplorationLedger:
    def __init__(self):
        self._tasks: dict[str, ExploreEntry] = {}
        self._reads: set[str] = set()
        self._lock = asyncio.Lock()

    async def register(self, tool_id: str, task: str, depth: str) -> None:
        async with self._lock:
            self._tasks[tool_id] = ExploreEntry(task=task, depth=depth, status="active")

    async def complete(self, tool_id: str) -> None:
        async with self._lock:
            if entry := self._tasks.get(tool_id):
                entry.status = "done"

    async def mark_read(self, path: str) -> bool:
        async with self._lock:
            if path in self._reads:
                return True
            self._reads.add(path)
            return False

    async def summary(self, exclude_id: str | None = None) -> str:
        async with self._lock:
            active = []
            done = []
            for tid, entry in self._tasks.items():
                if tid == exclude_id:
                    continue
                line = f'- "{entry.task}" ({entry.depth})'
                if entry.status == "active":
                    active.append(line)
                else:
                    done.append(line)
            read_count = len(self._reads)

        if not active and not done and not read_count:
            return ""

        parts = ["EXPLORATION CONTEXT (shared across all agents in this run):"]
        if active:
            parts.append("Active:\n" + "\n".join(active))
        if done:
            parts.append("Done:\n" + "\n".join(done))
        if read_count:
            parts.append(f"Documents already read: {read_count}")
        parts.append("Do not re-explore topics already covered. Focus on your specific scope.")
        return "\n".join(parts)
