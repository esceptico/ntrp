import aiosqlite

from ntrp.logging import get_logger

_logger = get_logger(__name__)

CURRENT_VERSION = 15


async def _get_version(conn: aiosqlite.Connection) -> int:
    try:
        rows = await conn.execute_fetchall("SELECT value FROM meta WHERE key = 'schema_version'")
        return int(rows[0][0]) if rows else 0
    except Exception:
        return 0


async def _set_version(conn: aiosqlite.Connection, version: int) -> None:
    await conn.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', ?)",
        (str(version),),
    )


async def _table_exists(conn: aiosqlite.Connection, table: str) -> bool:
    rows = await conn.execute_fetchall(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    )
    return bool(rows)


async def _migrate_v1(conn: aiosqlite.Connection) -> None:
    """Enable foreign keys + recreate entity_refs with ON DELETE CASCADE."""
    _logger.info("Migration v1: adding ON DELETE CASCADE to entity_refs")

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS entity_refs_new (
            id INTEGER PRIMARY KEY,
            fact_id INTEGER REFERENCES facts(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            entity_id INTEGER REFERENCES entities(id) ON DELETE SET NULL
        )
    """)
    await conn.execute("INSERT INTO entity_refs_new SELECT * FROM entity_refs")
    await conn.execute("DROP TABLE entity_refs")
    await conn.execute("ALTER TABLE entity_refs_new RENAME TO entity_refs")

    await conn.execute("CREATE INDEX IF NOT EXISTS idx_entity_refs_fact ON entity_refs(fact_id)")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_entity_refs_name ON entity_refs(name)")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_entity_refs_entity ON entity_refs(entity_id)")


async def _migrate_v2(conn: aiosqlite.Connection) -> None:
    """Drop evidence_count column (redundant with len(source_fact_ids))."""
    _logger.info("Migration v2: dropping evidence_count from observations")

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS observations_new (
            id INTEGER PRIMARY KEY,
            summary TEXT NOT NULL,
            embedding BLOB,
            source_fact_ids TEXT DEFAULT '[]',
            history TEXT DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            access_count INTEGER DEFAULT 0
        )
    """)
    await conn.execute("""
        INSERT INTO observations_new (id, summary, embedding, source_fact_ids, history,
            created_at, updated_at, last_accessed_at, access_count)
        SELECT id, summary, embedding, source_fact_ids, history,
            created_at, updated_at, last_accessed_at, access_count
        FROM observations
    """)

    # Preserve FTS and vec data by dropping triggers first, then swapping
    await conn.execute("DROP TRIGGER IF EXISTS observations_ai")
    await conn.execute("DROP TRIGGER IF EXISTS observations_ad")
    await conn.execute("DROP TRIGGER IF EXISTS observations_au")

    await conn.execute("DROP TABLE observations")
    await conn.execute("ALTER TABLE observations_new RENAME TO observations")

    # Recreate triggers
    await conn.execute("""
        CREATE TRIGGER IF NOT EXISTS observations_ai AFTER INSERT ON observations BEGIN
            INSERT INTO observations_fts(rowid, summary) VALUES (new.id, new.summary);
        END
    """)
    await conn.execute("""
        CREATE TRIGGER IF NOT EXISTS observations_ad AFTER DELETE ON observations BEGIN
            INSERT INTO observations_fts(observations_fts, rowid, summary) VALUES('delete', old.id, old.summary);
        END
    """)
    await conn.execute("""
        CREATE TRIGGER IF NOT EXISTS observations_au AFTER UPDATE ON observations BEGIN
            INSERT INTO observations_fts(observations_fts, rowid, summary) VALUES('delete', old.id, old.summary);
            INSERT INTO observations_fts(rowid, summary) VALUES (new.id, new.summary);
        END
    """)


async def _migrate_v3(conn: aiosqlite.Connection) -> None:
    """Add archived_at column to facts and observations for memory archival."""
    _logger.info("Migration v3: adding archived_at to facts and observations")

    for table in ("facts", "observations"):
        try:
            await conn.execute(f"ALTER TABLE {table} ADD COLUMN archived_at TIMESTAMP")
        except aiosqlite.OperationalError:
            pass  # Column already exists (fresh install)
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_facts_archived ON facts(archived_at)")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_observations_archived ON observations(archived_at)")


