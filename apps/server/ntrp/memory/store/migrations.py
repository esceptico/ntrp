import aiosqlite

from ntrp.logging import get_logger

_logger = get_logger(__name__)

CURRENT_VERSION = 31


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

    if await _table_exists(conn, "observations"):
        await conn.execute("""
            INSERT OR IGNORE INTO observation_facts (observation_id, fact_id, role, created_at)
            SELECT o.id, f.id, 'support', COALESCE(o.created_at, CURRENT_TIMESTAMP)
            FROM observations o, json_each(o.source_fact_ids) source
            JOIN facts f ON f.id = CAST(source.value AS INTEGER)
            WHERE json_valid(o.source_fact_ids)
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


async def _migrate_v16(conn: aiosqlite.Connection) -> None:
    """Drop removed dream and continual-learning storage."""
    _logger.info("Migration v16: dropping dream and continual-learning tables")

    for table in (
        "learning_event_processing",
        "learning_candidate_events",
        "learning_candidates",
        "learning_events",
        "dream_facts",
        "dreams",
    ):
        await conn.execute(f"DROP TABLE IF EXISTS {table}")


async def _migrate_v17(conn: aiosqlite.Connection) -> None:
    """Drop removed profile storage."""
    _logger.info("Migration v17: dropping profile table")

    await conn.execute("DROP TABLE IF EXISTS profile_entries")


async def _migrate_v18(conn: aiosqlite.Connection) -> None:
    """Add explicit validity windows to facts."""
    _logger.info("Migration v18: adding fact validity windows")

    if not await _table_exists(conn, "facts"):
        return

    existing = {row["name"] for row in await conn.execute_fetchall("PRAGMA table_info(facts)")}
    if "valid_from" not in existing:
        await conn.execute("ALTER TABLE facts ADD COLUMN valid_from TIMESTAMP")
    if "valid_until" not in existing:
        await conn.execute("ALTER TABLE facts ADD COLUMN valid_until TIMESTAMP")

    existing = {row["name"] for row in await conn.execute_fetchall("PRAGMA table_info(facts)")}
    if {"valid_from", "created_at"}.issubset(existing):
        happened_expr = "happened_at" if "happened_at" in existing else "NULL"
        await conn.execute(f"""
            UPDATE facts
            SET valid_from = COALESCE(valid_from, {happened_expr}, created_at, CURRENT_TIMESTAMP)
        """)

    await conn.execute("CREATE INDEX IF NOT EXISTS idx_facts_valid_from ON facts(valid_from)")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_facts_valid_until ON facts(valid_until)")


async def _migrate_v19(conn: aiosqlite.Connection) -> None:
    """Add canonical knowledge object storage."""
    _logger.info("Migration v19: adding knowledge object storage")

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_objects (
            id INTEGER PRIMARY KEY,
            object_type TEXT NOT NULL,
            title TEXT NOT NULL,
            text TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            scope TEXT,
            activation TEXT NOT NULL DEFAULT 'prompt',
            proactiveness_level TEXT NOT NULL DEFAULT 'L0',
            score REAL NOT NULL DEFAULT 0.0,
            source_ids TEXT NOT NULL DEFAULT '[]',
            metadata TEXT NOT NULL DEFAULT '{}',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            reviewed_at TIMESTAMP,
            superseded_by_object_id INTEGER REFERENCES knowledge_objects(id) ON DELETE SET NULL,
            superseded_at TIMESTAMP,
            supersession_reason TEXT
        )
    """)
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_knowledge_objects_type_status ON knowledge_objects(object_type, status)"
    )
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_objects_updated ON knowledge_objects(updated_at DESC)")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_objects_scope ON knowledge_objects(scope)")
    columns = {row["name"] for row in await conn.execute_fetchall("PRAGMA table_info(knowledge_objects)")}
    if "superseded_by_object_id" in columns:
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_knowledge_objects_superseded ON knowledge_objects(superseded_by_object_id)"
        )


