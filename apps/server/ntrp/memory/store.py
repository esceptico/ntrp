"""SQLite store for the Stage-2 memory schema.

Two tables: `memory_items` (claims-only, subject-keyed) and `lenses` (a registry
of views), plus a `lens_membership_cache` that is a cache, not graph truth (drop
it and nothing breaks except projection latency). Edges in `memory_item_parents`
are claim->claim only. FTS5 over claim content/subject and (separately) over
lens text. Storage only: CRUD, scope/validity queries, edges, invalidate/
supersede (never a hard delete), and registry CRUD. No pipeline, no ranking.

Conventions match search/automation stores: injected connection, async API,
meta-table schema-version ladder, ISO-8601 UTC TEXT timestamps, JSON TEXT for
structured fields, commit after every write.
"""

import json

import aiosqlite

from ntrp.logging import get_logger
from ntrp.memory.migrations import run_migrations
from ntrp.memory.models import (
    EdgeRole,
    Feedback,
    LensDetailLevel,
    LensProvenance,
    LensRow,
    LensStatus,
    MembershipDecision,
    MembershipVerdict,
    MemoryEdge,
    MemoryItem,
    Provenance,
    Scope,
    ScopeKind,
    SourceRef,
    Status,
    now_iso,
)

_logger = get_logger(__name__)

DQ = '"'

SCHEMA = """
CREATE TABLE IF NOT EXISTS memory_items (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    canonical_subject TEXT NOT NULL,
    scope_kind TEXT NOT NULL,
    scope_key TEXT,
    provenance TEXT NOT NULL,

    status TEXT NOT NULL DEFAULT 'active',
    valid_from TEXT,
    invalid_at TEXT,

    source_refs TEXT NOT NULL DEFAULT '[]',

    corroboration INTEGER NOT NULL DEFAULT 0,
    last_relevant_at TEXT,
    feedback TEXT NOT NULL DEFAULT 'none',

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memory_item_parents (
    child_id TEXT NOT NULL,
    parent_id TEXT NOT NULL,
    role TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    PRIMARY KEY (child_id, parent_id, role),
    FOREIGN KEY (child_id) REFERENCES memory_items(id) ON DELETE CASCADE,
    FOREIGN KEY (parent_id) REFERENCES memory_items(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS lenses (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    criterion TEXT NOT NULL,
    scope_kind TEXT NOT NULL,
    scope_key TEXT,
    detail_level TEXT NOT NULL DEFAULT 'structured',
    provenance TEXT NOT NULL DEFAULT 'user_authored',
    status TEXT NOT NULL DEFAULT 'active',
    page TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lens_membership_cache (
    lens_id TEXT NOT NULL,
    claim_id TEXT NOT NULL,
    decision TEXT NOT NULL,
    rationale TEXT,
    scored_at TEXT NOT NULL,
    PRIMARY KEY (lens_id, claim_id)
);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

-- Hot path: active claims filtered by scope.
CREATE INDEX IF NOT EXISTS idx_items_status_scope
    ON memory_items(status, scope_kind, scope_key);
-- Subject recall channel (coreference grouping).
CREATE INDEX IF NOT EXISTS idx_items_subject ON memory_items(canonical_subject);
CREATE INDEX IF NOT EXISTS idx_edges_child ON memory_item_parents(child_id, role);
CREATE INDEX IF NOT EXISTS idx_edges_parent ON memory_item_parents(parent_id, role);
CREATE INDEX IF NOT EXISTS idx_lenses_scope ON lenses(status, scope_kind, scope_key);
CREATE INDEX IF NOT EXISTS idx_lmc_lens ON lens_membership_cache(lens_id, decision);
"""

_COLUMNS = (
    "id, content, canonical_subject, scope_kind, scope_key, provenance, status, valid_from, "
    "invalid_at, source_refs, corroboration, last_relevant_at, feedback, created_at, updated_at"
)
_N_COLUMNS = len(_COLUMNS.split(", "))

_LENS_COLUMNS = (
    "id, name, criterion, scope_kind, scope_key, detail_level, provenance, status, page, "
    "created_at, updated_at"
)
_N_LENS_COLUMNS = len(_LENS_COLUMNS.split(", "))

