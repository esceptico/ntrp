from fastapi import APIRouter, HTTPException

from ntrp.server.runtime import get_runtime
from ntrp.server.schemas import UpdateFactRequest, UpdateObservationRequest

router = APIRouter(tags=["data"])


def _require_memory():
    runtime = get_runtime()
    if not runtime.memory_service:
        raise HTTPException(status_code=503, detail="Memory is disabled")
    return runtime


@router.get("/facts")
async def get_facts(limit: int = 100, offset: int = 0):
    runtime = _require_memory()
    facts, total = await runtime.memory_service.facts.list_recent(limit=limit, offset=offset)
    return {
        "facts": [
            {
                "id": f.id,
                "text": f.text,
                "source_type": f.source_type,
                "created_at": f.created_at.isoformat(),
            }
            for f in facts
        ],
        "total": total,
    }


@router.get("/facts/{fact_id}")
async def get_fact_details(fact_id: int):
    runtime = _require_memory()
    try:
        fact, entity_refs = await runtime.memory_service.facts.get(fact_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Fact not found")

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


@router.patch("/facts/{fact_id}")
async def update_fact(fact_id: int, request: UpdateFactRequest):
    runtime = _require_memory()

    try:
        fact, entity_refs = await runtime.memory_service.facts.update(fact_id, request.text)
    except KeyError:
        raise HTTPException(status_code=404, detail="Fact not found")

    return {
        "fact": {
            "id": fact.id,
            "text": fact.text,
            "source_type": fact.source_type,
            "source_ref": fact.source_ref,
            "created_at": fact.created_at.isoformat(),
            "access_count": fact.access_count,
        },
        "entity_refs": entity_refs,
    }


@router.delete("/facts/{fact_id}")
async def delete_fact(fact_id: int):
    runtime = _require_memory()

    try:
        cascaded = await runtime.memory_service.facts.delete(fact_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Fact not found")

    return {
        "status": "deleted",
        "fact_id": fact_id,
        "cascaded": cascaded,
    }


@router.get("/observations")
async def get_observations(limit: int = 50):
    runtime = _require_memory()
    observations = await runtime.memory_service.observations.list_recent(limit=limit)
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
    try:
        obs, facts = await runtime.memory_service.observations.get(observation_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Observation not found")

    return {
        "observation": {
            "id": obs.id,
            "summary": obs.summary,
            "evidence_count": obs.evidence_count,
            "access_count": obs.access_count,
            "created_at": obs.created_at.isoformat(),
            "updated_at": obs.updated_at.isoformat(),
        },
        "supporting_facts": [{"id": f.id, "text": f.text} for f in facts],
    }


@router.patch("/observations/{observation_id}")
async def update_observation(observation_id: int, request: UpdateObservationRequest):
    runtime = _require_memory()

    try:
        obs = await runtime.memory_service.observations.update(observation_id, request.summary)
    except KeyError:
        raise HTTPException(status_code=404, detail="Observation not found")

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

    try:
        await runtime.memory_service.observations.delete(observation_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Observation not found")

    return {
        "status": "deleted",
        "observation_id": observation_id,
    }


@router.get("/dreams")
async def get_dreams(limit: int = 50):
    runtime = _require_memory()
    dreams = await runtime.memory_service.dreams.list_recent(limit=limit)
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
    try:
        dream, source_facts = await runtime.memory_service.dreams.get(dream_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Dream not found")

    return {
        "dream": {
            "id": dream.id,
            "bridge": dream.bridge,
            "insight": dream.insight,
            "created_at": dream.created_at.isoformat(),
        },
        "source_facts": [{"id": f.id, "text": f.text} for f in source_facts],
    }


@router.delete("/dreams/{dream_id}")
async def delete_dream(dream_id: int):
    runtime = _require_memory()
    try:
        await runtime.memory_service.dreams.delete(dream_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Dream not found")

    return {"status": "deleted", "dream_id": dream_id}


@router.get("/stats")
async def get_stats():
    runtime = _require_memory()
    return await runtime.memory_service.stats()


@router.post("/memory/clear")
async def clear_memory():
    runtime = _require_memory()
    deleted = await runtime.memory_service.clear()
    return {"status": "cleared", "deleted": deleted}


@router.post("/memory/observations/clear")
async def clear_observations():
    runtime = _require_memory()
    result = await runtime.memory_service.clear_observations()
    return {"status": "cleared", **result}
