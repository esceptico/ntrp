from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from ntrp.knowledge import (
    KnowledgeArtifactRenderRequest,
    KnowledgeFactConsolidationCommitRequest,
    KnowledgeFeedbackRequest,
    KnowledgeObjectCreate,
    KnowledgeObjectStatus,
    KnowledgeObjectType,
    KnowledgeObjectUpdate,
    KnowledgeProfileSynthesisRequest,
    KnowledgePruneRequest,
    KnowledgePublishRequest,
    KnowledgeReflectRequest,
    KnowledgeUsageOutcomeRequest,
    KnowledgeWorkflowClusterReviewRequest,
)
from ntrp.knowledge.processors import KnowledgeProcessorService
from ntrp.knowledge.skill_promotions import KnowledgeSkillPromotionService
from ntrp.knowledge.usage_events import summarize_activation_usage_events
from ntrp.memory.activation import MemoryActivationRequest
from ntrp.memory.service import MemoryService
from ntrp.server.deps import require_knowledge_runtime, require_memory, require_skill_service
from ntrp.server.response_cache import AsyncResponseCache
from ntrp.server.runtime.knowledge import KnowledgeRuntime
from ntrp.skills.service import SkillService

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


_HEAVY_ENDPOINT_CACHE = AsyncResponseCache(ttl_seconds=60.0)


def _invalidate_workflow_cluster_cache(svc: MemoryService) -> None:
    _HEAVY_ENDPOINT_CACHE.invalidate(prefix="workflow_clusters", scope=id(svc))


async def _fact_consolidation_payload(svc: MemoryService, *, limit: int, min_confidence: float, max_proposals: int) -> dict[str, Any]:
    result = await svc.propose_fact_consolidation(
        limit=limit,
        min_confidence=min_confidence,
        max_proposals=max_proposals,
    )
    payload = result.model_dump()
    ids: set[int] = set()
    for proposal in result.proposals:
        ids.add(proposal.canonical_object_id)
        ids.update(proposal.duplicate_object_ids)
    objects_by_id = await svc.knowledge_objects.get_batch(sorted(ids)) if ids else {}
    enriched: list[dict[str, Any]] = []
    for proposal in result.proposals:
        item = proposal.model_dump()
        canonical = objects_by_id.get(proposal.canonical_object_id)
        duplicates = [objects_by_id.get(object_id) for object_id in proposal.duplicate_object_ids]
        item.update(
            {
                "canonical_id": proposal.canonical_object_id,
                "canonical_title": canonical.title if canonical else f"knowledge:{proposal.canonical_object_id}",
                "canonical_text": canonical.text if canonical else "",
                "duplicate_ids": proposal.duplicate_object_ids,
                "duplicate_titles": [
                    duplicate.title if duplicate else f"knowledge:{object_id}"
                    for object_id, duplicate in zip(proposal.duplicate_object_ids, duplicates, strict=False)
                ],
            }
        )
        enriched.append(item)
    payload["proposals"] = enriched
    return payload


def _knowledge_surface_description(object_type: KnowledgeObjectType) -> str:
    return {
        KnowledgeObjectType.FACT: "durable source-backed facts",
        KnowledgeObjectType.LESSON: "reusable conclusions and preferences",
        KnowledgeObjectType.ARTIFACT: "important reusable outputs",
        KnowledgeObjectType.MEMORY_EPISODE: "short rolling conversation episodes",
        KnowledgeObjectType.OUTCOME_FEEDBACK: "feedback captured from memory outcomes",
    }.get(object_type, object_type.value.replace("_", " "))


def _knowledge_surface_name(object_type: KnowledgeObjectType) -> str:
    return {
        KnowledgeObjectType.MEMORY_EPISODE: "Episodes",
        KnowledgeObjectType.OUTCOME_FEEDBACK: "Outcome feedback",
    }.get(object_type, object_type.value.replace("_", " ").title())


