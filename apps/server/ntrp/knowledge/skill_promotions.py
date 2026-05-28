from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from re import findall
from typing import Any, Protocol

from ntrp.knowledge.metadata import (
    APPROVAL_FLOW_MEMORY_REVIEW_CREATE_SKILL,
    PROMOTION_KIND_SKILL,
    PROMOTION_KIND_WORKFLOW_CLUSTER_REVIEW,
    WRITE_GATE_VERSION,
    is_skill_promotion_candidate,
    is_workflow_cluster_review_marker,
)
from ntrp.knowledge.models import (
    KnowledgeObject,
    KnowledgeObjectCreate,
    KnowledgeObjectStatus,
    KnowledgeObjectType,
    KnowledgeObjectUpdate,
    KnowledgeSkillPromotionResult,
    KnowledgeWorkflowCluster,
    KnowledgeWorkflowClusterResult,
)
from ntrp.knowledge.workflow_lifecycle import current_workflow_review_markers
from ntrp.memory.models import MemoryAccessEvent


@dataclass
class WorkflowUsageEvidence:
    event_ids: list[int] = field(default_factory=list)
    success_count: int = 0
    helpful_count: int = 0
    failure_count: int = 0
    correction_count: int = 0
    last_seen_at: str | None = None

class SkillCreator(Protocol):
    def create(self, name: str, description: str, body: str, *, source: str | None = None): ...

def _skill_slug(title: str) -> str:
    words = [word.lower() for word in findall(r"[a-zA-Z0-9]+", title) if word.strip()]
    slug = "-".join(words)[:48].strip("-")
    return slug if slug and slug[0].isalpha() else "memory-skill"

def _skill_body_from_lesson(lesson: KnowledgeObject) -> str:
    return (
        f"# {lesson.title}\n\n"
        f"Use this when the current task matches this remembered workflow from ntrp memory.\n\n"
        "## Procedure\n\n"
        f"{lesson.text.strip()}\n\n"
        "## Source Memory\n\n"
        f"- knowledge:{lesson.id}: {lesson.title}\n"
        + "".join(f"- {source_id}\n" for source_id in lesson.source_ids[:10])
    ).strip()

def _lesson_evidence(lesson: KnowledgeObject) -> tuple[int, int]:
    feedback_counts = lesson.metadata.get("feedback_counts")
    try:
        legacy_helpful = int(feedback_counts.get("helpful", 0)) if isinstance(feedback_counts, dict) else 0
    except (TypeError, ValueError):
        legacy_helpful = 0
    helpful_count = _int_metadata(lesson.metadata, "helpful_count")
    success_count = _int_metadata(lesson.metadata, "success_count")
    return max(legacy_helpful, helpful_count), success_count

def _workflow_cluster_key(lesson: KnowledgeObject) -> str | None:
    for key in ("workflow_cluster_key", "workflow_key", "task_pattern"):
        value = lesson.metadata.get(key)
        if isinstance(value, str) and value.strip():
            return _skill_slug(value)
    for key in ("workflow_title", "task_title", "task_name", "task"):
        value = lesson.metadata.get(key)
        if isinstance(value, str) and value.strip():
            return _skill_slug(value)
    return None

def _workflow_cluster_scope(lesson: KnowledgeObject) -> str:
    return lesson.scope or "global"

def _workflow_cluster_id(scope: str, key: str) -> str:
    clean_scope = (scope or "global").strip() or "global"
    return f"{clean_scope}:{key}"

def _split_workflow_cluster_id(cluster_id: str) -> tuple[str, str]:
    scope, sep, key = cluster_id.rpartition(":")
    if not sep:
        return "global", cluster_id
    return scope or "global", key

def _sort_workflow_lessons(lessons: list[KnowledgeObject]) -> list[KnowledgeObject]:
    return sorted(lessons, key=lambda item: (-item.score, item.id))

def _workflow_clusters_from_lessons(
    lessons: list[KnowledgeObject],
    *,
    excluded_lesson_ids: set[int] | None = None,
) -> dict[str, list[KnowledgeObject]]:
    excluded = excluded_lesson_ids or set()
    clusters: dict[str, list[KnowledgeObject]] = defaultdict(list)
    for lesson in lessons:
        key = _workflow_cluster_key(lesson)
        if key and lesson.id not in excluded:
            clusters[_workflow_cluster_id(_workflow_cluster_scope(lesson), key)].append(lesson)
    return clusters

def _workflow_event_sequence(details: dict[str, Any]) -> list[str]:
    for key in ("workflow_steps", "action_sequence", "tool_sequence", "tool_names", "actions", "tools", "tool_calls"):
        raw = details.get(key)
        if not isinstance(raw, list):
            continue
        items: list[str] = []
        for value in raw:
            if isinstance(value, str) and value.strip():
                items.append(value.strip())
            elif isinstance(value, dict):
                name = value.get("name") or value.get("tool_name") or value.get("action") or value.get("type")
                if isinstance(name, str) and name.strip():
                    items.append(name.strip())
        if len(items) >= 2:
            return items[:5]
    return []

def _workflow_event_key(event: MemoryAccessEvent) -> str | None:
    if not event.policy_version.startswith("knowledge.activation"):
        return None
    details = event.details if isinstance(event.details, dict) else {}
    for key in ("workflow_cluster_key", "workflow_key", "task_pattern", "workflow_title", "task_title", "task_name", "task"):
        value = details.get(key)
        if isinstance(value, str) and value.strip():
            return _skill_slug(value)
    sequence = _workflow_event_sequence(details)
    if sequence:
        return _skill_slug(" ".join(sequence))
    return None