async def _migrate_v4(conn: aiosqlite.Connection) -> None:
    """Add ON DELETE CASCADE to obs_entity_refs for entity_id."""
    _logger.info("Migration v4: adding ON DELETE CASCADE to obs_entity_refs")

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS obs_entity_refs_new (
            observation_id INTEGER REFERENCES observations(id) ON DELETE CASCADE,
            entity_id INTEGER REFERENCES entities(id) ON DELETE CASCADE,
            PRIMARY KEY (observation_id, entity_id)
        )
    """)
    await conn.execute("INSERT OR IGNORE INTO obs_entity_refs_new SELECT * FROM obs_entity_refs")
    await conn.execute("DROP TABLE obs_entity_refs")
    await conn.execute("ALTER TABLE obs_entity_refs_new RENAME TO obs_entity_refs")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_obs_entity_refs_entity ON obs_entity_refs(entity_id)")


async def _migrate_v5(conn: aiosqlite.Connection) -> None:
    """Add typed fact metadata."""
    _logger.info("Migration v5: adding typed fact metadata")

    existing = {row["name"] for row in await conn.execute_fetchall("PRAGMA table_info(facts)")}
    columns = (
        ("kind", "TEXT NOT NULL DEFAULT 'note'"),
        ("salience", "INTEGER NOT NULL DEFAULT 0"),
        ("confidence", "REAL NOT NULL DEFAULT 1.0"),
        ("expires_at", "TIMESTAMP"),
        ("pinned_at", "TIMESTAMP"),
        ("superseded_by_fact_id", "INTEGER REFERENCES facts(id) ON DELETE SET NULL"),
    )
    for name, definition in columns:
        if name not in existing:
            await conn.execute(f"ALTER TABLE facts ADD COLUMN {name} {definition}")

    await conn.execute("CREATE INDEX IF NOT EXISTS idx_facts_kind ON facts(kind)")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_facts_expires ON facts(expires_at)")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_facts_superseded ON facts(superseded_by_fact_id)")


async def _migrate_v6(conn: aiosqlite.Connection) -> None:
    """Add relation-table provenance for generated memory."""
    _logger.info("Migration v6: adding generated memory provenance tables")

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS observation_facts (
            observation_id INTEGER NOT NULL REFERENCES observations(id) ON DELETE CASCADE,
            fact_id INTEGER NOT NULL REFERENCES facts(id) ON DELETE CASCADE,
            role TEXT NOT NULL DEFAULT 'support',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (observation_id, fact_id)
        )
    """)
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_observation_facts_fact ON observation_facts(fact_id)")

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS dream_facts (
            dream_id INTEGER NOT NULL REFERENCES dreams(id) ON DELETE CASCADE,
            fact_id INTEGER NOT NULL REFERENCES facts(id) ON DELETE CASCADE,
            role TEXT NOT NULL DEFAULT 'support',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (dream_id, fact_id)
        )
    """)
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_dream_facts_fact ON dream_facts(fact_id)")

    if await _table_exists(conn, "observations"):
        await conn.execute("""
            INSERT OR IGNORE INTO observation_facts (observation_id, fact_id, role, created_at)
            SELECT o.id, f.id, 'support', COALESCE(o.created_at, CURRENT_TIMESTAMP)
            FROM observations o, json_each(o.source_fact_ids) source
            JOIN facts f ON f.id = CAST(source.value AS INTEGER)
            WHERE json_valid(o.source_fact_ids)
        """)

    if await _table_exists(conn, "dreams"):
        await conn.execute("""
            INSERT OR IGNORE INTO dream_facts (dream_id, fact_id, role, created_at)
            SELECT d.id, f.id, 'support', COALESCE(d.created_at, CURRENT_TIMESTAMP)
            FROM dreams d, json_each(d.source_fact_ids) source
            JOIN facts f ON f.id = CAST(source.value AS INTEGER)
            WHERE json_valid(d.source_fact_ids)
        """)


async def _migrate_v7(conn: aiosqlite.Connection) -> None:
    """Add memory event log for provenance and automation audit."""
    _logger.info("Migration v7: adding memory event log")

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS memory_events (
            id INTEGER PRIMARY KEY,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            actor TEXT NOT NULL,
            action TEXT NOT NULL,
            target_type TEXT NOT NULL,
            target_id INTEGER,
            source_type TEXT,
            source_ref TEXT,
            reason TEXT,
            policy_version TEXT NOT NULL,
            details TEXT NOT NULL DEFAULT '{}'
        )
    """)
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_events_created ON memory_events(created_at DESC)")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_events_target ON memory_events(target_type, target_id)")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_events_action ON memory_events(action)")


