"""Backfill the live memory_items DB with a hand-curated, trustworthy slice of
the pre-v26 backup (``memory.db.pre-v26-cleanup.20260520-204629``).

The backup uses the OLD multi-table schema (facts/observations/...). We pull
only 38 durable, high-signal personal facts (identity / preference /
relationship + one decision + one constraint), deliberately excluding the
~290 rows of stale Dex/Aside audit-ops noise and one-off LinkedIn chatter.

Every imported fact becomes a ``claim`` (scope=user, provenance=inferred),
re-embedded with the live embedder, original confidence + date preserved, and
tagged with its original kind + ``backfill``.

The live memory_items table is WIPED first (user confirmed it is empty). Back
up the live DB before running.

Run:  uv run python scripts/backfill_pre_v26.py
"""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import UTC, datetime

import numpy as np

from ntrp.config import get_config
from ntrp.llm import router
from ntrp.memory.items_store import MemoryItemInsert
from ntrp.memory.runtime import MemoryDatabase

BACKUP_NAME = "memory.db.pre-v26-cleanup.20260520-204629"

# Hand-curated fact ids from the backup, grouped by original kind.
CURATED: dict[str, list[int]] = {
    "identity": [6166, 6168, 5362, 5380, 5470, 5471, 5547, 5742, 5859, 6141, 5843, 6609, 5306],
    "preference": [5493, 5501, 5339, 5668, 5473, 5481, 5864, 6225, 5860, 5861, 5699, 5670, 5637, 5469],
    "relationship": [5233, 5238, 5776, 5596, 5597, 6319, 5393, 6381, 5963],
    "decision": [6178],
    "constraint": [6012],
}

# Corrected text for facts with typos in the backup (user's name is Timur).
TEXT_OVERRIDES: dict[int, str] = {
    6141: "User's name is Timur",
    5547: "Timur worked at Replika recently.",
}


def _parse_dt(raw: str | None) -> datetime | None:
    if not raw:
        return None
    value = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


async def main() -> None:
    config = get_config()
    backup_path = config.ntrp_dir / BACKUP_NAME
    if not backup_path.exists():
        raise SystemExit(f"backup not found: {backup_path}")
    if config.embedding is None:
        raise SystemExit("no embedding model configured")
    router.init(config)

    id_to_kind = {fid: kind for kind, ids in CURATED.items() for fid in ids}
    all_ids = list(id_to_kind)
    placeholders = ",".join("?" for _ in all_ids)

    src = sqlite3.connect(f"file:{backup_path}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row
    rows = src.execute(
        f"SELECT id, text, confidence, created_at FROM facts WHERE id IN ({placeholders})",
        all_ids,
    ).fetchall()
    src.close()
    if len(rows) != len(all_ids):
        found = {r["id"] for r in rows}
        raise SystemExit(f"missing ids in backup: {sorted(set(all_ids) - found)}")

    print("creating memory db...", flush=True)
    memory = await MemoryDatabase.create(
        db_path=config.memory_db_path,
        embedding=config.embedding,
        model=config.embedding_model,
    )
    conn = memory.conn

    texts = [TEXT_OVERRIDES.get(r["id"], str(r["text"]).strip()) for r in rows]
    print(f"embedding {len(texts)} texts...", flush=True)
    embeddings = await memory.embedder.embed(texts)
    print("embedded; wiping + inserting...", flush=True)

    await conn.execute("DELETE FROM memory_items_vec")
    await conn.execute("DELETE FROM memory_items")

    inserted = 0
    for row, text, emb in zip(rows, texts, embeddings, strict=True):
        await memory.items.insert_item(
            MemoryItemInsert(
                kind="claim",
                content=text,
                source_refs=[],
                confidence=float(row["confidence"]),
                scope="user",
                provenance="inferred",
                tags=[id_to_kind[row["id"]], "backfill"],
                embedding=np.asarray(emb, dtype=np.float32),
                valid_from=_parse_dt(row["created_at"]),
            ),
            commit=False,
        )
        inserted += 1

    await conn.commit()
    await memory.close()

    print(f"wiped live memory_items and imported {inserted} curated claim(s)")
    for kind, ids in CURATED.items():
        print(f"  {kind:12} {len(ids)}")


if __name__ == "__main__":
    asyncio.run(main())
