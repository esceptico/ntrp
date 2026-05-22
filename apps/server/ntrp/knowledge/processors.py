from datetime import UTC, datetime

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
)
from ntrp.knowledge.profiles import PROFILE_POLICY_VERSION, profile_entity_name, unique
from ntrp.knowledge.sinks import publish_artifact
from ntrp.memory.service import MemoryService

_ACTION_HINTS = ("note", "artifact", "reminder", "task", "todo", "verify", "obsidian", "publish")
_PROCEDURE_HINTS = ("failed", "error", "correction", "corrected", "should", "prefer", "always", "never")
_NEGATIVE_SIGNALS = {"not_helpful", "harmful", "corrected", "wrong", "failed"}
_POSITIVE_SIGNALS = {"helpful", "success", "used"}
def _first_line(text: str, limit: int = 100) -> str:
    line = text.strip().splitlines()[0] if text.strip() else "Untitled"
    return line[:limit]


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

    async def synthesize_profiles(self, request: KnowledgeProfileSynthesisRequest) -> KnowledgeProfileSynthesisResult:
        list_names = getattr(self.memory.knowledge_objects, "list_profile_entity_names", None)
        entity_names = unique(
            [name for raw in request.entity_names if (name := profile_entity_name(raw, explicit=True)) is not None]
        )
        if not entity_names and list_names is not None:
            listed = await list_names(limit=max(request.limit_entities * 4, request.limit_entities))
            entity_names = unique([name for raw in listed if (name := profile_entity_name(raw, explicit=False)) is not None])
        entity_names = entity_names[: request.limit_entities]

        refresh_profile = getattr(self.memory.knowledge_objects, "refresh_entity_profile", None)
        if refresh_profile is None or not request.apply:
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
        if request.target_object_id is not None:
            source_ids.append(f"knowledge:{request.target_object_id}")
            target = await self.memory.knowledge_objects.get(request.target_object_id)
            if target is not None and request.score_delta:
                metadata = dict(target.metadata)
                counts = dict(metadata.get("feedback_counts") if isinstance(metadata.get("feedback_counts"), dict) else {})
                counts[request.signal] = int(counts.get(request.signal, 0)) + 1
                metadata["feedback_counts"] = counts
                metadata["last_feedback_signal"] = request.signal
                metadata["last_feedback_at"] = datetime.now(UTC).isoformat()
                if target.object_type == KnowledgeObjectType.PROCEDURE:
                    if request.signal in _POSITIVE_SIGNALS:
                        metadata["success_count"] = int(metadata.get("success_count", 0)) + 1
                    if request.signal in _NEGATIVE_SIGNALS:
                        metadata["failure_count"] = int(metadata.get("failure_count", 0)) + 1
                await self.memory.knowledge_objects.update(
                    target.id,
                    KnowledgeObjectUpdate(score=target.score + request.score_delta, metadata=metadata),
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
                    "query": request.query,
                    "signal": request.signal,
                    "score_delta": request.score_delta,
                },
            )
        )
        if target is not None and target.object_type == KnowledgeObjectType.PROCEDURE and request.signal in _NEGATIVE_SIGNALS:
            await self.memory.knowledge_objects.create(
                KnowledgeObjectCreate(
                    object_type=KnowledgeObjectType.PROCEDURE_CANDIDATE,
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
                        "target_procedure_id": target.id,
                        "feedback_object_id": feedback.id,
                        "signal": request.signal,
                    },
                )
            )
        return feedback

    async def prune_retention(self, request: KnowledgePruneRequest) -> KnowledgePruneResult:
        return await self.memory.knowledge_objects.prune_retention(request)

    async def health(self) -> KnowledgeHealthResult:
        objects = await self.memory.knowledge_objects.list_many(limit=1000)
        counts = await self.memory.knowledge_objects.count_by_type()
        now = datetime.now(UTC)
        missing_provenance = 0
        stale = 0
        review_queue = 0
        for obj in objects:
            if obj.object_type not in {KnowledgeObjectType.SOURCE, KnowledgeObjectType.EVIDENCE_REF} and not obj.source_ids:
                missing_provenance += 1
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
        return KnowledgeHealthResult(
            counts=counts,
            missing_provenance=missing_provenance,
            stale=stale,
            review_queue=review_queue,
        )

    async def _reflect_episode(self, episode: KnowledgeObject) -> list[KnowledgeObject]:
        if episode.object_type != KnowledgeObjectType.MEMORY_EPISODE:
            return []

        extracted = await self.memory.knowledge_objects._extract_memories_from_closed_episode(episode)
        if extracted:
            metadata = dict(episode.metadata)
            metadata["extracted_memory_ids"] = list(dict.fromkeys(obj.id for obj in extracted))
            await self.memory.knowledge_objects.update(episode.id, KnowledgeObjectUpdate(metadata=metadata))
            return extracted

        source_id = f"knowledge:{episode.id}"
        lowered = episode.text.lower()
        created: list[KnowledgeObject] = []

        if (
            any(hint in lowered for hint in _PROCEDURE_HINTS)
            and await self.memory.knowledge_objects.get_by_source_id(source_id, KnowledgeObjectType.PATTERN) is None
        ):
            created.append(
                await self.memory.knowledge_objects.create(
                    KnowledgeObjectCreate(
                        object_type=KnowledgeObjectType.PATTERN,
                        title=f"Pattern from {episode.title}",
                        text=f"Potential repeated pattern to validate: {_first_line(episode.text, 240)}",
                        status=KnowledgeObjectStatus.DRAFT,
                        scope=episode.scope,
                        activation="review",
                        proactiveness_level="L2",
                        score=0.25,
                        source_ids=[source_id],
                        metadata={"processor": "reflect", "episode_id": episode.id},
                    )
                )
            )
        if any(hint in lowered for hint in _PROCEDURE_HINTS):
            if (
                await self.memory.knowledge_objects.get_by_source_id(source_id, KnowledgeObjectType.PROCEDURE_CANDIDATE)
                is None
            ):
                created.append(
                    await self.memory.knowledge_objects.create(
                        KnowledgeObjectCreate(
                            object_type=KnowledgeObjectType.PROCEDURE_CANDIDATE,
                            title=f"Procedure candidate from {episode.title}",
                            text=f"Review whether this episode should change future behavior: {_first_line(episode.text, 240)}",
                            status=KnowledgeObjectStatus.DRAFT,
                            scope=episode.scope,
                            activation="review",
                            proactiveness_level="L2",
                            score=0.3,
                            source_ids=[source_id],
                            metadata={"processor": "reflect", "episode_id": episode.id},
                        )
                    )
                )
        if any(hint in lowered for hint in _ACTION_HINTS):
            if (
                await self.memory.knowledge_objects.get_by_source_id(source_id, KnowledgeObjectType.ACTION_CANDIDATE)
                is None
            ):
                created.append(
                    await self.memory.knowledge_objects.create(
                        KnowledgeObjectCreate(
                            object_type=KnowledgeObjectType.ACTION_CANDIDATE,
                            title=f"Action candidate from {episode.title}",
                            text=f"Review whether this episode needs a follow-up action: {_first_line(episode.text, 240)}",
                            status=KnowledgeObjectStatus.DRAFT,
                            scope=episode.scope,
                            activation="review",
                            proactiveness_level="L2",
                            score=0.3,
                            source_ids=[source_id],
                            metadata={"processor": "reflect", "episode_id": episode.id},
                        )
                    )
                )
        return created