def _knowledge_summary_counts_for_type(counts: Any, object_type: KnowledgeObjectType) -> dict[str, int]:
    """Normalize summary counts from both repository and legacy service shapes.

    Supported shapes:
    - {(KnowledgeObjectType.FACT, KnowledgeObjectStatus.ACTIVE): 3}
    - {"fact": {"active": 3}}
    """
    if not isinstance(counts, dict):
        return {}

    nested = counts.get(object_type)
    if nested is None:
        nested = counts.get(object_type.value)
    if isinstance(nested, dict):
        normalized: dict[str, int] = {}
        for raw_status, raw_count in nested.items():
            status_value = raw_status.value if isinstance(raw_status, KnowledgeObjectStatus) else str(raw_status)
            try:
                count = int(raw_count)
            except (TypeError, ValueError):
                continue
            if count:
                normalized[status_value] = count
        return normalized

    normalized: dict[str, int] = {}
    for raw_key, raw_count in counts.items():
        if not isinstance(raw_key, tuple) or len(raw_key) != 2:
            continue
        raw_type, raw_status = raw_key
        type_value = raw_type.value if isinstance(raw_type, KnowledgeObjectType) else str(raw_type)
        if type_value != object_type.value:
            continue
        status_value = raw_status.value if isinstance(raw_status, KnowledgeObjectStatus) else str(raw_status)
        try:
            count = int(raw_count)
        except (TypeError, ValueError):
            continue
        if count:
            normalized[status_value] = count
    return normalized


@router.get("/summary")
async def get_knowledge_summary(svc: MemoryService = Depends(require_memory)):
    counts = await svc.knowledge_objects.count_by_type_and_status()
    surface_types = [
        KnowledgeObjectType.FACT,
        KnowledgeObjectType.LESSON,
        KnowledgeObjectType.ARTIFACT,
        KnowledgeObjectType.MEMORY_EPISODE,
        KnowledgeObjectType.OUTCOME_FEEDBACK,
    ]
    surfaces = []
    for object_type in surface_types:
        counts_by_status = _knowledge_summary_counts_for_type(counts, object_type)
        active_count = counts_by_status.get(KnowledgeObjectStatus.ACTIVE.value, 0)
        surfaces.append(
            {
                "name": _knowledge_surface_name(object_type),
                "object_type": object_type.value,
                "count": active_count,
                "description": _knowledge_surface_description(object_type),
                "counts_by_status": counts_by_status,
            }
        )
    return {
        "surfaces": surfaces,
        "next_actions": [],
        "policy_version": "knowledge.summary.v1",
    }


@router.get("/objects")
async def list_knowledge_objects(
    object_type: KnowledgeObjectType | None = None,
    status: KnowledgeObjectStatus | None = None,
    query: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    svc: MemoryService = Depends(require_memory),
):
    objects = await svc.knowledge_objects.list(
        object_type=object_type,
        status=status,
        query=query,
        limit=limit,
        offset=offset,
    )
    return {"objects": [obj.model_dump() for obj in objects]}


@router.post("/objects")
async def create_knowledge_object(
    request: KnowledgeObjectCreate,
    svc: MemoryService = Depends(require_memory),
):
    return {"object": (await svc.knowledge_objects.create(request)).model_dump()}


@router.patch("/objects/{object_id}")
async def update_knowledge_object(
    object_id: int,
    request: KnowledgeObjectUpdate,
    svc: MemoryService = Depends(require_memory),
):
    return {"object": (await svc.knowledge_objects.update(object_id, request)).model_dump()}


@router.get("/objects/{object_id}/sources")
async def get_knowledge_object_sources(
    object_id: int,
    svc: MemoryService = Depends(require_memory),
):
    try:
        return (await svc.knowledge_objects.source_trace(object_id)).model_dump()
    except KeyError as exc:
        detail = str(exc.args[0]) if exc.args else f"Knowledge object {object_id} not found"
        raise HTTPException(status_code=404, detail=detail) from exc


@router.post("/processors/reflect")
async def reflect_knowledge(
    request: KnowledgeReflectRequest,
    svc: MemoryService = Depends(require_memory),
):
    return (await KnowledgeProcessorService(svc).reflect(request)).model_dump()


