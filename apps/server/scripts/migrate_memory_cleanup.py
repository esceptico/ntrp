"""One-time memory cleanup migration.

Repairs three pieces of damage left by the now-removed inline-supersede /
over-segmentation behavior, then leaves a hook for de-duplicating claims via the
Step-1 adjudicator (rather than hardcoding any similarity rule):

  (a) Drop ``episode -> episode`` ``supersedes`` edges. Episodes are immutable;
      these edges were written by the rogue inline-supersede path. Removing them
      and restoring the superseded episodes to ``status='active'`` lets them
      re-enter consolidation.
  (b) Recompute every ``inferred`` claim that carries a literal ``confidence=1.0``
      (no claim is authored with a literal — confidence is ALWAYS derived). The
      recompute runs the canonical ``compute_confidence(...)`` with the claim's
      real provenance, its evidence-parent confidences, and its live contradiction
      count, matching exactly what the claim writer would have produced.
  (c) (TODO hook) Collapse obvious duplicate claims by deferring to the Step-1
      dedup adjudicator. Intentionally NOT implemented with a heuristic.

The script is idempotent: re-running it is a no-op once the data is clean. It
backs up the target DB file before touching it and prints a before/after summary.

Run against a COPY first. Never point it at the live DB without a backup:

    cp ~/.ntrp/memory.db /tmp/memory_copy.db
    uv run python scripts/migrate_memory_cleanup.py /tmp/memory_copy.db
"""

from __future__ import annotations

import argparse
import asyncio
import shutil
from datetime import datetime
from pathlib import Path

import ntrp.database as database
from ntrp.memory.connectors._confidence import compute_confidence
from ntrp.memory.store.base import GraphDatabase

# Provenance values that can never legitimately reach a literal 1.0 — their
# confidence is always derived. ``user_authored`` (remember()) is deliberately
# excluded: it is allowed to be high and is not the rogue writer.
_DERIVED_PROVENANCES = ("inferred",)


