from datetime import UTC, datetime
from re import findall

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

_ACTION_TERMS = {
    "artifact",
    "brief",
    "doc",
    "document",
    "draft",
    "note",
    "obsidian",
    "plan",
    "proposal",
    "reminder",
    "task",
    "todo",
    "verify",
}

_TYPE_WEIGHTS = {
    KnowledgeObjectType.PROCEDURE: 0.55,
    KnowledgeObjectType.PROCEDURE_CANDIDATE: 0.45,
    KnowledgeObjectType.LESSON: 0.4,
    KnowledgeObjectType.PATTERN: 0.35,
    KnowledgeObjectType.FACT: 0.3,
    KnowledgeObjectType.ACTION_CANDIDATE: 0.1,
    KnowledgeObjectType.ARTIFACT: 0.08,
}

_EVIDENCE_TYPE_WEIGHTS = {
    **_TYPE_WEIGHTS,
    KnowledgeObjectType.MEMORY_EPISODE: 0.06,
    KnowledgeObjectType.RUN_PROVENANCE: 0.03,
    KnowledgeObjectType.EPISODE: 0.03,
}

_STATUS_WEIGHTS = {
    KnowledgeObjectStatus.APPROVED: 0.25,
    KnowledgeObjectStatus.ACTIVE: 0.15,
    KnowledgeObjectStatus.DRAFT: -0.05,
}

_ACTIVATABLE_OBJECT_TYPES = set(_TYPE_WEIGHTS)
_EVIDENCE_OBJECT_TYPES = set(_EVIDENCE_TYPE_WEIGHTS)
_ACTIVATION_SCAN_LIMIT = 10_000
_MEMORY_SYSTEM_TERMS = {
    "activation",
    "activations",
    "activated",
    "database",
    "db",
    "inject",
    "injected",
    "knowledge",
    "memory",
    "memories",
    "retrieval",
    "retrieved",
    "sources",
    "telemetry",
    "trace",
    "traces",
}
_MEMORY_SYSTEM_HINTS = {
    "activation_access",
    "activation",
    "activated knowledge",
    "database",
    "entity",
    "knowledge",
    "memory",
    "retrieval",
    "source",
    "telemetry",
}
_AMBIGUOUS_ACTIVATION_DOMAIN_HINTS = {
    "activation oracle",
    "activation oracles",
    "activations oracle",
    "mats",
    "mechinterp",
    "mechanistic",
    "latent",
    "probe",
}


def _parse_iso(raw: object) -> datetime | None:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _feedback_counts(obj: KnowledgeObject) -> dict[str, int]:
    raw = obj.metadata.get("feedback_counts")
    if not isinstance(raw, dict):
        return {}
    out: dict[str, int] = {}
    for key, value in raw.items():
        try:
            out[str(key)] = int(value)
        except (TypeError, ValueError):
            continue
    return out


def _query_terms(text: str, *, min_len: int = 3) -> set[str]:
    return {term for term in findall(r"[a-zA-Z0-9_]+", text.lower()) if len(term) >= min_len}


def _query_wants_memory_system(query: str) -> bool:
    lowered = query.lower()
    terms = _query_terms(query, min_len=2)
    if not ({"activation", "activations", "activated"} & terms):
        return False
    if len(terms) <= 6 and any(phrase in lowered for phrase in ("what", "have", "activations")):
        return True
    return bool(terms & _MEMORY_SYSTEM_TERMS) and any(
        phrase in lowered
        for phrase in (
            "what we have",
            "what do we have",
            "current",
            "database",
            "debug",
            "inspect",
            "memory",
            "retrieval",
            "telemetry",
        )
    )


def _memory_system_adjustment(obj: KnowledgeObject, query: str) -> tuple[float, list[str], list[ActivationSignal]]:
    if not _query_wants_memory_system(query):
        return 0.0, [], []
    haystack = f"{obj.title} {obj.text} {obj.object_type.value} {obj.metadata}".lower()
    has_memory_hint = any(hint in haystack for hint in _MEMORY_SYSTEM_HINTS)
    has_wrong_domain_hint = any(hint in haystack for hint in _AMBIGUOUS_ACTIVATION_DOMAIN_HINTS)
    if has_memory_hint and not has_wrong_domain_hint:
        return (
            0.18,
            ["memory_system_query"],
            [ActivationSignal(name="query_domain", value="memory_system", reason="query asks about memory/activation internals")],
        )
    if has_wrong_domain_hint or "activation" in haystack or "activations" in haystack:
        return (
            -0.42,
            ["ambiguous_activation_domain"],
            [
                ActivationSignal(
                    name="query_domain",
                    value="ambiguous_activation_penalty",
                    reason="activation term appears to refer to a non-memory domain",
                )
            ],
        )
    return 0.0, [], []


