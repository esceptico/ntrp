from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from ntrp.sources.models import RawItem


@runtime_checkable
class Indexable(Protocol):
    name: str

    async def scan(self) -> list[RawItem]: ...


@dataclass(frozen=True)
class SourceItem:
    identity: str
    title: str
    source: str
    timestamp: datetime | None = None
    preview: str | None = None


