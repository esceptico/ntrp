from datetime import UTC, datetime, timedelta

from ntrp.knowledge.metadata import has_write_gate_decision, is_correction_candidate, is_skill_promotion_candidate
from ntrp.knowledge.models import KnowledgeHealthResult, KnowledgeObjectStatus, KnowledgeObjectType


class KnowledgeHealthService:
    def __init__(self, memory):
        self.memory = memory

    async def health(self) -> KnowledgeHealthResult:
        objects = await self.memory.knowledge_objects.list_many(limit=1000)
        counts = await self.memory.knowledge_objects.count_by_type()
        now = datetime.now(UTC)
        missing_provenance = 0
        stale = 0
        review_queue = 0
        active_legacy_objects = 0
        tool_episode_candidates = 0
        extracted_without_source_episode = 0
        unsourced_active_durable_objects = 0
        write_gate_decisions = 0
        write_gate_reviews_pending = 0
        correction_candidates_pending = 0
        skill_candidates_pending = 0
        knowledge_ref_ids: set[int] = set()
        memory_usage_events_7d = 0
        memory_helped_7d = 0
        memory_irrelevant_7d = 0
        memory_harmful_7d = 0
        legacy_active_types = {
            KnowledgeObjectType.ENTITY_PROFILE,
            KnowledgeObjectType.PATTERN,
            KnowledgeObjectType.PROCEDURE,
            KnowledgeObjectType.PROCEDURE_CANDIDATE,
        }
        extracted_types = {KnowledgeObjectType.FACT, KnowledgeObjectType.LESSON, KnowledgeObjectType.ARTIFACT}
        for obj in objects:
            if obj.object_type not in {KnowledgeObjectType.SOURCE, KnowledgeObjectType.EVIDENCE_REF} and not obj.source_ids:
                missing_provenance += 1
            if (
                obj.status == KnowledgeObjectStatus.ACTIVE
                and obj.object_type in extracted_types
                and not obj.source_ids
            ):
                unsourced_active_durable_objects += 1
            if has_write_gate_decision(obj):
                write_gate_decisions += 1
                if (
                    obj.status == KnowledgeObjectStatus.DRAFT
                    and obj.object_type == KnowledgeObjectType.ACTION_CANDIDATE
                    and obj.metadata.get("write_gate_action") == "review"
                ):
                    write_gate_reviews_pending += 1
            if obj.status == KnowledgeObjectStatus.DRAFT and is_correction_candidate(obj):
                correction_candidates_pending += 1
            if obj.status == KnowledgeObjectStatus.DRAFT and is_skill_promotion_candidate(obj):
                skill_candidates_pending += 1
            for source_id in obj.source_ids:
                if source_id.startswith("knowledge:"):
                    try:
                        knowledge_ref_ids.add(int(source_id.split(":", 1)[1]))
                    except (IndexError, ValueError):
                        continue
            if obj.status == KnowledgeObjectStatus.ACTIVE and obj.object_type in legacy_active_types:
                active_legacy_objects += 1
            if obj.object_type == KnowledgeObjectType.MEMORY_EPISODE and obj.status == KnowledgeObjectStatus.ACTIVE:
                episode_text = f"{obj.title}\n{obj.text}".casefold()
                if episode_text.startswith("tool:") or "role: tool" in episode_text or "tool_result" in episode_text:
                    tool_episode_candidates += 1
            if obj.object_type in extracted_types and str(obj.metadata.get("extractor", "")).startswith("episode.close."):
                if not any("episode" in source_id.casefold() for source_id in obj.source_ids):
                    extracted_without_source_episode += 1
            if obj.status == KnowledgeObjectStatus.DRAFT and obj.object_type in {
                KnowledgeObjectType.PROCEDURE_CANDIDATE,
                KnowledgeObjectType.ACTION_CANDIDATE,
                KnowledgeObjectType.ARTIFACT,
            }:
                review_queue += 1
            verified_at = obj.metadata.get("verified_at")
            stale_after_days = obj.metadata.get("stale_after_days")
            if isinstance(verified_at, str) and stale_after_days is not None:
                try:
                    verified = datetime.fromisoformat(verified_at)
                    if verified.tzinfo is None:
                        verified = verified.replace(tzinfo=UTC)
                    if (now - verified.astimezone(UTC)).days > int(stale_after_days):
                        stale += 1
                except (TypeError, ValueError):
                    continue

        access_events = getattr(self.memory, "access_events", None)
        list_recent_access = getattr(access_events, "list_recent", None)
        if list_recent_access is not None:
            cutoff = now - timedelta(days=7)
            for event in await list_recent_access(limit=1_000):
                created_at = getattr(event, "created_at", None)
                if isinstance(created_at, datetime):
                    comparable = created_at if created_at.tzinfo else created_at.replace(tzinfo=UTC)
                    if comparable.astimezone(UTC) < cutoff:
                        continue
                details = getattr(event, "details", {})
                outcome = details.get("outcome") if isinstance(details, dict) else None
                memory_usage_events_7d += 1
                if outcome == "helped":
                    memory_helped_7d += 1
                elif outcome == "irrelevant":
                    memory_irrelevant_7d += 1
                elif outcome == "harmful":
                    memory_harmful_7d += 1

        propose_fact_consolidation = getattr(self.memory.knowledge_objects, "propose_fact_consolidation", None)
        duplicate_result = await propose_fact_consolidation(max_proposals=100) if propose_fact_consolidation else None
        dangling_source_refs = 0
        get_batch = getattr(self.memory.knowledge_objects, "get_batch", None)
        if get_batch is not None and knowledge_ref_ids:
            existing_refs = await get_batch(sorted(knowledge_ref_ids))
            dangling_source_refs = len(knowledge_ref_ids - set(existing_refs))
        return KnowledgeHealthResult(
            counts=counts,
            missing_provenance=missing_provenance,
            stale=stale,
            review_queue=review_queue,
            memory_usage_events_7d=memory_usage_events_7d,
            memory_helped_7d=memory_helped_7d,
            memory_irrelevant_7d=memory_irrelevant_7d,
            memory_harmful_7d=memory_harmful_7d,
            active_legacy_objects=active_legacy_objects,
            tool_episode_candidates=tool_episode_candidates,
            extracted_without_source_episode=extracted_without_source_episode,
            unsourced_active_durable_objects=unsourced_active_durable_objects,
            write_gate_decisions=write_gate_decisions,
            write_gate_reviews_pending=write_gate_reviews_pending,
            correction_candidates_pending=correction_candidates_pending,
            skill_candidates_pending=skill_candidates_pending,
            dangling_source_refs=dangling_source_refs,
            duplicate_fact_clusters=len(duplicate_result.proposals) if duplicate_result is not None else 0,
            fact_conflict_clusters=len(duplicate_result.conflicts) if duplicate_result is not None else 0,
        )
