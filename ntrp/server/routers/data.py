from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from ntrp.memory.formatting import format_memory_context, format_session_memory
from ntrp.memory.models import (
    Fact,
    FactKind,
    LearningCandidate,
    LearningEvent,
    MemoryAccessEvent,
    MemoryEvent,
    Observation,
    SourceType,
)
from ntrp.memory.profile_policy import ProfilePolicyItem
from ntrp.memory.service import MemoryService
from ntrp.server.deps import require_memory
from ntrp.server.schemas import (
    CreateLearningCandidateRequest,
    CreateLearningEventRequest,
    FactKindReviewSuggestionRequest,
    MemoryPruneApplyRequest,
    MemoryPruneDryRunRequest,
    MemoryRecallInspectRequest,
    MemoryRepairEmbeddingsRequest,
    ProposeLearningCandidatesRequest,
    UpdateFactMetadataRequest,
    UpdateFactRequest,
    UpdateLearningCandidateStatusRequest,
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


def _observation_payload(observation: Observation) -> dict:
    return {
        "id": observation.id,
        "summary": observation.summary,
        "evidence_count": observation.evidence_count,
        "access_count": observation.access_count,
        "created_at": observation.created_at.isoformat(),
        "updated_at": observation.updated_at.isoformat(),
        "last_accessed_at": observation.last_accessed_at.isoformat(),
        "archived_at": observation.archived_at.isoformat() if observation.archived_at else None,
        "created_by": observation.created_by,
        "policy_version": observation.policy_version,
    }


def _memory_event_payload(event: MemoryEvent) -> dict:
    return {
        "id": event.id,
        "created_at": event.created_at.isoformat(),
        "actor": event.actor,
        "action": event.action,
        "target_type": event.target_type,
        "target_id": event.target_id,
        "source_type": event.source_type,
        "source_ref": event.source_ref,
        "reason": event.reason,
        "policy_version": event.policy_version,
        "details": event.details,
    }


def _memory_access_event_payload(event: MemoryAccessEvent) -> dict:
    return {
        "id": event.id,
        "created_at": event.created_at.isoformat(),
        "source": event.source,
        "query": event.query,
        "retrieved_fact_ids": event.retrieved_fact_ids,
        "retrieved_observation_ids": event.retrieved_observation_ids,
        "injected_fact_ids": event.injected_fact_ids,
        "injected_observation_ids": event.injected_observation_ids,
        "omitted_fact_ids": event.omitted_fact_ids,
        "omitted_observation_ids": event.omitted_observation_ids,
        "bundled_fact_ids": event.bundled_fact_ids,
        "formatted_chars": event.formatted_chars,
        "policy_version": event.policy_version,
        "details": event.details,
    }


def _profile_policy_item_payload(item: ProfilePolicyItem) -> dict:
    return {
        "fact": _fact_payload(item.fact),
        "reasons": list(item.reasons),
        "recommendation": item.recommendation,
    }


def _learning_event_payload(event: LearningEvent) -> dict:
    return {
        "id": event.id,
        "created_at": event.created_at.isoformat(),
        "source_type": event.source_type,
        "source_id": event.source_id,
        "scope": event.scope,
        "signal": event.signal,
        "evidence_ids": event.evidence_ids,
        "outcome": event.outcome,
        "details": event.details,
    }


def _learning_candidate_payload(candidate: LearningCandidate) -> dict:
    return {
        "id": candidate.id,
        "created_at": candidate.created_at.isoformat(),
        "updated_at": candidate.updated_at.isoformat(),
        "status": candidate.status,
        "change_type": candidate.change_type,
        "target_key": candidate.target_key,
        "proposal": candidate.proposal,
        "rationale": candidate.rationale,
        "evidence_event_ids": candidate.evidence_event_ids,
        "expected_metric": candidate.expected_metric,
        "policy_version": candidate.policy_version,
        "applied_at": candidate.applied_at.isoformat() if candidate.applied_at else None,
        "reverted_at": candidate.reverted_at.isoformat() if candidate.reverted_at else None,
        "details": candidate.details,
    }


@router.get("/facts")
async def get_facts(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    kind: FactKind | None = None,
    source_type: SourceType | None = None,
    status: Literal["active", "archived", "superseded", "expired", "temporary", "pinned", "all"] = "active",
    accessed: Literal["never", "used"] | None = None,
    entity: str | None = Query(default=None, min_length=1),
    svc: MemoryService = Depends(require_memory),
):
    facts, total = await svc.facts.list_filtered(
        limit=limit,
        offset=offset,
        kind=kind,
        source_type=source_type,
        status=status,
        accessed=accessed,
        entity=entity,
    )
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
    offset: int = Query(default=0, ge=0),
    status: Literal["active", "archived", "all"] = "active",
    accessed: Literal["never", "used"] | None = None,
    min_sources: int | None = Query(default=None, ge=0),
    max_sources: int | None = Query(default=None, ge=0),
    svc: MemoryService = Depends(require_memory),
):
    observations, total = await svc.observations.list_filtered(
        limit=limit,
        offset=offset,
        status=status,
        accessed=accessed,
        min_sources=min_sources,
        max_sources=max_sources,
    )
    return {
        "observations": [_observation_payload(o) for o in observations],
        "total": total,
    }


