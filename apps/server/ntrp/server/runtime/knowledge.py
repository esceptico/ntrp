import asyncio
import hashlib
import json
from dataclasses import dataclass

from ntrp.config import Config
from ntrp.database import connect as db_connect
from ntrp.llm.router import get_completion_client
from ntrp.logging import get_logger
from ntrp.server.indexer import Indexer
from ntrp.server.stores import Stores

_logger = get_logger(__name__)
_ARTIFACT_FINGERPRINT_KEY = "memory_artifacts_fingerprint"


@dataclass(frozen=True)
class ArtifactPublishReport:
    refreshed: bool
    artifact_count: int
    fingerprint: str

    @property
    def skipped(self) -> bool:
        return not self.refreshed


class KnowledgeRuntime:
    def __init__(self, config: Config):
        self.config = config
        self.embedding = config.embedding
        self.indexer = Indexer(db_path=config.search_db_path, embedding=self.embedding) if self.embedding else None
        self.search_index = None
        self.memory_curator = None
        self.chat_connector = None

        self._record_store = None
        self._consolidate = None
        self._artifact_refresh_task: asyncio.Task | None = None

    @property
    def memory_ready(self) -> bool:
        return self._record_store is not None

    @property
    def record_store(self):
        return self._record_store

    @property
    def consolidate(self):
        return self._consolidate

    def _memory_llm(self):
        """(client, model) for memory-page synthesis — the same completion client
        and model the curator/consolidate use. (None, "") when no memory_model is
        configured, which keeps the export mechanical."""
        if not self.config.memory_model:
            return None, ""
        return get_completion_client(self.config.memory_model), self.config.memory_model

    async def rebuild_artifacts(self) -> int:
        """Regenerate the markdown projection (entities/, projects/, …) from the
        canonical record pool, LLM-synthesizing the prose pages. Returns the
        artifact count."""
        if self._record_store is None:
            return 0
        from ntrp.memory.artifacts import ArtifactMemoryStore

        fingerprint = await self._artifact_fingerprint()
        llm, model = self._memory_llm()
        artifacts = await ArtifactMemoryStore(self.config.memory_artifacts_dir).export_from_records(
            self._record_store, llm=llm, model=model
        )
        await self._write_artifact_fingerprint(fingerprint)
        return len(artifacts)

    async def publish_artifacts_if_dirty(self) -> ArtifactPublishReport:
        """Publish artifacts only when canonical memory inputs changed."""
        if self._record_store is None:
            return ArtifactPublishReport(refreshed=False, artifact_count=0, fingerprint="")
        fingerprint = await self._artifact_fingerprint()
        if await self._read_artifact_fingerprint() == fingerprint:
            return ArtifactPublishReport(refreshed=False, artifact_count=0, fingerprint=fingerprint)

        from ntrp.memory.artifacts import ArtifactMemoryStore

        llm, model = self._memory_llm()
        artifacts = await ArtifactMemoryStore(self.config.memory_artifacts_dir).export_from_records(
            self._record_store, llm=llm, model=model
        )
        await self._write_artifact_fingerprint(fingerprint)
        return ArtifactPublishReport(refreshed=True, artifact_count=len(artifacts), fingerprint=fingerprint)

    async def _artifact_fingerprint(self) -> str:
        records = await self._record_store.list(limit=None)
        record_ids = [record.id for record in records]
        labels_by_id = await self._record_store.labels_for(record_ids, include_kind=True) if record_ids else {}
        payload = []
        for record in sorted(records, key=lambda item: item.id):
            labels = sorted(
                labels_by_id.get(record.id, []),
                key=lambda entry: (entry.get("label", ""), entry.get("kind", "")),
            )
            payload.append(
                {
                    "id": record.id,
                    "text": record.text,
                    "kind": record.kind,
                    "scope_kind": record.scope_kind,
                    "scope_key": record.scope_key,
                    "created_at": record.created_at,
                    "last_confirmed_at": record.last_confirmed_at,
                    "pinned": record.pinned,
                    "source_ref": record.source_ref.to_dict() if record.source_ref is not None else None,
                    "labels": labels,
                }
            )
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    async def _read_artifact_fingerprint(self) -> str | None:
        conn = await db_connect(self.config.memory_db_path)
        try:
            await conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            rows = await conn.execute_fetchall("SELECT value FROM meta WHERE key = ?", (_ARTIFACT_FINGERPRINT_KEY,))
            return rows[0]["value"] if rows else None
        finally:
            await conn.close()

    async def _write_artifact_fingerprint(self, fingerprint: str) -> None:
        conn = await db_connect(self.config.memory_db_path)
        try:
            await conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            await conn.execute(
                "INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (_ARTIFACT_FINGERPRINT_KEY, fingerprint),
            )
            await conn.commit()
        finally:
            await conn.close()

    async def connect(self, stores: Stores) -> None:
        await self._init_search()
        await self._init_memory(stores)
        if self.search_index is not None:
            stores.sessions.store.attach_search_index(self.search_index)
        if self.memory_curator is not None:
            self.memory_curator.start_sweep()
        if self.memory_ready:
            # Refresh the markdown projection once on boot so pre-existing files
            # adopt the current generator (e.g. frontmatter) with no manual
            # rebuild. Background + best-effort: never blocks startup.
            self._artifact_refresh_task = asyncio.create_task(self._refresh_artifacts_on_start())

    async def _refresh_artifacts_on_start(self) -> None:
        if self._record_store is None:
            return
        try:
            # Classify the label vocabulary first (cold-start backlog → entity
            # dossiers) so a fresh deploy self-populates subject pages on boot
            # instead of waiting for the daily consolidation.
            if self._consolidate is not None:
                await self._consolidate.lint_labels_once()
            from ntrp.memory.artifacts import ArtifactMemoryStore

            # MECHANICAL only — the boot refresh exists to let pre-existing files
            # adopt the current generator (frontmatter); synthesized pages survive
            # a mechanical sync by design. Full LLM synthesis (~27 calls) belongs
            # on the explicit triggers (/init, the rebuild endpoint, the CLI), not
            # on every restart / crash-loop.
            await ArtifactMemoryStore(self.config.memory_artifacts_dir).export_from_records(self._record_store)
        except Exception:
            _logger.warning("startup artifact refresh failed", exc_info=True)

    async def reload_config(self, config: Config, stores: Stores | None) -> None:
        self.config = config
        await self._sync_embedding()
        # Re-wire the live transcript store to the (possibly new/None) index so
        # toggling embedding at runtime enables/disables hybrid search + indexing
        # without a restart. attach_search_index is idempotent and clears on None.
        if stores is not None:
            stores.sessions.store.attach_search_index(self.search_index)
        # Same re-wire for the record store (the curator shares it).
        if self._record_store is not None:
            self._record_store.attach_search_index(self.search_index)

    async def stop(self) -> None:
        if self._artifact_refresh_task is not None:
            self._artifact_refresh_task.cancel()
        if self.memory_curator:
            await self.memory_curator.stop()
        if self._consolidate:
            await self._consolidate.close()
        if self._record_store:
            await self._record_store.close()
        if self.indexer:
            await self.indexer.stop()

    async def close(self) -> None:
        if self._consolidate:
            await self._consolidate.close()
        if self._record_store:
            await self._record_store.close()
        if self.indexer:
            await self.indexer.close()

    def tool_services(self) -> dict[str, object]:
        services: dict[str, object] = {}
        if self.search_index:
            services["search_index"] = self.search_index
        if self._record_store is not None:
            from ntrp.tools.memory import MEMORY_RECORDS_SERVICE

            services[MEMORY_RECORDS_SERVICE] = self._record_store
        return services

    def start_indexing(self) -> None:
        if self.indexer:
            self.indexer.start(None)

    async def get_index_status(self) -> dict:
        return await self.indexer.get_status() if self.indexer else {"status": "disabled"}

    # --- search index ----------------------------------------------------

    async def _init_search(self) -> None:
        if self.indexer:
            await self.indexer.connect()
            self.search_index = self.indexer.index

    async def _sync_embedding(self) -> None:
        new_embedding = self.config.embedding
        if new_embedding == self.embedding:
            return

        self.embedding = new_embedding

        if new_embedding is None:
            if self.indexer:
                await self.indexer.stop()
                await self.indexer.close()
            self.indexer = None
            self.search_index = None
            return

        if self.indexer:
            await self.indexer.stop()
            await self.indexer.update_embedding(new_embedding)
        else:
            self.indexer = Indexer(db_path=self.config.search_db_path, embedding=new_embedding)
            await self.indexer.connect()
        self.search_index = self.indexer.index

    # --- flat-records memory ---------------------------------------------

    async def _init_memory(self, stores: Stores) -> None:
        if not self.config.memory:
            _logger.info("memory disabled by config")
            return

        from ntrp.memory.consolidate import Consolidate
        from ntrp.memory.curator import Curator
        from ntrp.memory.records import RecordStore

        # Flat record pool (rows in memory.db, vectors via the shared index).
        self._record_store = RecordStore(
            db_path=self.config.memory_db_path,
            search_index=self.search_index,
        )

        memory_llm = get_completion_client(self.config.memory_model) if self.config.memory_model else None
        memory_effort = self._memory_reasoning_effort(self.config.memory_model)

        # CONSOLIDATE/LINT — the background pass that turns the raw record pile
        # into the actual memory (merge/supersede/drop). O(delta), watermark-durable.
        self._consolidate = Consolidate(
            self._record_store,
            memory_llm,
            model=self.config.memory_model,
            db_path=self.config.memory_db_path,
            reasoning_effort=memory_effort,
        )

        if self.config.memory_model:
            self.memory_curator = Curator(
                memory_llm,
                stores.sessions,
                model=self.config.memory_model,
                db_path=self.config.memory_db_path,
                record_store=self._record_store,
                consolidate=self._consolidate,
                reasoning_effort=memory_effort,
                artifacts_dir=self.config.memory_artifacts_dir,
            )
        else:
            _logger.warning("memory enabled but no memory_model; curator disabled")

        # Run the record-store schema migration NOW, serially, while it is the
        # only open connection to memory.db. Deferring it to the first lazy
        # _ensure_conn lets the consolidate/curator connections race the
        # one-time DROP/ALTER rebuild (writer-vs-writer lock contention).
        await self._record_store.open()

        _logger.info("memory ready", db_path=str(self.config.memory_db_path))

    def _memory_reasoning_effort(self, model_id: str | None) -> str | None:
        """Effort for memory's structured calls: the user's configured effort if set,
        else 'low' (or the model's lowest) so a reasoning model doesn't run at its slow
        API-default and time out. Returns None for non-reasoning models."""
        if not model_id:
            return None
        configured = self.config.reasoning_effort_for(model_id)
        if configured:
            return configured
        from ntrp.llm.models import get_models

        efforts = get_models()[model_id].reasoning_efforts
        if not efforts:
            return None
        return "low" if "low" in efforts else efforts[0]