@router.post("/processors/prune")
async def prune_knowledge(
    request: KnowledgePruneRequest,
    svc: MemoryService = Depends(require_memory),
):
    return (await KnowledgeProcessorService(svc).prune_retention(request)).model_dump()


@router.post("/processors/profiles")
async def synthesize_knowledge_profiles(
    request: KnowledgeProfileSynthesisRequest,
    svc: MemoryService = Depends(require_memory),
):
    return (await KnowledgeProcessorService(svc).synthesize_profiles(request)).model_dump()


@router.post("/processors/skill-promotions")
async def propose_skill_promotions(
    limit: int = 100,
    min_successes: int = 3,
    svc: MemoryService = Depends(require_memory),
):
    result = await KnowledgeProcessorService(svc).propose_skill_promotions(
        limit=limit,
        min_successes=min_successes,
    )
    _invalidate_workflow_cluster_cache(svc)
    return result.model_dump()


@router.get("/processors/workflow-clusters")
async def workflow_clusters(
    limit: int = 100,
    min_successes: int = 3,
    include_below_threshold: bool = False,
    refresh: bool = False,
    svc: MemoryService = Depends(require_memory),
):
    bounded_limit = max(1, min(limit, 10_000))
    bounded_min_successes = max(1, min(min_successes, 100))

    async def load() -> dict[str, Any]:
        return (
            await KnowledgeProcessorService(svc).workflow_clusters(
                limit=bounded_limit,
                min_successes=bounded_min_successes,
                include_below_threshold=include_below_threshold,
            )
        ).model_dump()

    return await _HEAVY_ENDPOINT_CACHE.get_or_load(
        key=(
            "workflow_clusters",
            id(svc),
            bounded_limit,
            bounded_min_successes,
            include_below_threshold,
        ),
        refresh=refresh,
        loader=load,
    )


@router.post("/processors/workflow-clusters/{cluster_id}/review")
async def review_workflow_cluster(
    cluster_id: str,
    request: KnowledgeWorkflowClusterReviewRequest,
    svc: MemoryService = Depends(require_memory),
):
    try:
        marker = await KnowledgeSkillPromotionService(svc).mark_workflow_cluster_review(
            cluster_id,
            status=request.status,
            reason=request.reason,
        )
    except KeyError as exc:
        detail = str(exc.args[0]) if exc.args else f"Workflow cluster {cluster_id} not found"
        raise HTTPException(status_code=404, detail=detail) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _invalidate_workflow_cluster_cache(svc)
    return {"object": marker.model_dump()}


@router.post("/skill-promotions/{object_id}/create")
async def create_skill_from_promotion(
    object_id: int,
    svc: MemoryService = Depends(require_memory),
    skill_service: SkillService = Depends(require_skill_service),
):
    try:
        obj = await KnowledgeSkillPromotionService(svc).create_skill_from_candidate(object_id, skill_service)
    except KeyError as exc:
        detail = str(exc.args[0]) if exc.args else f"Knowledge object {object_id} not found"
        raise HTTPException(status_code=404, detail=detail) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _invalidate_workflow_cluster_cache(svc)
    return {
        "object": obj.model_dump(),
        "skill": {
            "name": obj.metadata.get("skill_created_name"),
            "path": obj.metadata.get("skill_created_path"),
        },
    }


@router.get("/processors/health")
async def knowledge_health(refresh: bool = False, svc: MemoryService = Depends(require_memory)):
    async def load() -> dict[str, Any]:
        return (await KnowledgeProcessorService(svc).health()).model_dump()

    return await _HEAVY_ENDPOINT_CACHE.get_or_load(
        key=("processor_health", id(svc)),
        refresh=refresh,
        loader=load,
    )