async def _create_knowledge_objects_fts(conn: aiosqlite.Connection) -> None:
    await conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_objects_fts USING fts5(
            title,
            text,
            content='knowledge_objects',
            content_rowid='id'
        )
    """)
    await conn.execute("""
        CREATE TRIGGER IF NOT EXISTS knowledge_objects_ai AFTER INSERT ON knowledge_objects BEGIN
            INSERT INTO knowledge_objects_fts(rowid, title, text) VALUES (new.id, new.title, new.text);
        END
    """)
    await conn.execute("""
        CREATE TRIGGER IF NOT EXISTS knowledge_objects_ad AFTER DELETE ON knowledge_objects BEGIN
            INSERT INTO knowledge_objects_fts(knowledge_objects_fts, rowid, title, text)
            VALUES('delete', old.id, old.title, old.text);
        END
    """)
    await conn.execute("""
        CREATE TRIGGER IF NOT EXISTS knowledge_objects_au AFTER UPDATE ON knowledge_objects BEGIN
            INSERT INTO knowledge_objects_fts(knowledge_objects_fts, rowid, title, text)
            VALUES('delete', old.id, old.title, old.text);
            INSERT INTO knowledge_objects_fts(rowid, title, text) VALUES (new.id, new.title, new.text);
        END
    """)
    await conn.execute("INSERT INTO knowledge_objects_fts(knowledge_objects_fts) VALUES('rebuild')")


async def _migrate_v20(conn: aiosqlite.Connection) -> None:
    """Migrate legacy fact/observation memory into knowledge objects."""
    _logger.info("Migration v20: migrating facts and observations to knowledge objects")

    await _migrate_v19(conn)

    if await _table_exists(conn, "facts"):
        existing = {row["name"] for row in await conn.execute_fetchall("PRAGMA table_info(facts)")}
        fact_defaults = {
            "archived_at": "TIMESTAMP",
            "superseded_by_fact_id": "INTEGER",
            "salience": "INTEGER NOT NULL DEFAULT 0",
            "lifetime": "TEXT NOT NULL DEFAULT 'durable'",
            "kind": "TEXT NOT NULL DEFAULT 'note'",
            "source_ref": "TEXT",
            "confidence": "REAL NOT NULL DEFAULT 1.0",
            "created_at": "TIMESTAMP",
            "last_accessed_at": "TIMESTAMP",
        }
        for column, definition in fact_defaults.items():
            if column not in existing:
                await conn.execute(f"ALTER TABLE facts ADD COLUMN {column} {definition}")
        await conn.execute("""
            INSERT INTO knowledge_objects (
                object_type, title, text, status, scope, activation, proactiveness_level,
                score, source_ids, metadata, created_at, updated_at, reviewed_at
            )
            SELECT
                'fact',
                'Fact ' || f.id,
                f.text,
                CASE
                    WHEN f.archived_at IS NOT NULL THEN 'archived'
                    WHEN f.superseded_by_fact_id IS NOT NULL THEN 'superseded'
                    ELSE 'active'
                END,
                f.kind,
                'prompt',
                'L0',
                COALESCE(f.salience, 0) * 0.2,
                json_array('legacy-fact:' || f.id),
                json_object(
                    'legacy_fact_id', f.id,
                    'kind', f.kind,
                    'lifetime', f.lifetime,
                    'source_type', f.source_type,
                    'source_ref', f.source_ref,
                    'confidence', f.confidence
                ),
                COALESCE(f.created_at, CURRENT_TIMESTAMP),
                COALESCE(f.last_accessed_at, f.created_at, CURRENT_TIMESTAMP),
                NULL
            FROM facts f
            WHERE NOT EXISTS (
                SELECT 1
                FROM knowledge_objects ko, json_each(ko.source_ids) source
                WHERE source.value = 'legacy-fact:' || f.id
            )
        """)

    if await _table_exists(conn, "observations"):
        existing = {row["name"] for row in await conn.execute_fetchall("PRAGMA table_info(observations)")}
        observation_defaults = {
            "archived_at": "TIMESTAMP",
            "created_by": "TEXT NOT NULL DEFAULT 'legacy'",
            "policy_version": "TEXT NOT NULL DEFAULT 'legacy'",
            "updated_at": "TIMESTAMP",
            "source_fact_ids": "TEXT DEFAULT '[]'",
            "created_at": "TIMESTAMP",
        }
        for column, definition in observation_defaults.items():
            if column not in existing:
                await conn.execute(f"ALTER TABLE observations ADD COLUMN {column} {definition}")
        await conn.execute("""
            INSERT INTO knowledge_objects (
                object_type, title, text, status, scope, activation, proactiveness_level,
                score, source_ids, metadata, created_at, updated_at, reviewed_at
            )
            SELECT
                'pattern',
                'Pattern ' || o.id,
                o.summary,
                CASE WHEN o.archived_at IS NOT NULL THEN 'archived' ELSE 'active' END,
                o.created_by,
                'prompt',
                'L0',
                MIN(COALESCE(json_array_length(o.source_fact_ids), 0) * 0.1, 1.0),
                json_array('legacy-observation:' || o.id),
                json_object(
                    'legacy_observation_id', o.id,
                    'source_fact_ids', json(o.source_fact_ids),
                    'created_by', o.created_by,
                    'policy_version', o.policy_version
                ),
                COALESCE(o.created_at, CURRENT_TIMESTAMP),
                COALESCE(o.updated_at, o.created_at, CURRENT_TIMESTAMP),
                NULL
            FROM observations o
            WHERE NOT EXISTS (
                SELECT 1
                FROM knowledge_objects ko, json_each(ko.source_ids) source
                WHERE source.value = 'legacy-observation:' || o.id
            )
        """)


async def _migrate_v21(conn: aiosqlite.Connection) -> None:
    """Add full-text search for canonical knowledge objects."""
    _logger.info("Migration v21: adding knowledge object full-text search")

    await _migrate_v19(conn)
    await _create_knowledge_objects_fts(conn)


async def _migrate_v22(conn: aiosqlite.Connection) -> None:
    """Add canonical knowledge object embedding storage."""
    _logger.info("Migration v22: adding knowledge object embeddings")

    await _migrate_v19(conn)
    columns = {row["name"] for row in await conn.execute_fetchall("PRAGMA table_info(knowledge_objects)")}
    if "embedding" not in columns:
        await conn.execute("ALTER TABLE knowledge_objects ADD COLUMN embedding BLOB")


async def _migrate_v23(conn: aiosqlite.Connection) -> None:
    """Add first-class knowledge object supersession fields."""
    _logger.info("Migration v23: adding knowledge object supersession fields")

    await _migrate_v19(conn)
    columns = {row["name"] for row in await conn.execute_fetchall("PRAGMA table_info(knowledge_objects)")}
    for name, definition in (
        ("superseded_by_object_id", "INTEGER REFERENCES knowledge_objects(id) ON DELETE SET NULL"),
        ("superseded_at", "TIMESTAMP"),
        ("supersession_reason", "TEXT"),
    ):
        if name not in columns:
            await conn.execute(f"ALTER TABLE knowledge_objects ADD COLUMN {name} {definition}")

    await conn.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_objects_superseded ON knowledge_objects(superseded_by_object_id)")
    await conn.execute("""
        UPDATE knowledge_objects
        SET
            superseded_by_object_id = COALESCE(
                superseded_by_object_id,
                CAST(json_extract(metadata, '$.superseded_by_object_id') AS INTEGER),
                CAST(json_extract(metadata, '$.superseded_by_id') AS INTEGER),
                CAST(json_extract(metadata, '$.replaced_by_object_id') AS INTEGER)
            ),
            superseded_at = COALESCE(
                superseded_at,
                json_extract(metadata, '$.superseded_at'),
                json_extract(metadata, '$.invalidated_at'),
                updated_at
            ),
            supersession_reason = COALESCE(
                supersession_reason,
                json_extract(metadata, '$.supersession_reason'),
                json_extract(metadata, '$.semantic_contradiction.reason'),
                json_extract(metadata, '$.supersession.reason')
            ),
            status = CASE
                WHEN status NOT IN ('archived', 'rejected', 'superseded') THEN 'superseded'
                ELSE status
            END
        WHERE
            superseded_by_object_id IS NOT NULL
            OR json_extract(metadata, '$.superseded_by_object_id') IS NOT NULL
            OR json_extract(metadata, '$.superseded_by_id') IS NOT NULL
            OR json_extract(metadata, '$.replaced_by_object_id') IS NOT NULL
    """)


async def _migrate_v24(conn: aiosqlite.Connection) -> None:
    """Add normalized entity refs for knowledge objects."""
    _logger.info("Migration v24: adding knowledge object entity refs")

    await _migrate_v19(conn)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS entities (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE COLLATE NOCASE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_entity_refs (
            knowledge_object_id INTEGER NOT NULL REFERENCES knowledge_objects(id) ON DELETE CASCADE,
            entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (knowledge_object_id, entity_id)
        )
    """)
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_entity_refs_entity ON knowledge_entity_refs(entity_id)")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_entity_refs_name ON knowledge_entity_refs(name)")

    await conn.execute("""
        INSERT OR IGNORE INTO entities (name, created_at, updated_at)
        SELECT DISTINCT value, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        FROM (
            SELECT e.value AS value
            FROM knowledge_objects ko, json_each(ko.metadata, '$.entities') e
            WHERE json_valid(ko.metadata) AND typeof(e.value) = 'text' AND length(trim(e.value)) > 0
            UNION
            SELECT e.value AS value
            FROM knowledge_objects ko, json_each(ko.metadata, '$.entity_graph.entities') e
            WHERE json_valid(ko.metadata) AND typeof(e.value) = 'text' AND length(trim(e.value)) > 0
        )
    """)
    await conn.execute("""
        INSERT OR IGNORE INTO knowledge_entity_refs (knowledge_object_id, entity_id, name, created_at)
        SELECT DISTINCT ko.id, ent.id, refs.name, CURRENT_TIMESTAMP
        FROM knowledge_objects ko
        JOIN (
            SELECT ko_inner.id AS knowledge_object_id, e.value AS name
            FROM knowledge_objects ko_inner, json_each(ko_inner.metadata, '$.entities') e
            WHERE json_valid(ko_inner.metadata) AND typeof(e.value) = 'text' AND length(trim(e.value)) > 0
            UNION
            SELECT ko_inner.id AS knowledge_object_id, e.value AS name
            FROM knowledge_objects ko_inner, json_each(ko_inner.metadata, '$.entity_graph.entities') e
            WHERE json_valid(ko_inner.metadata) AND typeof(e.value) = 'text' AND length(trim(e.value)) > 0
        ) refs ON refs.knowledge_object_id = ko.id
        JOIN entities ent ON ent.name = refs.name COLLATE NOCASE
    """)


