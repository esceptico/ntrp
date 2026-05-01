from datetime import UTC, datetime, timedelta
from typing import Any

import aiosqlite

DEFAULT_PRUNE_OLDER_THAN_DAYS = 30
DEFAULT_PRUNE_MAX_SOURCES = 5
DEFAULT_PRUNE_LIMIT = 100


def _dict(row: aiosqlite.Row) -> dict[str, Any]:
    return dict(row)


async def _one(conn: aiosqlite.Connection, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any]:
    rows = await conn.execute_fetchall(sql, params)
    return _dict(rows[0]) if rows else {}


async def _all(conn: aiosqlite.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    rows = await conn.execute_fetchall(sql, params)
    return [_dict(row) for row in rows]


async def _source_provenance(
    conn: aiosqlite.Connection,
    table: str,
    active_filter: str = "1 = 1",
    relation_table: str | None = None,
    relation_id_column: str | None = None,
) -> dict[str, Any]:
    result = await _one(
        conn,
        f"""
        WITH records AS (
            SELECT id, source_fact_ids
            FROM {table}
            WHERE {active_filter}
        ),
        refs AS (
            SELECT
                records.id AS record_id,
                CAST(json_each.value AS INTEGER) AS fact_id
            FROM records, json_each(records.source_fact_ids)
        ),
        joined AS (
            SELECT
                refs.record_id,
                refs.fact_id,
                facts.id AS matched_id,
                facts.archived_at
            FROM refs
            LEFT JOIN facts ON facts.id = refs.fact_id
        ),
        duplicate_refs AS (
            SELECT record_id, fact_id, COUNT(*) AS ref_count
            FROM refs
            GROUP BY record_id, fact_id
            HAVING ref_count > 1
        )
        SELECT
            (SELECT COUNT(*) FROM records) AS records,
            (
                SELECT COALESCE(SUM(COALESCE(json_array_length(source_fact_ids), 0) = 0), 0)
                FROM records
            ) AS records_without_sources,
            (SELECT COUNT(*) FROM refs) AS source_refs,
            (
                SELECT COALESCE(SUM(ref_count - 1), 0)
                FROM duplicate_refs
            ) AS duplicate_source_refs,
            (
                SELECT COUNT(*)
                FROM joined
                WHERE matched_id IS NULL
            ) AS missing_source_refs,
            (
                SELECT COUNT(DISTINCT record_id)
                FROM joined
                WHERE matched_id IS NULL
            ) AS records_with_missing_sources,
            (
                SELECT COUNT(*)
                FROM joined
                WHERE matched_id IS NOT NULL AND archived_at IS NOT NULL
            ) AS archived_source_refs,
            (
                SELECT COUNT(DISTINCT record_id)
                FROM joined
                WHERE matched_id IS NOT NULL AND archived_at IS NOT NULL
            ) AS records_with_archived_sources
        """,
    )
    if relation_table and relation_id_column:
        relation_refs = await _one(
            conn,
            f"""
            SELECT COUNT(*) AS relation_refs
            FROM {relation_table} rel
            JOIN {table} records ON records.id = rel.{relation_id_column}
            WHERE {active_filter}
            """,
        )
        result.update(relation_refs)
    return result


async def memory_audit(conn: aiosqlite.Connection) -> dict[str, Any]:
    """Read-only health snapshot for the memory database."""

    facts = await _one(
        conn,
        """
        SELECT
            COUNT(*) AS total,
            COALESCE(SUM(archived_at IS NULL), 0) AS active,
            COALESCE(SUM(archived_at IS NOT NULL), 0) AS archived,
            COALESCE(SUM(archived_at IS NULL AND consolidated_at IS NULL), 0) AS unconsolidated,
            COALESCE(SUM(archived_at IS NULL AND access_count = 0), 0) AS zero_access,
            COALESCE(SUM(embedding IS NULL), 0) AS no_embedding
        FROM facts
        """,
    )
    observations = await _one(
        conn,
        """
        SELECT
            COUNT(*) AS total,
            COALESCE(SUM(archived_at IS NULL), 0) AS active,
            COALESCE(SUM(archived_at IS NOT NULL), 0) AS archived,
            COALESCE(SUM(archived_at IS NULL AND access_count = 0), 0) AS zero_access,
            COALESCE(SUM(archived_at IS NULL AND embedding IS NULL), 0) AS no_embedding,
            COALESCE(SUM(archived_at IS NULL AND COALESCE(json_array_length(source_fact_ids), 0) = 0), 0) AS empty_sources,
            COALESCE(SUM(archived_at IS NULL AND length(summary) > 1000), 0) AS over_1000_chars,
            COALESCE(SUM(archived_at IS NULL AND length(summary) > 3000), 0) AS over_3000_chars,
            COALESCE(MAX(CASE WHEN archived_at IS NULL THEN length(summary) ELSE NULL END), 0) AS max_chars
        FROM observations
        """,
    )
    dreams = await _one(
        conn,
        """
        SELECT
            COUNT(*) AS total,
            COALESCE(SUM(embedding IS NULL), 0) AS no_embedding
        FROM dreams
        """,
    )

    by_source = await _all(
        conn,
        """
        SELECT
            source_type,
            COUNT(*) AS total,
            COALESCE(SUM(archived_at IS NULL), 0) AS active,
            COALESCE(SUM(archived_at IS NULL AND consolidated_at IS NULL), 0) AS unconsolidated,
            COALESCE(SUM(archived_at IS NULL AND access_count = 0), 0) AS zero_access
        FROM facts
        GROUP BY source_type
        ORDER BY total DESC
        """,
    )
    by_kind = await _all(
        conn,
        """
        SELECT
            kind,
            COUNT(*) AS total,
            COALESCE(SUM(archived_at IS NULL), 0) AS active,
            COALESCE(SUM(archived_at IS NULL AND access_count = 0), 0) AS zero_access,
            COALESCE(SUM(archived_at IS NULL AND expires_at IS NOT NULL AND expires_at <= CURRENT_TIMESTAMP), 0)
                AS expired_active,
            COALESCE(SUM(archived_at IS NULL AND pinned_at IS NOT NULL), 0) AS pinned_active
        FROM facts
        GROUP BY kind
        ORDER BY active DESC, total DESC
        """,
    )
    observation_sources = await _all(
        conn,
        """
        SELECT
            COALESCE(json_array_length(source_fact_ids), 0) AS sources,
            COUNT(*) AS total,
            COALESCE(SUM(access_count = 0), 0) AS zero_access,
            ROUND(AVG(length(summary)), 1) AS avg_chars
        FROM observations
        WHERE archived_at IS NULL
        GROUP BY sources
        ORDER BY sources
        """,
    )
    top_entities = await _all(
        conn,
        """
        SELECT e.name, COUNT(*) AS fact_refs
        FROM entity_refs er
        JOIN entities e ON e.id = er.entity_id
        GROUP BY e.id
        ORDER BY fact_refs DESC
        LIMIT 20
        """,
    )
    temporal = await _one(
        conn,
        """
        SELECT
            COUNT(*) AS checkpoints,
            COALESCE(COUNT(DISTINCT entity_id), 0) AS entities_seen
        FROM temporal_checkpoints
        """,
    )
    provenance = {
        "observations": await _source_provenance(
            conn,
            "observations",
            "archived_at IS NULL",
            relation_table="observation_facts",
            relation_id_column="observation_id",
        ),
        "dreams": await _source_provenance(
            conn,
            "dreams",
            relation_table="dream_facts",
            relation_id_column="dream_id",
        ),
    }

    return {
        "facts": facts,
        "observations": observations,
        "dreams": dreams,
        "facts_by_source": by_source,
        "facts_by_kind": by_kind,
        "observation_source_distribution": observation_sources,
        "top_entities": top_entities,
        "temporal": temporal,
        "provenance": provenance,
    }


async def observation_prune_dry_run(
    conn: aiosqlite.Connection,
    *,
    older_than_days: int = DEFAULT_PRUNE_OLDER_THAN_DAYS,
    max_sources: int = DEFAULT_PRUNE_MAX_SOURCES,
    limit: int = DEFAULT_PRUNE_LIMIT,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return observation archive candidates without mutating memory."""

    now = now or datetime.now(UTC)
    cutoff = now - timedelta(days=older_than_days)
    params: tuple[Any, ...] = (cutoff.isoformat(), max_sources)

    summary = await _one(
        conn,
        """
        SELECT
            COUNT(*) AS total,
            COALESCE(SUM(length(summary) > 1000), 0) AS over_1000_chars,
            COALESCE(SUM(COALESCE(json_array_length(source_fact_ids), 0) = 0), 0) AS empty_sources
        FROM observations
        WHERE archived_at IS NULL
          AND access_count = 0
          AND created_at < ?
          AND COALESCE(json_array_length(source_fact_ids), 0) <= ?
        """,
        params,
    )
    candidates = await _all(
        conn,
        """
        SELECT
            id,
            summary,
            created_at,
            updated_at,
            access_count,
            COALESCE(json_array_length(source_fact_ids), 0) AS evidence_count,
            length(summary) AS chars,
            'zero_access_low_support' AS reason
        FROM observations
        WHERE archived_at IS NULL
          AND access_count = 0
          AND created_at < ?
          AND COALESCE(json_array_length(source_fact_ids), 0) <= ?
        ORDER BY created_at ASC
        LIMIT ?
        """,
        (*params, limit),
    )

    return {
        "criteria": {
            "older_than_days": older_than_days,
            "max_sources": max_sources,
            "limit": limit,
            "cutoff": cutoff.isoformat(),
        },
        "summary": summary,
        "candidates": candidates,
    }


async def observation_prune_candidates_by_ids(
    conn: aiosqlite.Connection,
    observation_ids: list[int],
    *,
    older_than_days: int = DEFAULT_PRUNE_OLDER_THAN_DAYS,
    max_sources: int = DEFAULT_PRUNE_MAX_SOURCES,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Return requested observation IDs that still satisfy the prune rule."""

    if not observation_ids:
        return []

    now = now or datetime.now(UTC)
    cutoff = now - timedelta(days=older_than_days)
    placeholders = ",".join("?" * len(observation_ids))
    return await _all(
        conn,
        f"""
        SELECT
            id,
            summary,
            created_at,
            updated_at,
            access_count,
            COALESCE(json_array_length(source_fact_ids), 0) AS evidence_count,
            length(summary) AS chars,
            'zero_access_low_support' AS reason
        FROM observations
        WHERE id IN ({placeholders})
          AND archived_at IS NULL
          AND access_count = 0
          AND created_at < ?
          AND COALESCE(json_array_length(source_fact_ids), 0) <= ?
        ORDER BY created_at ASC
        """,
        (*observation_ids, cutoff.isoformat(), max_sources),
    )


async def observation_prune_candidates_matching(
    conn: aiosqlite.Connection,
    *,
    older_than_days: int = DEFAULT_PRUNE_OLDER_THAN_DAYS,
    max_sources: int = DEFAULT_PRUNE_MAX_SOURCES,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Return all observations that currently satisfy the prune rule."""

    now = now or datetime.now(UTC)
    cutoff = now - timedelta(days=older_than_days)
    return await _all(
        conn,
        """
        SELECT
            id,
            summary,
            created_at,
            updated_at,
            access_count,
            COALESCE(json_array_length(source_fact_ids), 0) AS evidence_count,
            length(summary) AS chars,
            'zero_access_low_support' AS reason
        FROM observations
        WHERE archived_at IS NULL
          AND access_count = 0
          AND created_at < ?
          AND COALESCE(json_array_length(source_fact_ids), 0) <= ?
        ORDER BY created_at ASC
        """,
        (cutoff.isoformat(), max_sources),
    )
