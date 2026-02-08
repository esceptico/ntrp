from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ntrp.database import serialize_embedding
from ntrp.memory.events import FactDeleted, FactUpdated, MemoryCleared
from ntrp.memory.store.linking import create_links_for_fact
from ntrp.server.runtime import get_runtime

router = APIRouter(tags=["data"])


class UpdateFactRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=10000)


class UpdateObservationRequest(BaseModel):
    summary: str = Field(..., min_length=1, max_length=10000)


def _require_memory():
    runtime = get_runtime()
    if not runtime.memory:
        raise HTTPException(status_code=503, detail="Memory is disabled")
    return runtime


@router.get("/facts")
async def get_facts(limit: int = 100, offset: int = 0):
    runtime = _require_memory()
    repo = runtime.memory.fact_repo()

    total = await repo.count()
    facts = await repo.list_recent(limit=limit + offset)
    sliced = facts[offset : offset + limit]

    return {
        "facts": [
            {
                "id": f.id,
                "text": f.text,
                "fact_type": f.fact_type.value,
                "source_type": f.source_type,
                "created_at": f.created_at.isoformat(),
            }
            for f in sliced
        ],
        "total": total,
    }


@router.get("/facts/{fact_id}")
async def get_fact_details(fact_id: int):
    runtime = _require_memory()
    repo = runtime.memory.fact_repo()

    fact = await repo.get(fact_id)
    if not fact:
        raise HTTPException(status_code=404, detail="Fact not found")

    links = await repo.get_links(fact_id)
    entity_refs = await repo.get_entity_refs(fact_id)

    # Dedupe: keep best link per fact (highest weight)
    best_links: dict[int, tuple] = {}  # other_id -> (link_type, weight, text)
    for link in links:
        other_id = link.target_fact_id if link.source_fact_id == fact_id else link.source_fact_id
        if other_id not in best_links or link.weight > best_links[other_id][1]:
            other = await repo.get(other_id)
            if other:
                best_links[other_id] = (link.link_type.value, link.weight, other.text)

    linked_facts = [
        {"id": oid, "text": data[2], "link_type": data[0], "weight": data[1]}
        for oid, data in sorted(best_links.items(), key=lambda x: x[1][1], reverse=True)
    ]

    return {
        "fact": {
            "id": fact.id,
            "text": fact.text,
            "fact_type": fact.fact_type.value,
            "source_type": fact.source_type,
            "source_ref": fact.source_ref,
            "created_at": fact.created_at.isoformat(),
            "access_count": fact.access_count,
        },
        "entities": [{"name": e.name, "type": e.entity_type} for e in entity_refs],
        "linked_facts": linked_facts,
    }


@router.post("/memory/clear")
async def clear_memory():
    runtime = _require_memory()
    deleted = await runtime.memory.clear()
    await runtime.bus.publish(MemoryCleared())
    return {"status": "cleared", "deleted": deleted}


@router.get("/observations")
async def get_observations(limit: int = 50):
    runtime = _require_memory()
    obs_repo = runtime.memory.obs_repo()

    observations = await obs_repo.list_recent(limit=limit)

    return {
        "observations": [
            {
                "id": o.id,
                "summary": o.summary,
                "evidence_count": o.evidence_count,
                "access_count": o.access_count,
                "created_at": o.created_at.isoformat(),
                "updated_at": o.updated_at.isoformat(),
            }
            for o in observations
        ],
    }


@router.get("/observations/{observation_id}")
async def get_observation_details(observation_id: int):
    runtime = _require_memory()
    obs_repo = runtime.memory.obs_repo()
    fact_repo = runtime.memory.fact_repo()

    obs = await obs_repo.get(observation_id)
    if not obs:
        raise HTTPException(status_code=404, detail="Observation not found")

    fact_ids = await obs_repo.get_fact_ids(observation_id)
    facts = []
    for fid in fact_ids:
        fact = await fact_repo.get(fid)
        if fact:
            facts.append({"id": fact.id, "text": fact.text})

    return {
        "observation": {
            "id": obs.id,
            "summary": obs.summary,
            "evidence_count": obs.evidence_count,
            "access_count": obs.access_count,
            "created_at": obs.created_at.isoformat(),
            "updated_at": obs.updated_at.isoformat(),
        },
        "supporting_facts": facts,
    }


@router.get("/stats")
async def get_stats():
    runtime = _require_memory()
    repo = runtime.memory.fact_repo()
    obs_repo = runtime.memory.obs_repo()

    return {
        "fact_count": await repo.count(),
        "link_count": await runtime.memory.link_count(),
        "observation_count": await obs_repo.count(),
    }