def _broad_pattern_adjustment(obj: KnowledgeObject, query: str) -> tuple[float, list[str], list[ActivationSignal]]:
    terms = _query_terms(query, min_len=3)
    if obj.object_type != KnowledgeObjectType.PATTERN or len(terms) > 8:
        return 0.0, [], []
    if "legacy_observation_id" not in obj.metadata:
        return 0.0, [], []
    if any(token in query.lower() for token in ("pattern", "trend", "history", "across", "over time")):
        return 0.0, [], []
    return (
        -0.08,
        ["short_query_broad_pattern_penalty"],
        [ActivationSignal(name="specificity", value="broad_pattern", reason="short/direct queries prefer concrete facts/procedures over broad patterns")],
    )


def _metadata_entities(obj: KnowledgeObject) -> set[str]:
    entities: set[str] = set()
    raw = obj.metadata.get("entities")
    if isinstance(raw, list):
        entities |= {str(entity).lower() for entity in raw if str(entity).strip()}
    graph = obj.metadata.get("entity_graph")
    if isinstance(graph, dict) and isinstance(graph.get("entities"), list):
        entities |= {str(entity).lower() for entity in graph["entities"] if str(entity).strip()}
    return entities


def _entity_adjustment(obj: KnowledgeObject, query: str) -> tuple[float, list[str], list[ActivationSignal]]:
    entities = _metadata_entities(obj)
    if not entities:
        return 0.0, [], []
    query_terms = _query_terms(query)
    matched = sorted(entity for entity in entities if entity in query.lower() or entity in query_terms)
    if not matched:
        return 0.0, [], []
    return (
        min(0.18, 0.08 + 0.03 * len(matched)),
        ["entity_match"],
        [ActivationSignal(name="entity_match", value=", ".join(matched), reason="query matched knowledge metadata entities")],
    )


def _recency_wanted(query: str) -> bool:
    lowered = query.lower()
    return any(term in lowered for term in ("recent", "latest", "current", "today", "yesterday", "lately", "this week", "last week"))


def _time_adjustment(obj: KnowledgeObject, query: str, now: datetime) -> tuple[float, list[str], list[ActivationSignal]]:
    if not _recency_wanted(query):
        return 0.0, [], []
    happened_at = _parse_iso(obj.metadata.get("happened_at"))
    updated_at = _parse_iso(obj.updated_at)
    reference = happened_at or updated_at
    if reference is None:
        return 0.0, [], []
    age_days = max(0, (now - reference).days)
    if age_days <= 14:
        return (
            0.14,
            ["recent_time_match"],
            [ActivationSignal(name="time_match", value=reference.isoformat(), reason="query requested recent/current knowledge")],
        )
    if age_days > 365:
        return (
            -0.08,
            ["old_for_recent_query"],
            [ActivationSignal(name="time_match", value=reference.isoformat(), reason="query requested recent/current knowledge but object is old")],
        )
    return 0.0, [], []


def _quality_adjustment(obj: KnowledgeObject) -> tuple[bool, float, list[str], list[ActivationSignal]]:
    metadata = obj.metadata
    if obj.superseded_by_object_id or metadata.get("superseded_by_object_id") or metadata.get("superseded_by_id") or metadata.get("replaced_by_object_id"):
        return (
            False,
            0.0,
            ["metadata_superseded"],
            [ActivationSignal(name="supersession", value="superseded", reason="metadata names a newer replacement")],
        )
    if (
        metadata.get("invalidated_by_object_id")
        or metadata.get("contradicted_by_object_id")
        or metadata.get("contradicted_by_object_ids")
    ):
        return (
            False,
            0.0,
            ["metadata_contradicted"],
            [ActivationSignal(name="contradiction", value="contradicted", reason="metadata names a contradicting object")],
        )
    tags = {str(tag).lower() for tag in metadata.get("tags", [])} if isinstance(metadata.get("tags"), list) else set()
    risks = {"stale", "poisoned", "unsafe", "untrusted", "deprecated"} & tags
    score_delta = 0.0
    reasons: list[str] = []
    signals: list[ActivationSignal] = []
    if risks:
        score_delta -= 0.25
        reasons.append("risk_tags")
        signals.append(ActivationSignal(name="quality_risk", value=", ".join(sorted(risks)), reason="knowledge metadata has risky tags"))
    if metadata.get("supersedes_object_id") or metadata.get("supersedes"):
        score_delta += 0.08
        reasons.append("supersedes_older_memory")
        signals.append(ActivationSignal(name="supersession", value="newer", reason="object supersedes older memory"))
    return True, score_delta, reasons, signals


