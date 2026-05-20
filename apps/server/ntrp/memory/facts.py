import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Self, TypedDict

import aiosqlite

import ntrp.database as database
from ntrp.embedder import Embedder, EmbeddingConfig
from ntrp.knowledge.store import KnowledgeObjectRepository
from ntrp.logging import get_logger
from ntrp.memory.store.access_events import MemoryAccessEventRepository
from ntrp.memory.store.base import GraphDatabase
from ntrp.memory.store.events import MemoryEventRepository
from ntrp.memory.store.facts import FactRepository
from ntrp.memory.store.observations import ObservationRepository

_logger = get_logger(__name__)


class ReembedProgress(TypedDict):
    total: int
    done: int


class RepairEmbeddingsResult(TypedDict):
    apply: bool
    fact_ids: list[int]
    observation_ids: list[int]
    knowledge_object_ids: list[int]
    facts_repaired: int
    observations_repaired: int
    knowledge_objects_repaired: int


class FactMemory:
    def __init__(
        self,
        conn: aiosqlite.Connection,
        embedding: EmbeddingConfig,
        model: str,
        embedder: Embedder | None = None,
        read_conn: aiosqlite.Connection | None = None,
    ):
        self.db = GraphDatabase(conn, embedding.dim)
        self.facts = FactRepository(conn, read_conn)
        self.observations = ObservationRepository(conn, read_conn)
        self.events = MemoryEventRepository(conn, read_conn)
        self.access_events = MemoryAccessEventRepository(conn, read_conn)
        self.knowledge_objects = KnowledgeObjectRepository(conn, read_conn)
        self.embedder = embedder or Embedder(embedding)
        self._model = model
        self._db_lock = asyncio.Lock()
        self._reembed_task: asyncio.Task | None = None
        self._reembed_progress: ReembedProgress | None = None

    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[None]:
        async with self._db_lock:
            try:
                yield
                await self.db.conn.commit()
            except Exception:
                await self.db.conn.rollback()
                raise

    @classmethod
    async def create(
        cls,
        db_path: Path,
        embedding: EmbeddingConfig,
        model: str,
    ) -> Self:
        conn = await database.connect(db_path, vec=True)
        read_conn = await database.connect(db_path, vec=True, readonly=True)
        instance = cls(
            conn,
            embedding,
            model,
            read_conn=read_conn,
        )
        await instance.db.init_schema()
        if instance.db.dim_changed:
            _logger.info("Embedding dimension changed — starting background re-embed")
            instance.start_reembed(embedding)
        return instance

    @property
    def reembed_running(self) -> bool:
        return self._reembed_task is not None and not self._reembed_task.done()

    @property
    def reembed_progress(self) -> ReembedProgress | None:
        return self._reembed_progress

    @property
    def model(self) -> str:
        return self._model

    def update_model(self, model: str) -> None:
        self._model = model

    def start_reembed(self, embedding: EmbeddingConfig, *, rebuild: bool = False) -> None:
        if self._reembed_task and not self._reembed_task.done():
            self._reembed_task.cancel()
        self._reembed_task = asyncio.create_task(self._run_reembed(embedding, rebuild=rebuild))

    async def repair_missing_embeddings(self, *, limit: int = 100, apply: bool = False) -> RepairEmbeddingsResult:
        facts = await self.facts.list_missing_embeddings(limit=max(0, limit))
        observation_limit = max(0, limit - len(facts))
        observations = await self.observations.list_missing_embeddings(limit=observation_limit)
        knowledge_limit = max(0, observation_limit - len(observations))
        knowledge_objects = await self.knowledge_objects.list_missing_embeddings(limit=knowledge_limit)

        result: RepairEmbeddingsResult = {
            "apply": apply,
            "fact_ids": [fact.id for fact in facts],
            "observation_ids": [obs.id for obs in observations],
            "knowledge_object_ids": [obj.id for obj in knowledge_objects],
            "facts_repaired": 0,
            "observations_repaired": 0,
            "knowledge_objects_repaired": 0,
        }
        if not apply or (not facts and not observations and not knowledge_objects):
            return result

        fact_embeddings = await self.embedder.embed([fact.text for fact in facts]) if facts else []
        observation_embeddings = await self.embedder.embed([obs.summary for obs in observations]) if observations else []
        knowledge_embeddings = (
            await self.embedder.embed([f"{obj.title}\n{obj.text}" for obj in knowledge_objects]) if knowledge_objects else []
        )

        async with self.transaction():
            for fact, embedding in zip(facts, fact_embeddings, strict=False):
                await self.facts.update_embedding(fact.id, embedding)
            for obs, embedding in zip(observations, observation_embeddings, strict=False):
                await self.observations.update_embedding(obs.id, embedding)
            for obj, embedding in zip(knowledge_objects, knowledge_embeddings, strict=False):
                await self.knowledge_objects.update_embedding(obj.id, embedding)
            await self.events.create(
                actor="backend",
                action="embeddings.repaired",
                target_type="memory",
                reason="manual missing-embedding repair",
                policy_version="memory.repair.v1",
                details={
                    "fact_ids": result["fact_ids"],
                    "observation_ids": result["observation_ids"],
                    "knowledge_object_ids": result["knowledge_object_ids"],
                },
            )

        result["facts_repaired"] = len(facts)
        result["observations_repaired"] = len(observations)
        result["knowledge_objects_repaired"] = len(knowledge_objects)
        return result

    async def _run_reembed(self, embedding: EmbeddingConfig, *, rebuild: bool = False, batch_size: int = 100) -> None:
        try:
            new_embedder = Embedder(embedding)
            if rebuild:
                await self.db.rebuild_vec_tables(embedding.dim)

            facts = await self.facts.list_all_with_embeddings()
            observations = await self.observations.list_all_with_embeddings()
            knowledge_objects = await self.knowledge_objects.list_all_with_embeddings()
            total = len(facts) + len(observations) + len(knowledge_objects)
            self._reembed_progress = {"total": total, "done": 0}

            done = 0
            for i in range(0, len(facts), batch_size):
                batch = facts[i : i + batch_size]
                embeddings = await new_embedder.embed([f.text for f in batch])
                for fact, emb in zip(batch, embeddings):
                    await self.facts.update_embedding(fact.id, emb)
                done += len(batch)
                self._reembed_progress["done"] = done

            for i in range(0, len(observations), batch_size):
                batch = observations[i : i + batch_size]
                embeddings = await new_embedder.embed([o.summary for o in batch])
                for obs, emb in zip(batch, embeddings):
                    await self.observations.update_embedding(obs.id, emb)
                done += len(batch)
                self._reembed_progress["done"] = done

            for i in range(0, len(knowledge_objects), batch_size):
                batch = knowledge_objects[i : i + batch_size]
                embeddings = await new_embedder.embed([f"{obj.title}\n{obj.text}" for obj in batch])
                for obj, emb in zip(batch, embeddings):
                    await self.knowledge_objects.update_embedding(obj.id, emb)
                done += len(batch)
                self._reembed_progress["done"] = done

            await self.db.conn.commit()
            self.embedder = new_embedder
            _logger.info("Re-embedded %d memory vectors", total)
        except asyncio.CancelledError:
            raise
        except Exception:
            _logger.warning("Memory re-embed failed", exc_info=True)
        finally:
            self._reembed_progress = None

    # --- Lifecycle ---

    async def close(self) -> None:
        if self._reembed_task:
            self._reembed_task.cancel()
            try:
                await self._reembed_task
            except asyncio.CancelledError:
                pass
            self._reembed_task = None
        if self.facts.read_conn is not self.db.conn:
            await self.facts.read_conn.close()
        await self.db.conn.close()

    async def clear(self) -> dict[str, int]:
        async with self.transaction():
            counts = {
                "facts": await self.facts.count(),
                "observations": await self.observations.count(),
            }
            await self.db.clear_all()
            return counts