async def _migrate_v25(conn: aiosqlite.Connection) -> None:
    """Add provenance-backed entity-resolution identity layer."""
    _logger.info("Migration v25: adding entity mentions, aliases, candidates, identity edges, and commits")

    entity_columns = {row["name"] for row in await conn.execute_fetchall("PRAGMA table_info(entities)")}
    for name, definition in (
        ("entity_type", "TEXT NOT NULL DEFAULT 'other'"),
        ("lifecycle_status", "TEXT NOT NULL DEFAULT 'active'"),
        ("merged_into_entity_id", "INTEGER REFERENCES entities(id) ON DELETE SET NULL"),
        ("metadata", "TEXT NOT NULL DEFAULT '{}'"),
    ):
        if name not in entity_columns:
            await conn.execute(f"ALTER TABLE entities ADD COLUMN {name} {definition}")

    await conn.execute("CREATE INDEX IF NOT EXISTS idx_entities_lifecycle ON entities(lifecycle_status)")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_entities_merged_into ON entities(merged_into_entity_id)")

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS entity_mentions (
            id INTEGER PRIMARY KEY,
            knowledge_object_id INTEGER NOT NULL REFERENCES knowledge_objects(id) ON DELETE CASCADE,
            entity_id INTEGER REFERENCES entities(id) ON DELETE SET NULL,
            surface_text TEXT NOT NULL,
            normalized_surface TEXT NOT NULL,
            canonical_name TEXT,
            entity_type_hint TEXT NOT NULL DEFAULT 'other',
            evidence_quote TEXT,
            extraction_confidence REAL NOT NULL DEFAULT 0.0,
            resolution_confidence REAL,
            resolution_status TEXT NOT NULL DEFAULT 'unresolved',
            extractor TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'extractor',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_entity_mentions_object ON entity_mentions(knowledge_object_id)")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_entity_mentions_entity ON entity_mentions(entity_id)")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_entity_mentions_surface ON entity_mentions(normalized_surface)")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_entity_mentions_status ON entity_mentions(resolution_status)")

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS entity_aliases (
            id INTEGER PRIMARY KEY,
            entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
            alias_text TEXT NOT NULL,
            normalized_alias TEXT NOT NULL,
            alias_type TEXT NOT NULL DEFAULT 'extracted',
            source_mention_id INTEGER REFERENCES entity_mentions(id) ON DELETE SET NULL,
            confidence REAL NOT NULL DEFAULT 0.0,
            scope TEXT,
            valid_from TIMESTAMP,
            valid_to TIMESTAMP,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_entity_aliases_lookup ON entity_aliases(normalized_alias, status)")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_entity_aliases_entity ON entity_aliases(entity_id)")

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS entity_resolution_candidates (
            id INTEGER PRIMARY KEY,
            mention_id INTEGER NOT NULL REFERENCES entity_mentions(id) ON DELETE CASCADE,
            candidate_entity_id INTEGER REFERENCES entities(id) ON DELETE SET NULL,
            method TEXT NOT NULL,
            score REAL NOT NULL DEFAULT 0.0,
            features TEXT NOT NULL DEFAULT '{}',
            rank INTEGER,
            decision_status TEXT NOT NULL DEFAULT 'proposed',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_entity_resolution_candidates_mention ON entity_resolution_candidates(mention_id)")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_entity_resolution_candidates_entity ON entity_resolution_candidates(candidate_entity_id)")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_entity_resolution_candidates_status ON entity_resolution_candidates(decision_status)")

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS entity_resolution_commits (
            id INTEGER PRIMARY KEY,
            action TEXT NOT NULL,
            actor TEXT NOT NULL DEFAULT 'system',
            before_entity_ids TEXT NOT NULL DEFAULT '[]',
            after_entity_ids TEXT NOT NULL DEFAULT '[]',
            evidence TEXT NOT NULL DEFAULT '{}',
            reversible_patch TEXT NOT NULL DEFAULT '{}',
            confidence REAL,
            rule_version TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_entity_resolution_commits_action ON entity_resolution_commits(action)")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_entity_resolution_commits_created ON entity_resolution_commits(created_at DESC)")

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS entity_identity_edges (
            id INTEGER PRIMARY KEY,
            entity_a_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
            entity_b_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
            relation TEXT NOT NULL,
            confidence REAL NOT NULL DEFAULT 0.0,
            evidence TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'active',
            commit_id INTEGER REFERENCES entity_resolution_commits(id) ON DELETE SET NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_entity_identity_edges_entities ON entity_identity_edges(entity_a_id, entity_b_id)")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_entity_identity_edges_relation ON entity_identity_edges(relation, status)")

    await conn.execute("""
        INSERT OR IGNORE INTO entity_aliases (entity_id, alias_text, normalized_alias, alias_type, confidence, status, created_at, updated_at)
        SELECT id, name, lower(name), 'canonical', 1.0, 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        FROM entities
    """)