def _backup_db(db_path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = db_path.with_name(f"{db_path.name}.bak-{stamp}")
    shutil.copy2(db_path, backup_path)
    return backup_path


async def _count(conn, sql: str, params: tuple = ()) -> int:
    rows = await conn.execute_fetchall(sql, params)
    return int(rows[0][0]) if rows else 0


async def _snapshot(conn) -> dict[str, int]:
    return {
        "episode_supersedes_edges": await _count(
            conn,
            """
            SELECT COUNT(*)
            FROM memory_item_parents e
            JOIN memory_items c ON c.id = e.child_id
            JOIN memory_items p ON p.id = e.parent_id
            WHERE e.role = 'supersedes' AND c.kind = 'episode' AND p.kind = 'episode'
            """,
        ),
        "superseded_episodes": await _count(
            conn,
            "SELECT COUNT(*) FROM memory_items WHERE kind = 'episode' AND status = 'superseded'",
        ),
        "literal_confidence_claims": await _count(
            conn,
            f"""
            SELECT COUNT(*) FROM memory_items
            WHERE provenance IN ({",".join("?" for _ in _DERIVED_PROVENANCES)})
              AND kind = 'claim' AND confidence = 1.0
            """,
            _DERIVED_PROVENANCES,
        ),
    }


async def _drop_episode_supersedes(conn) -> tuple[int, int]:
    """Delete episode->episode supersedes edges and reactivate the episodes they
    pinned to ``superseded``. Returns (edges_deleted, episodes_reactivated)."""
    edges = await conn.execute_fetchall(
        """
        SELECT e.child_id, e.parent_id
        FROM memory_item_parents e
        JOIN memory_items c ON c.id = e.child_id
        JOIN memory_items p ON p.id = e.parent_id
        WHERE e.role = 'supersedes' AND c.kind = 'episode' AND p.kind = 'episode'
        """
    )
    superseded_ids = {row["parent_id"] for row in edges}

    for row in edges:
        await conn.execute(
            "DELETE FROM memory_item_parents WHERE child_id = ? AND parent_id = ? AND role = 'supersedes'",
            (row["child_id"], row["parent_id"]),
        )

    reactivated = 0
    for episode_id in superseded_ids:
        cursor = await conn.execute(
            """
            UPDATE memory_items
            SET status = 'active', invalid_at = NULL, updated_at = ?
            WHERE id = ? AND kind = 'episode' AND status = 'superseded'
            """,
            (datetime.now().astimezone().isoformat(), episode_id),
        )
        reactivated += cursor.rowcount
    return len(edges), reactivated


async def _evidence_parent_confidences(conn, claim_id: str) -> list[float]:
    rows = await conn.execute_fetchall(
        """
        SELECT p.confidence
        FROM memory_item_parents e
        JOIN memory_items p ON p.id = e.parent_id
        WHERE e.child_id = ? AND e.role = 'evidence'
        """,
        (claim_id,),
    )
    return [float(row["confidence"]) for row in rows]


async def _contradiction_count(conn, claim_id: str) -> int:
    return await _count(
        conn,
        """
        SELECT COUNT(*) FROM memory_item_parents
        WHERE role = 'contradicts' AND (child_id = ? OR parent_id = ?)
        """,
        (claim_id, claim_id),
    )


async def _recompute_literal_confidences(conn) -> int:
    """Recompute every derived-provenance claim stuck at a literal 1.0 via the
    canonical ``compute_confidence``. Mirrors the claim writer's write-time
    semantics (age/last_used = 0) while honoring each claim's real evidence
    parents and live contradiction count. Returns the number updated."""
    rows = await conn.execute_fetchall(
        f"""
        SELECT id, provenance FROM memory_items
        WHERE provenance IN ({",".join("?" for _ in _DERIVED_PROVENANCES)})
          AND kind = 'claim' AND confidence = 1.0
        """,
        _DERIVED_PROVENANCES,
    )
    updated = 0
    for row in rows:
        claim_id = row["id"]
        confidence = compute_confidence(
            provenance=str(row["provenance"]),
            parent_confidences=await _evidence_parent_confidences(conn, claim_id),
            contradiction_count=await _contradiction_count(conn, claim_id),
            age_days=0,
            last_used_days=0,
            helped=0,
            hurt=0,
            ignored=0,
        )
        await conn.execute(
            "UPDATE memory_items SET confidence = ?, updated_at = ? WHERE id = ?",
            (confidence, datetime.now().astimezone().isoformat(), claim_id),
        )
        updated += 1
    return updated


async def _collapse_duplicate_claims(conn) -> int:
    """Collapse obvious duplicate claims.

    TODO: wire this to the Step-1 dedup adjudicator
    (``ntrp.memory.connectors.claim_writer`` adjudicate path /
    ``learnings/dedup.md`` + not_same guard) so duplicates are merged by an LLM
    DECISION, not a similarity threshold. Embeddings/FTS may shortlist
    candidates, but the keep/merge call must go through the adjudicator. Until
    that is wired, this is a deliberate no-op so the migration never makes a
    rule-based merge decision.
    """
    return 0


async def migrate(db_path: Path) -> None:
    backup_path = _backup_db(db_path)
    print(f"backup: {backup_path}")

    conn = await database.connect(db_path, vec=True)
    await conn.execute("PRAGMA foreign_keys=ON")
    GraphDatabase(conn, 1536)  # ensure vec extension is loaded

    before = await _snapshot(conn)

    edges_deleted, episodes_reactivated = await _drop_episode_supersedes(conn)
    confidences_recomputed = await _recompute_literal_confidences(conn)
    duplicates_collapsed = await _collapse_duplicate_claims(conn)

    await conn.commit()
    after = await _snapshot(conn)
    await conn.close()

    print("\n=== migration summary ===")
    print(f"episode->episode supersedes edges deleted: {edges_deleted}")
    print(f"superseded episodes reactivated:           {episodes_reactivated}")
    print(f"literal-confidence claims recomputed:      {confidences_recomputed}")
    print(f"duplicate claims collapsed:                {duplicates_collapsed} (adjudicator TODO)")
    print("\n         before -> after")
    for key in before:
        print(f"  {key:<28} {before[key]:>4} -> {after[key]:>4}")


def main() -> None:
    parser = argparse.ArgumentParser(description="One-time memory cleanup migration.")
    parser.add_argument("db_path", type=Path, help="Path to the memory SQLite DB to migrate.")
    args = parser.parse_args()
    if not args.db_path.exists():
        raise SystemExit(f"DB not found: {args.db_path}")
    asyncio.run(migrate(args.db_path))


if __name__ == "__main__":
    main()
