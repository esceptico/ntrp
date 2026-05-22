from datetime import UTC, datetime

from ntrp.knowledge.activation_evidence import focused_evidence_text
from ntrp.knowledge.activation_query import (
    lexical_score,
    query_terms,
    query_wants_memory_system,
    query_wants_personal_memory,
    query_wants_profile,
    semantic_alias_score,
)
from ntrp.knowledge.models import (
    ActivationCandidate,
    ActivationSignal,
    KnowledgeObject,
    KnowledgeObjectStatus,
    KnowledgeObjectType,
)

_TYPE_WEIGHTS = {
    KnowledgeObjectType.PROCEDURE: 0.55,
    KnowledgeObjectType.ENTITY_PROFILE: 0.5,
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

ACTIVATABLE_OBJECT_TYPES = set(_TYPE_WEIGHTS)
EVIDENCE_OBJECT_TYPES = set(_EVIDENCE_TYPE_WEIGHTS)
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


def _memory_system_adjustment(obj: KnowledgeObject, query: str) -> tuple[float, list[str], list[ActivationSignal]]:
    if not query_wants_memory_system(query):
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
    terms = query_terms(query, min_len=3)
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
    terms = query_terms(query)
    matched = sorted(entity for entity in entities if entity in query.lower() or entity in terms)
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


def _profile_adjustment(obj: KnowledgeObject, query: str) -> tuple[float, list[str], list[ActivationSignal]]:
    if obj.object_type != KnowledgeObjectType.ENTITY_PROFILE:
        return 0.0, [], []
    if query_wants_profile(query):
        return (
            0.22,
            ["profile_tier_match"],
            [ActivationSignal(name="memory_tier", value="profile", reason="query asks for synthesized entity/context understanding")],
        )
    if query_wants_personal_memory(query):
        return (
            0.08,
            ["personal_memory_profile_fallback"],
            [ActivationSignal(name="memory_tier", value="profile", reason="direct personal-memory query can use profile fallback")],
        )
    return 0.0, [], []


def _semantic_alias_adjustment(obj: KnowledgeObject, query: str) -> tuple[float, list[str], list[ActivationSignal]]:
    alias_score = semantic_alias_score(query, f"{obj.title} {obj.text}")
    if alias_score <= 0:
        return 0.0, [], []
    return (
        0.45,
        ["semantic_alias_match"],
        [ActivationSignal(name="semantic_alias", value="matched", reason="query category matched a known instance alias in memory")],
    )


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


def object_candidate(
    obj: KnowledgeObject,
    query: str,
    *,
    scope: str | None,
    now: datetime,
    retrieval_score: float = 0.0,
    retrieval_reasons: list[str] | None = None,
) -> ActivationCandidate | None:
    if obj.object_type == KnowledgeObjectType.ENTITY_PROFILE and not (
        query_wants_profile(query) or query_wants_personal_memory(query)
    ):
        return None
    valid, temporal_delta, temporal_reasons, temporal_signals = _temporal_adjustment(obj, now)
    if not valid:
        return None
    quality_valid, quality_delta, quality_reasons, quality_signals = _quality_adjustment(obj)
    if not quality_valid:
        return None
    lexical = lexical_score(query, f"{obj.title} {obj.text}")
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
    profile_delta, profile_reasons, profile_signals = _profile_adjustment(obj, query)
    semantic_delta, semantic_reasons, semantic_signals = _semantic_alias_adjustment(obj, query)
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
        + profile_delta
        + semantic_delta
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
    reasons.extend(profile_reasons)
    reasons.extend(semantic_reasons)
    reasons.extend(procedure_reasons)
    candidate_text, focused = focused_evidence_text(obj, query)
    if focused:
        reasons.append("focused_evidence_snippet")
    return ActivationCandidate(
        object_type=obj.object_type,
        object_id=str(obj.id),
        title=obj.title,
        text=candidate_text,
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
            *profile_signals,
            *semantic_signals,
            *procedure_signals,
        ],
        activation=obj.activation,
        proactiveness_level=obj.proactiveness_level,
    )