def _workflow_event_scope(event: MemoryAccessEvent) -> str | None:
    details = event.details if isinstance(event.details, dict) else {}
    for key in ("scope", "project_scope", "project_id", "project"):
        value = details.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None

def _workflow_event_signal_counts(event: MemoryAccessEvent) -> tuple[int, int, int, int]:
    details = event.details if isinstance(event.details, dict) else {}
    outcome = str(details.get("outcome") or "").strip().lower()
    signal = str(details.get("signal") or "").strip().lower()
    success = 1 if outcome in {"success", "task_success", "completed", "complete"} else 0
    helpful = 1 if outcome == "helpful" or signal == "helpful" else 0
    failure = 1 if outcome in {"failure", "failed", "task_failed", "harmful"} or signal == "harmful" else 0
    corrected = 1 if outcome == "corrected" or signal == "corrected" or details.get("user_corrected_answer") is True else 0
    feedback = details.get("feedback_by_object")
    if isinstance(feedback, dict):
        for item in feedback.values():
            if not isinstance(item, dict):
                continue
            item_outcome = str(item.get("outcome") or "").strip().lower()
            item_signal = str(item.get("signal") or "").strip().lower()
            helpful += 1 if item_outcome == "helpful" or item_signal == "helpful" else 0
            failure += 1 if item_outcome == "harmful" or item_signal == "harmful" else 0
            corrected += 1 if item_outcome == "corrected" or item_signal == "corrected" else 0
    return helpful, success, failure, corrected

def _ambiguous_unscoped_usage_keys(cluster_ids: set[str]) -> set[str]:
    counts: dict[str, int] = defaultdict(int)
    for cluster_id in cluster_ids:
        _scope, key = _split_workflow_cluster_id(cluster_id)
        counts[key] += 1
    return {key for key, count in counts.items() if count > 1}

def _usage_evidence_for_cluster(
    usage_clusters: dict[str, WorkflowUsageEvidence],
    cluster_id: str,
    key: str,
    *,
    ambiguous_unscoped_keys: set[str],
) -> WorkflowUsageEvidence:
    scoped = usage_clusters.get(cluster_id)
    if scoped is not None:
        return scoped
    if key in ambiguous_unscoped_keys:
        return WorkflowUsageEvidence()
    return usage_clusters.get(key, WorkflowUsageEvidence())

def _workflow_clusters_from_usage_events(events: list[MemoryAccessEvent]) -> dict[str, WorkflowUsageEvidence]:
    clusters: dict[str, WorkflowUsageEvidence] = defaultdict(WorkflowUsageEvidence)
    for event in events:
        key = _workflow_event_key(event)
        if not key:
            continue
        scope = _workflow_event_scope(event)
        evidence = clusters[_workflow_cluster_id(scope, key) if scope else key]
        if isinstance(event.id, int):
            evidence.event_ids.append(event.id)
        event_seen_at = event.created_at.isoformat()
        if evidence.last_seen_at is None or event_seen_at > evidence.last_seen_at:
            evidence.last_seen_at = event_seen_at
        helpful, success, failure, corrected = _workflow_event_signal_counts(event)
        evidence.helpful_count += helpful
        evidence.success_count += success
        evidence.failure_count += failure
        evidence.correction_count += corrected
    return clusters

def _string_list_metadata(metadata: dict[str, Any], *keys: str) -> list[str]:
    values: list[str] = []
    for key in keys:
        raw = metadata.get(key)
        if isinstance(raw, str) and raw.strip():
            values.append(raw.strip())
        elif isinstance(raw, list):
            values.extend(item.strip() for item in raw if isinstance(item, str) and item.strip())
    return values

def _cluster_last_seen_at(lessons: list[KnowledgeObject], usage_evidence: WorkflowUsageEvidence) -> str | None:
    timestamps = [lesson.updated_at for lesson in lessons if lesson.updated_at]
    if usage_evidence.last_seen_at:
        timestamps.append(usage_evidence.last_seen_at)
    return max(timestamps) if timestamps else None

def _workflow_cluster_summary(
    *,
    title: str,
    lesson_count: int,
    usage_event_count: int,
    success_count: int,
    failure_count: int,
    correction_count: int,
) -> str:
    evidence_bits = [f"{lesson_count} lessons"]
    if usage_event_count:
        evidence_bits.append(f"{usage_event_count} usage events")
    outcome_bits = [f"{success_count} successes"]
    if failure_count:
        outcome_bits.append(f"{failure_count} failures")
    if correction_count:
        outcome_bits.append(f"{correction_count} corrections")
    return f"{title}: repeated workflow with {', '.join(evidence_bits)} and {', '.join(outcome_bits)}."

def _workflow_cluster_trigger_description(scope: str, key: str) -> str:
    readable_key = key.replace("-", " ")
    if scope == "global":
        return f"Tasks matching workflow '{readable_key}'."
    return f"Tasks in {scope} matching workflow '{readable_key}'."

