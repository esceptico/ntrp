from fastapi import APIRouter, HTTPException

from ntrp.server.runtime import get_runtime

router = APIRouter(tags=["data"])


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
        "sources": runtime.get_available_sources(),
    }