@router.get("/facts/consolidation")
async def propose_fact_consolidation(
    limit: int = 1_000,
    min_confidence: float = 0.86,
    max_proposals: int = 50,
    refresh: bool = False,
    svc: MemoryService = Depends(require_memory),
):
    bounded_limit = max(1, min(limit, 10_000))
    bounded_confidence = max(0.0, min(min_confidence, 1.0))
    bounded_max_proposals = max(1, min(max_proposals, 200))

    async def load() -> dict[str, Any]:
        return await _fact_consolidation_payload(
            svc,
            limit=bounded_limit,
            min_confidence=bounded_confidence,
            max_proposals=bounded_max_proposals,
        )

    return await _HEAVY_ENDPOINT_CACHE.get_or_load(
        key=("fact_consolidation", id(svc), bounded_limit, bounded_confidence, bounded_max_proposals),
        refresh=refresh,
        loader=load,
    )


@router.post("/facts/consolidation/commit")
async def commit_fact_consolidation(
    request: KnowledgeFactConsolidationCommitRequest,
    svc: MemoryService = Depends(require_memory),
):
    result = await svc.commit_fact_consolidation_proposal(request.proposal, apply=True)
    _HEAVY_ENDPOINT_CACHE.invalidate(prefix="fact_consolidation", scope=id(svc))
    return result.model_dump()


@router.post("/maintenance/backfill-embeddings")
async def backfill_knowledge_embeddings(
    limit: int = 1_000,
    batch_size: int = 100,
    apply: bool = False,
    svc: MemoryService = Depends(require_memory),
):
    return await svc.knowledge_objects.backfill_embeddings(limit=limit, batch_size=batch_size, apply=apply)


@router.post("/artifacts/render")
async def render_knowledge_artifact(
    request: KnowledgeArtifactRenderRequest,
    svc: MemoryService = Depends(require_memory),
):
    return {"object": (await KnowledgeProcessorService(svc).render_artifact(request)).model_dump()}


@router.post("/artifacts/publish")
async def publish_knowledge_artifact(
    request: KnowledgePublishRequest,
    svc: MemoryService = Depends(require_memory),
):
    return {"receipt": (await KnowledgeProcessorService(svc).publish(request)).model_dump()}


@router.post("/feedback")
async def record_knowledge_feedback(
    request: KnowledgeFeedbackRequest,
    svc: MemoryService = Depends(require_memory),
):
    return {"object": (await KnowledgeProcessorService(svc).feedback(request)).model_dump()}


@router.get("/activation/usage-events")
async def list_activation_usage_events(
    limit: int = 100,
    offset: int = 0,
    source: str | None = "knowledge_activation",
    svc: MemoryService = Depends(require_memory),
):
    bounded_limit = max(1, min(limit, 500))
    bounded_offset = max(0, offset)
    events = await svc.access_events.list_recent(
        limit=bounded_limit,
        offset=bounded_offset,
        source=source or None,
    )
    return {"events": [event.model_dump() for event in events]}


@router.get("/activation/usage-summary")
async def summarize_activation_usage(
    limit: int = 500,
    offset: int = 0,
    max_objects: int = 100,
    source: str | None = "knowledge_activation",
    svc: MemoryService = Depends(require_memory),
):
    bounded_limit = max(1, min(limit, 500))
    bounded_offset = max(0, offset)
    bounded_max_objects = max(1, min(max_objects, 500))
    events = await svc.access_events.list_recent(
        limit=bounded_limit,
        offset=bounded_offset,
        source=source or None,
    )
    summaries = summarize_activation_usage_events(events)[:bounded_max_objects]
    objects_by_id = await svc.knowledge_objects.get_batch([summary.object_id for summary in summaries])
    hydrated = []
    for summary in summaries:
        obj = objects_by_id.get(summary.object_id)
        hydrated.append(
            summary.model_copy(
                update={
                    "object_type": obj.object_type if obj else None,
                    "object_status": obj.status if obj else None,
                    "object_title": obj.title if obj else None,
                }
            )
        )
    return {
        "objects": [summary.model_dump() for summary in hydrated],
        "events_scanned": len(events),
        "policy_version": "knowledge.activation.usage_summary.v1",
    }


