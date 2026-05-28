from datetime import UTC, datetime

from ntrp.knowledge.health import KnowledgeHealthService
from ntrp.knowledge.metadata import PROMOTION_KIND_LESSON_REVISION, WRITE_GATE_VERSION
from ntrp.knowledge.models import (
    KnowledgeArtifactRenderRequest,
    KnowledgeFeedbackRequest,
    KnowledgeHealthResult,
    KnowledgeObject,
    KnowledgeObjectCreate,
    KnowledgeObjectStatus,
    KnowledgeObjectType,
    KnowledgeObjectUpdate,
    KnowledgeProfileSynthesisRequest,
    KnowledgeProfileSynthesisResult,
    KnowledgePruneRequest,
    KnowledgePruneResult,
    KnowledgePublishRequest,
    KnowledgeReflectRequest,
    KnowledgeReflectResult,
    KnowledgeSkillPromotionResult,
    KnowledgeWorkflowClusterResult,
)
from ntrp.knowledge.profiles import PROFILE_POLICY_VERSION, profile_entity_name, unique
from ntrp.knowledge.sinks import publish_artifact
from ntrp.knowledge.skill_promotions import KnowledgeSkillPromotionService
from ntrp.memory.service import MemoryService

_NEGATIVE_SIGNALS = {"not_helpful", "harmful", "corrected", "wrong", "failed"}
_POSITIVE_SIGNALS = {"helpful", "success", "used"}


def _usage_outcome(signal: str, explicit: str | None) -> str:
    if explicit is not None:
        return explicit
    if signal in _POSITIVE_SIGNALS:
        return "helped"
    if signal in {"not_helpful", "irrelevant"}:
        return "irrelevant"
    if signal in _NEGATIVE_SIGNALS:
        return "harmful"
    return "unknown"