SQL_INSERT = f"INSERT INTO memory_items ({_COLUMNS}) VALUES ({','.join('?' * _N_COLUMNS)})"
SQL_GET = f"SELECT {_COLUMNS} FROM memory_items WHERE id = ?"
SQL_INSERT_EDGE = (
    "INSERT OR IGNORE INTO memory_item_parents (child_id, parent_id, role, position, created_at) "
    "VALUES (?, ?, ?, ?, ?)"
)
SQL_EDGES_FROM = (
    "SELECT child_id, parent_id, role, position, created_at FROM memory_item_parents "
    "WHERE child_id = ? ORDER BY role, position"
)
SQL_EDGES_TO = (
    "SELECT child_id, parent_id, role, position, created_at FROM memory_item_parents "
    "WHERE parent_id = ? ORDER BY role, position"
)
SQL_INVALIDATE = (
    "UPDATE memory_items SET status = ?, invalid_at = ?, updated_at = ? "
    "WHERE id = ? AND status = 'active'"
)
SQL_SET_FEEDBACK = "UPDATE memory_items SET feedback = ?, updated_at = ? WHERE id = ?"
SQL_BUMP_CORROBORATION = (
    "UPDATE memory_items SET corroboration = corroboration + 1, updated_at = ? WHERE id = ?"
)

SQL_INSERT_LENS = f"INSERT INTO lenses ({_LENS_COLUMNS}) VALUES ({','.join('?' * _N_LENS_COLUMNS)})"
SQL_GET_LENS = f"SELECT {_LENS_COLUMNS} FROM lenses WHERE id = ?"
SQL_DELETE_LENS = "DELETE FROM lenses WHERE id = ?"
SQL_UPSERT_MEMBERSHIP = (
    "INSERT OR REPLACE INTO lens_membership_cache (lens_id, claim_id, decision, rationale, scored_at) "
    "VALUES (?, ?, ?, ?, ?)"
)
SQL_INVALIDATE_MEMBERSHIP = "DELETE FROM lens_membership_cache WHERE lens_id = ?"


