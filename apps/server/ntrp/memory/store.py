"""SQLite store for the Stage-2 memory schema.

Single object table + role-typed edge table + FTS5 over claim content and lens
text. Storage only: CRUD, scope/validity queries, edges, and invalidate/
supersede (never a hard delete). No pipeline, no ranking.

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
    Kind,
    LensDetailLevel,
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
    kind TEXT NOT NULL,
    content TEXT NOT NULL,
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

    lens_name TEXT,
    lens_criterion TEXT,
    lens_kind TEXT,
    lens_page TEXT,
    lens_detail_level TEXT,
    lens_exclusive INTEGER NOT NULL DEFAULT 0,

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

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

-- Hot path: active items filtered by scope + kind.
CREATE INDEX IF NOT EXISTS idx_items_status_scope_kind
    ON memory_items(status, scope_kind, scope_key, kind);
CREATE INDEX IF NOT EXISTS idx_items_kind ON memory_items(kind);
CREATE INDEX IF NOT EXISTS idx_edges_child ON memory_item_parents(child_id, role);
CREATE INDEX IF NOT EXISTS idx_edges_parent ON memory_item_parents(parent_id, role);
"""

_COLUMNS = (
    "id, kind, content, scope_kind, scope_key, provenance, status, valid_from, invalid_at, "
    "source_refs, corroboration, last_relevant_at, feedback, lens_name, lens_criterion, "
    "lens_kind, lens_page, lens_detail_level, lens_exclusive, created_at, updated_at"
)

SQL_INSERT = f"INSERT INTO memory_items ({_COLUMNS}) VALUES ({','.join('?' * 21)})"
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


class MemoryStore:
    def __init__(self, conn: aiosqlite.Connection):
        self.conn = conn
        self._has_fts = False

    async def init_schema(self) -> None:
        await self.conn.executescript(SCHEMA)
        try:
            await self.conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS memory_items_fts USING fts5(
                    content, lens_name, lens_criterion, lens_page,
                    content='memory_items',
                    content_rowid='rowid'
                );
                """
            )
            await self.conn.executescript(
                """
                CREATE TRIGGER IF NOT EXISTS memory_items_ai AFTER INSERT ON memory_items BEGIN
                    INSERT INTO memory_items_fts(rowid, content, lens_name, lens_criterion, lens_page)
                    VALUES (new.rowid, new.content, new.lens_name, new.lens_criterion, new.lens_page);
                END;
                CREATE TRIGGER IF NOT EXISTS memory_items_ad AFTER DELETE ON memory_items BEGIN
                    INSERT INTO memory_items_fts(memory_items_fts, rowid, content, lens_name, lens_criterion, lens_page)
                    VALUES ('delete', old.rowid, old.content, old.lens_name, old.lens_criterion, old.lens_page);
                END;
                CREATE TRIGGER IF NOT EXISTS memory_items_au AFTER UPDATE ON memory_items BEGIN
                    INSERT INTO memory_items_fts(memory_items_fts, rowid, content, lens_name, lens_criterion, lens_page)
                    VALUES ('delete', old.rowid, old.content, old.lens_name, old.lens_criterion, old.lens_page);
                    INSERT INTO memory_items_fts(rowid, content, lens_name, lens_criterion, lens_page)
                    VALUES (new.rowid, new.content, new.lens_name, new.lens_criterion, new.lens_page);
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
            kind=Kind(row["kind"]),
            content=row["content"],
            scope=Scope(kind=ScopeKind(row["scope_kind"]), key=row["scope_key"]),
            provenance=Provenance(row["provenance"]),
            status=Status(row["status"]),
            valid_from=row["valid_from"],
            invalid_at=row["invalid_at"],
            source_refs=[SourceRef.from_dict(d) for d in json.loads(row["source_refs"])],
            corroboration=row["corroboration"],
            last_relevant_at=row["last_relevant_at"],
            feedback=Feedback(row["feedback"]),
            lens_name=row["lens_name"],
            lens_criterion=row["lens_criterion"],
            lens_kind=row["lens_kind"],
            lens_page=row["lens_page"],
            lens_detail_level=(
                LensDetailLevel(row["lens_detail_level"]) if row["lens_detail_level"] else None
            ),
            lens_exclusive=bool(row["lens_exclusive"]),
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

    # --- writes ---

    async def create_item(self, item: MemoryItem, *, commit: bool = True) -> MemoryItem:
        await self.conn.execute(
            SQL_INSERT,
            (
                item.id,
                str(item.kind),
                item.content,
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
                item.lens_name,
                item.lens_criterion,
                item.lens_kind,
                item.lens_page,
                str(item.lens_detail_level) if item.lens_detail_level else None,
                1 if item.lens_exclusive else 0,
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

    # --- reads ---

    async def get(self, item_id: str) -> MemoryItem | None:
        rows = await self.conn.execute_fetchall(SQL_GET, (item_id,))
        return self._row_to_item(rows[0]) if rows else None

    async def query(
        self,
        *,
        kind: Kind | None = None,
        scope: Scope | None = None,
        status: Status | None = Status.ACTIVE,
        valid_at: str | None = None,
        limit: int = 100,
    ) -> list[MemoryItem]:
        """Query items by kind, scope, status, and an optional validity instant.

        `valid_at` (ISO-8601): keep items whose validity window contains it
        (valid_from <= valid_at and (invalid_at is null or invalid_at > valid_at)).
        `status=None` returns all statuses.
        """
        clauses: list[str] = []
        params: list = []
        if kind is not None:
            clauses.append("kind = ?")
            params.append(str(kind))
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
        """List edges touching an item.

        direction='from': edges where item is the child (its parents/provenance).
        direction='to': edges where item is the parent (its dependents/members).
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
        """FTS5 search over claim content and lens text.

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