def _temporal_adjustment(obj: KnowledgeObject, now: datetime) -> tuple[bool, float, list[str], list[ActivationSignal]]:
    metadata = obj.metadata
    expires_at = _parse_iso(metadata.get("expires_at"))
    valid_to = _parse_iso(metadata.get("valid_to"))
    invalid_at = _parse_iso(metadata.get("invalid_at"))
    valid_from = _parse_iso(metadata.get("valid_from") or metadata.get("valid_at"))

    if expires_at and expires_at <= now:
        return False, 0.0, ["expired"], [ActivationSignal(name="temporal_validity", value="expired", reason="expires_at is in the past")]
    if valid_to and valid_to <= now:
        return False, 0.0, ["invalid"], [ActivationSignal(name="temporal_validity", value="invalid", reason="valid_to is in the past")]
    if invalid_at and invalid_at <= now:
        return False, 0.0, ["invalid"], [ActivationSignal(name="temporal_validity", value="invalid", reason="invalid_at is in the past")]
    if valid_from and valid_from > now:
        return False, 0.0, ["not_yet_valid"], [ActivationSignal(name="temporal_validity", value="future", reason="valid_from is in the future")]

    verified_at = _parse_iso(metadata.get("verified_at"))
    stale_after_days = metadata.get("stale_after_days")
    signals: list[ActivationSignal] = []
    reasons: list[str] = []
    score_delta = 0.0
    if verified_at:
        signals.append(ActivationSignal(name="verified_at", value=verified_at.isoformat(), reason="last explicit verification"))
        score_delta += 0.04
    if stale_after_days is not None and verified_at:
        try:
            max_age_days = int(stale_after_days)
        except (TypeError, ValueError):
            max_age_days = 0
        age_days = (now - verified_at).days
        if max_age_days > 0 and age_days > max_age_days:
            reasons.append("stale")
            score_delta -= 0.2
            signals.append(ActivationSignal(name="temporal_validity", value="stale", reason="verified_at is older than stale_after_days"))
    if not signals:
        signals.append(ActivationSignal(name="temporal_validity", value="current", reason="no expiry or invalidation metadata"))
    return True, score_delta, reasons, signals


def _procedure_adjustment(obj: KnowledgeObject) -> tuple[float, list[str], list[ActivationSignal]]:
    if obj.object_type != KnowledgeObjectType.PROCEDURE:
        return 0.0, [], []
    counts = _feedback_counts(obj)
    success = counts.get("helpful", 0) + counts.get("success", 0) + counts.get("used", 0)
    failure = counts.get("not_helpful", 0) + counts.get("harmful", 0) + counts.get("corrected", 0) + counts.get("failed", 0)
    delta = min(success, 5) * 0.04 - min(failure, 5) * 0.08
    reasons: list[str] = []
    if success:
        reasons.append("procedure_success")
    if failure:
        reasons.append("procedure_failures")
    signals = [
        ActivationSignal(name="procedure_success", value=success, reason="positive feedback count"),
        ActivationSignal(name="procedure_failure", value=failure, reason="negative feedback count"),
    ]
    return delta, reasons, signals


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
    return {term for term in findall(r"[a-zA-Z0-9_]+", text.lower()) if len(term) > 3}


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


def _query_wants_action(query: str) -> bool:
    lowered = query.lower()
    return any(term in lowered for term in _ACTION_TERMS)


def _query_wants_evidence(query: str) -> bool:
    lowered = query.lower()
    return any(
        term in lowered
        for term in (
            "why",
            "how did",
            "source",
            "sources",
            "evidence",
            "provenance",
            "episode",
            "run",
            "where did",
            "when did",
            "context",
        )
    )


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


def _normalize_activation_terms(terms: set[str]) -> set[str]:
    normalized = set(terms)
    if "activation" in normalized or "activations" in normalized:
        normalized |= {"activation", "activations"}
    return normalized


def _lexical_score(query: str, text: str) -> float:
    query_terms = _normalize_activation_terms(_query_terms(query))
    if not query_terms:
        return 0.0
    text_terms = _normalize_activation_terms(set(findall(r"[a-zA-Z0-9_]+", text.lower())))
    return len(query_terms & text_terms) / len(query_terms)


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