def _workflow_cluster_metadata(
    *,
    cluster_id: str,
    scope: str,
    key: str,
    lifecycle_status: str,
    promotion_status: str,
    candidate_ids: list[int],
    review_markers: list[KnowledgeObject] | None = None,
) -> dict[str, object]:
    current_review_markers = sorted(review_markers or [], key=lambda item: item.id, reverse=True)
    latest_review_marker = current_review_markers[0] if current_review_markers else None
    metadata: dict[str, object] = {
        "workflow_cluster_id": cluster_id,
        "workflow_cluster_key": key,
        "scope": scope,
        "lifecycle_status": lifecycle_status,
        "promotion_status": promotion_status,
        "skill_candidate_ids": candidate_ids,
        "workflow_review_object_ids": sorted(marker.id for marker in current_review_markers),
    }
    if latest_review_marker is not None:
        marker_metadata = latest_review_marker.metadata
        metadata.update(
            {
                "workflow_review_object_id": latest_review_marker.id,
                "workflow_review_status": marker_metadata.get("workflow_review_status"),
                "workflow_review_reason": marker_metadata.get("workflow_review_reason"),
                "workflow_reviewed_at": marker_metadata.get("workflow_reviewed_at"),
            }
        )
    return metadata

def _workflow_cluster_lifecycle_status(
    candidates: list[KnowledgeObject],
    review_markers: list[KnowledgeObject],
    *,
    meets_threshold: bool,
) -> str:
    if any(
        candidate.status == KnowledgeObjectStatus.APPROVED
        and (candidate.metadata.get("skill_created_at") or candidate.metadata.get("skill_created_path"))
        for candidate in candidates
    ):
        return "promoted"
    if any(marker.status == KnowledgeObjectStatus.REJECTED or marker.metadata.get("workflow_review_status") == "rejected" for marker in review_markers):
        return "rejected"
    if any(candidate.status == KnowledgeObjectStatus.REJECTED for candidate in candidates):
        return "rejected"
    if any(candidate.status == KnowledgeObjectStatus.DRAFT for candidate in candidates):
        return "candidate"
    if any(candidate.status == KnowledgeObjectStatus.APPROVED for candidate in candidates) or any(
        marker.status == KnowledgeObjectStatus.APPROVED or marker.metadata.get("workflow_review_status") == "reviewed"
        for marker in review_markers
    ):
        return "reviewed"
    if meets_threshold:
        return "candidate"
    return "stale"

def _source_episode_ids(lessons: list[KnowledgeObject]) -> list[str]:
    ids: list[str] = []
    for lesson in lessons:
        ids.extend(_string_list_metadata(lesson.metadata, "source_episode_ids", "episode_ids", "episode_id"))
        for source_id in lesson.source_ids:
            if source_id.startswith(("episode:", "memory_episode:")):
                ids.append(source_id)
    return list(dict.fromkeys(ids))[:25]

def _source_artifact_ids(lessons: list[KnowledgeObject]) -> list[str]:
    ids: list[str] = []
    for lesson in lessons:
        ids.extend(_string_list_metadata(lesson.metadata, "source_artifact_ids", "artifact_ids", "artifact_id"))
        for source_id in lesson.source_ids:
            if source_id.startswith("artifact:"):
                ids.append(source_id)
    return list(dict.fromkeys(ids))[:25]

def _lesson_negative_evidence(lesson: KnowledgeObject) -> tuple[int, int]:
    failure_count = _int_metadata(lesson.metadata, "failure_count")
    correction_count = max(
        _int_metadata(lesson.metadata, "correction_count"),
        _int_metadata(lesson.metadata, "corrected_count"),
    )
    return failure_count, correction_count

def _cluster_evidence(lessons: list[KnowledgeObject]) -> tuple[int, int, int, int]:
    helpful = 0
    successes = 0
    failures = 0
    corrections = 0
    for lesson in lessons:
        lesson_helpful, lesson_successes = _lesson_evidence(lesson)
        lesson_failures, lesson_corrections = _lesson_negative_evidence(lesson)
        helpful += lesson_helpful
        successes += lesson_successes
        failures += lesson_failures
        corrections += lesson_corrections
    return helpful, successes, failures, corrections

def _skill_body_from_workflow_cluster(title: str, lessons: list[KnowledgeObject]) -> str:
    lines = [
        f"# {title}",
        "",
        "Use this when the current task matches this repeated workflow mined from ntrp memory.",
        "",
        "## Procedure",
        "",
    ]
    for index, lesson in enumerate(lessons, start=1):
        lines.append(f"{index}. {lesson.text.strip()}")
    lines.extend(["", "## Source Memories", ""])
    for lesson in lessons:
        lines.append(f"- knowledge:{lesson.id}: {lesson.title}")
    for source_id in _source_episode_ids(lessons):
        lines.append(f"- {source_id}")
    for artifact_id in _source_artifact_ids(lessons):
        lines.append(f"- {artifact_id}")
    return "\n".join(lines).strip()

def _int_ids(value: object) -> list[int]:
    if not isinstance(value, list):
        return []
    ids: list[int] = []
    for item in value:
        if isinstance(item, int | str) and str(item).isdigit():
            ids.append(int(item))
    return list(dict.fromkeys(ids))

def _knowledge_ref_ids(source_ids: list[str]) -> list[int]:
    ids: list[int] = []
    for source_id in source_ids:
        if not source_id.startswith("knowledge:"):
            continue
        raw_id = source_id.removeprefix("knowledge:")
        if raw_id.isdigit():
            ids.append(int(raw_id))
    return list(dict.fromkeys(ids))

