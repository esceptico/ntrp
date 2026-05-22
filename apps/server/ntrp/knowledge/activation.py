from datetime import UTC, datetime

from ntrp.knowledge.activation_query import (
    lexical_score,
    query_terms,
    query_wants_action,
    query_wants_evidence,
    query_wants_personal_memory,
    query_wants_temporal_memory,
    reformulated_query,
)
from ntrp.knowledge.activation_scoring import (
    ACTIVATABLE_OBJECT_TYPES,
    EVIDENCE_OBJECT_TYPES,
    object_candidate,
)
from ntrp.knowledge.models import (
    ActivationBundle,
    ActivationCandidate,
    ActivationRequest,
    ActivationSignal,
    KnowledgeNextAction,
    KnowledgeObject,
    KnowledgeObjectStatus,
    KnowledgeObjectType,
    KnowledgeSummary,
    KnowledgeSurface,
)
from ntrp.memory.service import MemoryService

_ACTIVATION_SCAN_LIMIT = 10_000


def _fit_budget(
    candidates: list[ActivationCandidate], budget_chars: int, *, max_items: int | None = None
) -> tuple[list[ActivationCandidate], list[ActivationCandidate], int]:
    selected: list[ActivationCandidate] = []
    omitted: list[ActivationCandidate] = []
    used = 0
    for candidate in candidates:
        if _is_near_duplicate(candidate, selected):
            candidate.reasons.append("diversity:near_duplicate")
            omitted.append(candidate)
            continue
        if max_items is not None and len(selected) >= max_items:
            candidate.reasons.append("limit_exceeded")
            omitted.append(candidate)
            continue
        size = len(candidate.text)
        if selected and used + size > budget_chars:
            candidate.reasons.append("budget_exceeded")
            omitted.append(candidate)
            continue
        selected.append(candidate)
        used += size
    return selected, omitted, used


def _terms(text: str) -> set[str]:
    return query_terms(text, min_len=4)


def _is_near_duplicate(candidate: ActivationCandidate, selected: list[ActivationCandidate]) -> bool:
    candidate_terms = _terms(f"{candidate.title} {candidate.text}")
    if not candidate_terms:
        return False
    for item in selected:
        item_terms = _terms(f"{item.title} {item.text}")
        if not item_terms:
            continue
        overlap = len(candidate_terms & item_terms) / max(1, min(len(candidate_terms), len(item_terms)))
        same_source = bool(candidate.source_ids and item.source_ids and set(candidate.source_ids) & set(item.source_ids))
        if same_source and overlap >= 0.65:
            return True
        if candidate.object_type == item.object_type and overlap >= 0.92:
            return True
    return False


def _action_candidate(query: str, score: float) -> ActivationCandidate:
    return ActivationCandidate(
        object_type=KnowledgeObjectType.ACTION_CANDIDATE,
        object_id="artifact-review",
        title="Review artifact/action candidate",
        text=f"Review whether this request should produce a note, artifact, reminder, verification task, or external sink draft: {query}",
        score=score,
        reasons=["action_term_match"],
        signals=[
            ActivationSignal(
                name="interruption_cost", value="review", reason="external or durable action should be gated"
            ),
            ActivationSignal(name="proactiveness", value="L2", reason="review queue item, not direct execution"),
        ],
        activation="review",
        proactiveness_level="L2",
    )


def _format_prompt_context(candidates: list[ActivationCandidate]) -> str | None:
    prompt_candidates = [
        candidate
        for candidate in candidates
        if candidate.activation == "prompt"
        and candidate.proactiveness_level in {"L0", "L1"}
        and candidate.object_type != KnowledgeObjectType.ACTION_CANDIDATE
    ]
    if not prompt_candidates:
        return None
    lines = ["Activated knowledge:"]
    for candidate in prompt_candidates:
        reasons = ", ".join(candidate.reasons[:3]) if candidate.reasons else "selected"
        lines.append(f"- [{candidate.object_type.value}] {candidate.title}: {candidate.text} (why: {reasons})")
    return "\n".join(lines)


def _activation_trace_item(
    candidate: ActivationCandidate,
    *,
    rank: int,
    selected: bool,
    injected: bool,
) -> dict[str, object]:
    return {
        "rank": rank,
        "object_id": candidate.object_id,
        "object_type": candidate.object_type.value,
        "title": candidate.title,
        "score": round(candidate.score, 6),
        "selected": selected,
        "injected": injected,
        "activation": candidate.activation,
        "proactiveness_level": candidate.proactiveness_level,
        "reasons": candidate.reasons,
        "signals": [signal.model_dump(mode="json") for signal in candidate.signals],
        "source_ids": candidate.source_ids,
        "chars": len(candidate.text),
    }


