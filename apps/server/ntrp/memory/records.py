"""RecordStore — the atomic memory unit.

Free-form, self-contained records (typed by function, not subject) in one FLAT
pool in `config.memory_db_path` (the same DB the Curator owns). NO scope/project
partition — every read path searches/lists ALL records. Lexical retrieval via a
local `records_fts`; semantic retrieval via the shared `SearchIndex`
(`source="record"`). Hybrid `search` fuses the two legs with `rrf_merge`, exactly
like transcript search, then post-filters by kinds / supersession.

The legacy `scope_kind`/`scope_key` columns are kept (the seeded rows hold their
provenance there) but are inert — never a WHERE clause, never an index. New
provenance lives in `source_ref`.

No bitemporal axis. Freshness = `last_confirmed_at`; `superseded_by` closes a
lineage (never hard-delete on supersede). `pinned` survives decay.

Open-vocabulary LABELS (referents AND categories, attached by the curator at
write time) live in `record_labels`. Merge unions labels onto the survivor,
supersede_with passes them to the successor, delete cascades them.
"""

from __future__ import annotations

import asyncio
import json
from enum import StrEnum
from typing import TYPE_CHECKING

from ntrp.constants import RRF_K
from ntrp.database import connect as db_connect
from ntrp.database import serialize_embedding
from ntrp.logging import get_logger
from ntrp.memory.models import (
    Justification,
    Kind,
    Provenance,
    Record,
    SourceRef,
    Standing,
    now_iso,
)
from ntrp.search.fts import build_fts_or_query
from ntrp.search.retrieval import rrf_merge

_logger = get_logger(__name__)

if TYPE_CHECKING:
    from pathlib import Path

# scope_kind/scope_key remain NULLABLE provenance columns. The 753 seeded rows
# wrote them NOT NULL; new rows write them only when source_ref carries them.
_SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
    id TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'note',
    scope_kind TEXT,
    scope_key TEXT,
    created_at TEXT NOT NULL,
    last_confirmed_at TEXT NOT NULL,
    superseded_by TEXT,
    pinned INTEGER NOT NULL DEFAULT 0,
    source_ref TEXT
);
CREATE INDEX IF NOT EXISTS idx_records_active ON records(superseded_by);
CREATE INDEX IF NOT EXISTS idx_records_confirmed ON records(last_confirmed_at);

CREATE VIRTUAL TABLE IF NOT EXISTS records_fts USING fts5(
    text,
    content='records',
    content_rowid='rowid'
);

CREATE TRIGGER IF NOT EXISTS records_ai AFTER INSERT ON records BEGIN
    INSERT INTO records_fts(rowid, text) VALUES (new.rowid, new.text);
END;
CREATE TRIGGER IF NOT EXISTS records_ad AFTER DELETE ON records BEGIN
    INSERT INTO records_fts(records_fts, rowid, text) VALUES ('delete', old.rowid, old.text);
END;
CREATE TRIGGER IF NOT EXISTS records_au AFTER UPDATE ON records BEGIN
    INSERT INTO records_fts(records_fts, rowid, text) VALUES ('delete', old.rowid, old.text);
    INSERT INTO records_fts(rowid, text) VALUES (new.rowid, new.text);
END;

CREATE TABLE IF NOT EXISTS record_labels (
    record_id TEXT NOT NULL,
    label TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (record_id, label)
);
CREATE INDEX IF NOT EXISTS idx_labels_label ON record_labels(label);