class KnowledgeProcessorService:
    def __init__(self, memory: MemoryService):
        self.memory = memory

    async def reflect(self, request: KnowledgeReflectRequest) -> KnowledgeReflectResult:
        episodes = await self.memory.knowledge_objects.list(
            object_type=KnowledgeObjectType.MEMORY_EPISODE,
            status=KnowledgeObjectStatus.ACTIVE,
            limit=max(request.limit * 5, request.limit),
        )
        # Reflect only true multi-turn memory episodes. Legacy `episode` rows are
        # raw run provenance and produced generic garbage like "Fact from Run X".
        episodes = [
            episode
            for episode in episodes
            if episode.metadata.get("episode_status") == "closed" and not episode.metadata.get("extracted_memory_ids")
        ][: request.limit]
        created: list[KnowledgeObject] = []
        skipped = 0
        for episode in episodes:
            made = await self._reflect_episode(episode)
            if made:
                created.extend(made)
            else:
                skipped += 1
        return KnowledgeReflectResult(created=created, skipped=skipped)

    async def propose_skill_promotions(
        self,
        *,
        limit: int = 100,
        min_successes: int = 3,
    ) -> KnowledgeSkillPromotionResult:
        return await KnowledgeSkillPromotionService(self.memory).propose_skill_promotions(
            limit=limit,
            min_successes=min_successes,
        )

    async def workflow_clusters(
        self,
        *,
        limit: int = 100,
        min_successes: int = 3,
        include_below_threshold: bool = False,
    ) -> KnowledgeWorkflowClusterResult:
        return await KnowledgeSkillPromotionService(self.memory).list_workflow_clusters(
            limit=limit,
            min_successes=min_successes,
            include_below_threshold=include_below_threshold,
        )

    async def synthesize_profiles(self, request: KnowledgeProfileSynthesisRequest) -> KnowledgeProfileSynthesisResult:
        # Profiles are deliberately manual/explicit only. The previous auto-candidate
        # path could turn noisy extracted entities and topic labels into durable
        # active profiles, which polluted recall. Keep the endpoint for typed names,
        # but never fan out over every entity in the store.
        entity_names = unique(
            [name for raw in request.entity_names if (name := profile_entity_name(raw, explicit=True)) is not None]
        )[: request.limit_entities]

        refresh_profile = getattr(self.memory.knowledge_objects, "refresh_entity_profile", None)
        if refresh_profile is None or not request.apply or not entity_names:
            return KnowledgeProfileSynthesisResult(skipped=len(entity_names), policy_version=PROFILE_POLICY_VERSION)

        profiles: list[KnowledgeObject] = []
        skipped = 0
        for entity_name in entity_names:
            profile = await refresh_profile(entity_name, evidence_limit=request.evidence_limit, explicit_refresh=True)
            if profile is None:
                skipped += 1
            else:
                profiles.append(profile)
        return KnowledgeProfileSynthesisResult(profiles=profiles, skipped=skipped, policy_version=PROFILE_POLICY_VERSION)

    async def render_artifact(self, request: KnowledgeArtifactRenderRequest) -> KnowledgeObject:
        objects = await self.memory.knowledge_objects.get_batch(request.object_ids)
        ordered = [objects[object_id] for object_id in request.object_ids if object_id in objects]
        if not ordered:
            raise KeyError("No source knowledge objects found")
        body = [f"# {request.title}", ""]
        for obj in ordered:
            body.extend(
                [
                    f"## {obj.title}",
                    "",
                    obj.text,
                    "",
                    f"Sources: {', '.join(obj.source_ids) if obj.source_ids else 'none'}",
                    "",
                ]
            )
        return await self.memory.knowledge_objects.create(
            KnowledgeObjectCreate(
                object_type=KnowledgeObjectType.ARTIFACT,
                title=request.title,
                text="\n".join(body).strip(),
                status=KnowledgeObjectStatus.DRAFT,
                scope=request.scope,
                activation="review",
                proactiveness_level="L4",
                source_ids=[f"knowledge:{obj.id}" for obj in ordered],
                metadata={"source_object_ids": [obj.id for obj in ordered]},
            )
        )

    async def publish(self, request: KnowledgePublishRequest) -> KnowledgeObject:
        artifact = await self.memory.knowledge_objects.get(request.artifact_id)
        if artifact is None or artifact.object_type != KnowledgeObjectType.ARTIFACT:
            raise KeyError("Artifact not found")
        sink_result = await publish_artifact(artifact, sink=request.sink, sink_ref=request.sink_ref)
        return await self.memory.knowledge_objects.create(
            KnowledgeObjectCreate(
                object_type=KnowledgeObjectType.SINK_RECEIPT,
                title=f"Published {artifact.title}",
                text=f"Artifact {artifact.id} published to {request.sink}: {sink_result['path']}",
                status=KnowledgeObjectStatus.ACTIVE,
                scope=artifact.scope,
                activation="audit",
                proactiveness_level="L0",
                source_ids=[f"knowledge:{artifact.id}"],
                metadata={"artifact_id": artifact.id, **sink_result},
            )
        )

    async def feedback(self, request: KnowledgeFeedbackRequest) -> KnowledgeObject:
        source_ids: list[str] = []
        target: KnowledgeObject | None = None
        outcome = _usage_outcome(request.signal, request.outcome)
        usage_event = None
        if request.usage_event_id is not None:
            access_events = getattr(self.memory, "access_events", None)
            update_outcome = getattr(access_events, "update_outcome", None)
            if update_outcome is not None:
                usage_event = await update_outcome(
                    event_id=request.usage_event_id,
                    outcome=outcome,
                    reason=request.detail,
                    user_corrected_answer=outcome == "harmful" or request.signal in _NEGATIVE_SIGNALS,
                    signal=request.signal,
                )
        outcome_object_ids: list[int] = []
        if request.target_object_id is not None:
            source_ids.append(f"knowledge:{request.target_object_id}")
            target = await self.memory.knowledge_objects.get(request.target_object_id)
            if target is not None:
                await self._apply_feedback_to_target(target, request.signal, request.score_delta)
                outcome_object_ids.append(target.id)
        if usage_event is not None:
            outcome_object_ids.extend(
                object_id for object_id in usage_event.injected_fact_ids if object_id != request.target_object_id
            )
        record_usage_outcome = getattr(self.memory.knowledge_objects, "record_usage_outcome", None)
        if record_usage_outcome is not None:
            await record_usage_outcome(
                object_ids=outcome_object_ids,
                signal=request.signal,
                outcome=outcome,
                usage_event_id=request.usage_event_id,
            )
        feedback = await self.memory.knowledge_objects.create(
            KnowledgeObjectCreate(
                object_type=KnowledgeObjectType.OUTCOME_FEEDBACK,
                title=f"Feedback: {request.signal}",
                text=request.detail or request.signal,
                status=KnowledgeObjectStatus.ACTIVE,
                activation="audit",
                proactiveness_level="L0",
                score=request.score_delta,
                source_ids=source_ids,
                metadata={
                    "target_object_id": request.target_object_id,
                    "usage_event_id": request.usage_event_id,
                    "query": request.query,
                    "signal": request.signal,
                    "score_delta": request.score_delta,
                    "outcome": outcome,
                },
            )
        )
        if target is not None and target.object_type == KnowledgeObjectType.PROCEDURE and request.signal in _NEGATIVE_SIGNALS:
            await self.memory.knowledge_objects.create(
                KnowledgeObjectCreate(
                    object_type=KnowledgeObjectType.ACTION_CANDIDATE,
                    title=f"Revise procedure: {target.title}",
                    text=f"Review whether this procedure should be updated or deprecated after feedback '{request.signal}': {target.text}",
                    status=KnowledgeObjectStatus.DRAFT,
                    scope=target.scope,
                    activation="review",
                    proactiveness_level="L2",
                    score=max(0.2, target.score),
                    source_ids=[f"knowledge:{target.id}", f"knowledge:{feedback.id}", *target.source_ids],
                    metadata={
                        "processor": "feedback",
                        "promotion_kind": PROMOTION_KIND_LESSON_REVISION,
                        "target_object_id": target.id,
                        "target_procedure_id": target.id,
                        "feedback_object_id": feedback.id,
                        "signal": request.signal,
                        "write_gate": WRITE_GATE_VERSION,
                        "write_gate_action": "review",
                        "write_gate_reason": "negative_procedure_feedback",
                        "write_gate_confidence": 0.85,
                    },
                )
            )
        return feedback

    async def _apply_feedback_to_target(self, target: KnowledgeObject, signal: str, score_delta: float) -> None:
        metadata = dict(target.metadata)
        counts = dict(metadata.get("feedback_counts") if isinstance(metadata.get("feedback_counts"), dict) else {})
        counts[signal] = int(counts.get(signal, 0)) + 1
        metadata["feedback_counts"] = counts
        metadata["last_feedback_signal"] = signal
        metadata["last_feedback_at"] = datetime.now(UTC).isoformat()

        if target.object_type in {KnowledgeObjectType.LESSON, KnowledgeObjectType.PROCEDURE}:
            if signal in _POSITIVE_SIGNALS:
                metadata["success_count"] = int(metadata.get("success_count", 0)) + 1
            if signal in _NEGATIVE_SIGNALS:
                metadata["failure_count"] = int(metadata.get("failure_count", 0)) + 1

        await self.memory.knowledge_objects.update(
            target.id,
            KnowledgeObjectUpdate(score=target.score + score_delta, metadata=metadata),
        )

    async def prune_retention(self, request: KnowledgePruneRequest) -> KnowledgePruneResult:
        return await self.memory.knowledge_objects.prune_retention(request)

    async def health(self) -> KnowledgeHealthResult:
        return await KnowledgeHealthService(self.memory).health()

    async def _reflect_episode(self, episode: KnowledgeObject) -> list[KnowledgeObject]:
        if episode.object_type != KnowledgeObjectType.MEMORY_EPISODE:
            return []

        extracted = await self.memory.knowledge_objects._extract_memories_from_closed_episode(episode)
        if extracted:
            metadata = dict(episode.metadata)
            metadata["extracted_memory_ids"] = list(dict.fromkeys(obj.id for obj in extracted))
            await self.memory.knowledge_objects.update(episode.id, KnowledgeObjectUpdate(metadata=metadata))
            return extracted

        # Do not synthesize legacy review objects from keyword heuristics. They were noisy
        # enough to dominate memory cleanup (pattern/procedure/action candidates) and should
        # only come from explicit, source-backed extraction paths.
        return []
