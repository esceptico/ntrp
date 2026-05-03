import asyncio
from dataclasses import dataclass, field


@dataclass(frozen=True)
class WorkItem:
    id: str
    label: str
    done: bool
    metadata: dict = field(default_factory=dict)


class SharedLedger:
    def __init__(self) -> None:
        self._items: dict[str, WorkItem] = {}
        self._accessed: set[str] = set()
        self._lock = asyncio.Lock()

    async def register(self, item_id: str, label: str, **metadata: object) -> None:
        async with self._lock:
            self._items[item_id] = WorkItem(id=item_id, label=label, done=False, metadata=dict(metadata))

    async def complete(self, item_id: str) -> None:
        async with self._lock:
            if item := self._items.get(item_id):
                self._items[item_id] = WorkItem(id=item.id, label=item.label, done=True, metadata=item.metadata)

    async def mark_accessed(self, resource_id: str) -> bool:
        async with self._lock:
            if resource_id in self._accessed:
                return True
            self._accessed.add(resource_id)
            return False

    def get_items(self, *, exclude_id: str | None = None) -> list[WorkItem]:
        return [item for item in self._items.values() if item.id != exclude_id]

    @property
    def accessed_count(self) -> int:
        return len(self._accessed)
