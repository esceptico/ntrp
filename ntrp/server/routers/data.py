from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ntrp.database import serialize_embedding
from ntrp.memory.events import FactDeleted, FactUpdated, MemoryCleared
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
    repo = runtime.memory.facts

    total = await repo.count()
    facts = await repo.list_recent(limit=limit + offset)
    sliced = facts[offset : offset + limit]

    return {
        "facts": [
            {
                "id": f.id,
                "text": f.text,
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
    repo = runtime.memory.facts

    fact = await repo.get(fact_id)
    if not fact:
        raise HTTPException(status_code=404, detail="Fact not found")

    entity_refs = await repo.get_entity_refs(fact_id)

    return {
        "fact": {
            "id": fact.id,
            "text": fact.text,
            "source_type": fact.source_type,
            "source_ref": fact.source_ref,
            "created_at": fact.created_at.isoformat(),
            "access_count": fact.access_count,
        },
        "entities": [{"name": e.name, "entity_id": e.entity_id} for e in entity_refs],
        "linked_facts": [],
    }


@router.post("/memory/clear")
async def clear_memory():
    runtime = _require_memory()
    deleted = await runtime.memory.clear()
    runtime.channel.publish(MemoryCleared())
    return {"status": "cleared", "deleted": deleted}


@router.post("/memory/observations/clear")
async def clear_observations():
    runtime = _require_memory()
    result = await runtime.memory.clear_observations()
    return {"status": "cleared", **result}


@router.get("/observations")
async def get_observations(limit: int = 50):
    runtime = _require_memory()
    obs_repo = runtime.memory.observations

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
    obs_repo = runtime.memory.observations
    fact_repo = runtime.memory.facts

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


@router.get("/dreams")
async def get_dreams(limit: int = 50):
    runtime = _require_memory()
    dream_repo = runtime.memory.dreams

    dreams = await dream_repo.list_recent(limit=limit)

    return {
        "dreams": [
            {
                "id": d.id,
                "bridge": d.bridge,
                "insight": d.insight,
                "created_at": d.created_at.isoformat(),
            }
            for d in dreams
        ],
    }


@router.get("/dreams/{dream_id}")
async def get_dream_details(dream_id: int):
    runtime = _require_memory()
    dream_repo = runtime.memory.dreams
    fact_repo = runtime.memory.facts

    dream = await dream_repo.get(dream_id)
    if not dream:
        raise HTTPException(status_code=404, detail="Dream not found")

    source_facts = []
    for fid in dream.source_fact_ids:
        fact = await fact_repo.get(fid)
        if fact:
            source_facts.append({"id": fact.id, "text": fact.text})

    return {
        "dream": {
            "id": dream.id,
            "bridge": dream.bridge,
            "insight": dream.insight,
            "created_at": dream.created_at.isoformat(),
        },
        "source_facts": source_facts,
    }


@router.delete("/dreams/{dream_id}")
async def delete_dream(dream_id: int):
    runtime = _require_memory()
    dream_repo = runtime.memory.dreams

    dream = await dream_repo.get(dream_id)
    if not dream:
        raise HTTPException(status_code=404, detail="Dream not found")

    async with runtime.memory.transaction():
        await dream_repo.delete(dream_id)

    return {"status": "deleted", "dream_id": dream_id}


@router.get("/stats")
async def get_stats():
    runtime = _require_memory()
    repo = runtime.memory.facts
    obs_repo = runtime.memory.observations

    return {
        "fact_count": await repo.count(),
        "observation_count": await obs_repo.count(),
    }


@router.patch("/facts/{fact_id}")
async def update_fact(fact_id: int, request: UpdateFactRequest):
    runtime = _require_memory()

    async with runtime.memory.transaction():
        repo = runtime.memory.facts

        fact = await repo.get(fact_id)
        if not fact:
            raise HTTPException(status_code=404, detail="Fact not found")

        new_embedding = await runtime.memory.embedder.embed_one(request.text)

        await repo.conn.execute("DELETE FROM entity_refs WHERE fact_id = ?", (fact_id,))

        embedding_bytes = serialize_embedding(new_embedding)
        await repo.conn.execute(
            """
            UPDATE facts
            SET text = ?, embedding = ?, consolidated_at = NULL
            WHERE id = ?
            """,
            (request.text, embedding_bytes, fact_id),
        )

        await repo.conn.execute("DELETE FROM facts_vec WHERE fact_id = ?", (fact_id,))
        await repo.conn.execute(
            "INSERT INTO facts_vec (fact_id, embedding) VALUES (?, ?)",
            (fact_id, embedding_bytes),
        )

        extraction = await runtime.memory.extractor.extract(request.text)
        await runtime.memory._process_extraction(fact_id, extraction)

        fact = await repo.get(fact_id)

    runtime.channel.publish(FactUpdated(fact_id=fact_id, text=request.text))

    entity_refs = await repo.get_entity_refs(fact_id)
    return {
        "fact": {
            "id": fact.id,
            "text": fact.text,
            "source_type": fact.source_type,
            "source_ref": fact.source_ref,
            "created_at": fact.created_at.isoformat(),
            "access_count": fact.access_count,
        },
        "entity_refs": [{"name": e.name, "entity_id": e.entity_id} for e in entity_refs],
    }


@router.delete("/facts/{fact_id}")
async def delete_fact(fact_id: int):
    runtime = _require_memory()

    async with runtime.memory.transaction():
        repo = runtime.memory.facts

        fact = await repo.get(fact_id)
        if not fact:
            raise HTTPException(status_code=404, detail="Fact not found")

        entity_refs_rows = await repo.conn.execute_fetchall(
            "SELECT COUNT(*) FROM entity_refs WHERE fact_id = ?", (fact_id,)
        )
        entity_refs_count = entity_refs_rows[0][0] if entity_refs_rows else 0

        await repo.delete(fact_id)

    runtime.channel.publish(FactDeleted(fact_id=fact_id))

    return {
        "status": "deleted",
        "fact_id": fact_id,
        "cascaded": {
            "entity_refs": entity_refs_count,
        },
    }


@router.patch("/observations/{observation_id}")
async def update_observation(observation_id: int, request: UpdateObservationRequest):
    runtime = _require_memory()

    async with runtime.memory.transaction():
        obs_repo = runtime.memory.observations

        obs = await obs_repo.get(observation_id)
        if not obs:
            raise HTTPException(status_code=404, detail="Observation not found")

        new_embedding = await runtime.memory.embedder.embed_one(request.summary)

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

        await obs_repo.conn.execute("DELETE FROM observations_vec WHERE observation_id = ?", (observation_id,))
        await obs_repo.conn.execute(
            "INSERT INTO observations_vec (observation_id, embedding) VALUES (?, ?)", (observation_id, embedding_bytes)
        )

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

    async with runtime.memory.transaction():
        obs_repo = runtime.memory.observations

        obs = await obs_repo.get(observation_id)
        if not obs:
            raise HTTPException(status_code=404, detail="Observation not found")

        await obs_repo.conn.execute("DELETE FROM observations_vec WHERE observation_id = ?", (observation_id,))
        await obs_repo.conn.execute("DELETE FROM observations WHERE id = ?", (observation_id,))

    return {
        "status": "deleted",
        "observation_id": observation_id,
    }