def _object_candidate(
    obj: KnowledgeObject,
    query: str,
    *,
    scope: str | None,
    now: datetime,
    retrieval_score: float = 0.0,
    retrieval_reasons: list[str] | None = None,
) -> ActivationCandidate | None:
    valid, temporal_delta, temporal_reasons, temporal_signals = _temporal_adjustment(obj, now)
    if not valid:
        return None
    quality_valid, quality_delta, quality_reasons, quality_signals = _quality_adjustment(obj)
    if not quality_valid:
        return None
    lexical = _lexical_score(query, f"{obj.title} {obj.text}")
    entity_delta, entity_reasons, entity_signals = _entity_adjustment(obj, query)
    time_delta, time_reasons, time_signals = _time_adjustment(obj, query, now)
    memory_delta, memory_reasons, memory_signals = _memory_system_adjustment(obj, query)
    broad_delta, broad_reasons, broad_signals = _broad_pattern_adjustment(obj, query)
    type_boost = _EVIDENCE_TYPE_WEIGHTS.get(obj.object_type, 0.0)
    status_boost = _STATUS_WEIGHTS.get(obj.status, 0.0)
    evidence_boost = min(len(obj.source_ids), 5) * 0.03
    scope_boost = 0.0
    scope_reason: str | None = None
    if scope:
        if obj.scope == scope:
            scope_boost = 0.2
            scope_reason = "scope_match"
        elif obj.scope is None:
            scope_boost = 0.05
            scope_reason = "global_scope"
        else:
            scope_boost = -0.03
            scope_reason = "scope_mismatch_allowed"
    elif obj.scope is None:
        scope_boost = 0.02
        scope_reason = "global_scope"
    procedure_delta, procedure_reasons, procedure_signals = _procedure_adjustment(obj)
    score = (
        max(obj.score, lexical)
        + retrieval_score
        + type_boost
        + status_boost
        + evidence_boost
        + scope_boost
        + temporal_delta
        + entity_delta
        + time_delta
        + memory_delta
        + broad_delta
        + quality_delta
        + procedure_delta
    )
    reasons = list(retrieval_reasons or [])
    if lexical:
        reasons.append("lexical_match")
    if type_boost:
        reasons.append(f"type_weight:{obj.object_type.value}")
    if status_boost:
        reasons.append(f"status:{obj.status.value}")
    if evidence_boost:
        reasons.append("source_support")
    if scope_reason:
        reasons.append(scope_reason)
    reasons.extend(temporal_reasons)
    reasons.extend(entity_reasons)
    reasons.extend(time_reasons)
    reasons.extend(memory_reasons)
    reasons.extend(broad_reasons)
    reasons.extend(quality_reasons)
    reasons.extend(procedure_reasons)
    return ActivationCandidate(
        object_type=obj.object_type,
        object_id=str(obj.id),
        title=obj.title,
        text=obj.text,
        score=score,
        reasons=reasons or ["knowledge_object_available"],
        source_ids=obj.source_ids,
        signals=[
            ActivationSignal(name="scope", value=obj.scope, reason="knowledge object scope"),
            ActivationSignal(name="status", value=obj.status.value, reason="knowledge object lifecycle"),
            ActivationSignal(name="evidence_strength", value=len(obj.source_ids), reason="source reference count"),
            ActivationSignal(name="outcome_score", value=obj.score, reason="feedback-adjusted object score"),
            *temporal_signals,
            *entity_signals,
            *time_signals,
            *memory_signals,
            *broad_signals,
            *quality_signals,
            *procedure_signals,
        ],
        activation=obj.activation,
        proactiveness_level=obj.proactiveness_level,
    )


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
        if request.include_actions and _query_wants_action(request.query):
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
        object_types = _EVIDENCE_OBJECT_TYPES if _query_wants_evidence(request.query) else _ACTIVATABLE_OBJECT_TYPES

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
                    request.query,
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
                    request.query,
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
                    request.query,
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
                    request.query,
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
            candidate = _object_candidate(
                obj,
                request.query,
                scope=request.scope,
                now=now,
                retrieval_score=retrieval_score,
                retrieval_reasons=retrieval_reasons,
            )
            if candidate and (_lexical_score(request.query, f"{obj.title} {obj.text}") > 0 or retrieval_score > 0 or obj.activation == "review"):
                candidates.append(candidate)
        return candidates
