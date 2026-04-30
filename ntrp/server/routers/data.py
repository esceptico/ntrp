from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from ntrp.memory.models import Fact
from ntrp.memory.service import MemoryService
from ntrp.server.deps import require_memory
from ntrp.server.schemas import (
    FactKindReviewSuggestionRequest,
    MemoryPruneDryRunRequest,
    UpdateFactMetadataRequest,
    UpdateFactRequest,
    UpdateObservationRequest,
)

router = APIRouter(tags=["data"])


def _fact_payload(fact: Fact) -> dict:
    return {
        "id": fact.id,
        "text": fact.text,
        "source_type": fact.source_type,
        "source_ref": fact.source_ref,
        "created_at": fact.created_at.isoformat(),
        "happened_at": fact.happened_at.isoformat() if fact.happened_at else None,
        "last_accessed_at": fact.last_accessed_at.isoformat(),
        "access_count": fact.access_count,
        "consolidated_at": fact.consolidated_at.isoformat() if fact.consolidated_at else None,
        "archived_at": fact.archived_at.isoformat() if fact.archived_at else None,
        "kind": fact.kind,
        "salience": fact.salience,
        "confidence": fact.confidence,
        "expires_at": fact.expires_at.isoformat() if fact.expires_at else None,
        "pinned_at": fact.pinned_at.isoformat() if fact.pinned_at else None,
        "superseded_by_fact_id": fact.superseded_by_fact_id,
    }


@router.get("/facts")
async def get_facts(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    svc: MemoryService = Depends(require_memory),
):
    facts, total = await svc.facts.list_recent(limit=limit, offset=offset)
    return {
        "facts": [_fact_payload(f) for f in facts],
        "total": total,
    }


@router.get("/memory/facts/kind-review")
async def get_fact_kind_review(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    svc: MemoryService = Depends(require_memory),
):
    facts, total = await svc.facts.list_kind_review(limit=limit, offset=offset)
    return {
        "facts": [_fact_payload(f) for f in facts],
        "total": total,
    }


@router.post("/memory/facts/kind-review/suggestions")
async def suggest_fact_kind_review(
    request: FactKindReviewSuggestionRequest,
    svc: MemoryService = Depends(require_memory),
):
    suggestions, total = await svc.facts.suggest_kind_review(
        fact_ids=request.fact_ids,
        limit=request.limit,
        offset=request.offset,
    )
    return {
        "suggestions": [
            {
                "fact": _fact_payload(fact),
                "suggestion": {
                    "kind": suggestion.kind,
                    "salience": suggestion.salience,
                    "confidence": suggestion.confidence,
                    "expires_at": suggestion.expires_at.isoformat() if suggestion.expires_at else None,
                    "reason": suggestion.reason,
                },
            }
            for fact, suggestion in suggestions
        ],
        "total_reviewable": total,
    }


@router.get("/memory/supersession/candidates")
async def get_supersession_candidates(
    limit: int = Query(default=100, ge=1, le=500),
    svc: MemoryService = Depends(require_memory),
):
    candidates = await svc.facts.list_supersession_candidates(limit=limit)
    return {
        "candidates": [
            {
                "kind": row["kind"],
                "entity": row["entity"],
                "older_fact": _fact_payload(row["older_fact"]),
                "newer_fact": _fact_payload(row["newer_fact"]),
                "reason": row["reason"],
            }
            for row in candidates
        ],
        "total": len(candidates),
    }