async def _migrate_v26(conn: aiosqlite.Connection) -> None:
    """Archive legacy reflect spam and prune identifier-like entity junk."""
    _logger.info("Migration v26: archiving legacy reflect spam and pruning invalid entities")

    await conn.execute("""
        UPDATE knowledge_objects
        SET
            status = 'archived',
            metadata = json_set(
                CASE WHEN json_valid(metadata) THEN metadata ELSE '{}' END,
                '$.archived_reason', 'legacy_reflect_spam',
                '$.archived_by_migration', 'v26'
            ),
            updated_at = CURRENT_TIMESTAMP
        WHERE status NOT IN ('archived', 'rejected', 'superseded')
          AND json_valid(metadata)
          AND json_extract(metadata, '$.processor') = 'reflect'
          AND CAST(json_extract(metadata, '$.episode_id') AS INTEGER) IN (
              SELECT id FROM knowledge_objects WHERE object_type = 'episode'
          )
    """)

    await conn.execute("DROP TABLE IF EXISTS bad_entities_v26")
    await conn.execute("""
        CREATE TEMP TABLE bad_entities_v26 AS
        SELECT id
        FROM entities
        WHERE lower(name) LIKE 'knowledge:%'
           OR lower(name) LIKE 'session:%'
           OR lower(name) LIKE 'run:%'
           OR lower(name) LIKE 'turn:%'
           OR (name GLOB '*[0-9]*' AND lower(name) NOT GLOB '*[a-z]*')
           OR lower(name) GLOB '[0-9]* runs'
           OR lower(name) GLOB '[0-9]* run details'
           OR lower(name) GLOB '[0-9]* artifacts'
           OR lower(name) LIKE '% utc window'
    """)
    await conn.execute("DELETE FROM knowledge_entity_refs WHERE entity_id IN (SELECT id FROM bad_entities_v26)")
    await conn.execute("DELETE FROM entity_aliases WHERE entity_id IN (SELECT id FROM bad_entities_v26)")
    await conn.execute("""
        UPDATE entity_mentions
        SET entity_id = NULL, resolution_status = 'ignored'
        WHERE entity_id IN (SELECT id FROM bad_entities_v26)
    """)
    await conn.execute("DELETE FROM entity_resolution_candidates WHERE candidate_entity_id IN (SELECT id FROM bad_entities_v26)")
    await conn.execute("""
        DELETE FROM entity_identity_edges
        WHERE entity_a_id IN (SELECT id FROM bad_entities_v26)
           OR entity_b_id IN (SELECT id FROM bad_entities_v26)
    """)
    await conn.execute("DELETE FROM entities WHERE id IN (SELECT id FROM bad_entities_v26)")
    await conn.execute("DROP TABLE IF EXISTS bad_entities_v26")