@router.post("/activation/usage-events/{event_id}/outcome")
async def record_activation_usage_event_outcome(
    event_id: int,
    request: KnowledgeUsageOutcomeRequest,
    svc: MemoryService = Depends(require_memory),
):
    user_corrected_answer = request.user_corrected_answer
    if user_corrected_answer is None:
        signal = request.signal.lower()
        outcome = request.outcome.lower()
        user_corrected_answer = signal == "corrected" or outcome in {"corrected", "harmful", "task_failure"}

    requested_target_ids = sorted(set(request.target_object_ids)) if request.target_object_ids is not None else None
    existing_event = await svc.access_events.get(event_id)
    if existing_event is None:
        raise HTTPException(status_code=404, detail=f"Memory access event {event_id} not found")

    allowed_target_ids = {
        *list(existing_event.retrieved_fact_ids or []),
        *list(existing_event.injected_fact_ids or []),
        *list(existing_event.omitted_fact_ids or []),
    }
    if requested_target_ids is not None:
        unknown_target_ids = sorted(set(requested_target_ids) - allowed_target_ids)
        if unknown_target_ids:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "target_object_ids must belong to the memory access event",
                    "unknown_target_object_ids": unknown_target_ids,
                },
            )

    object_ids = requested_target_ids if requested_target_ids is not None else existing_event.injected_fact_ids
    raw_feedback_by_object = existing_event.details.get("feedback_by_object")
    feedback_by_object = dict(raw_feedback_by_object) if isinstance(raw_feedback_by_object, dict) else {}
    changed_feedback: list[tuple[int, dict[str, object] | None]] = []
    feedback_updated_at = datetime.now(UTC).isoformat()
    for object_id in sorted(set(object_ids)):
        key = str(object_id)
        previous = feedback_by_object.get(key) if isinstance(feedback_by_object.get(key), dict) else None
        raw_previous_signal = previous.get("signal") if previous else None
        raw_previous_outcome = previous.get("outcome") if previous else None
        previous_signal = raw_previous_signal if isinstance(raw_previous_signal, str) else None
        previous_outcome = raw_previous_outcome if isinstance(raw_previous_outcome, str) else None
        incoming_feedback = {
            "signal": request.signal,
            "outcome": request.outcome,
            "detail": request.detail,
            "updated_at": feedback_updated_at,
        }
        if previous_signal == request.signal and previous_outcome == request.outcome:
            if previous and previous.get("detail") == request.detail:
                continue
            feedback_by_object[key] = incoming_feedback
            continue
        changed_feedback.append((object_id, previous))
        feedback_by_object[key] = incoming_feedback

    event = await svc.access_events.update_outcome(
        event_id=event_id,
        outcome=request.outcome,
        reason=request.detail,
        user_corrected_answer=user_corrected_answer,
        signal=request.signal,
        target_object_ids=requested_target_ids,
        feedback_by_object=feedback_by_object,
    )
    if event is None:
        raise HTTPException(status_code=404, detail=f"Memory access event {event_id} not found")

    updated_object_ids = [object_id for object_id, _ in changed_feedback]
    for object_id, previous in changed_feedback:
        await svc.knowledge_objects.record_usage_outcome(
            object_ids=[object_id],
            signal=request.signal,
            outcome=request.outcome,
            usage_event_id=event.id,
            feedback_at=feedback_updated_at,
            previous_signal=previous.get("signal") if previous and isinstance(previous.get("signal"), str) else None,
            previous_outcome=previous.get("outcome") if previous and isinstance(previous.get("outcome"), str) else None,
            replace_existing=previous is not None,
        )

    return {"event": event.model_dump(), "updated_object_ids": updated_object_ids}


@router.post("/activation/inspect")
async def inspect_knowledge_activation(
    request: MemoryActivationRequest,
    runtime: KnowledgeRuntime = Depends(require_knowledge_runtime),
):
    if runtime.memory_retrieval is None:
        raise HTTPException(status_code=503, detail="Memory retrieval is unavailable")
    return (await runtime.memory_retrieval.search(request)).model_dump()
