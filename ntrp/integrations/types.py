from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class RawItem:
    source: str
    source_id: str
    title: str
    content: str
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Indexable(Protocol):
    name: str

    async def scan(self) -> list[RawItem]: ...