async def _migrate_v27(conn: aiosqlite.Connection) -> None:
    """Expose source/provenance and metadata rows as queryable views."""
    _logger.info("Migration v27: adding knowledge source and metadata views")

    await conn.execute("DROP VIEW IF EXISTS knowledge_object_source_refs")
    await conn.execute("""
        CREATE VIEW knowledge_object_source_refs AS
        SELECT
            ko.id AS knowledge_object_id,
            'source_ids' AS source_field,
            CASE
                WHEN source.value LIKE 'knowledge:%' THEN 'knowledge'
                WHEN source.value LIKE 'run:%' THEN 'run'
                WHEN source.value LIKE 'turn:%' THEN 'turn'
                WHEN instr(source.value, ':') > 0 THEN substr(source.value, 1, instr(source.value, ':') - 1)
                ELSE 'external'
            END AS source_kind,
            source.value AS source_id,
            target.id AS source_object_id,
            target.object_type AS source_object_type,
            target.status AS source_status,
            target.title AS source_title,
            target.created_at AS source_created_at
        FROM knowledge_objects ko
        JOIN json_each(CASE WHEN json_valid(ko.source_ids) THEN ko.source_ids ELSE '[]' END) AS source
        LEFT JOIN knowledge_objects target ON source.value = 'knowledge:' || target.id
        WHERE source.value IS NOT NULL AND trim(source.value) <> ''

        UNION ALL

        SELECT
            ko.id AS knowledge_object_id,
            'metadata.source_episode_id' AS source_field,
            'knowledge' AS source_kind,
            'knowledge:' || json_extract(ko.metadata, '$.source_episode_id') AS source_id,
            target.id AS source_object_id,
            target.object_type AS source_object_type,
            target.status AS source_status,
            target.title AS source_title,
            target.created_at AS source_created_at
        FROM knowledge_objects ko
        LEFT JOIN knowledge_objects target ON target.id = CAST(json_extract(ko.metadata, '$.source_episode_id') AS INTEGER)
        WHERE json_valid(ko.metadata)
          AND json_extract(ko.metadata, '$.source_episode_id') IS NOT NULL

        UNION ALL

        SELECT
            ko.id AS knowledge_object_id,
            'metadata.source_run_ids' AS source_field,
            'run' AS source_kind,
            'run:' || run.value AS source_id,
            NULL AS source_object_id,
            NULL AS source_object_type,
            NULL AS source_status,
            NULL AS source_title,
            NULL AS source_created_at
        FROM knowledge_objects ko
        JOIN json_each(CASE WHEN json_valid(ko.metadata) THEN json_extract(ko.metadata, '$.source_run_ids') ELSE '[]' END) AS run
        WHERE run.value IS NOT NULL AND trim(run.value) <> ''

        UNION ALL

        SELECT
            ko.id AS knowledge_object_id,
            'metadata.source_turn_ids' AS source_field,
            'turn' AS source_kind,
            'turn:' || turn.value AS source_id,
            NULL AS source_object_id,
            NULL AS source_object_type,
            NULL AS source_status,
            NULL AS source_title,
            NULL AS source_created_at
        FROM knowledge_objects ko
        JOIN json_each(CASE WHEN json_valid(ko.metadata) THEN json_extract(ko.metadata, '$.source_turn_ids') ELSE '[]' END) AS turn
        WHERE turn.value IS NOT NULL AND trim(turn.value) <> ''
    """)

    await conn.execute("DROP VIEW IF EXISTS knowledge_object_metadata_entries")
    await conn.execute("""
        CREATE VIEW knowledge_object_metadata_entries AS
        SELECT
            ko.id AS knowledge_object_id,
            entry.key AS metadata_key,
            entry.type AS value_type,
            entry.value AS value
        FROM knowledge_objects ko
        JOIN json_each(CASE WHEN json_valid(ko.metadata) THEN ko.metadata ELSE '{}' END) AS entry
    """)