def _skill_source_memory_ids(candidate: KnowledgeObject, metadata: dict[str, object]) -> list[int]:
    ids = [
        *_int_ids(metadata.get("source_memory_ids")),
        *_int_ids(metadata.get("source_lesson_ids")),
        *_int_ids(metadata.get("source_episode_ids")),
        *_knowledge_ref_ids(candidate.source_ids),
    ]
    return [object_id for object_id in dict.fromkeys(ids) if object_id != candidate.id]

def _string_metadata(metadata: dict[str, object], key: str) -> str:
    value = metadata.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Skill promotion candidate is missing {key}")
    return value.strip()

def _int_metadata(metadata: dict[str, object], key: str) -> int:
    try:
        return int(metadata.get(key, 0) or 0)
    except (TypeError, ValueError):
        return 0

class KnowledgeSkillPromotionService:
    def __init__(self, memory):
        self.memory = memory

    async def propose_skill_promotions(
        self,
        *,
        limit: int = 100,
        min_successes: int = 3,
    ) -> KnowledgeSkillPromotionResult:
        lessons = await self.memory.knowledge_objects.list_many(
            object_types={KnowledgeObjectType.LESSON},
            statuses={KnowledgeObjectStatus.ACTIVE, KnowledgeObjectStatus.APPROVED},
            limit=limit,
        )
        existing_candidates = await self.memory.knowledge_objects.list_many(
            object_types={KnowledgeObjectType.ACTION_CANDIDATE},
            statuses={KnowledgeObjectStatus.DRAFT, KnowledgeObjectStatus.APPROVED, KnowledgeObjectStatus.REJECTED},
            limit=1_000,
        )
        existing_lesson_ids, existing_cluster_keys = self._existing_skill_candidate_keys(existing_candidates)
        review_markers_by_key = self._workflow_review_markers_by_cluster_key(existing_candidates)
        usage_clusters = await self._workflow_usage_event_clusters(limit=limit)
        review_blocked_lesson_ids = self._review_blocked_workflow_lesson_ids(
            lessons,
            existing_lesson_ids=existing_lesson_ids,
            usage_clusters=usage_clusters,
            review_markers_by_key=review_markers_by_key,
        )

        created: list[KnowledgeObject] = []
        skipped = 0
        cluster_result = await self._propose_workflow_cluster_promotions(
            lessons,
            existing_lesson_ids=existing_lesson_ids | review_blocked_lesson_ids,
            existing_cluster_keys=existing_cluster_keys,
            min_successes=min_successes,
            usage_clusters=usage_clusters,
            review_markers_by_key=review_markers_by_key,
        )
        created.extend(cluster_result.created)
        skipped += cluster_result.skipped
        clustered_lesson_ids = {
            lesson_id
            for candidate in cluster_result.created
            for lesson_id in _int_ids(candidate.metadata.get("source_lesson_ids"))
        }

        for lesson in lessons:
            if lesson.id in existing_lesson_ids or lesson.id in review_blocked_lesson_ids or lesson.id in clustered_lesson_ids:
                skipped += 1
                continue
            made = await self._propose_single_lesson_skill(lesson, min_successes=min_successes)
            if made is None:
                skipped += 1
                continue
            created.append(made)
        return KnowledgeSkillPromotionResult(created=created, skipped=skipped)

    async def list_workflow_clusters(
        self,
        *,
        limit: int = 100,
        min_successes: int = 3,
        include_below_threshold: bool = False,
    ) -> KnowledgeWorkflowClusterResult:
        lessons = await self.memory.knowledge_objects.list_many(
            object_types={KnowledgeObjectType.LESSON},
            statuses={KnowledgeObjectStatus.ACTIVE, KnowledgeObjectStatus.APPROVED},
            limit=limit,
        )
        existing_candidates = await self.memory.knowledge_objects.list_many(
            object_types={KnowledgeObjectType.ACTION_CANDIDATE},
            statuses={KnowledgeObjectStatus.DRAFT, KnowledgeObjectStatus.APPROVED, KnowledgeObjectStatus.REJECTED},
            limit=1_000,
        )
        candidates_by_key = self._skill_candidates_by_cluster_key(existing_candidates)
        review_markers_by_key = self._workflow_review_markers_by_cluster_key(existing_candidates)
        clusters = _workflow_clusters_from_lessons(lessons)
        usage_clusters = await self._workflow_usage_event_clusters(limit=limit)

        ambiguous_unscoped_keys = _ambiguous_unscoped_usage_keys(set(clusters))

        items: list[KnowledgeWorkflowCluster] = []
        skipped = 0
        for cluster_id in sorted(set(clusters) | set(usage_clusters)):
            scope, key = _split_workflow_cluster_id(cluster_id)
            cluster_lessons = clusters.get(cluster_id, [])
            usage_evidence = _usage_evidence_for_cluster(
                usage_clusters,
                cluster_id,
                key,
                ambiguous_unscoped_keys=ambiguous_unscoped_keys,
            )
            sorted_lessons = _sort_workflow_lessons(cluster_lessons)
            helpful, successes, failures, corrections = _cluster_evidence(sorted_lessons)
            helpful += usage_evidence.helpful_count
            successes += usage_evidence.success_count
            failures += usage_evidence.failure_count
            corrections += usage_evidence.correction_count
            usage_event_count = len(usage_evidence.event_ids)
            has_promotable_lessons = len(sorted_lessons) >= 2
            has_repeated_usage = usage_event_count >= 2 and max(usage_evidence.helpful_count, usage_evidence.success_count) >= min_successes
            meets_threshold = (has_promotable_lessons or has_repeated_usage) and max(helpful, successes, helpful + successes) >= min_successes
            if not meets_threshold and not include_below_threshold:
                skipped += len(cluster_lessons) or usage_event_count
                continue
            legacy_candidates = [] if key in ambiguous_unscoped_keys else candidates_by_key.get(key, [])
            candidate_objects = candidates_by_key.get(cluster_id) or legacy_candidates
            legacy_review_markers = [] if key in ambiguous_unscoped_keys else review_markers_by_key.get(key, [])
            review_markers = review_markers_by_key.get(cluster_id) or legacy_review_markers
            cluster_last_seen_at = _cluster_last_seen_at(sorted_lessons, usage_evidence)
            current_review_markers = current_workflow_review_markers(review_markers, cluster_last_seen_at)
            candidate_ids = sorted(candidate.id for candidate in candidate_objects)
            lifecycle_status = _workflow_cluster_lifecycle_status(candidate_objects, current_review_markers, meets_threshold=meets_threshold)
            promotion_ready = meets_threshold and has_promotable_lessons and lifecycle_status not in {"reviewed", "rejected"}
            status = (
                "candidate_exists"
                if candidate_ids
                else "ready"
                if promotion_ready
                else "below_threshold"
            )
            title = sorted_lessons[0].title if sorted_lessons else key.replace("-", " ").title()
            lesson_count = len(sorted_lessons)
            items.append(
                KnowledgeWorkflowCluster(
                    id=cluster_id,
                    scope=scope,
                    key=key,
                    title=title,
                    summary=_workflow_cluster_summary(
                        title=title,
                        lesson_count=lesson_count,
                        usage_event_count=usage_event_count,
                        success_count=successes,
                        failure_count=failures,
                        correction_count=corrections,
                    ),
                    trigger_description=_workflow_cluster_trigger_description(scope, key),
                    status=lifecycle_status,
                    promotion_status=status,
                    lesson_count=lesson_count,
                    usage_event_count=usage_event_count,
                    source_lesson_ids=[lesson.id for lesson in sorted_lessons],
                    source_episode_ids=_source_episode_ids(sorted_lessons),
                    source_artifact_ids=_source_artifact_ids(sorted_lessons),
                    source_usage_event_ids=usage_evidence.event_ids[:25],
                    last_seen_at=cluster_last_seen_at,
                    success_count=successes,
                    helpful_count=helpful,
                    failure_count=failures,
                    correction_count=corrections,
                    has_skill_candidate=bool(candidate_ids),
                    skill_candidate_ids=candidate_ids,
                    why_should_exist=(
                        f"Workflow cluster '{cluster_id}' has lesson_count={lesson_count}, "
                        f"usage_event_count={usage_event_count}, "
                        f"success_count={successes}, helpful_count={helpful}, "
                        f"failure_count={failures}, correction_count={corrections}, "
                        f"promotion_status={status}."
                    ),
                    metadata=_workflow_cluster_metadata(
                        cluster_id=cluster_id,
                        scope=scope,
                        key=key,
                        lifecycle_status=lifecycle_status,
                        promotion_status=status,
                        candidate_ids=candidate_ids,
                        review_markers=current_review_markers,
                    ),
                )
            )
        items.sort(
            key=lambda item: (
                item.promotion_status != "ready",
                -(item.success_count + item.helpful_count),
                -item.lesson_count,
                item.id,
            )
        )
        return KnowledgeWorkflowClusterResult(clusters=items, skipped=skipped)

    async def _workflow_usage_event_clusters(self, *, limit: int) -> dict[str, WorkflowUsageEvidence]:
        access_events = getattr(self.memory, "access_events", None)
        list_recent = getattr(access_events, "list_recent", None)
        if list_recent is None:
            return {}
        events = await list_recent(limit=max(limit, 100), source=None)
        return _workflow_clusters_from_usage_events(events)

    def _existing_skill_candidate_keys(self, candidates: list[KnowledgeObject]) -> tuple[set[int], set[str]]:
        lesson_ids: set[int] = set()
        cluster_keys: set[str] = set()
        for candidate in candidates:
            if is_workflow_cluster_review_marker(candidate):
                continue
            if not is_skill_promotion_candidate(candidate):
                continue
            lesson_ids.update(_int_ids(candidate.metadata.get("source_lesson_ids")))
            cluster_id = candidate.metadata.get("workflow_cluster_id")
            if isinstance(cluster_id, str) and cluster_id.strip():
                cluster_keys.add(cluster_id.strip())
            value = candidate.metadata.get("workflow_cluster_key")
            if isinstance(value, str) and value.strip():
                cluster_keys.add(_skill_slug(value))
        return lesson_ids, cluster_keys

    def _skill_candidates_by_cluster_key(self, candidates: list[KnowledgeObject]) -> dict[str, list[KnowledgeObject]]:
        candidates_by_key: dict[str, list[KnowledgeObject]] = defaultdict(list)
        for candidate in candidates:
            if not is_skill_promotion_candidate(candidate):
                continue
            cluster_id = candidate.metadata.get("workflow_cluster_id")
            if isinstance(cluster_id, str) and cluster_id.strip():
                candidates_by_key[cluster_id.strip()].append(candidate)
            value = candidate.metadata.get("workflow_cluster_key")
            if isinstance(value, str) and value.strip():
                candidates_by_key[_skill_slug(value)].append(candidate)
        return {key: sorted(items, key=lambda item: item.id) for key, items in candidates_by_key.items()}

    def _workflow_review_markers_by_cluster_key(self, candidates: list[KnowledgeObject]) -> dict[str, list[KnowledgeObject]]:
        markers_by_key: dict[str, list[KnowledgeObject]] = defaultdict(list)
        for marker in candidates:
            if not is_workflow_cluster_review_marker(marker):
                continue
            cluster_id = marker.metadata.get("workflow_cluster_id")
            if isinstance(cluster_id, str) and cluster_id.strip():
                markers_by_key[cluster_id.strip()].append(marker)
            value = marker.metadata.get("workflow_cluster_key")
            if isinstance(value, str) and value.strip():
                markers_by_key[_skill_slug(value)].append(marker)
        return {key: sorted(items, key=lambda item: item.id) for key, items in markers_by_key.items()}

    def _review_blocked_workflow_lesson_ids(
        self,
        lessons: list[KnowledgeObject],
        *,
        existing_lesson_ids: set[int],
        usage_clusters: dict[str, WorkflowUsageEvidence],
        review_markers_by_key: dict[str, list[KnowledgeObject]],
    ) -> set[int]:
        clusters = _workflow_clusters_from_lessons(lessons, excluded_lesson_ids=existing_lesson_ids)
        ambiguous_unscoped_keys = _ambiguous_unscoped_usage_keys(set(clusters))
        blocked: set[int] = set()
        for cluster_id, cluster_lessons in clusters.items():
            _scope, key = _split_workflow_cluster_id(cluster_id)
            review_markers = review_markers_by_key.get(cluster_id) or (
                [] if key in ambiguous_unscoped_keys else review_markers_by_key.get(key, [])
            )
            if not review_markers:
                continue
            usage_evidence = _usage_evidence_for_cluster(
                usage_clusters,
                cluster_id,
                key,
                ambiguous_unscoped_keys=ambiguous_unscoped_keys,
            )
            last_seen_at = _cluster_last_seen_at(_sort_workflow_lessons(cluster_lessons), usage_evidence)
            if current_workflow_review_markers(review_markers, last_seen_at):
                blocked.update(lesson.id for lesson in cluster_lessons)
        return blocked

    async def _propose_workflow_cluster_promotions(
        self,
        lessons: list[KnowledgeObject],
        *,
        existing_lesson_ids: set[int],
        existing_cluster_keys: set[str],
        min_successes: int,
        usage_clusters: dict[str, WorkflowUsageEvidence],
        review_markers_by_key: dict[str, list[KnowledgeObject]] | None = None,
    ) -> KnowledgeSkillPromotionResult:
        clusters = _workflow_clusters_from_lessons(lessons, excluded_lesson_ids=existing_lesson_ids)

        ambiguous_unscoped_keys = _ambiguous_unscoped_usage_keys(set(clusters))
        review_markers_by_key = review_markers_by_key or {}

        created: list[KnowledgeObject] = []
        skipped = 0
        for cluster_id, cluster_lessons in sorted(clusters.items()):
            _scope, key = _split_workflow_cluster_id(cluster_id)
            made = await self._propose_workflow_cluster_skill(
                cluster_id,
                key,
                cluster_lessons,
                existing_cluster_keys=existing_cluster_keys,
                min_successes=min_successes,
                usage_evidence=_usage_evidence_for_cluster(
                    usage_clusters,
                    cluster_id,
                    key,
                    ambiguous_unscoped_keys=ambiguous_unscoped_keys,
                ),
                review_markers=(
                    review_markers_by_key.get(cluster_id)
                    or ([] if key in ambiguous_unscoped_keys else review_markers_by_key.get(key, []))
                ),
            )
            if made is None:
                skipped += len(cluster_lessons)
                continue
            created.append(made)
        return KnowledgeSkillPromotionResult(created=created, skipped=skipped)

    async def _propose_workflow_cluster_skill(
        self,
        cluster_id: str,
        key: str,
        lessons: list[KnowledgeObject],
        *,
        existing_cluster_keys: set[str],
        min_successes: int,
        usage_evidence: WorkflowUsageEvidence,
        review_markers: list[KnowledgeObject] | None = None,
    ) -> KnowledgeObject | None:
        if cluster_id in existing_cluster_keys or key in existing_cluster_keys or len(lessons) < 2:
            return None
        sorted_lessons = _sort_workflow_lessons(lessons)
        cluster_last_seen_at = _cluster_last_seen_at(sorted_lessons, usage_evidence)
        if current_workflow_review_markers(review_markers or [], cluster_last_seen_at):
            return None
        helpful, successes, failures, corrections = _cluster_evidence(sorted_lessons)
        helpful += usage_evidence.helpful_count
        successes += usage_evidence.success_count
        failures += usage_evidence.failure_count
        corrections += usage_evidence.correction_count
        if max(helpful, successes, helpful + successes) < min_successes:
            return None

        skill_lessons = sorted_lessons[:8]
        title = skill_lessons[0].title
        skill_body = _skill_body_from_workflow_cluster(title, skill_lessons)
        source_episode_ids = _source_episode_ids(sorted_lessons)
        source_artifact_ids = _source_artifact_ids(sorted_lessons)
        source_lesson_ids = [lesson.id for lesson in sorted_lessons]
        return await self.memory.knowledge_objects.create(
            KnowledgeObjectCreate(
                object_type=KnowledgeObjectType.ACTION_CANDIDATE,
                title=f"Propose workflow skill: {title}",
                text=f"Review this repeated workflow cluster as a possible skill:\n\n{skill_body}",
                status=KnowledgeObjectStatus.DRAFT,
                scope=skill_lessons[0].scope,
                activation="review",
                proactiveness_level="L3",
                score=max(max(lesson.score for lesson in sorted_lessons), 0.65),
                source_ids=[f"knowledge:{lesson.id}" for lesson in sorted_lessons] + source_episode_ids + source_artifact_ids,
                metadata=self._workflow_cluster_metadata(
                    cluster_id=cluster_id,
                    key=key,
                    title=title,
                    lessons=skill_lessons,
                    cluster_size=len(sorted_lessons),
                    source_lesson_ids=source_lesson_ids,
                    skill_body=skill_body,
                    source_episode_ids=source_episode_ids,
                    source_artifact_ids=source_artifact_ids,
                    source_usage_event_ids=usage_evidence.event_ids[:25],
                    last_seen_at=cluster_last_seen_at,
                    usage_event_count=len(usage_evidence.event_ids),
                    successes=successes,
                    helpful=helpful,
                    failures=failures,
                    corrections=corrections,
                ),
            )
        )

    def _workflow_cluster_metadata(
        self,
        *,
        cluster_id: str,
        key: str,
        title: str,
        lessons: list[KnowledgeObject],
        cluster_size: int,
        source_lesson_ids: list[int],
        skill_body: str,
        source_episode_ids: list[str],
        source_artifact_ids: list[str],
        source_usage_event_ids: list[int],
        last_seen_at: str | None,
        usage_event_count: int,
        successes: int,
        helpful: int,
        failures: int,
        corrections: int,
    ) -> dict[str, object]:
        return {
            "processor": "workflow_skill_promotion",
            "promotion_kind": PROMOTION_KIND_SKILL,
            "promotion_source": "workflow_cluster",
            "workflow_cluster_id": cluster_id,
            "workflow_cluster_key": key,
            "workflow_cluster_size": cluster_size,
            "source_lesson_ids": source_lesson_ids,
            "skill_body_lesson_ids": [lesson.id for lesson in lessons],
            "source_episode_ids": source_episode_ids,
            "source_artifact_ids": source_artifact_ids,
            "source_usage_event_ids": source_usage_event_ids,
            "last_seen_at": last_seen_at,
            "usage_event_count": usage_event_count,
            "approval_flow": APPROVAL_FLOW_MEMORY_REVIEW_CREATE_SKILL,
            "skill_name": _skill_slug(title),
            "skill_description": f"Use when this repeated workflow applies: {title}",
            "skill_body": skill_body,
            "success_count": successes,
            "helpful_count": helpful,
            "failure_count": failures,
            "correction_count": corrections,
            "why_should_exist": (
                f"Repeated workflow cluster '{key}' has {cluster_size} source lessons "
                f"and usage_event_count={usage_event_count} "
                f"with success_count={successes}, helpful_count={helpful}, "
                f"failure_count={failures}, and correction_count={corrections}."
            ),
            "write_gate": WRITE_GATE_VERSION,
            "write_gate_action": "review",
            "write_gate_reason": "workflow_cluster_success",
            "write_gate_confidence": 0.82,
        }

    async def _propose_single_lesson_skill(
        self,
        lesson: KnowledgeObject,
        *,
        min_successes: int,
    ) -> KnowledgeObject | None:
        helpful, success_count = _lesson_evidence(lesson)
        if max(helpful, success_count) < min_successes and helpful + success_count < min_successes:
            return None
        if len(lesson.text.split()) < 8:
            return None

        skill_name = _skill_slug(lesson.title)
        skill_description = f"Use when this remembered workflow applies: {lesson.title}"
        skill_body = _skill_body_from_lesson(lesson)
        return await self.memory.knowledge_objects.create(
            KnowledgeObjectCreate(
                object_type=KnowledgeObjectType.ACTION_CANDIDATE,
                title=f"Propose skill: {lesson.title}",
                text=f"Review this repeated lesson as a possible skill:\n\n{lesson.text}",
                status=KnowledgeObjectStatus.DRAFT,
                scope=lesson.scope,
                activation="review",
                proactiveness_level="L3",
                score=max(lesson.score, 0.6),
                source_ids=[f"knowledge:{lesson.id}", *lesson.source_ids],
                metadata={
                    "processor": "skill_promotion",
                    "promotion_kind": PROMOTION_KIND_SKILL,
                    "source_lesson_ids": [lesson.id],
                    "approval_flow": APPROVAL_FLOW_MEMORY_REVIEW_CREATE_SKILL,
                    "skill_name": skill_name,
                    "skill_description": skill_description,
                    "skill_body": skill_body,
                    "success_count": success_count,
                    "helpful_count": helpful,
                    "write_gate": WRITE_GATE_VERSION,
                    "write_gate_action": "review",
                    "write_gate_reason": "repeated_successful_lesson",
                    "write_gate_confidence": 0.78,
                },
            )
        )

    async def mark_workflow_cluster_review(
        self,
        cluster_id: str,
        *,
        status: str,
        reason: str | None = None,
    ) -> KnowledgeObject:
        if status not in {"reviewed", "rejected"}:
            raise ValueError("Workflow cluster review status must be 'reviewed' or 'rejected'")

        snapshot = await self.list_workflow_clusters(limit=10_000, min_successes=1, include_below_threshold=True)
        cluster = next((item for item in snapshot.clusters if item.id == cluster_id), None)
        if cluster is None:
            raise KeyError(f"Workflow cluster {cluster_id} not found")

        now = datetime.now(UTC).isoformat()
        object_status = KnowledgeObjectStatus.APPROVED if status == "reviewed" else KnowledgeObjectStatus.REJECTED
        reason_text = reason.strip() if isinstance(reason, str) and reason.strip() else None
        source_ids = [f"knowledge:{lesson_id}" for lesson_id in cluster.source_lesson_ids[:25]]
        metadata = {
            "promotion_kind": PROMOTION_KIND_WORKFLOW_CLUSTER_REVIEW,
            "workflow_cluster_id": cluster.id,
            "workflow_cluster_key": cluster.key,
            "workflow_review_status": status,
            "workflow_reviewed_at": now,
            "workflow_review_reason": reason_text,
            "source_lesson_ids": cluster.source_lesson_ids,
            "source_episode_ids": cluster.source_episode_ids,
            "source_artifact_ids": cluster.source_artifact_ids,
            "source_usage_event_ids": cluster.source_usage_event_ids,
            "usage_event_count": cluster.usage_event_count,
            "success_count": cluster.success_count,
            "helpful_count": cluster.helpful_count,
            "failure_count": cluster.failure_count,
            "correction_count": cluster.correction_count,
            "last_seen_at": cluster.last_seen_at,
            "write_gate": WRITE_GATE_VERSION,
            "write_gate_action": "review",
            "write_gate_reason": "workflow_cluster_lifecycle_review",
            "write_gate_confidence": 0.9,
        }
        title = f"Workflow cluster {status}: {cluster.title}"
        text = f"Workflow cluster `{cluster.id}` marked {status}."
        if reason_text:
            text += f"\n\nReason: {reason_text}"
        text += f"\n\n{cluster.why_should_exist}"
        existing_markers = await self.memory.knowledge_objects.list_many(
            object_types={KnowledgeObjectType.ACTION_CANDIDATE},
            statuses={KnowledgeObjectStatus.APPROVED, KnowledgeObjectStatus.REJECTED},
            limit=1_000,
        )
        existing_marker = next(
            (
                marker
                for marker in sorted(existing_markers, key=lambda item: item.id, reverse=True)
                if is_workflow_cluster_review_marker(marker)
                and marker.metadata.get("workflow_cluster_id") == cluster.id
            ),
            None,
        )
        if existing_marker is not None:
            return await self.memory.knowledge_objects.update(
                existing_marker.id,
                KnowledgeObjectUpdate(
                    title=title,
                    text=text,
                    status=object_status,
                    scope=cluster.scope,
                    score=0.5,
                    source_ids=source_ids,
                    metadata=metadata,
                ),
            )
        return await self.memory.knowledge_objects.create(
            KnowledgeObjectCreate(
                object_type=KnowledgeObjectType.ACTION_CANDIDATE,
                title=title,
                text=text,
                status=object_status,
                scope=cluster.scope,
                score=0.5,
                source_ids=source_ids,
                metadata=metadata,
            )
        )

    async def create_skill_from_candidate(self, candidate_id: int, skill_service: SkillCreator) -> KnowledgeObject:
        candidate = await self.memory.knowledge_objects.get(candidate_id)
        if candidate is None:
            raise KeyError(f"Knowledge object {candidate_id} not found")
        if not is_skill_promotion_candidate(candidate):
            raise ValueError("Knowledge object is not a skill promotion candidate")

        metadata = dict(candidate.metadata)
        name = _string_metadata(metadata, "skill_name")
        description = _string_metadata(metadata, "skill_description")
        body = _string_metadata(metadata, "skill_body")
        skill = skill_service.create(name, description, body, source=f"knowledge:{candidate.id}")

        now = datetime.now(UTC).isoformat()
        metadata.update(
            {
                "skill_created_name": getattr(skill, "name", name),
                "skill_created_path": str(getattr(skill, "path", "")),
                "skill_created_at": now,
            }
        )
        updated = await self.memory.knowledge_objects.update(
            candidate.id,
            KnowledgeObjectUpdate(status=KnowledgeObjectStatus.APPROVED, metadata=metadata),
        )
        skill_link = {
            "candidate_id": candidate.id,
            "skill_name": name,
            "skill_path": str(getattr(skill, "path", "")),
            "created_at": now,
        }
        for object_id in _skill_source_memory_ids(candidate, metadata):
            source = await self.memory.knowledge_objects.get(object_id)
            if source is None:
                continue
            source_metadata = dict(source.metadata)
            promotions = source_metadata.get("skill_promotions")
            if not isinstance(promotions, list):
                promotions = []
            promotions.append(skill_link)
            source_metadata["skill_promotions"] = promotions[-20:]
            await self.memory.knowledge_objects.update(source.id, KnowledgeObjectUpdate(metadata=source_metadata))
        return updated
