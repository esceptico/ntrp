from fastapi import APIRouter, HTTPException

from ntrp.memory.store.facts import FactRepository
from ntrp.memory.store.observations import ObservationRepository
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
    repo = FactRepository(runtime.memory.db.conn)

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
    repo = FactRepository(runtime.memory.db.conn)

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
    repo = FactRepository(runtime.memory.db.conn)
    obs_repo = ObservationRepository(runtime.memory.db.conn)

    fact_count = await repo.count()
    links = await runtime.memory.db.conn.execute_fetchall("SELECT COUNT(*) FROM fact_links")
    link_count = links[0][0] if links else 0
    observation_count = await obs_repo.count()

    await runtime.memory.db.conn.execute("DELETE FROM observations_vec")
    await runtime.memory.db.conn.execute("DELETE FROM observations")
    await runtime.memory.db.conn.execute("DELETE FROM entity_refs")
    await runtime.memory.db.conn.execute("DELETE FROM fact_links")
    await runtime.memory.db.conn.execute("DELETE FROM facts_vec")
    await runtime.memory.db.conn.execute("DELETE FROM facts")
    await runtime.memory.db.conn.commit()

    return {
        "status": "cleared",
        "deleted": {"facts": fact_count, "links": link_count, "observations": observation_count},
    }


@router.get("/observations")
async def get_observations(limit: int = 50):
    runtime = _require_memory()
    obs_repo = ObservationRepository(runtime.memory.db.conn)

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
    obs_repo = ObservationRepository(runtime.memory.db.conn)
    fact_repo = FactRepository(runtime.memory.db.conn)

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
    repo = FactRepository(runtime.memory.db.conn)
    obs_repo = ObservationRepository(runtime.memory.db.conn)

    fact_count = await repo.count()
    links = await runtime.memory.db.conn.execute_fetchall("SELECT COUNT(*) FROM fact_links")
    link_count = links[0][0] if links else 0
    observation_count = await obs_repo.count()

    return {
        "fact_count": fact_count,
        "link_count": link_count,
        "observation_count": observation_count,
        "sources": runtime.get_available_sources(),
    }