_KNOWLEDGE_ACTIVATION_ITEMS_VIEW_SQL = """
    CREATE VIEW knowledge_activation_items AS
    SELECT
        event.id AS access_event_id,
        event.created_at AS created_at,
        event.source AS source,
        event.query AS query,
        json_extract(event.details, '$.run_id') AS run_id,
        json_extract(event.details, '$.session_id') AS session_id,
        json_extract(event.details, '$.task_id') AS task_id,
        CAST(json_extract(item.value, '$.rank') AS INTEGER) AS rank,
        json_extract(item.value, '$.object_id') AS object_id,
        CAST(json_extract(item.value, '$.object_id') AS INTEGER) AS knowledge_object_id,
        json_extract(item.value, '$.object_type') AS object_type,
        CAST(json_extract(item.value, '$.score') AS REAL) AS score,
        CASE WHEN json_extract(item.value, '$.selected') THEN 1 ELSE 0 END AS selected,
        CASE WHEN json_extract(item.value, '$.injected') THEN 1 ELSE 0 END AS injected,
        CASE
            WHEN json_type(item.value, '$.used_by_model') IS NOT NULL
            THEN CASE WHEN json_extract(item.value, '$.used_by_model') THEN 1 ELSE 0 END
            ELSE CASE WHEN json_extract(item.value, '$.injected') THEN 1 ELSE 0 END
        END AS used_by_model,
        COALESCE(json_extract(item.value, '$.surface'), 'prompt') AS surface,
        COALESCE(
            json_extract(item.value, '$.selection_reason'),
            CASE
                WHEN json_extract(item.value, '$.injected') THEN 'selected_for_prompt'
                ELSE 'selected_not_injected'
            END
        ) AS selection_reason,
        json_extract(item.value, '$.activation') AS activation,
        json_extract(item.value, '$.proactiveness_level') AS proactiveness_level,
        json_extract(item.value, '$.chars') AS chars,
        json_extract(item.value, '$.reasons') AS reasons,
        json_extract(item.value, '$.signals') AS signals,
        json_extract(item.value, '$.source_ids') AS source_ids,
        ko.title AS object_title,
        ko.status AS object_status
    FROM memory_access_events event
    JOIN json_each(CASE
        WHEN json_valid(event.details) AND json_type(event.details, '$.candidates') = 'array'
        THEN json_extract(event.details, '$.candidates')
        ELSE '[]'
    END) AS item
    LEFT JOIN knowledge_objects ko ON ko.id = CAST(json_extract(item.value, '$.object_id') AS INTEGER)

    UNION ALL

    SELECT
        event.id AS access_event_id,
        event.created_at AS created_at,
        event.source AS source,
        event.query AS query,
        json_extract(event.details, '$.run_id') AS run_id,
        json_extract(event.details, '$.session_id') AS session_id,
        json_extract(event.details, '$.task_id') AS task_id,
        CAST(json_extract(omitted.value, '$.rank') AS INTEGER) AS rank,
        json_extract(omitted.value, '$.object_id') AS object_id,
        CAST(json_extract(omitted.value, '$.object_id') AS INTEGER) AS knowledge_object_id,
        json_extract(omitted.value, '$.object_type') AS object_type,
        CAST(json_extract(omitted.value, '$.score') AS REAL) AS score,
        0 AS selected,
        0 AS injected,
        CASE WHEN json_extract(omitted.value, '$.used_by_model') THEN 1 ELSE 0 END AS used_by_model,
        COALESCE(json_extract(omitted.value, '$.surface'), 'context') AS surface,
        COALESCE(
            json_extract(omitted.value, '$.selection_reason'),
            'omitted_by_budget_or_limit'
        ) AS selection_reason,
        json_extract(omitted.value, '$.activation') AS activation,
        json_extract(omitted.value, '$.proactiveness_level') AS proactiveness_level,
        json_extract(omitted.value, '$.chars') AS chars,
        json_extract(omitted.value, '$.reasons') AS reasons,
        json_extract(omitted.value, '$.signals') AS signals,
        json_extract(omitted.value, '$.source_ids') AS source_ids,
        ko.title AS object_title,
        ko.status AS object_status
    FROM memory_access_events event
    JOIN json_each(CASE
        WHEN json_valid(event.details) AND json_type(event.details, '$.omitted') = 'array'
        THEN json_extract(event.details, '$.omitted')
        ELSE '[]'
    END) AS omitted
    LEFT JOIN knowledge_objects ko ON ko.id = CAST(json_extract(omitted.value, '$.object_id') AS INTEGER)

    UNION ALL

    SELECT
        event.id AS access_event_id,
        event.created_at AS created_at,
        event.source AS source,
        event.query AS query,
        json_extract(event.details, '$.run_id') AS run_id,
        json_extract(event.details, '$.session_id') AS session_id,
        json_extract(event.details, '$.task_id') AS task_id,
        NULL AS rank,
        fallback.value AS object_id,
        CAST(fallback.value AS INTEGER) AS knowledge_object_id,
        json_extract(event.details, '$.candidate_types[0]') AS object_type,
        NULL AS score,
        1 AS selected,
        CASE WHEN json_extract(event.details, '$.injected') THEN 1 ELSE 0 END AS injected,
        CASE WHEN json_extract(event.details, '$.injected') THEN 1 ELSE 0 END AS used_by_model,
        'prompt' AS surface,
        'legacy_candidate_id' AS selection_reason,
        NULL AS activation,
        NULL AS proactiveness_level,
        NULL AS chars,
        NULL AS reasons,
        NULL AS signals,
        NULL AS source_ids,
        ko.title AS object_title,
        ko.status AS object_status
    FROM memory_access_events event
    JOIN json_each(CASE
        WHEN json_valid(event.details)
         AND json_type(event.details, '$.candidates') IS NULL
         AND json_type(event.details, '$.candidate_ids') = 'array'
        THEN json_extract(event.details, '$.candidate_ids')
        ELSE '[]'
    END) AS fallback
    LEFT JOIN knowledge_objects ko ON ko.id = CAST(fallback.value AS INTEGER)
"""