class MemoryStore:
    def __init__(self, conn: aiosqlite.Connection):
        self.conn = conn
        self._has_fts = False

    @property
    def has_fts(self) -> bool:
        """Whether FTS5 is available. Read-only view over the private flag so a
        consumer can distinguish 'FTS matched nothing' from 'FTS unavailable'.
        Adds no state, no schema, no invariant change."""
        return self._has_fts

    async def init_schema(self) -> None:
        await self.conn.executescript(SCHEMA)
        try:
            await self.conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS memory_items_fts USING fts5(
                    content, canonical_subject,
                    content='memory_items',
                    content_rowid='rowid'
                );
                """
            )
            await self.conn.executescript(
                """
                CREATE TRIGGER IF NOT EXISTS memory_items_ai AFTER INSERT ON memory_items BEGIN
                    INSERT INTO memory_items_fts(rowid, content, canonical_subject)
                    VALUES (new.rowid, new.content, new.canonical_subject);
                END;
                CREATE TRIGGER IF NOT EXISTS memory_items_ad AFTER DELETE ON memory_items BEGIN
                    INSERT INTO memory_items_fts(memory_items_fts, rowid, content, canonical_subject)
                    VALUES ('delete', old.rowid, old.content, old.canonical_subject);
                END;
                CREATE TRIGGER IF NOT EXISTS memory_items_au AFTER UPDATE ON memory_items BEGIN
                    INSERT INTO memory_items_fts(memory_items_fts, rowid, content, canonical_subject)
                    VALUES ('delete', old.rowid, old.content, old.canonical_subject);
                    INSERT INTO memory_items_fts(rowid, content, canonical_subject)
                    VALUES (new.rowid, new.content, new.canonical_subject);
                END;
                """
            )
            await self.conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS lenses_fts USING fts5(
                    name, criterion, page,
                    content='lenses',
                    content_rowid='rowid'
                );
                """
            )
            await self.conn.executescript(
                """
                CREATE TRIGGER IF NOT EXISTS lenses_ai AFTER INSERT ON lenses BEGIN
                    INSERT INTO lenses_fts(rowid, name, criterion, page)
                    VALUES (new.rowid, new.name, new.criterion, new.page);
                END;
                CREATE TRIGGER IF NOT EXISTS lenses_ad AFTER DELETE ON lenses BEGIN
                    INSERT INTO lenses_fts(lenses_fts, rowid, name, criterion, page)
                    VALUES ('delete', old.rowid, old.name, old.criterion, old.page);
                END;
                CREATE TRIGGER IF NOT EXISTS lenses_au AFTER UPDATE ON lenses BEGIN
                    INSERT INTO lenses_fts(lenses_fts, rowid, name, criterion, page)
                    VALUES ('delete', old.rowid, old.name, old.criterion, old.page);
                    INSERT INTO lenses_fts(rowid, name, criterion, page)
                    VALUES (new.rowid, new.name, new.criterion, new.page);
                END;
                """
            )
            self._has_fts = True
        except Exception as e:
            _logger.warning("memory FTS5 unavailable: %s", e)
            self._has_fts = False

        await run_migrations(self.conn)
        await self.conn.commit()

    # --- row mapping ---

    def _row_to_item(self, row: aiosqlite.Row) -> MemoryItem:
        return MemoryItem(
            id=row["id"],
            content=row["content"],
            canonical_subject=row["canonical_subject"],
            scope=Scope(kind=ScopeKind(row["scope_kind"]), key=row["scope_key"]),
            provenance=Provenance(row["provenance"]),
            status=Status(row["status"]),
            valid_from=row["valid_from"],
            invalid_at=row["invalid_at"],
            source_refs=[SourceRef.from_dict(d) for d in json.loads(row["source_refs"])],
            corroboration=row["corroboration"],
            last_relevant_at=row["last_relevant_at"],
            feedback=Feedback(row["feedback"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _row_to_edge(self, row: aiosqlite.Row) -> MemoryEdge:
        return MemoryEdge(
            child_id=row["child_id"],
            parent_id=row["parent_id"],
            role=EdgeRole(row["role"]),
            position=row["position"],
            created_at=row["created_at"],
        )

    def _row_to_lens(self, row: aiosqlite.Row) -> LensRow:
        return LensRow(
            id=row["id"],
            name=row["name"],
            criterion=row["criterion"],
            scope=Scope(kind=ScopeKind(row["scope_kind"]), key=row["scope_key"]),
            detail_level=LensDetailLevel(row["detail_level"]),
            provenance=LensProvenance(row["provenance"]),
            status=LensStatus(row["status"]),
            page=row["page"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    # --- claim writes ---

    async def create_item(self, item: MemoryItem, *, commit: bool = True) -> MemoryItem:
        await self.conn.execute(
            SQL_INSERT,
            (
                item.id,
                item.content,
                item.canonical_subject,
                str(item.scope.kind),
                item.scope.key,
                str(item.provenance),
                str(item.status),
                item.valid_from,
                item.invalid_at,
                json.dumps([r.to_dict() for r in item.source_refs]),
                item.corroboration,
                item.last_relevant_at,
                str(item.feedback),
                item.created_at,
                item.updated_at,
            ),
        )
        if commit:
            await self.conn.commit()
        return item

    async def add_edge(self, edge: MemoryEdge, *, commit: bool = True) -> bool:
        cursor = await self.conn.execute(
            SQL_INSERT_EDGE,
            (edge.child_id, edge.parent_id, str(edge.role), edge.position, edge.created_at),
        )
        if commit:
            await self.conn.commit()
        return cursor.rowcount > 0

    async def invalidate(self, item_id: str, *, status: Status = Status.ARCHIVED) -> bool:
        """Close an item's validity interval. Never deletes the row.

        Sets invalid_at to now and moves status off 'active'. No-op if the item
        is not currently active.
        """
        if status is Status.ACTIVE:
            raise ValueError("invalidate must move status off 'active'")
        now = now_iso()
        cursor = await self.conn.execute(SQL_INVALIDATE, (str(status), now, now, item_id))
        await self.conn.commit()
        return cursor.rowcount > 0

    async def supersede(self, *, old_id: str, new_item: MemoryItem) -> MemoryItem:
        """Create a successor, close the predecessor, link with a supersedes edge.

        The predecessor row is preserved (status=superseded, invalid_at set);
        history stays walkable. No row is removed.
        """
        await self.create_item(new_item, commit=False)
        now = now_iso()
        await self.conn.execute(SQL_INVALIDATE, (str(Status.SUPERSEDED), now, now, old_id))
        await self.add_edge(
            MemoryEdge(child_id=new_item.id, parent_id=old_id, role=EdgeRole.SUPERSEDES),
            commit=False,
        )
        await self.conn.commit()
        return new_item

    async def set_feedback(self, item_id: str, feedback: Feedback) -> bool:
        cursor = await self.conn.execute(SQL_SET_FEEDBACK, (str(feedback), now_iso(), item_id))
        await self.conn.commit()
        return cursor.rowcount > 0

    async def bump_corroboration(self, item_id: str) -> bool:
        cursor = await self.conn.execute(SQL_BUMP_CORROBORATION, (now_iso(), item_id))
        await self.conn.commit()
        return cursor.rowcount > 0

    # --- claim reads ---

    async def get(self, item_id: str) -> MemoryItem | None:
        rows = await self.conn.execute_fetchall(SQL_GET, (item_id,))
        return self._row_to_item(rows[0]) if rows else None

    async def query(
        self,
        *,
        scope: Scope | None = None,
        status: Status | None = Status.ACTIVE,
        subject: str | None = None,
        valid_at: str | None = None,
        limit: int = 100,
    ) -> list[MemoryItem]:
        """Query claims by scope, status, optional subject, and validity instant.

        `subject`: exact `canonical_subject` match (coreference grouping).
        `valid_at` (ISO-8601): keep items whose validity window contains it
        (valid_from <= valid_at and (invalid_at is null or invalid_at > valid_at)).
        `status=None` returns all statuses.
        """
        clauses: list[str] = []
        params: list = []
        if scope is not None:
            clauses.append("scope_kind = ?")
            params.append(str(scope.kind))
            if scope.key is None:
                clauses.append("scope_key IS NULL")
            else:
                clauses.append("scope_key = ?")
                params.append(scope.key)
        if status is not None:
            clauses.append("status = ?")
            params.append(str(status))
        if subject is not None:
            clauses.append("canonical_subject = ?")
            params.append(subject)
        if valid_at is not None:
            clauses.append("(valid_from IS NULL OR valid_from <= ?)")
            params.append(valid_at)
            clauses.append("(invalid_at IS NULL OR invalid_at > ?)")
            params.append(valid_at)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT {_COLUMNS} FROM memory_items {where} ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = await self.conn.execute_fetchall(sql, tuple(params))
        return [self._row_to_item(r) for r in rows]

    async def list_edges(
        self, item_id: str, *, direction: str = "from", role: EdgeRole | None = None
    ) -> list[MemoryEdge]:
        """List claim->claim edges touching an item.

        direction='from': edges where item is the child (its parents/provenance).
        direction='to': edges where item is the parent (its dependents).
        """
        sql = SQL_EDGES_FROM if direction == "from" else SQL_EDGES_TO
        rows = await self.conn.execute_fetchall(sql, (item_id,))
        edges = [self._row_to_edge(r) for r in rows]
        if role is not None:
            edges = [e for e in edges if e.role is role]
        return edges

    async def search(
        self, query: str, *, limit: int = 20, include_inactive: bool = False
    ) -> list[MemoryItem]:
        """FTS5 search over claim content and canonical_subject.

        Active-only by default — superseded/archived rows are indexed by FTS but
        excluded here so invalidated items never surface as live. Pass
        include_inactive=True for forensic/provenance queries. Empty if FTS
        unavailable.
        """
        if not self._has_fts:
            return []
        terms = [t for t in query.split() if t]
        if not terms:
            return []
        match = " OR ".join(DQ + t.replace(DQ, DQ + DQ) + DQ for t in terms)
        status_clause = "" if include_inactive else " AND i.status = 'active'"
        sql = f"""
            SELECT {','.join('i.' + c for c in _COLUMNS.split(', '))}
            FROM memory_items_fts f
            JOIN memory_items i ON i.rowid = f.rowid
            WHERE memory_items_fts MATCH ?{status_clause}
            ORDER BY f.rank
            LIMIT ?
        """
        rows = await self.conn.execute_fetchall(sql, (match, limit))
        return [self._row_to_item(r) for r in rows]

    # --- lens registry (views over claims; never memory) ---

    async def create_lens_row(self, lens: LensRow, *, commit: bool = True) -> LensRow:
        await self.conn.execute(
            SQL_INSERT_LENS,
            (
                lens.id,
                lens.name,
                lens.criterion,
                str(lens.scope.kind),
                lens.scope.key,
                str(lens.detail_level),
                str(lens.provenance),
                str(lens.status),
                lens.page,
                lens.created_at,
                lens.updated_at,
            ),
        )
        if commit:
            await self.conn.commit()
        return lens

    async def get_lens(self, lens_id: str) -> LensRow | None:
        rows = await self.conn.execute_fetchall(SQL_GET_LENS, (lens_id,))
        return self._row_to_lens(rows[0]) if rows else None

    async def update_lens(self, lens_id: str, **fields) -> LensRow | None:
        """In-place registry UPDATE. A lens is not a memory participant: it has no
        provenance DAG, so edits are plain UPDATEs (no supersede chain).

        Accepts: name, criterion, detail_level, provenance, status, page.
        """
        allowed = {"name", "criterion", "detail_level", "provenance", "status", "page"}
        sets: list[str] = []
        params: list = []
        for key, value in fields.items():
            if key not in allowed:
                raise ValueError(f"update_lens: unknown field {key!r}")
            sets.append(f"{key} = ?")
            params.append(str(value) if isinstance(value, LensProvenance | LensDetailLevel | LensStatus) else value)
        if not sets:
            return await self.get_lens(lens_id)
        sets.append("updated_at = ?")
        params.append(now_iso())
        params.append(lens_id)
        await self.conn.execute(f"UPDATE lenses SET {', '.join(sets)} WHERE id = ?", tuple(params))
        await self.conn.commit()
        return await self.get_lens(lens_id)

    async def list_lenses(
        self, *, scope: Scope | None = None, status: LensStatus | None = LensStatus.ACTIVE
    ) -> list[LensRow]:
        clauses: list[str] = []
        params: list = []
        if scope is not None:
            clauses.append("scope_kind = ?")
            params.append(str(scope.kind))
            if scope.key is None:
                clauses.append("scope_key IS NULL")
            else:
                clauses.append("scope_key = ?")
                params.append(scope.key)
        if status is not None:
            clauses.append("status = ?")
            params.append(str(status))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT {_LENS_COLUMNS} FROM lenses {where} ORDER BY created_at DESC"
        rows = await self.conn.execute_fetchall(sql, tuple(params))
        return [self._row_to_lens(r) for r in rows]

    async def delete_lens(self, lens_id: str) -> bool:
        """Hard-delete a lens row + its membership cache. A lens owns no data, so
        deleting it touches zero claims and zero edges."""
        cursor = await self.conn.execute(SQL_DELETE_LENS, (lens_id,))
        await self.conn.execute(SQL_INVALIDATE_MEMBERSHIP, (lens_id,))
        await self.conn.commit()
        return cursor.rowcount > 0

    async def search_lenses(self, query: str, *, limit: int = 20) -> list[LensRow]:
        """FTS5 search over lens name/criterion/page (registry-name recall)."""
        if not self._has_fts:
            return []
        terms = [t for t in query.split() if t]
        if not terms:
            return []
        match = " OR ".join(DQ + t.replace(DQ, DQ + DQ) + DQ for t in terms)
        sql = f"""
            SELECT {','.join('l.' + c for c in _LENS_COLUMNS.split(', '))}
            FROM lenses_fts f
            JOIN lenses l ON l.rowid = f.rowid
            WHERE lenses_fts MATCH ? AND l.status = 'active'
            ORDER BY f.rank
            LIMIT ?
        """
        rows = await self.conn.execute_fetchall(sql, (match, limit))
        return [self._row_to_lens(r) for r in rows]

    # --- membership cache (a cache, not graph truth) ---

    async def put_membership(
        self, verdicts: list[MembershipVerdict], *, commit: bool = True
    ) -> None:
        for v in verdicts:
            await self.conn.execute(
                SQL_UPSERT_MEMBERSHIP,
                (v.lens_id, v.claim_id, str(v.decision), v.rationale, v.scored_at),
            )
        if commit:
            await self.conn.commit()

    async def get_membership(
        self, lens_id: str, *, decision: MembershipDecision | None = None
    ) -> list[MembershipVerdict]:
        clauses = ["lens_id = ?"]
        params: list = [lens_id]
        if decision is not None:
            clauses.append("decision = ?")
            params.append(str(decision))
        sql = (
            "SELECT lens_id, claim_id, decision, rationale, scored_at FROM lens_membership_cache "
            f"WHERE {' AND '.join(clauses)}"
        )
        rows = await self.conn.execute_fetchall(sql, tuple(params))
        return [
            MembershipVerdict(
                lens_id=r["lens_id"],
                claim_id=r["claim_id"],
                decision=MembershipDecision(r["decision"]),
                rationale=r["rationale"],
                scored_at=r["scored_at"],
            )
            for r in rows
        ]

    async def invalidate_lens_membership(self, lens_id: str) -> None:
        await self.conn.execute(SQL_INVALIDATE_MEMBERSHIP, (lens_id,))
        await self.conn.commit()