CREATE TABLE IF NOT EXISTS justifications (
    id TEXT PRIMARY KEY,
    derived_id TEXT NOT NULL,
    mode TEXT NOT NULL,
    question TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_just_derived ON justifications(derived_id);

CREATE TABLE IF NOT EXISTS justification_premises (
    justification_id TEXT NOT NULL,
    premise_id TEXT NOT NULL,
    PRIMARY KEY (justification_id, premise_id)
);
CREATE INDEX IF NOT EXISTS idx_just_premise ON justification_premises(premise_id);

CREATE TABLE IF NOT EXISTS nogoods (
    id TEXT PRIMARY KEY,
    premise_ids TEXT NOT NULL,
    conclusion TEXT NOT NULL,
    why TEXT NOT NULL,
    created_at TEXT NOT NULL
);

DROP INDEX IF EXISTS idx_records_scope;
DROP TABLE IF EXISTS record_edges;
DROP TABLE IF EXISTS label_pages;
"""

# The v2 `records` table declared scope_kind NOT NULL. Flat records write it NULL
# (scope is provenance inside source_ref now). CREATE TABLE IF NOT EXISTS can't
# relax an existing column, so rebuild the table once. rowids are preserved so the
# external-content FTS stays mapped; we rebuild it afterwards regardless.
_MIGRATE_NULLABLE_SCOPE = """
BEGIN;
CREATE TABLE records_new (
    id TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'note',
    scope_kind TEXT,
    scope_key TEXT,
    created_at TEXT NOT NULL,
    last_confirmed_at TEXT NOT NULL,
    superseded_by TEXT,
    pinned INTEGER NOT NULL DEFAULT 0,
    source_ref TEXT
);
INSERT INTO records_new
    (rowid, id, text, kind, scope_kind, scope_key, created_at,
     last_confirmed_at, superseded_by, pinned, source_ref)
SELECT rowid, id, text, kind, scope_kind, scope_key, created_at,
       last_confirmed_at, superseded_by, pinned, source_ref FROM records;
DROP TABLE records;
ALTER TABLE records_new RENAME TO records;
CREATE INDEX IF NOT EXISTS idx_records_active ON records(superseded_by);
CREATE INDEX IF NOT EXISTS idx_records_confirmed ON records(last_confirmed_at);
CREATE TRIGGER IF NOT EXISTS records_ai AFTER INSERT ON records BEGIN
    INSERT INTO records_fts(rowid, text) VALUES (new.rowid, new.text);
END;
CREATE TRIGGER IF NOT EXISTS records_ad AFTER DELETE ON records BEGIN
    INSERT INTO records_fts(records_fts, rowid, text) VALUES ('delete', old.rowid, old.text);
END;
CREATE TRIGGER IF NOT EXISTS records_au AFTER UPDATE ON records BEGIN
    INSERT INTO records_fts(records_fts, rowid, text) VALUES ('delete', old.rowid, old.text);
    INSERT INTO records_fts(rowid, text) VALUES (new.rowid, new.text);
END;
COMMIT;
"""


class RecordOp(StrEnum):
    """Transient — the dreamer LLM's reconciliation verb. Never persisted."""

    ADD = "ADD"
    UPDATE = "UPDATE"
    SUPERSEDE = "SUPERSEDE"
    NOOP = "NOOP"


class RecordStore:
    def __init__(self, db_path: Path, search_index: object | None = None) -> None:
        self._db_path = db_path
        self._search_index = search_index  # may be None -> FTS-only
        self._conn = None
        self._conn_lock = asyncio.Lock()
        self._bg: set[asyncio.Task] = set()  # tracked index tasks (no GC, errors logged)

    def attach_search_index(self, search_index: object | None) -> None:
        """Re-wire the vector index after a runtime embedding toggle (mirrors the
        transcript store). Idempotent; None reverts to FTS-only."""
        self._search_index = search_index

    def _track(self, coro) -> None:
        """Fire-and-forget an index op, but keep a ref (no GC) and log failures —
        a swallowed embed error otherwise leaves a record FTS-findable yet
        semantically invisible with zero diagnostics."""
        task = asyncio.create_task(coro)
        self._bg.add(task)
        task.add_done_callback(
            lambda t: (
                self._bg.discard(t),
                None if t.cancelled() or not t.exception()
                else _logger.warning("record index task failed", exc_info=t.exception()),
            )
        )

    # -- connection (mirrors curator._ensure_conn) ---------------------------

    async def _ensure_conn(self):
        if self._conn is not None:
            return self._conn
        async with self._conn_lock:
            if self._conn is None:
                conn = await db_connect(self._db_path)
                await conn.executescript(_SCHEMA)
                await conn.commit()
                await self._migrate_nullable_scope(conn)
                # Derivation columns (additive; existing DBs predate them). After
                # the scope rebuild so a rebuilt table gains them too.
                for col in (
                    "provenance TEXT NOT NULL DEFAULT 'ground'",
                    "standing TEXT NOT NULL DEFAULT 'active'",
                    "depth INTEGER NOT NULL DEFAULT 0",
                ):
                    try:
                        await conn.execute(f"ALTER TABLE records ADD COLUMN {col}")
                    except Exception:
                        pass  # column already present
                await conn.commit()
                self._conn = conn
        return self._conn

    async def _migrate_nullable_scope(self, conn) -> None:
        cur = await conn.execute("PRAGMA table_info(records)")
        cols = await cur.fetchall()
        scope = next((c for c in cols if c[1] == "scope_kind"), None)
        if scope is None or scope[3] == 0:  # col[3] = notnull flag; 0 = already nullable
            return
        _logger.info("migrating records.scope_kind NOT NULL -> nullable (table rebuild)")
        await conn.executescript(_MIGRATE_NULLABLE_SCOPE)
        await conn.execute("INSERT INTO records_fts(records_fts) VALUES('rebuild')")
        await conn.commit()

    async def open(self) -> None:
        """Eagerly connect + apply the one-time scope_kind rebuild. Called at
        startup so the migration's DROP/ALTER runs strictly serially, before the
        lens/consolidate/curator connections to the same memory.db open — a
        concurrent first writer would otherwise contend with the rebuild's lock."""
        await self._ensure_conn()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    # -- writes --------------------------------------------------------------

    async def add(
        self,
        text: str,
        *,
        kind: str = Kind.NOTE,
        pinned: bool = False,
        source_ref: SourceRef | None = None,
    ) -> Record:
        from uuid import uuid4

        record = Record(
            id=uuid4().hex,
            text=text,
            kind=kind,
            pinned=pinned,
            source_ref=source_ref,
        )
        conn = await self._ensure_conn()
        await conn.execute(
            """
            INSERT INTO records
                (id, text, kind, scope_kind, scope_key, created_at,
                 last_confirmed_at, superseded_by, pinned, source_ref)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.id,
                record.text,
                record.kind,
                source_ref.scope_kind if source_ref else None,
                source_ref.scope_key if source_ref else None,
                record.created_at,
                record.last_confirmed_at,
                record.superseded_by,
                1 if record.pinned else 0,
                json.dumps(source_ref.to_dict()) if source_ref else None,
            ),
        )
        await conn.commit()
        self._index(record)
        return record

    async def supersede(self, old_id: str, new_id: str) -> bool:
        """Close a lineage: old.superseded_by = new_id. Evicts the old record
        from the vector index (the row stays in SQLite for history but must not
        keep occupying retrieval slots). Returns whether the old id existed."""
        conn = await self._ensure_conn()
        cur = await conn.execute(
            "UPDATE records SET superseded_by = ? WHERE id = ?", (new_id, old_id)
        )
        await conn.commit()
        await self._unindex(old_id)
        await self.mark_unresolved_dependents(old_id)
        return cur.rowcount > 0

    async def supersede_with(
        self, old_id: str, *, text: str, kind: str = Kind.NOTE,
        source_ref: SourceRef | None = None,
    ) -> Record:
        """Insert a replacement AND close the old lineage in ONE transaction, so a
        mid-op failure can't strand a half-applied SUPERSEDE (orphan duplicate).
        The successor inherits the old record's labels (the caller may then set
        more). If `old_id` doesn't exist this is just an ADD (the correction
        still lands)."""
        from uuid import uuid4

        record = Record(id=uuid4().hex, text=text, kind=kind, source_ref=source_ref)
        conn = await self._ensure_conn()
        await conn.execute(
            """
            INSERT INTO records
                (id, text, kind, scope_kind, scope_key, created_at,
                 last_confirmed_at, superseded_by, pinned, source_ref)
            VALUES (?, ?, ?, ?, ?, ?, ?, NULL, 0, ?)
            """,
            (record.id, record.text, record.kind,
             source_ref.scope_kind if source_ref else None,
             source_ref.scope_key if source_ref else None,
             record.created_at, record.last_confirmed_at,
             json.dumps(source_ref.to_dict()) if source_ref else None),
        )
        cur = await conn.execute(
            "UPDATE records SET superseded_by = ? WHERE id = ?", (record.id, old_id)
        )
        await conn.execute(
            "INSERT OR IGNORE INTO record_labels (record_id, label, created_at) "
            "SELECT ?, label, created_at FROM record_labels WHERE record_id = ?",
            (record.id, old_id),
        )
        await conn.commit()
        self._index(record)
        await self._unindex(old_id)
        await self.mark_unresolved_dependents(old_id)
        if cur.rowcount == 0:
            _logger.warning("supersede target id not found; landed as ADD", old_id=old_id)
        return record

    async def set_kind(self, record_id: str, kind: str) -> bool:
        """Reclassify a record's function-type (consolidation's retype op)."""
        conn = await self._ensure_conn()
        cur = await conn.execute(
            "UPDATE records SET kind = ? WHERE id = ?", (kind, record_id)
        )
        await conn.commit()
        return cur.rowcount > 0

    async def merge(
        self, survivor_id: str, loser_ids: list[str], *, text: str | None = None,
        kind: str | None = None,
    ) -> Record | None:
        """Collapse N records into ONE in a single transaction (the consolidate
        primitive). Each loser's `superseded_by` is pointed at the survivor and
        evicted from the vector index; the survivor's labels become the union of
        all members' labels. If `text` is given the survivor is re-texted (and
        re-confirmed) in the same transaction. Aborts (returns None) if the
        survivor or any loser is pinned — pinned records are never merged away.
        Returns the (re-fetched) survivor."""
        conn = await self._ensure_conn()
        survivor = await self.get(survivor_id)
        if survivor is None or survivor.pinned:
            return None
        losers: list[Record] = []
        for lid in loser_ids:
            if lid == survivor_id:
                continue
            loser = await self.get(lid)
            if loser is None:
                continue
            if loser.pinned:
                return None  # never merge a pinned record away
            losers.append(loser)
        if not losers:
            return survivor

        new_text = (text or "").strip() or None
        if new_text and new_text != survivor.text:
            await conn.execute(
                "UPDATE records SET text = ?, last_confirmed_at = ? WHERE id = ?",
                (new_text, now_iso(), survivor_id),
            )
        if kind and kind != survivor.kind:
            await conn.execute(
                "UPDATE records SET kind = ? WHERE id = ?", (kind, survivor_id)
            )
        for loser in losers:
            await conn.execute(
                "UPDATE records SET superseded_by = ? WHERE id = ?",
                (survivor_id, loser.id),
            )
            await conn.execute(
                "INSERT OR IGNORE INTO record_labels (record_id, label, created_at) "
                "SELECT ?, label, created_at FROM record_labels WHERE record_id = ?",
                (survivor_id, loser.id),
            )
        await conn.commit()

        for loser in losers:
            await self._unindex(loser.id)
            await self.mark_unresolved_dependents(loser.id)
        merged = await self.get(survivor_id)
        if merged is not None and new_text:
            self._index(merged)  # re-embed the re-texted survivor
        return merged

    async def confirm(self, record_id: str) -> bool:
        conn = await self._ensure_conn()
        cur = await conn.execute(
            "UPDATE records SET last_confirmed_at = ? WHERE id = ?", (now_iso(), record_id)
        )
        await conn.commit()
        return cur.rowcount > 0

    async def set_pinned(self, record_id: str, pinned: bool) -> bool:
        conn = await self._ensure_conn()
        cur = await conn.execute(
            "UPDATE records SET pinned = ? WHERE id = ?", (1 if pinned else 0, record_id)
        )
        await conn.commit()
        return cur.rowcount > 0

    async def update(self, record_id: str, text: str) -> bool:
        conn = await self._ensure_conn()
        cur = await conn.execute(
            "UPDATE records SET text = ?, last_confirmed_at = ? WHERE id = ?",
            (text, now_iso(), record_id),
        )
        await conn.commit()
        if cur.rowcount == 0:
            return False
        record = await self.get(record_id)
        if record is not None:
            self._index(record)
        return True

    async def delete(self, record_id: str) -> None:
        conn = await self._ensure_conn()
        await self.mark_unresolved_dependents(record_id)  # before the row vanishes
        await conn.execute("DELETE FROM record_labels WHERE record_id = ?", (record_id,))
        await conn.execute(
            "DELETE FROM justification_premises WHERE justification_id IN "
            "(SELECT id FROM justifications WHERE derived_id = ?)",
            (record_id,),
        )
        await conn.execute("DELETE FROM justifications WHERE derived_id = ?", (record_id,))
        await conn.execute("DELETE FROM records WHERE id = ?", (record_id,))
        await conn.commit()
        await self._unindex(record_id)  # inline (cheap, pure-DB) — no upsert-vs-delete race

    async def _unindex(self, record_id: str) -> None:
        if self._search_index is not None:
            try:
                await self._search_index.delete("record", record_id)
            except Exception:
                _logger.warning("record index delete failed", exc_info=True)

    # -- labels (open-vocabulary, attached at write time by the curator) ------

    async def set_labels(self, record_id: str, labels: list[str]) -> None:
        """Replace the record's labels wholesale (the curator's UPDATE semantics)."""
        conn = await self._ensure_conn()
        await conn.execute("DELETE FROM record_labels WHERE record_id = ?", (record_id,))
        ts = now_iso()
        await conn.executemany(
            "INSERT OR IGNORE INTO record_labels (record_id, label, created_at) VALUES (?, ?, ?)",
            [(record_id, label, ts) for label in labels],
        )
        await conn.commit()

    async def add_labels(self, record_id: str, labels: list[str]) -> None:
        """Union new labels onto the record (backfill / lens promotion)."""
        if not labels:
            return
        conn = await self._ensure_conn()
        ts = now_iso()
        await conn.executemany(
            "INSERT OR IGNORE INTO record_labels (record_id, label, created_at) VALUES (?, ?, ?)",
            [(record_id, label, ts) for label in labels],
        )
        await conn.commit()

    async def labels_of(self, record_id: str) -> list[str]:
        conn = await self._ensure_conn()
        rows = await conn.execute_fetchall(
            "SELECT label FROM record_labels WHERE record_id = ? ORDER BY label",
            (record_id,),
        )
        return [row["label"] for row in rows]

    async def labels_for(self, record_ids: list[str]) -> dict[str, list[str]]:
        """Batch-hydrate labels for many records in ONE query (no N+1). Every
        requested id is a key; unlabeled records map to []."""
        if not record_ids:
            return {}
        conn = await self._ensure_conn()
        rows = await conn.execute_fetchall(
            f"SELECT record_id, label FROM record_labels "
            f"WHERE record_id IN ({','.join('?' * len(record_ids))}) ORDER BY label",
            tuple(record_ids),
        )
        out: dict[str, list[str]] = {rid: [] for rid in record_ids}
        for row in rows:
            out[row["record_id"]].append(row["label"])
        return out

    async def records_for_label(self, label: str, *, limit: int = 200) -> list[Record]:
        """The "everything about X" page: active records carrying the label,
        newest-confirmed first."""
        conn = await self._ensure_conn()
        rows = await conn.execute_fetchall(
            "SELECT records.* FROM records "
            "JOIN record_labels ON record_labels.record_id = records.id "
            "WHERE record_labels.label = ? AND records.superseded_by IS NULL AND records.standing = 'active' "
            "ORDER BY records.last_confirmed_at DESC LIMIT ?",
            (label, limit),
        )
        return [self._row_to_record(row) for row in rows]

    async def list_labels(self) -> list[dict]:
        """[{"label", "count"}] counting ACTIVE records only, biggest hubs first."""
        conn = await self._ensure_conn()
        rows = await conn.execute_fetchall(
            "SELECT record_labels.label AS label, COUNT(*) AS count FROM record_labels "
            "JOIN records ON records.id = record_labels.record_id "
            "WHERE records.superseded_by IS NULL AND records.standing = 'active' "
            "GROUP BY record_labels.label ORDER BY count DESC, label ASC"
        )
        return [{"label": row["label"], "count": row["count"]} for row in rows]

    async def rename_label(self, old: str, new: str) -> None:
        """Lint canonicalization: fold `old` into `new` with union semantics — a
        record already carrying both keeps one row."""
        conn = await self._ensure_conn()
        await conn.execute(
            "INSERT OR IGNORE INTO record_labels (record_id, label, created_at) "
            "SELECT record_id, ?, created_at FROM record_labels WHERE label = ?",
            (new, old),
        )
        await conn.execute("DELETE FROM record_labels WHERE label = ?", (old,))
        await conn.commit()

    # -- derivation (the recursive memory: justifications, standing, nogoods) --
    # A derived record exists only with >=1 justification (cite-or-void). It may
    # hold SEVERAL (JTMS) — it stays active while any justification's premises
    # all live. Premise death marks dependents `unresolved` (excluded from
    # recall); the dreamer re-judges them. Confidence is never stored — trust is
    # computed from the DAG (justification count, disjoint evidence, depth).

    async def add_derived(
        self, text: str, *, premise_ids: list[str], mode: str, question: str,
        kind: str = Kind.NOTE,
    ) -> Record:
        """Insert an inferred record + its first justification atomically."""
        from uuid import uuid4

        premises = await self._live_premises(premise_ids)
        record = Record(
            id=uuid4().hex, text=text, kind=kind,
            source_ref=SourceRef(kind="dreamer", ref=question),
            provenance=Provenance.DERIVED,
            depth=max(p.depth for p in premises) + 1,
        )
        conn = await self._ensure_conn()
        await conn.execute(
            """
            INSERT INTO records
                (id, text, kind, scope_kind, scope_key, created_at,
                 last_confirmed_at, superseded_by, pinned, source_ref,
                 provenance, standing, depth)
            VALUES (?, ?, ?, NULL, NULL, ?, ?, NULL, 0, ?, ?, ?, ?)
            """,
            (record.id, record.text, record.kind, record.created_at,
             record.last_confirmed_at, json.dumps(record.source_ref.to_dict()),
             record.provenance, record.standing, record.depth),
        )
        await self._insert_justification(conn, record.id, premise_ids, mode, question)
        await conn.commit()
        self._index(record)
        return record

    async def add_justification(
        self, record_id: str, *, premise_ids: list[str], mode: str, question: str,
    ) -> Justification:
        """Append an independent justification to an existing record (a
        re-derivation landed on the same conclusion). Reactivates an unresolved
        record — fresh living support resolves it. Raises on cyclic support."""
        premises = await self._live_premises(premise_ids)
        record = await self.get(record_id)
        if record is None:
            raise ValueError(f"record {record_id!r} not found")
        conn = await self._ensure_conn()
        just = await self._insert_justification(conn, record_id, premise_ids, mode, question)
        # A GROUND record gaining a justification stays ground at depth 0 (direct
        # evidence outranks inference — the justification is corroboration, not
        # pedigree). Only derived records carry chain depth.
        depth = record.depth
        if record.provenance == Provenance.DERIVED:
            depth = max(record.depth, max(p.depth for p in premises) + 1)
        await conn.execute(
            "UPDATE records SET depth = ?, standing = ? WHERE id = ?",
            (depth, Standing.ACTIVE, record_id),
        )
        await conn.commit()
        if record.standing != Standing.ACTIVE:
            self._index(record)  # back into retrieval circulation
        return just

    async def _insert_justification(
        self, conn, derived_id: str, premise_ids: list[str], mode: str, question: str,
    ) -> Justification:
        from uuid import uuid4

        for pid in premise_ids:
            if pid == derived_id or derived_id in await self._ancestry(pid):
                raise ValueError(f"cyclic justification: {pid!r} depends on {derived_id!r}")
        just = Justification(
            id=uuid4().hex, derived_id=derived_id,
            premise_ids=tuple(premise_ids), mode=mode, question=question,
        )
        await conn.execute(
            "INSERT INTO justifications (id, derived_id, mode, question, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (just.id, just.derived_id, just.mode, just.question, just.created_at),
        )
        for pid in premise_ids:
            await conn.execute(
                "INSERT OR IGNORE INTO justification_premises (justification_id, premise_id) "
                "VALUES (?, ?)",
                (just.id, pid),
            )
        return just

    async def _live_premises(self, premise_ids: list[str]) -> list[Record]:
        """Resolve premises, requiring every one alive — a derivation may only be
        built on live knowledge."""
        if not premise_ids:
            raise ValueError("a derivation needs at least one premise")
        premises = []
        for pid in premise_ids:
            p = await self.get(pid)
            if p is None or not self._alive(p):
                raise ValueError(f"premise {pid!r} is not a live record")
            premises.append(p)
        return premises

    @staticmethod
    def _alive(record: Record) -> bool:
        return record.superseded_by is None and record.standing == Standing.ACTIVE

    async def justifications_of(self, record_id: str) -> list[Justification]:
        conn = await self._ensure_conn()
        rows = await conn.execute_fetchall(
            "SELECT * FROM justifications WHERE derived_id = ? ORDER BY created_at",
            (record_id,),
        )
        out = []
        for row in rows:
            prem = await conn.execute_fetchall(
                "SELECT premise_id FROM justification_premises WHERE justification_id = ?",
                (row["id"],),
            )
            out.append(Justification(
                id=row["id"], derived_id=row["derived_id"],
                premise_ids=tuple(p["premise_id"] for p in prem),
                mode=row["mode"], question=row["question"], created_at=row["created_at"],
            ))
        return out

    async def dependents_of(self, record_id: str) -> list[str]:
        """Ids of derived records holding a justification that cites this one."""
        conn = await self._ensure_conn()
        rows = await conn.execute_fetchall(
            "SELECT DISTINCT j.derived_id FROM justifications j "
            "JOIN justification_premises p ON p.justification_id = j.id "
            "WHERE p.premise_id = ?",
            (record_id,),
        )
        return [r["derived_id"] for r in rows]

    async def _ancestry(self, record_id: str, *, _seen: set | None = None) -> set[str]:
        """All premise ids reachable upward from a record (cycle-guarded)."""
        seen = _seen if _seen is not None else set()
        for just in await self.justifications_of(record_id):
            for pid in just.premise_ids:
                if pid not in seen:
                    seen.add(pid)
                    await self._ancestry(pid, _seen=seen)
        return seen

    async def evidence_base(self, record_id: str) -> set[str]:
        """The GROUND record ids in this record's derivation ancestry — the
        NARS evidential stamp (disjointness = real corroboration)."""
        base: set[str] = set()
        for rid in await self._ancestry(record_id) or {record_id}:
            r = await self.get(rid)
            if r is not None and r.provenance == Provenance.GROUND:
                base.add(rid)
        return base

    async def trust_signals(self, record_id: str) -> dict:
        """The vision-§7 signals, computed from the DAG — shown, never a gate."""
        record = await self.get(record_id)
        justs = await self.justifications_of(record_id)
        bases: list[set[str]] = []
        for j in justs:
            b: set[str] = set()
            for pid in j.premise_ids:
                p = await self.get(pid)
                if p is None:
                    continue
                b |= {pid} if p.provenance == Provenance.GROUND else await self.evidence_base(pid)
            bases.append(b)
        independent = 0
        covered: set[str] = set()
        for b in bases:
            if b - covered:
                independent += 1
                covered |= b
        return {
            "provenance": record.provenance if record else Provenance.GROUND,
            "standing": record.standing if record else Standing.ACTIVE,
            "depth": record.depth if record else 0,
            "justifications": len(justs),
            "independent_grounds": independent,
            "modes": sorted({j.mode for j in justs}),
        }

    async def mark_unresolved_dependents(self, dead_id: str) -> int:
        """Premise death propagation (JTMS): walk dependents; a derivation goes
        `unresolved` ONLY when every justification it holds contains a dead
        premise — surviving independent support keeps it active untouched.
        Unresolved records leave retrieval until the dreamer re-judges them."""
        conn = await self._ensure_conn()
        marked = 0
        frontier = {dead_id}
        for _ in range(10):  # bounded transitive depth
            nxt: set[str] = set()
            for fid in frontier:
                for dep_id in await self.dependents_of(fid):
                    dep = await self.get(dep_id)
                    if dep is None or not self._alive(dep):
                        continue
                    if await self._has_living_justification(dep_id):
                        continue
                    await conn.execute(
                        "UPDATE records SET standing = ? WHERE id = ?",
                        (Standing.UNRESOLVED, dep_id),
                    )
                    await self._unindex(dep_id)
                    marked += 1
                    nxt.add(dep_id)
            await conn.commit()
            if not nxt:
                break
            frontier = nxt
        return marked

    async def _has_living_justification(self, record_id: str) -> bool:
        for just in await self.justifications_of(record_id):
            alive = True
            for pid in just.premise_ids:
                p = await self.get(pid)
                if p is None or not self._alive(p):
                    alive = False
                    break
            if alive:
                return True
        return False

    async def unresolved(self, *, limit: int = 50) -> list[Record]:
        """Derivations awaiting re-judgment, oldest first."""
        conn = await self._ensure_conn()
        rows = await conn.execute_fetchall(
            "SELECT * FROM records WHERE standing = ? AND superseded_by IS NULL "
            "ORDER BY last_confirmed_at ASC LIMIT ?",
            (Standing.UNRESOLVED, limit),
        )
        return [self._row_to_record(row) for row in rows]

    async def retire(self, record_id: str, *, nogood_why: str | None = None) -> bool:
        """Take a derivation out of circulation (lint hygiene / re-judgment).
        With `nogood_why` the retirement also records a nogood so the dreamer
        never re-derives the same junk from the same premises."""
        record = await self.get(record_id)
        if record is None or record.pinned:
            return False
        conn = await self._ensure_conn()
        await conn.execute(
            "UPDATE records SET standing = ? WHERE id = ?", (Standing.RETIRED, record_id)
        )
        await conn.commit()
        await self._unindex(record_id)
        if nogood_why:
            for just in await self.justifications_of(record_id):
                await self.add_nogood(list(just.premise_ids), record.text, nogood_why)
        await self.mark_unresolved_dependents(record_id)
        return True

    async def add_nogood(self, premise_ids: list[str], conclusion: str, why: str) -> None:
        from uuid import uuid4

        conn = await self._ensure_conn()
        await conn.execute(
            "INSERT INTO nogoods (id, premise_ids, conclusion, why, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (uuid4().hex, json.dumps(sorted(premise_ids)), conclusion, why, now_iso()),
        )
        await conn.commit()

    async def justification_edges_among(self, record_ids: list[str]) -> list[dict]:
        """Evidence edges (derived -> premise) with BOTH endpoints in `record_ids`
        — the graph view's epistemic structure, one query."""
        if not record_ids:
            return []
        conn = await self._ensure_conn()
        ph = ",".join("?" * len(record_ids))
        rows = await conn.execute_fetchall(
            f"SELECT j.derived_id AS derived_id, p.premise_id AS premise_id, "
            f"j.created_at AS created_at FROM justifications j "
            f"JOIN justification_premises p ON p.justification_id = j.id "
            f"WHERE j.derived_id IN ({ph}) AND p.premise_id IN ({ph})",
            (*record_ids, *record_ids),
        )
        return [
            {"derived_id": r["derived_id"], "premise_id": r["premise_id"],
             "created_at": r["created_at"]}
            for r in rows
        ]

    async def derived_records(self, *, limit: int = 200) -> list[Record]:
        """Active inferred records, newest first — the dream's output surface."""
        conn = await self._ensure_conn()
        rows = await conn.execute_fetchall(
            "SELECT * FROM records WHERE provenance = 'derived' AND superseded_by IS NULL "
            "ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        return [self._row_to_record(row) for row in rows]

    async def nogoods_for(self, record_ids: list[str]) -> list[dict]:
        """Nogoods whose premises overlap `record_ids` — injected into dream
        prompts so retracted junk is not re-derived. The table is small; filter
        in Python."""
        conn = await self._ensure_conn()
        rows = await conn.execute_fetchall("SELECT * FROM nogoods")
        wanted = set(record_ids)
        out = []
        for row in rows:
            premises = set(json.loads(row["premise_ids"]))
            if premises & wanted:
                out.append({
                    "premise_ids": sorted(premises),
                    "conclusion": row["conclusion"],
                    "why": row["why"],
                })
        return out

    # -- reads ---------------------------------------------------------------

    async def get(self, record_id: str) -> Record | None:
        conn = await self._ensure_conn()
        rows = await conn.execute_fetchall(
            "SELECT * FROM records WHERE id = ?", (record_id,)
        )
        return self._row_to_record(rows[0]) if rows else None

    async def search(
        self,
        query: str,
        *,
        kinds: list[str] | None = None,
        limit: int = 10,
        include_superseded: bool = False,
    ) -> list[Record]:
        """Hybrid FTS (records_fts) ⊕ vector (SearchIndex, source="record")
        fused with rrf_merge over the WHOLE flat pool, then post-filtered by
        kinds/supersession. Bridges the two databases in Python on the record id."""
        conn = await self._ensure_conn()
        window = max(limit * 4, 40)

        def _matches(record: Record) -> bool:
            if not include_superseded and not self._alive(record):
                return False
            if kinds is not None and record.kind not in kinds:
                return False
            return True

        # FTS leg (local records_fts in memory.db) — kind/active in SQL.
        fts_ranked: list[tuple[str, float]] = []
        fts_query = build_fts_or_query(query)
        if fts_query:
            where = ["records_fts MATCH ?"]
            params: list = [fts_query]
            if not include_superseded:
                # `unresolved`/`retired` derivations leave recall with their premises.
                where.append("records.superseded_by IS NULL")
                where.append("records.standing = 'active'")
            if kinds:
                where.append(f"records.kind IN ({','.join('?' * len(kinds))})")
                params += list(kinds)
            params.append(window)
            try:
                rows = await conn.execute_fetchall(
                    f"SELECT records.id AS id FROM records_fts "
                    f"JOIN records ON records_fts.rowid = records.rowid "
                    f"WHERE {' AND '.join(where)} ORDER BY records_fts.rank LIMIT ?",
                    tuple(params),
                )
                fts_ranked = [(row["id"], 1.0) for row in rows]
            except Exception:
                _logger.warning("record FTS search failed; vector-only", exc_info=True)

        # Vector leg (search.db) — kind filtered on metadata; superseded records
        # are already evicted from the index on supersede/delete.
        vec_ranked: list[tuple[str, float]] = []
        index = self._search_index
        if index is not None:
            try:
                emb = await index.embedder.embed_one(query)
                raw = await index.store.vector_search(
                    serialize_embedding(emb), sources=["record"], limit=window
                )
                for item_id, score in raw:
                    item = await index.store.get_by_id(item_id)
                    meta = item.metadata if item and item.metadata else None
                    if not meta or "record_id" not in meta:
                        continue
                    if kinds is not None and meta.get("kind") not in kinds:
                        continue
                    vec_ranked.append((meta["record_id"], score))
            except Exception:
                _logger.warning("record vector search failed; FTS-only", exc_info=True)

        fused = rrf_merge([fts_ranked, vec_ranked], k=RRF_K)
        ordered = sorted(fused, key=lambda rid: fused[rid], reverse=True)
        if not ordered:
            return []

        # Batch-hydrate (one query, not N+1), preserve rank order, re-apply the
        # filters as a safety net (covers any lingering index/SQL skew).
        rows = await conn.execute_fetchall(
            f"SELECT * FROM records WHERE id IN ({','.join('?' * len(ordered))})",
            tuple(ordered),
        )
        by_id = {r["id"]: self._row_to_record(r) for r in rows}
        out: list[Record] = []
        for rid in ordered:
            record = by_id.get(rid)
            if record is not None and _matches(record):
                out.append(record)
                if len(out) >= limit:
                    break
        return out

    async def list(
        self, *, pinned_only: bool = False, include_superseded: bool = False, limit: int = 50
    ) -> list[Record]:
        """The flat Records list — active records (newest-confirmed first) by
        default; `include_superseded` widens it to the whole lineage for the
        admin claim browser's "all statuses" view."""
        conn = await self._ensure_conn()
        where = [] if include_superseded else ["superseded_by IS NULL"]
        if pinned_only:
            where.append("pinned = 1")
        sql = "SELECT * FROM records"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY last_confirmed_at DESC LIMIT ?"
        rows = await conn.execute_fetchall(sql, (limit,))
        return [self._row_to_record(row) for row in rows]

    async def count_active(self) -> int:
        """Size of the active pool — the lens-coverage denominator (scope_pool)."""
        conn = await self._ensure_conn()
        rows = await conn.execute_fetchall(
            "SELECT COUNT(*) AS n FROM records WHERE superseded_by IS NULL AND standing = 'active'"
        )
        return rows[0]["n"] if rows else 0

    async def neighborhood(self, record: Record, *, limit: int = 8) -> list[Record]:
        """The active records that lexically/semantically resemble `record`
        (hybrid recall), minus the record itself — its consolidation neighborhood.
        Thin wrapper over `search`, which already excludes superseded records and
        degrades to a single available leg when the other is down."""
        hits = await self.search(record.text, limit=limit + 1, include_superseded=False)
        return [h for h in hits if h.id != record.id][:limit]

    async def updated_since(self, watermark: str | None, *, limit: int) -> list[Record]:
        """Active records confirmed at/after the watermark, oldest-confirmed first
        (the O(delta) consolidation candidate set). `>=`-inclusive so a tie-group
        sharing the boundary timestamp is never skipped; `None` returns the whole
        active pool oldest-first."""
        conn = await self._ensure_conn()
        sql = "SELECT * FROM records WHERE superseded_by IS NULL AND standing = 'active'"
        params: list = []
        if watermark is not None:
            sql += " AND last_confirmed_at >= ?"
            params.append(watermark)
        sql += " ORDER BY last_confirmed_at ASC LIMIT ?"
        params.append(limit)
        rows = await conn.execute_fetchall(sql, tuple(params))
        return [self._row_to_record(row) for row in rows]

    # -- internals -----------------------------------------------------------

    def _index(self, record: Record) -> None:
        """Fire-and-forget vector index (mirror the transcript hook). The
        SearchIndex embeds unconditionally on upsert — no EMBED_SOURCES gate."""
        if self._search_index is not None and record.text.strip():
            self._track(
                self._search_index.upsert(
                    source="record",
                    source_id=record.id,
                    title=f"{record.kind} record",
                    content=record.text,
                    metadata={"record_id": record.id, "kind": record.kind},
                )
            )

    @staticmethod
    def _row_to_record(row) -> Record:
        return Record(
            id=row["id"],
            text=row["text"],
            kind=row["kind"],
            created_at=row["created_at"],
            last_confirmed_at=row["last_confirmed_at"],
            superseded_by=row["superseded_by"],
            pinned=bool(row["pinned"]),
            source_ref=SourceRef.from_dict(json.loads(row["source_ref"]))
            if row["source_ref"]
            else None,
            provenance=row["provenance"],
            standing=row["standing"],
            depth=row["depth"],
        )