async def _recreate_knowledge_activation_items_view(conn: aiosqlite.Connection) -> None:
    await conn.execute("DROP VIEW IF EXISTS knowledge_activation_items")
    await conn.execute(_KNOWLEDGE_ACTIVATION_ITEMS_VIEW_SQL)


async def _migrate_v28(conn: aiosqlite.Connection) -> None:
    """Move activation telemetry out of active knowledge and expose activation item traces."""
    _logger.info("Migration v28: archiving legacy activation telemetry and adding activation item view")

    await conn.execute("""
        UPDATE knowledge_objects
        SET
            status = 'archived',
            metadata = json_set(
                CASE WHEN json_valid(metadata) THEN metadata ELSE '{}' END,
                '$.archived_reason', 'activation_access_telemetry',
                '$.archived_by_migration', 'v28'
            ),
            updated_at = CURRENT_TIMESTAMP
        WHERE object_type = 'outcome_feedback'
          AND status NOT IN ('archived', 'rejected', 'superseded')
          AND json_valid(metadata)
          AND json_extract(metadata, '$.kind') = 'activation_access'
    """)

    await _recreate_knowledge_activation_items_view(conn)


async def _migrate_v29(conn: aiosqlite.Connection) -> None:
    """Expose closed-loop usage fields in activation item traces."""
    _logger.info("Migration v29: adding closed-loop usage fields to activation item view")
    await _recreate_knowledge_activation_items_view(conn)


async def _migrate_v30(conn: aiosqlite.Connection) -> None:
    """Expose run/session/task identifiers in activation item traces."""
    _logger.info("Migration v30: adding context identifiers to activation item view")
    await _recreate_knowledge_activation_items_view(conn)