async def _migrate_v8(conn: aiosqlite.Connection) -> None:
    """Add lightweight observation policy metadata."""
    _logger.info("Migration v8: adding observation policy metadata")

    if not await _table_exists(conn, "observations"):
        return

    existing = {row["name"] for row in await conn.execute_fetchall("PRAGMA table_info(observations)")}
    columns = (
        ("created_by", "TEXT NOT NULL DEFAULT 'legacy'"),
        ("policy_version", "TEXT NOT NULL DEFAULT 'legacy'"),
    )
    for name, definition in columns:
        if name not in existing:
            await conn.execute(f"ALTER TABLE observations ADD COLUMN {name} {definition}")

    await conn.execute("CREATE INDEX IF NOT EXISTS idx_observations_policy ON observations(policy_version)")


async def _migrate_v9(conn: aiosqlite.Connection) -> None:
    """Add model-facing memory access telemetry."""
    _logger.info("Migration v9: adding memory access telemetry")

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS memory_access_events (
            id INTEGER PRIMARY KEY,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            source TEXT NOT NULL,
            query TEXT,
            retrieved_fact_ids TEXT NOT NULL DEFAULT '[]',
            retrieved_observation_ids TEXT NOT NULL DEFAULT '[]',
            injected_fact_ids TEXT NOT NULL DEFAULT '[]',
            injected_observation_ids TEXT NOT NULL DEFAULT '[]',
            omitted_fact_ids TEXT NOT NULL DEFAULT '[]',
            omitted_observation_ids TEXT NOT NULL DEFAULT '[]',
            bundled_fact_ids TEXT NOT NULL DEFAULT '[]',
            formatted_chars INTEGER NOT NULL DEFAULT 0,
            policy_version TEXT NOT NULL,
            details TEXT NOT NULL DEFAULT '{}'
        )
    """)
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_memory_access_events_created ON memory_access_events(created_at DESC)"
    )
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_access_events_source ON memory_access_events(source)")


async def _migrate_v10(conn: aiosqlite.Connection) -> None:
    """Add continuous-learning event and candidate logs."""
    _logger.info("Migration v10: adding continuous-learning tables")

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS learning_events (
            id INTEGER PRIMARY KEY,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            source_type TEXT NOT NULL,
            source_id TEXT,
            scope TEXT NOT NULL,
            signal TEXT NOT NULL,
            evidence_ids TEXT NOT NULL DEFAULT '[]',
            outcome TEXT NOT NULL DEFAULT 'unknown',
            details TEXT NOT NULL DEFAULT '{}'
        )
    """)
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_learning_events_created ON learning_events(created_at DESC)")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_learning_events_scope ON learning_events(scope)")
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_learning_events_source ON learning_events(source_type, source_id)"
    )

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS learning_candidates (
            id INTEGER PRIMARY KEY,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            status TEXT NOT NULL DEFAULT 'proposed',
            change_type TEXT NOT NULL,
            target_key TEXT NOT NULL,
            proposal TEXT NOT NULL,
            rationale TEXT NOT NULL,
            evidence_event_ids TEXT NOT NULL DEFAULT '[]',
            expected_metric TEXT,
            policy_version TEXT NOT NULL,
            applied_at TIMESTAMP,
            reverted_at TIMESTAMP,
            details TEXT NOT NULL DEFAULT '{}'
        )
    """)
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_learning_candidates_status ON learning_candidates(status)")
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_learning_candidates_change_type ON learning_candidates(change_type)"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_learning_candidates_created ON learning_candidates(created_at DESC)"
    )


async def _migrate_v11(conn: aiosqlite.Connection) -> None:
    """Add durable learning event processing state."""
    _logger.info("Migration v11: adding learning event processing table")

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS learning_event_processing (
            scanner TEXT NOT NULL,
            event_id INTEGER NOT NULL REFERENCES learning_events(id) ON DELETE CASCADE,
            candidate_id INTEGER REFERENCES learning_candidates(id) ON DELETE SET NULL,
            decision TEXT NOT NULL,
            processed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (scanner, event_id)
        )
    """)
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_learning_event_processing_event ON learning_event_processing(event_id)"
    )

    await conn.execute("""
        INSERT OR IGNORE INTO learning_event_processing (scanner, event_id, candidate_id, decision, processed_at)
        SELECT
            CASE learning_candidates.change_type
                WHEN 'skill_note' THEN 'skill_note'
                WHEN 'memory_feedback' THEN 'memory_feedback'
            END,
            CAST(event_id.value AS INTEGER),
            learning_candidates.id,
            'backfilled',
            COALESCE(learning_candidates.updated_at, CURRENT_TIMESTAMP)
        FROM learning_candidates, json_each(learning_candidates.evidence_event_ids) AS event_id
        WHERE json_valid(learning_candidates.evidence_event_ids)
          AND learning_candidates.change_type IN ('skill_note', 'memory_feedback')
    """)


