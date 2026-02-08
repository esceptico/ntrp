import asyncio
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path

from ntrp.channel import Channel
from ntrp.core.events import IndexingCompleted, IndexingStarted
from ntrp.embedder import EmbeddingConfig
from ntrp.logging import get_logger
from ntrp.search.index import SearchIndex
from ntrp.sources.base import IndexableSource

_logger = get_logger(__name__)


class IndexStatus(StrEnum):
    PENDING = "pending"
    INDEXING = "indexing"
    DONE = "done"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class IndexProgress:
    total: int = 0
    done: int = 0
    status: IndexStatus = IndexStatus.PENDING
    updated: int = 0
    deleted: int = 0


class Indexer:
    def __init__(self, db_path: Path, embedding: EmbeddingConfig, channel: Channel):
        self.index = SearchIndex(db_path=db_path, embedding=embedding)
        self.channel = channel
        self._progress = IndexProgress()
        self._error: str | None = None
        self._running = False
        self._task: asyncio.Task | None = None

    async def connect(self) -> None:
        await self.index.connect()

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def close(self) -> None:
        await self.index.close()

    @property
    def progress(self) -> IndexProgress:
        return self._progress

    @property
    def error(self) -> str | None:
        return self._error

    @property
    def running(self) -> bool:
        return self._running

    def start(self, sources: list[IndexableSource]) -> None:
        if self._running:
            return

        sources = [s for s in sources if self.index.should_embed(s.name)]
        if not sources:
            self._progress = IndexProgress(status=IndexStatus.SKIPPED)
            return

        self._task = asyncio.create_task(self._run(sources))

    async def _run(self, sources: list[IndexableSource]) -> None:
        self._running = True
        self._progress = IndexProgress()

        try:
            self._progress.status = IndexStatus.INDEXING
            await self.channel.publish(IndexingStarted(sources=[s.name for s in sources]))

            for source in sources:
                items = await source.scan()
                u, d = await self.index.sync(source.name, items, progress_callback=self._on_progress)
                self._progress.updated += u
                self._progress.deleted += d

            self._progress.status = IndexStatus.DONE
            await self.channel.publish(
                IndexingCompleted(updated=self._progress.updated, deleted=self._progress.deleted)
            )
        except Exception as e:
            self._error = str(e)
            self._progress.status = IndexStatus.ERROR
        finally:
            self._running = False

    def _on_progress(self, done: int, total: int) -> None:
        self._progress.done = done
        self._progress.total = total

    async def get_status(self) -> dict:
        return {
            "indexing": self._running,
            "progress": asdict(self._progress),
            "error": self._error,
            "stats": await self.index.get_stats(),
        }
