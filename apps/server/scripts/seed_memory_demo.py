"""Seed the live memory DB with a small, coherent demo dataset for testing the
directories / lenses feature and general memory browsing.

Everything inserted is tagged ``demo`` so it can be removed later with:
    DELETE FROM memory_items WHERE tags LIKE '%"demo"%';

Also strips the stale "**DURABLE KNOWLEDGE EXTRACTED:**" header from any existing
episodes (legacy artifact from before the episode-summary prompt was fixed).

Run:  uv run python scripts/seed_memory_demo.py
"""

from __future__ import annotations

import asyncio

import ntrp.database as database
from ntrp.config import get_config
from ntrp.memory.items_store import MemoryItemInsert, MemoryItemsRepository
from ntrp.memory.store.base import GraphDatabase

DEMO_TAG = "demo"

# (title, content) — people who anchor the lens extraction.
OBSERVATIONS = [
    ("Kevin Ortiz", "Kevin Ortiz is a backend engineer at Northwind. He owns the billing and payments service."),
    ("Kevin Ortiz", "Kevin led the migration of Northwind's billing service onto PostgreSQL last quarter."),
    ("Maria Chen", "Maria Chen leads frontend engineering at Northwind and maintains the shared design system."),
    ("Maria Chen", "Maria is the reviewer of record for all changes to Northwind's component library."),
    ("Sam Patel", "Sam Patel handles infrastructure at Northwind — the Kubernetes clusters and the CI pipeline."),
    ("Sam Patel", "Sam set up Northwind's blue/green deploy process and owns the on-call rotation tooling."),
    ("Dana Lee", "Dana Lee is the product manager for Northwind's growth team. She is not an engineer."),
]

CLAIMS = [
    "Northwind standardized on PostgreSQL for all new backend services.",
    "Northwind's billing service must remain PCI-compliant; card data never touches application logs.",
    "Tim prefers concise logging — avoid verbose debug output in production code.",
    "Northwind ships frontend changes behind feature flags rather than long-lived branches.",
]

EPISODES = [
    "Northwind Q2 planning settled on three priorities: finish the billing PostgreSQL migration, "
    "ship the new design system, and harden the CI pipeline. Kevin owns billing, Maria owns the "
    "design system, Sam owns CI.",
    "Incident postmortem: a billing deploy briefly double-charged a small set of customers. Root cause "
    "was a missing idempotency key on the payment retry path. Kevin added idempotency keys and Sam added "
    "a deploy gate that blocks billing changes without a passing integration suite.",
]

# slug, directory name, lens body, then which observation-titles belong as entities.
LENS_SLUG = "northwind-engineers"
LENS_NAME = "Northwind engineers"
LENS_DESCRIPTION = "Engineers who work at Northwind (backend, frontend, infrastructure). Excludes non-engineering roles."
LENS_BODY = """---
directory: Northwind engineers
entity_type: person
---
## Belongs
Engineers who work at Northwind. Include backend, frontend, and infrastructure
engineers. Exclude non-engineering roles such as product managers.

## Profile shape
- Role
- What they own
- Notable context
"""

ENTITIES = {
    "Kevin Ortiz": "Backend engineer at Northwind. Owns the billing and payments service; led its PostgreSQL migration.",
    "Maria Chen": "Frontend lead at Northwind. Maintains the shared design system and reviews the component library.",
    "Sam Patel": "Infrastructure engineer at Northwind. Owns the Kubernetes clusters, CI pipeline, and on-call tooling.",
}


async def _strip_durable_headers(repo: MemoryItemsRepository) -> int:
    rows = await repo.conn.execute_fetchall(
        "SELECT id, content FROM memory_items WHERE kind = 'episode' AND content LIKE '%DURABLE KNOWLEDGE EXTRACTED%'"
    )
    fixed = 0
    for row in rows:
        lines = row["content"].splitlines()
        kept = [ln for ln in lines if "DURABLE KNOWLEDGE EXTRACTED" not in ln.upper()]
        # drop a leading blank line left behind by the removed header
        while kept and not kept[0].strip():
            kept.pop(0)
        new_content = "\n".join(kept).strip()
        await repo.conn.execute(
            "UPDATE memory_items SET content = ? WHERE id = ?", (new_content, row["id"])
        )
        fixed += 1
    await repo.conn.commit()
    return fixed


async def main() -> None:
    config = get_config()
    conn = await database.connect(config.memory_db_path, vec=True)
    await conn.execute("PRAGMA foreign_keys=ON")
    db = GraphDatabase(conn, 1536)
    await db.init_schema()
    repo = MemoryItemsRepository(conn)

    stripped = await _strip_durable_headers(repo)

    obs_ids: dict[str, list[str]] = {}
    for title, content in OBSERVATIONS:
        item_id = await repo.insert_item(
            MemoryItemInsert(
                content=content, source_refs=[], confidence=0.7, title=title,
                kind="observation", provenance="inferred", tags=[DEMO_TAG],
            )
        )
        obs_ids.setdefault(title, []).append(item_id)

    for content in CLAIMS:
        await repo.insert_item(
            MemoryItemInsert(
                content=content, source_refs=[], confidence=0.8,
                kind="claim", provenance="user_authored", tags=[DEMO_TAG],
            )
        )

    for content in EPISODES:
        await repo.insert_item(
            MemoryItemInsert(
                content=content, source_refs=[], confidence=0.7,
                kind="episode", provenance="inferred", tags=[DEMO_TAG],
            )
        )

    # lens file
    lenses_dir = config.memory_db_path.parent / "memory" / "lenses"
    lenses_dir.mkdir(parents=True, exist_ok=True)
    lens_path = lenses_dir / f"{LENS_SLUG}.md"
    lens_path.write_text(LENS_BODY, encoding="utf-8")

    # pre-materialize directory + entities + edges so the tab is populated immediately
    directory_id = await repo.ensure_directory(LENS_SLUG, LENS_NAME, LENS_DESCRIPTION)
    edges = 0
    for name, profile in ENTITIES.items():
        existing = await repo.find_entity_by_title(name)
        entity_id = existing.id if existing else await repo.insert_item(
            MemoryItemInsert(
                content=profile, source_refs=[], confidence=0.7, title=name,
                kind="entity", provenance="inferred", tags=[DEMO_TAG, f"lens:{LENS_SLUG}"],
            ),
            commit=False,
        )
        await repo.insert_parent_edge(entity_id, directory_id, "member_of", commit=False)
        edges += 1
        for obs_id in obs_ids.get(name, []):
            await repo.insert_parent_edge(entity_id, obs_id, "evidence", commit=False)
            edges += 1
    await conn.commit()
    await conn.close()

    print(f"stripped DURABLE headers from {stripped} episode(s)")
    print(f"seeded {len(OBSERVATIONS)} observations, {len(CLAIMS)} claims, {len(EPISODES)} episodes")
    print(f"materialized directory '{LENS_NAME}' with {len(ENTITIES)} entities, {edges} edges")
    print(f"wrote lens file: {lens_path}")


if __name__ == "__main__":
    asyncio.run(main())