@router.get("/observations/{observation_id}")
async def get_observation_details(observation_id: int, svc: MemoryService = Depends(require_memory)):
    try:
        obs, facts, source_fact_ids, missing_source_fact_ids = await svc.observations.get(observation_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Observation not found")

    return {
        "observation": _observation_payload(obs),
        "supporting_facts": [_fact_payload(f) for f in facts],
        "source_fact_ids": source_fact_ids,
        "missing_source_fact_ids": missing_source_fact_ids,
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
        "observation": _observation_payload(obs),
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


@router.get("/memory/events")
async def get_event_log(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    target_type: str | None = Query(default=None, min_length=1),
    target_id: int | None = Query(default=None, ge=1),
    action: str | None = Query(default=None, min_length=1),
    svc: MemoryService = Depends(require_memory),
):
    events = await svc.events.list_recent(
        limit=limit,
        offset=offset,
        target_type=target_type,
        target_id=target_id,
        action=action,
    )
    return {"events": [_memory_event_payload(event) for event in events]}


@router.get("/memory/access/events")
async def get_memory_access_events(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    source: str | None = Query(default=None, min_length=1),
    svc: MemoryService = Depends(require_memory),
):
    events = await svc.access_events.list_recent(limit=limit, offset=offset, source=source)
    return {"events": [_memory_access_event_payload(event) for event in events]}


@router.get("/memory/injection-policy/preview")
async def get_memory_injection_policy_preview(
    limit: int = Query(default=100, ge=1, le=500),
    char_budget: int = Query(default=3000, ge=1, le=50000),
    svc: MemoryService = Depends(require_memory),
):
    return await svc.access_events.policy_preview(limit=limit, char_budget=char_budget)


@router.get("/memory/profile")
async def get_memory_profile(
    limit: int = Query(default=6, ge=1, le=50),
    svc: MemoryService = Depends(require_memory),
):
    facts = await svc.profile(limit=limit)
    return {"facts": [_fact_payload(f) for f in facts]}


@router.get("/memory/profile/policy/preview")
async def get_memory_profile_policy_preview(
    limit: int = Query(default=100, ge=1, le=500),
    profile_limit: int = Query(default=20, ge=1, le=100),
    char_budget: int = Query(default=1200, ge=1, le=20000),
    fact_char_budget: int = Query(default=220, ge=1, le=5000),
    review_access_count: int = Query(default=3, ge=1, le=1000),
    svc: MemoryService = Depends(require_memory),
):
    preview = await svc.profile_policy_preview(
        limit=limit,
        profile_limit=profile_limit,
        char_budget=char_budget,
        fact_char_budget=fact_char_budget,
        review_access_count=review_access_count,
    )
    return {
        "policy": {
            "version": preview.policy_version,
            "char_budget": preview.char_budget,
            "fact_char_budget": preview.fact_char_budget,
        },
        "summary": {
            "current_count": preview.current_count,
            "current_chars": preview.current_chars,
            "over_budget": preview.over_budget,
            "candidates": len(preview.candidates),
            "issues": len(preview.issues),
        },
        "candidates": [_profile_policy_item_payload(item) for item in preview.candidates],
        "issues": [_profile_policy_item_payload(item) for item in preview.issues],
    }


@router.post("/memory/learning/events")
async def create_learning_event(
    request: CreateLearningEventRequest,
    svc: MemoryService = Depends(require_memory),
):
    event = await svc.learning.create_event(
        source_type=request.source_type,
        source_id=request.source_id,
        scope=request.scope,
        signal=request.signal,
        evidence_ids=request.evidence_ids,
        outcome=request.outcome,
        details=request.details,
    )
    return {"event": _learning_event_payload(event)}


@router.get("/memory/learning/events")
async def get_learning_events(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    scope: str | None = Query(default=None, min_length=1),
    source_type: str | None = Query(default=None, min_length=1),
    svc: MemoryService = Depends(require_memory),
):
    events = await svc.learning.list_events(
        limit=limit,
        offset=offset,
        scope=scope,
        source_type=source_type,
    )
    return {"events": [_learning_event_payload(event) for event in events]}


@router.post("/memory/learning/candidates")
async def create_learning_candidate(
    request: CreateLearningCandidateRequest,
    svc: MemoryService = Depends(require_memory),
):
    try:
        candidate = await svc.learning.create_candidate(
            change_type=request.change_type,
            target_key=request.target_key,
            proposal=request.proposal,
            rationale=request.rationale,
            evidence_event_ids=request.evidence_event_ids,
            expected_metric=request.expected_metric,
            policy_version=request.policy_version,
            status=request.status,
            details=request.details,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"candidate": _learning_candidate_payload(candidate)}


@router.get("/memory/learning/candidates")
async def get_learning_candidates(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    status: str | None = Query(default=None, min_length=1),
    change_type: str | None = Query(default=None, min_length=1),
    svc: MemoryService = Depends(require_memory),
):
    try:
        candidates = await svc.learning.list_candidates(
            limit=limit,
            offset=offset,
            status=status,
            change_type=change_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"candidates": [_learning_candidate_payload(candidate) for candidate in candidates]}


@router.patch("/memory/learning/candidates/{candidate_id}/status")
async def update_learning_candidate_status(
    candidate_id: int,
    request: UpdateLearningCandidateStatusRequest,
    svc: MemoryService = Depends(require_memory),
):
    try:
        candidate = await svc.learning.update_candidate_status(candidate_id, request.status)
    except KeyError:
        raise HTTPException(status_code=404, detail="Learning candidate not found")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"candidate": _learning_candidate_payload(candidate)}


@router.post("/memory/learning/propose")
async def propose_learning_candidates(
    request: ProposeLearningCandidatesRequest,
    svc: MemoryService = Depends(require_memory),
):
    result = await svc.learning.propose_review_candidates(
        access_limit=request.access_limit,
        injection_char_budget=request.injection_char_budget,
        profile_limit=request.profile_limit,
        prune_older_than_days=request.prune_older_than_days,
        prune_max_sources=request.prune_max_sources,
        prune_limit=request.prune_limit,
        skill_event_limit=request.skill_event_limit,
        include_skill_notes=request.include_skill_notes,
    )
    return {
        "proposals_considered": result.proposals_considered,
        "created_events": [_learning_event_payload(event) for event in result.created_events],
        "created_candidates": [_learning_candidate_payload(candidate) for candidate in result.created_candidates],
        "skipped_candidates": [_learning_candidate_payload(candidate) for candidate in result.skipped_candidates],
    }


@router.post("/memory/recall/inspect")
async def inspect_memory_recall(request: MemoryRecallInspectRequest, svc: MemoryService = Depends(require_memory)):
    context, session_memory = await svc.inspect_recall(query=request.query, limit=request.limit)
    return {
        "query": request.query,
        "limit": request.limit,
        "formatted_recall": format_memory_context(
            query_facts=context.facts,
            query_observations=context.observations,
            bundled_sources=context.bundled_sources,
        ),
        "formatted_session": format_session_memory(
            profile_facts=session_memory.profile_facts,
            observations=session_memory.observations,
            user_facts=session_memory.user_facts,
        ),
        "facts": [_fact_payload(f) for f in context.facts],
        "observations": [_observation_payload(o) for o in context.observations],
        "bundled_sources": {
            str(observation_id): [_fact_payload(f) for f in facts]
            for observation_id, facts in context.bundled_sources.items()
        },
        "session": {
            "profile_facts": [_fact_payload(f) for f in session_memory.profile_facts],
            "observations": [_observation_payload(o) for o in session_memory.observations],
            "user_facts": [_fact_payload(f) for f in session_memory.user_facts],
        },
    }


@router.post("/memory/repair/embeddings")
async def repair_memory_embeddings(
    request: MemoryRepairEmbeddingsRequest,
    svc: MemoryService = Depends(require_memory),
):
    return await svc.repair_missing_embeddings(limit=request.limit, apply=request.apply)


@router.post("/memory/prune/dry-run")
async def prune_memory_dry_run(request: MemoryPruneDryRunRequest, svc: MemoryService = Depends(require_memory)):
    return await svc.prune_observations_dry_run(
        older_than_days=request.older_than_days,
        max_sources=request.max_sources,
        limit=request.limit,
    )


@router.post("/memory/prune/apply")
async def apply_memory_prune(request: MemoryPruneApplyRequest, svc: MemoryService = Depends(require_memory)):
    if not request.all_matching and not request.observation_ids:
        raise HTTPException(status_code=422, detail="observation_ids required unless all_matching is true")
    return await svc.prune_observations_apply(
        observation_ids=request.observation_ids,
        all_matching=request.all_matching,
        older_than_days=request.older_than_days,
        max_sources=request.max_sources,
    )


@router.post("/memory/clear")
async def clear_memory(svc: MemoryService = Depends(require_memory)):
    deleted = await svc.clear()
    return {"status": "cleared", "deleted": deleted}


@router.post("/memory/observations/clear")
async def clear_observations(svc: MemoryService = Depends(require_memory)):
    result = await svc.clear_observations()
    return {"status": "cleared", **result}