async def _migrate_v12(conn: aiosqlite.Connection) -> None:
    """Add relational provenance edges for learning candidates."""
    _logger.info("Migration v12: adding learning candidate event links")

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS learning_candidate_events (
            candidate_id INTEGER NOT NULL REFERENCES learning_candidates(id) ON DELETE CASCADE,
            event_id INTEGER NOT NULL REFERENCES learning_events(id) ON DELETE CASCADE,
            PRIMARY KEY (candidate_id, event_id)
        )
    """)
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_learning_candidate_events_event ON learning_candidate_events(event_id)"
    )
    await conn.execute("""
        INSERT OR IGNORE INTO learning_candidate_events (candidate_id, event_id)
        SELECT learning_candidates.id, CAST(event_id.value AS INTEGER)
        FROM learning_candidates, json_each(learning_candidates.evidence_event_ids) AS event_id
        WHERE json_valid(learning_candidates.evidence_event_ids)
    """)


async def _migrate_v13(conn: aiosqlite.Connection) -> None:
    """Add explicit fact lifetime metadata."""
    _logger.info("Migration v13: adding fact lifetime")

    if not await _table_exists(conn, "facts"):
        return

    existing = {row["name"] for row in await conn.execute_fetchall("PRAGMA table_info(facts)")}
    if "lifetime" not in existing:
        await conn.execute("ALTER TABLE facts ADD COLUMN lifetime TEXT NOT NULL DEFAULT 'durable'")

    existing = {row["name"] for row in await conn.execute_fetchall("PRAGMA table_info(facts)")}
    if "expires_at" in existing:
        await conn.execute("""
            UPDATE facts
            SET lifetime = 'temporary'
            WHERE expires_at IS NOT NULL
        """)
    if "kind" in existing:
        await conn.execute("""
            UPDATE facts
            SET kind = 'note'
            WHERE kind = 'temporary'
        """)
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_facts_lifetime ON facts(lifetime)")


async def _migrate_v14(conn: aiosqlite.Connection) -> None:
    """Close deprecated profile-learning candidates."""
    _logger.info("Migration v14: closing deprecated profile learning candidates")

    if not await _table_exists(conn, "learning_candidates"):
        return

    await conn.execute("""
        UPDATE learning_candidates
        SET status = 'rejected',
            updated_at = CURRENT_TIMESTAMP
        WHERE status IN ('proposed', 'approved')
          AND (
            change_type IN ('profile_rule', 'supersession_review')
            OR target_key LIKE 'memory.profile.%'
            OR target_key = 'memory.facts.supersession.profile'
          )
    """)


async def _migrate_v15(conn: aiosqlite.Connection) -> None:
    """Add explicit curated profile entries."""
    _logger.info("Migration v15: adding curated profile entries")

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS profile_entries (
            id INTEGER PRIMARY KEY,
            kind TEXT NOT NULL,
            summary TEXT NOT NULL,
            source_fact_ids TEXT NOT NULL DEFAULT '[]',
            source_observation_ids TEXT NOT NULL DEFAULT '[]',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            archived_at TIMESTAMP,
            created_by TEXT NOT NULL DEFAULT 'manual',
            policy_version TEXT NOT NULL DEFAULT 'manual',
            confidence REAL NOT NULL DEFAULT 1.0
        )
    """)
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_profile_entries_active ON profile_entries(archived_at, updated_at DESC)")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_profile_entries_kind ON profile_entries(kind)")


_MIGRATIONS: list[tuple[int, callable]] = [
    (1, _migrate_v1),
    (2, _migrate_v2),
    (3, _migrate_v3),
    (4, _migrate_v4),
    (5, _migrate_v5),
    (6, _migrate_v6),
    (7, _migrate_v7),
    (8, _migrate_v8),
    (9, _migrate_v9),
    (10, _migrate_v10),
    (11, _migrate_v11),
    (12, _migrate_v12),
    (13, _migrate_v13),
    (14, _migrate_v14),
    (15, _migrate_v15),
]


async def run_migrations(conn: aiosqlite.Connection) -> None:
    current = await _get_version(conn)
    if current >= CURRENT_VERSION:
        return

    for version, migrate_fn in _MIGRATIONS:
        if version <= current:
            continue
        _logger.info("Running memory schema migration v%d", version)
        await migrate_fn(conn)
        await _set_version(conn, version)
        await conn.commit()

    _logger.info("Vacuuming database after migrations")
    await conn.execute("VACUUM")
    await conn.commit()
    _logger.info("Memory schema up to date (v%d)", CURRENT_VERSION)