async def _migrate_v31(conn: aiosqlite.Connection) -> None:
    """Burn pre-v31 memory storage and create the redesigned primitive schema."""
    _logger.info(
        "Migration v31: memory redesign — burn old tables, create memory_items + memory_item_parents + episode_buffers"
    )
    _logger.warning(
        "Migration v31: dropping all pre-v31 memory tables (knowledge_objects, facts, observations, entities, …). "
        "This is the memory redesign burn step. Pre-v31 data is unrecoverable from this DB; restore from backup if needed."
    )
    foreign_key_rows = await conn.execute_fetchall("PRAGMA foreign_keys")
    restore_foreign_keys = bool(foreign_key_rows and foreign_key_rows[0][0])
    if restore_foreign_keys:
        await conn.execute("PRAGMA foreign_keys=OFF")

    for trigger in (
        "observations_ai",
        "observations_ad",
        "observations_au",
        "facts_ai",
        "facts_ad",
        "facts_au",
        "knowledge_objects_ai",
        "knowledge_objects_ad",
        "knowledge_objects_au",
    ):
        await conn.execute(f"DROP TRIGGER IF EXISTS {trigger}")

    for table in ("observations_fts", "facts_fts", "knowledge_objects_fts"):
        await conn.execute(f"DROP TABLE IF EXISTS {table}")

    for table in ("observations_vec", "facts_vec", "knowledge_objects_vec"):
        await conn.execute(f"DROP TABLE IF EXISTS {table}")

    for table in ("facts", "observations", "knowledge_objects"):
        await conn.execute(f"DROP TABLE IF EXISTS {table}")

    for table in (
        "entities",
        "entity_aliases",
        "entity_identity_edges",
        "entity_mentions",
        "entity_refs",
        "entity_resolution_candidates",
        "entity_resolution_commits",
        "obs_entity_refs",
        "observation_facts",
        "knowledge_entity_refs",
    ):
        await conn.execute(f"DROP TABLE IF EXISTS {table}")

    for table in ("memory_access_events", "memory_events", "temporal_checkpoints"):
        await conn.execute(f"DROP TABLE IF EXISTS {table}")

    if restore_foreign_keys:
        await conn.execute("PRAGMA foreign_keys=ON")

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS memory_items (
            id              TEXT PRIMARY KEY,
            kind            TEXT NOT NULL CHECK (kind IN (
                                'episode', 'observation', 'claim',
                                'skill', 'proposal', 'artifact_ref'
                            )),
            content         TEXT NOT NULL,
            provenance      TEXT NOT NULL CHECK (provenance IN (
                                'recorded', 'inferred', 'user_authored', 'external'
                            )),
            source_refs     TEXT NOT NULL DEFAULT '[]',
            confidence      REAL NOT NULL DEFAULT 0.5 CHECK (
                                confidence >= 0.0 AND confidence <= 1.0
                            ),
            status          TEXT NOT NULL DEFAULT 'active' CHECK (status IN (
                                'active', 'superseded', 'archived'
                            )),
            valid_from      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            invalid_at      TIMESTAMP,
            scope           TEXT NOT NULL DEFAULT 'user',
            tags            TEXT NOT NULL DEFAULT '[]',
            artifact_ref    TEXT,
            usage           TEXT NOT NULL DEFAULT '{"activated":0,"helped":0,"hurt":0,"ignored":0}',
            feedback        TEXT NOT NULL DEFAULT '{"thumbs_up":0,"thumbs_down":0,"corrections":0}',
            created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_memory_items_status_scope_kind ON memory_items(status, scope, kind)"
    )
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_items_valid_from ON memory_items(valid_from)")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_items_invalid_at ON memory_items(invalid_at)")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_items_updated_at ON memory_items(updated_at)")

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS memory_item_parents (
            child_id    TEXT NOT NULL REFERENCES memory_items(id) ON DELETE CASCADE,
            parent_id   TEXT NOT NULL REFERENCES memory_items(id) ON DELETE CASCADE,
            role        TEXT NOT NULL CHECK (role IN (
                            'step', 'evidence', 'contradicts',
                            'supersedes', 'similar_to'
                        )),
            "order"     INTEGER,
            created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (child_id, parent_id, role)
        )
    """)
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_mip_child ON memory_item_parents(child_id)")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_mip_parent ON memory_item_parents(parent_id)")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_mip_role ON memory_item_parents(role)")

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS episode_buffers (
            id                      TEXT PRIMARY KEY,
            scope                   TEXT NOT NULL,
            source_kind             TEXT NOT NULL,
            started_at              TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_activity_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            turn_count              INTEGER NOT NULL DEFAULT 0,
            tokens                  INTEGER NOT NULL DEFAULT 0,
            content_so_far          TEXT NOT NULL DEFAULT '',
            source_refs_so_far      TEXT NOT NULL DEFAULT '[]',
            running_centroid_vec    BLOB,
            closed_at               TIMESTAMP
        )
    """)
    await conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uniq_episode_buffers_open_per_scope
            ON episode_buffers(scope, source_kind)
            WHERE closed_at IS NULL
    """)
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_episode_buffers_last_activity ON episode_buffers(last_activity_at)"
    )

    await conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS memory_items_fts USING fts5(
            item_id UNINDEXED,
            content,
            tokenize = 'unicode61 remove_diacritics 2'
        )
    """)
    await conn.execute("""
        CREATE TRIGGER IF NOT EXISTS memory_items_ai AFTER INSERT ON memory_items BEGIN
            INSERT INTO memory_items_fts(item_id, content) VALUES (new.id, new.content);
        END
    """)
    await conn.execute("""
        CREATE TRIGGER IF NOT EXISTS memory_items_ad AFTER DELETE ON memory_items BEGIN
            DELETE FROM memory_items_fts WHERE item_id = old.id;
        END
    """)
    await conn.execute("""
        CREATE TRIGGER IF NOT EXISTS memory_items_au AFTER UPDATE ON memory_items BEGIN
            DELETE FROM memory_items_fts WHERE item_id = old.id;
            INSERT INTO memory_items_fts(item_id, content) VALUES (new.id, new.content);
        END
    """)


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
    (13, _migrate_v13),
    (16, _migrate_v16),
    (17, _migrate_v17),
    (18, _migrate_v18),
    (19, _migrate_v19),
    (20, _migrate_v20),
    (21, _migrate_v21),
    (22, _migrate_v22),
    (23, _migrate_v23),
    (24, _migrate_v24),
    (25, _migrate_v25),
    (26, _migrate_v26),
    (27, _migrate_v27),
    (28, _migrate_v28),
    (29, _migrate_v29),
    (30, _migrate_v30),
    (31, _migrate_v31),
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

    # Do not VACUUM automatically during app startup. On real user DBs this can
    # take minutes and block the server after an otherwise quick metadata-only
    # migration. Maintenance can run VACUUM explicitly when needed.
    await conn.execute("PRAGMA optimize")
    await conn.commit()
    _logger.info("Memory schema up to date (v%d)", CURRENT_VERSION)