@router.get("/facts/{fact_id}")
async def get_fact_details(fact_id: int, svc: MemoryService = Depends(require_memory)):
    try:
        fact, entity_refs = await svc.facts.get(fact_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Fact not found")

    return {
        "fact": _fact_payload(fact),
        "entities": [{"name": e.name, "entity_id": e.entity_id} for e in entity_refs],
        "linked_facts": [],
    }


@router.patch("/facts/{fact_id}")
async def update_fact(fact_id: int, request: UpdateFactRequest, svc: MemoryService = Depends(require_memory)):
    try:
        fact, entity_refs = await svc.facts.update(fact_id, request.text)
    except KeyError:
        raise HTTPException(status_code=404, detail="Fact not found")

    return {
        "fact": _fact_payload(fact),
        "entity_refs": entity_refs,
    }


@router.patch("/facts/{fact_id}/metadata")
async def update_fact_metadata(
    fact_id: int,
    request: UpdateFactMetadataRequest,
    svc: MemoryService = Depends(require_memory),
):
    updates: dict[str, object] = {}
    fields = request.model_fields_set
    if "kind" in fields and request.kind is not None:
        updates["kind"] = request.kind
    if "salience" in fields and request.salience is not None:
        updates["salience"] = request.salience
    if "confidence" in fields and request.confidence is not None:
        updates["confidence"] = request.confidence
    if "expires_at" in fields:
        updates["expires_at"] = request.expires_at
    if "pinned" in fields:
        updates["pinned_at"] = datetime.now(UTC) if request.pinned else None
    if "superseded_by_fact_id" in fields:
        updates["superseded_by_fact_id"] = request.superseded_by_fact_id

    try:
        fact = await svc.facts.update_metadata(fact_id, updates)
    except KeyError:
        raise HTTPException(status_code=404, detail="Fact not found")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return {"fact": _fact_payload(fact)}


@router.delete("/facts/{fact_id}")
async def delete_fact(fact_id: int, svc: MemoryService = Depends(require_memory)):
    try:
        cascaded = await svc.facts.delete(fact_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Fact not found")

    return {
        "status": "deleted",
        "fact_id": fact_id,
        "cascaded": cascaded,
    }


@router.get("/observations")
async def get_observations(
    limit: int = Query(default=50, ge=1, le=500),
    svc: MemoryService = Depends(require_memory),
):
    observations = await svc.observations.list_recent(limit=limit)
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
async def get_observation_details(observation_id: int, svc: MemoryService = Depends(require_memory)):
    try:
        obs, facts = await svc.observations.get(observation_id)
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
async def update_observation(
    observation_id: int, request: UpdateObservationRequest, svc: MemoryService = Depends(require_memory)
):
    try:
        obs = await svc.observations.update(observation_id, request.summary)
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
async def delete_observation(observation_id: int, svc: MemoryService = Depends(require_memory)):
    try:
        await svc.observations.delete(observation_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Observation not found")

    return {
        "status": "deleted",
        "observation_id": observation_id,
    }


@router.get("/dreams")
async def get_dreams(
    limit: int = Query(default=50, ge=1, le=500),
    svc: MemoryService = Depends(require_memory),
):
    dreams = await svc.dreams.list_recent(limit=limit)
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
async def get_dream_details(dream_id: int, svc: MemoryService = Depends(require_memory)):
    try:
        dream, source_facts = await svc.dreams.get(dream_id)
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
async def delete_dream(dream_id: int, svc: MemoryService = Depends(require_memory)):
    try:
        await svc.dreams.delete(dream_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Dream not found")

    return {"status": "deleted", "dream_id": dream_id}


@router.get("/stats")
async def get_stats(svc: MemoryService = Depends(require_memory)):
    return await svc.stats()


@router.get("/memory/audit")
async def get_memory_audit(svc: MemoryService = Depends(require_memory)):
    return await svc.audit()


@router.get("/memory/profile")
async def get_memory_profile(
    limit: int = Query(default=6, ge=1, le=50),
    svc: MemoryService = Depends(require_memory),
):
    facts = await svc.profile(limit=limit)
    return {"facts": [_fact_payload(f) for f in facts]}


@router.post("/memory/prune/dry-run")
async def prune_memory_dry_run(request: MemoryPruneDryRunRequest, svc: MemoryService = Depends(require_memory)):
    return await svc.prune_observations_dry_run(
        older_than_days=request.older_than_days,
        max_sources=request.max_sources,
        limit=request.limit,
    )


@router.post("/memory/clear")
async def clear_memory(svc: MemoryService = Depends(require_memory)):
    deleted = await svc.clear()
    return {"status": "cleared", "deleted": deleted}


@router.post("/memory/observations/clear")
async def clear_observations(svc: MemoryService = Depends(require_memory)):
    result = await svc.clear_observations()
    return {"status": "cleared", **result}