@router.patch("/facts/{fact_id}")
async def update_fact(fact_id: int, request: UpdateFactRequest):
    runtime = _require_memory()

    async with runtime.memory._db_lock:
        repo = runtime.memory.fact_repo()

        # Check if fact exists
        fact = await repo.get(fact_id)
        if not fact:
            raise HTTPException(status_code=404, detail="Fact not found")

        # Generate new embedding
        new_embedding = await runtime.memory.embedder.embed_one(request.text)

        # Delete existing entity refs and links
        await repo.conn.execute("DELETE FROM entity_refs WHERE fact_id = ?", (fact_id,))
        await repo.conn.execute(
            "DELETE FROM fact_links WHERE source_fact_id = ? OR target_fact_id = ?", (fact_id, fact_id)
        )

        # Update fact text, embedding, and mark for re-consolidation
        embedding_bytes = serialize_embedding(new_embedding)
        await repo.conn.execute(
            """
            UPDATE facts
            SET text = ?, embedding = ?, consolidated_at = NULL
            WHERE id = ?
            """,
            (request.text, embedding_bytes, fact_id),
        )

        # Update vector index
        await repo.conn.execute("DELETE FROM facts_vec WHERE fact_id = ?", (fact_id,))
        await repo.conn.execute("INSERT INTO facts_vec (fact_id, embedding) VALUES (?, ?)", (fact_id, embedding_bytes))

        # Re-extract entities
        extraction = await runtime.memory.extractor.extract(request.text)
        await runtime.memory._process_extraction(repo, fact_id, extraction, fact.source_ref)

        # Reload fact with new entity refs
        fact = await repo.get(fact_id)

        # Recreate links
        links_created = await create_links_for_fact(repo, fact)

        await repo.conn.commit()

    await runtime.bus.publish(FactUpdated(fact_id=fact_id, text=request.text))

    return {
        "fact": {
            "id": fact.id,
            "text": fact.text,
            "fact_type": fact.fact_type.value,
            "source_type": fact.source_type,
            "source_ref": fact.source_ref,
            "created_at": fact.created_at.isoformat(),
            "access_count": fact.access_count,
        },
        "entity_refs": [
            {"name": e.name, "type": e.entity_type, "canonical_id": e.canonical_id} for e in fact.entity_refs
        ],
        "links_created": links_created,
    }


@router.delete("/facts/{fact_id}")
async def delete_fact(fact_id: int):
    runtime = _require_memory()

    async with runtime.memory._db_lock:
        repo = runtime.memory.fact_repo()

        # Check if fact exists
        fact = await repo.get(fact_id)
        if not fact:
            raise HTTPException(status_code=404, detail="Fact not found")

        # Count what we're about to delete
        entity_refs_rows = await repo.conn.execute_fetchall(
            "SELECT COUNT(*) FROM entity_refs WHERE fact_id = ?", (fact_id,)
        )
        entity_refs_count = entity_refs_rows[0][0] if entity_refs_rows else 0

        links_rows = await repo.conn.execute_fetchall(
            "SELECT COUNT(*) FROM fact_links WHERE source_fact_id = ? OR target_fact_id = ?", (fact_id, fact_id)
        )
        links_count = links_rows[0][0] if links_rows else 0

        # Delete fact and cascades (uses existing method)
        await repo.delete(fact_id)

    await runtime.bus.publish(FactDeleted(fact_id=fact_id))

    return {
        "status": "deleted",
        "fact_id": fact_id,
        "cascaded": {
            "entity_refs": entity_refs_count,
            "links": links_count,
        },
    }


@router.patch("/observations/{observation_id}")
async def update_observation(observation_id: int, request: UpdateObservationRequest):
    runtime = _require_memory()

    async with runtime.memory._db_lock:
        obs_repo = runtime.memory.obs_repo()

        # Check if observation exists
        obs = await obs_repo.get(observation_id)
        if not obs:
            raise HTTPException(status_code=404, detail="Observation not found")

        # Generate new embedding
        new_embedding = await runtime.memory.embedder.embed_one(request.summary)

        # Update observation summary and embedding
        now = datetime.now(UTC)
        embedding_bytes = serialize_embedding(new_embedding)
        await obs_repo.conn.execute(
            """
            UPDATE observations
            SET summary = ?, embedding = ?, updated_at = ?
            WHERE id = ?
            """,
            (request.summary, embedding_bytes, now.isoformat(), observation_id),
        )

        # Update vector index
        await obs_repo.conn.execute("DELETE FROM observations_vec WHERE observation_id = ?", (observation_id,))
        await obs_repo.conn.execute(
            "INSERT INTO observations_vec (observation_id, embedding) VALUES (?, ?)", (observation_id, embedding_bytes)
        )

        await obs_repo.conn.commit()

        # Reload observation
        obs = await obs_repo.get(observation_id)

    return {
        "observation": {
            "id": obs.id,
            "summary": obs.summary,
            "evidence_count": obs.evidence_count,
            "access_count": obs.access_count,
            "created_at": obs.created_at.isoformat(),
            "updated_at": obs.updated_at.isoformat(),
        }
    }


@router.delete("/observations/{observation_id}")
async def delete_observation(observation_id: int):
    runtime = _require_memory()

    async with runtime.memory._db_lock:
        obs_repo = runtime.memory.obs_repo()

        # Check if observation exists
        obs = await obs_repo.get(observation_id)
        if not obs:
            raise HTTPException(status_code=404, detail="Observation not found")

        # Delete observation and vector embedding
        await obs_repo.conn.execute("DELETE FROM observations_vec WHERE observation_id = ?", (observation_id,))
        await obs_repo.conn.execute("DELETE FROM observations WHERE id = ?", (observation_id,))
        await obs_repo.conn.commit()

    return {
        "status": "deleted",
        "observation_id": observation_id,
    }