class KnowledgeActivationService:
    def __init__(self, memory: MemoryService):
        self.memory = memory

    async def inspect(self, request: ActivationRequest) -> ActivationBundle:
        candidates = await self._object_candidates(request)
        if request.include_actions and query_wants_action(request.query):
            candidates.append(_action_candidate(request.query, score=0.25))

        candidates.sort(key=lambda candidate: candidate.score, reverse=True)
        selected, omitted, used = _fit_budget(candidates, request.budget_chars, max_items=request.limit)
        prompt_context = _format_prompt_context(selected)
        if request.record_access:
            await self._record_access(request, selected, omitted, prompt_context)
        return ActivationBundle(
            query=request.query,
            scope=request.scope,
            task=request.task,
            budget_chars=request.budget_chars,
            used_chars=used,
            candidates=selected,
            omitted=omitted,
            prompt_context=prompt_context,
        )

    async def _record_access(
        self,
        request: ActivationRequest,
        candidates: list[ActivationCandidate],
        omitted: list[ActivationCandidate],
        prompt_context: str | None,
    ) -> None:
        access_events = getattr(self.memory, "access_events", None)
        if access_events is None:
            return

        def numeric(candidate_list: list[ActivationCandidate]) -> list[int]:
            return [int(candidate.object_id) for candidate in candidate_list if candidate.object_id.isdigit()]

        prompt_ids = {candidate.object_id for candidate in candidates if candidate.activation == "prompt"}
        candidate_trace = [
            _activation_trace_item(candidate, rank=rank, selected=True, injected=bool(prompt_context and candidate.object_id in prompt_ids))
            for rank, candidate in enumerate(candidates, start=1)
        ]
        omitted_trace = [
            _activation_trace_item(candidate, rank=rank, selected=False, injected=False)
            for rank, candidate in enumerate(omitted, start=len(candidate_trace) + 1)
        ]
        await access_events.create(
            source=request.task or "knowledge_activation",
            query=request.query,
            retrieved_fact_ids=numeric(candidates + omitted),
            injected_fact_ids=numeric(candidates) if prompt_context else [],
            omitted_fact_ids=numeric(omitted),
            formatted_chars=len(prompt_context or ""),
            policy_version="knowledge.activation.v2",
            details={
                "scope": request.scope,
                "candidate_ids": [candidate.object_id for candidate in candidates],
                "candidate_types": [candidate.object_type.value for candidate in candidates],
                "candidates": candidate_trace,
                "omitted": omitted_trace[:100],
                "omitted_count": len(omitted),
                "injected": bool(prompt_context),
                "used_chars": len(prompt_context or ""),
            },
        )

    async def _activation_event_count(self) -> int:
        access_events = getattr(self.memory, "access_events", None)
        if access_events is None:
            return 0
        count = getattr(access_events, "count", None)
        if count is not None:
            return await count()
        list_recent = getattr(access_events, "list_recent", None)
        if list_recent is not None:
            return len(await list_recent(limit=1_000))
        return 0

    async def summary(self) -> KnowledgeSummary:
        object_counts = await self.memory.knowledge_objects.count_by_type()
        recent_events = await self.memory.events.list_recent(limit=20)
        activation_count = await self._activation_event_count()
        next_actions: list[KnowledgeNextAction] = []
        if activation_count == 0:
            next_actions.append(
                KnowledgeNextAction(
                    title="Review empty activations",
                    detail="No activation records exist yet.",
                )
            )
        if any(event.action.endswith(".updated") or event.action.endswith(".deleted") for event in recent_events):
            next_actions.append(
                KnowledgeNextAction(
                    title="Review manual knowledge edits",
                    detail="Recent knowledge edits may indicate a reusable lesson or procedure candidate.",
                )
            )
        if object_counts.get(KnowledgeObjectType.MEMORY_EPISODE.value, 0) or object_counts.get(
            KnowledgeObjectType.EPISODE.value, 0
        ):
            next_actions.append(
                KnowledgeNextAction(
                    title="Reflect recent memory episodes",
                    detail="Closed task/event episodes can produce lessons, procedures, actions, or artifacts.",
                )
            )

        return KnowledgeSummary(
            surfaces=[
                KnowledgeSurface(
                    name="Episodes",
                    object_type=KnowledgeObjectType.EPISODE,
                    count=object_counts.get(KnowledgeObjectType.EPISODE.value, 0),
                    description="captured work moments",
                ),
                KnowledgeSurface(
                    name="Facts",
                    object_type=KnowledgeObjectType.FACT,
                    count=object_counts.get(KnowledgeObjectType.FACT.value, 0),
                    description="source-backed facts",
                ),
                KnowledgeSurface(
                    name="Patterns",
                    object_type=KnowledgeObjectType.PATTERN,
                    count=object_counts.get(KnowledgeObjectType.PATTERN.value, 0),
                    description="derived context with fact provenance",
                ),
                KnowledgeSurface(
                    name="Lessons",
                    object_type=KnowledgeObjectType.LESSON,
                    count=object_counts.get(KnowledgeObjectType.LESSON.value, 0),
                    description="reusable conclusions from episodes and feedback",
                ),
                KnowledgeSurface(
                    name="Procedures",
                    object_type=KnowledgeObjectType.PROCEDURE,
                    count=object_counts.get(KnowledgeObjectType.PROCEDURE.value, 0),
                    description="approved behavior",
                ),
                KnowledgeSurface(
                    name="Profiles",
                    object_type=KnowledgeObjectType.ENTITY_PROFILE,
                    count=object_counts.get(KnowledgeObjectType.ENTITY_PROFILE.value, 0),
                    description="source-backed entity/context profiles",
                ),
                KnowledgeSurface(
                    name="Improve",
                    object_type=KnowledgeObjectType.PROCEDURE_CANDIDATE,
                    count=object_counts.get(KnowledgeObjectType.PROCEDURE_CANDIDATE.value, 0),
                    description="review-gated behavior changes",
                ),
                KnowledgeSurface(
                    name="Actions",
                    object_type=KnowledgeObjectType.ACTION_CANDIDATE,
                    count=object_counts.get(KnowledgeObjectType.ACTION_CANDIDATE.value, 0),
                    description="proactive suggestions and drafts",
                ),
                KnowledgeSurface(
                    name="Artifacts",
                    object_type=KnowledgeObjectType.ARTIFACT,
                    count=object_counts.get(KnowledgeObjectType.ARTIFACT.value, 0),
                    description="human-facing reusable outputs",
                ),
                KnowledgeSurface(
                    name="Activation",
                    object_type=KnowledgeObjectType.OUTCOME_FEEDBACK,
                    count=activation_count,
                    description="activation/access events",
                ),
            ],
            next_actions=next_actions,
        )

    async def _object_candidates(self, request: ActivationRequest) -> list[ActivationCandidate]:
        statuses = {
            KnowledgeObjectStatus.ACTIVE,
            KnowledgeObjectStatus.APPROVED,
        }
        objects_by_id: dict[int, KnowledgeObject] = {}
        retrieval: dict[int, tuple[float, list[str]]] = {}
        object_types = (
            EVIDENCE_OBJECT_TYPES
            if (
                query_wants_evidence(request.query)
                or query_wants_personal_memory(request.query)
                or query_wants_temporal_memory(request.query)
            )
            else ACTIVATABLE_OBJECT_TYPES
        )
        search_query, plan_reasons = reformulated_query(request.query)

        def add_objects(objects: list[KnowledgeObject], score: float, reason: str) -> None:
            for obj in objects:
                objects_by_id[obj.id] = obj
                current_score, current_reasons = retrieval.get(obj.id, (0.0, []))
                if score > 0 and reason not in current_reasons:
                    current_reasons.append(reason)
                retrieval[obj.id] = (max(current_score, score), current_reasons)

        search_text = getattr(self.memory.knowledge_objects, "search_text", None)
        if search_text is not None:
            add_objects(
                await search_text(
                    search_query,
                    object_types=object_types,
                    statuses=statuses,
                    limit=_ACTIVATION_SCAN_LIMIT,
                ),
                0.08,
                "fts_match",
            )
        else:
            add_objects(
                await self.memory.knowledge_objects.list_many(
                    object_types=object_types,
                    statuses=statuses,
                    limit=_ACTIVATION_SCAN_LIMIT,
                ),
                0.0,
                "scan_fallback",
            )

        search_entities = getattr(self.memory.knowledge_objects, "search_entities", None)
        if search_entities is not None:
            add_objects(
                await search_entities(
                    search_query,
                    object_types=object_types,
                    statuses=statuses,
                    limit=min(_ACTIVATION_SCAN_LIMIT, 500),
                ),
                0.12,
                "entity_retrieval",
            )

        search_temporal = getattr(self.memory.knowledge_objects, "search_temporal", None)
        if search_temporal is not None:
            add_objects(
                await search_temporal(
                    search_query,
                    object_types=object_types,
                    statuses=statuses,
                    limit=min(_ACTIVATION_SCAN_LIMIT, 500),
                ),
                0.1,
                "temporal_retrieval",
            )

        search_vector = getattr(self.memory.knowledge_objects, "search_vector", None)
        if search_vector is not None:
            try:
                vector_results = await search_vector(
                    search_query,
                    object_types=object_types,
                    statuses=statuses,
                    limit=min(_ACTIVATION_SCAN_LIMIT, 500),
                )
            except Exception:
                vector_results = []
            for obj, similarity in vector_results:
                objects_by_id[obj.id] = obj
                current_score, current_reasons = retrieval.get(obj.id, (0.0, []))
                if "vector_match" not in current_reasons:
                    current_reasons.append("vector_match")
                retrieval[obj.id] = (max(current_score, max(0.0, similarity) * 0.25), current_reasons)

        now = datetime.now(UTC)
        candidates: list[ActivationCandidate] = []
        for obj in objects_by_id.values():
            retrieval_score, retrieval_reasons = retrieval.get(obj.id, (0.0, []))
            candidate = object_candidate(
                obj,
                request.query,
                scope=request.scope,
                now=now,
                retrieval_score=retrieval_score,
                retrieval_reasons=[*plan_reasons, *retrieval_reasons],
            )
            if candidate and (lexical_score(request.query, f"{obj.title} {obj.text}") > 0 or retrieval_score > 0 or obj.activation == "review"):
                candidates.append(candidate)
        return candidates
