from __future__ import annotations

import json
from datetime import UTC, datetime
from inspect import isawaitable
from re import findall, search
from typing import TYPE_CHECKING, Any, TypedDict

from ntrp.events.internal import RunCompleted
from ntrp.events.triggers import KnowledgeObjectChanged
from ntrp.knowledge.contradictions import annotate_conflicts, semantic_conflict
from ntrp.knowledge.entity_extraction import (
    EntityExtractionPipeline,
    EntityResolutionResult,
    ModelEntityExtractor,
    merge_resolved_entity_metadata,
)
from ntrp.knowledge.episodes import (
    EpisodeBoundaryClassifier,
    EpisodeBoundaryDecision,
    EpisodeMemoryExtraction,
    ModelBackedEpisodeBoundaryClassifier,
)
from ntrp.knowledge.models import (
    KnowledgeObject,
    KnowledgeObjectCreate,
    KnowledgeObjectStatus,
    KnowledgeObjectType,
    KnowledgeObjectUpdate,
    KnowledgePruneRequest,
    KnowledgePruneResult,
    KnowledgeSourceTrace,
    KnowledgeSourceTraceResult,
    KnowledgeSupersessionCommitResult,
    KnowledgeSupersessionProposal,
)
from ntrp.knowledge.profiles import (
    KnowledgeProfileService,
    KnowledgeProfileSynthesizer,
    profile_entity_resolution,
)
from ntrp.knowledge.store import KnowledgeObjectRepository
from ntrp.logging import get_logger
from ntrp.memory.facts import FactMemory
from ntrp.memory.models import MemoryAccessEvent, MemoryEvent

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

_logger = get_logger(__name__)

MAX_ACTIVE_MEMORY_EPISODES = 250
MAX_ACTIVE_MEMORY_EPISODES_PER_SESSION = 30
MAX_ACTIVE_PATTERN_CHARS = 1_800
MAX_ACTIVE_PATTERN_LINES = 40


class KnowledgeEmbeddingBackfillResult(TypedDict):
    apply: bool
    total_missing: int
    selected: int
    repaired: int
    object_ids: list[int]


class MemoryAccessEventService:
    def __init__(self, memory: FactMemory):
        self._memory = memory

    async def create(
        self,
        *,
        source: str,
        query: str | None = None,
        retrieved_fact_ids: list[int] | None = None,
        injected_fact_ids: list[int] | None = None,
        omitted_fact_ids: list[int] | None = None,
        formatted_chars: int = 0,
        policy_version: str,
        details: dict[str, Any] | None = None,
    ) -> MemoryAccessEvent:
        event = await self._memory.access_events.create(
            source=source,
            query=query,
            retrieved_fact_ids=retrieved_fact_ids,
            injected_fact_ids=injected_fact_ids,
            omitted_fact_ids=omitted_fact_ids,
            formatted_chars=formatted_chars,
            policy_version=policy_version,
            details=details,
        )
        await self._memory.db.conn.commit()
        return event

    async def list_recent(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        source: str | None = None,
    ) -> list[MemoryAccessEvent]:
        return await self._memory.access_events.list_recent(limit=limit, offset=offset, source=source)


class MemoryEventService:
    def __init__(self, memory: FactMemory):
        self._memory = memory

    async def list_recent(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        target_type: str | None = None,
        target_id: int | None = None,
        action: str | None = None,
    ) -> list[MemoryEvent]:
        return await self._memory.events.list_recent(
            limit=limit,
            offset=offset,
            target_type=target_type,
            target_id=target_id,
            action=action,
        )


class KnowledgeObjectService:
    def __init__(
        self,
        memory: FactMemory,
        *,
        entity_pipeline: EntityExtractionPipeline | None = None,
        profile_synthesizer: KnowledgeProfileSynthesizer | None = None,
    ):
        self._memory = memory
        self._repo = KnowledgeObjectRepository(memory.db.conn, memory.facts.read_conn)
        model = getattr(memory, "model", None)
        self._model = model if isinstance(model, str) and model else None
        primary_extractor = ModelEntityExtractor(model=model) if isinstance(model, str) and model else None
        self._entity_pipeline = entity_pipeline or EntityExtractionPipeline(primary=primary_extractor)
        self._boundary_classifier = (
            ModelBackedEpisodeBoundaryClassifier(model=model) if isinstance(model, str) and model else EpisodeBoundaryClassifier()
        )
        self._event_dispatcher: Callable[[KnowledgeObjectChanged], Awaitable[None]] | None = None
        self._profiles = KnowledgeProfileService(
            repo=self._repo,
            memory=self._memory,
            synthesizer=profile_synthesizer or KnowledgeProfileSynthesizer(model=self._model),
            sync_entity_resolution=self._sync_entity_resolution,
            embed_object=self._embed_object,
            emit_event=self._emit_event,
        )

    def set_event_dispatcher(self, dispatcher: Callable[[KnowledgeObjectChanged], Awaitable[None]] | None) -> None:
        self._event_dispatcher = dispatcher

    def _derived_profile_entity_result(self, object_type: KnowledgeObjectType, metadata: dict[str, Any]) -> EntityResolutionResult | None:
        return profile_entity_resolution(object_type, metadata)

    def _apply_create_policy(self, payload: KnowledgeObjectCreate) -> KnowledgeObjectCreate:
        metadata = dict(payload.metadata)
        status = payload.status
        policy_reason: str | None = None

        if payload.object_type in {KnowledgeObjectType.PROCEDURE, KnowledgeObjectType.PROCEDURE_CANDIDATE} and str(
            metadata.get("extractor", "")
        ).startswith("episode.close."):
            metadata.update(
                {
                    "create_policy": "knowledge.write_guardrails.v1",
                    "create_policy_reason": "episode_extractor_legacy_procedure_normalized_to_lesson",
                    "normalized_from_object_type": payload.object_type.value,
                    "requested_status": payload.status.value,
                }
            )
            return payload.model_copy(
                update={
                    "object_type": KnowledgeObjectType.LESSON,
                    "status": KnowledgeObjectStatus.ACTIVE,
                    "activation": "prompt",
                    "metadata": metadata,
                }
            )

        if payload.object_type == KnowledgeObjectType.PATTERN and status == KnowledgeObjectStatus.ACTIVE:
            is_large = len(payload.text) > MAX_ACTIVE_PATTERN_CHARS or payload.text.count("\n") + 1 > MAX_ACTIVE_PATTERN_LINES
            explicitly_allowed = bool(metadata.get("allow_active_pattern"))
            if is_large and not explicitly_allowed:
                status = KnowledgeObjectStatus.ARCHIVED
                policy_reason = "large_pattern_summaries_are_not_active_memory"

        if payload.object_type == KnowledgeObjectType.ENTITY_PROFILE and status == KnowledgeObjectStatus.ACTIVE:
            source_object_ids = metadata.get("source_object_ids") or metadata.get("last_updated_from_object_ids")
            source_backed = bool(payload.source_ids) and bool(metadata.get("source_anchored")) and bool(source_object_ids)
            if not source_backed:
                status = KnowledgeObjectStatus.ARCHIVED
                policy_reason = "entity_profiles_must_be_source_backed"

        if policy_reason is None:
            return payload

        metadata.update(
            {
                "create_policy": "knowledge.write_guardrails.v1",
                "create_policy_reason": policy_reason,
                "requested_status": payload.status.value,
            }
        )
        return payload.model_copy(update={"status": status, "metadata": metadata})

    async def _with_extracted_entities(
        self, payload: KnowledgeObjectCreate
    ) -> tuple[KnowledgeObjectCreate, EntityResolutionResult]:
        derived_result = self._derived_profile_entity_result(payload.object_type, payload.metadata)
        if derived_result is not None:
            return payload, derived_result
        result = await self._entity_pipeline.extract(payload.title, payload.text, source_ids=payload.source_ids)
        metadata = merge_resolved_entity_metadata(payload.metadata, result)
        updated = payload if metadata == payload.metadata else payload.model_copy(update={"metadata": metadata})
        return updated, result

    def _metadata_entity_names(self, obj: KnowledgeObject) -> list[str]:
        names: list[str] = []
        raw = obj.metadata.get("entities")
        if isinstance(raw, list):
            names.extend(str(item) for item in raw if str(item).strip())
        graph = obj.metadata.get("entity_graph")
        if isinstance(graph, dict) and isinstance(graph.get("entities"), list):
            names.extend(str(item) for item in graph["entities"] if str(item).strip())
        return list(dict.fromkeys(names))

    async def _sync_entity_refs(self, obj: KnowledgeObject) -> None:
        await self._repo.replace_entity_refs(obj.id, self._metadata_entity_names(obj))

    async def _sync_entity_resolution(self, obj: KnowledgeObject, result: EntityResolutionResult) -> None:
        extra_names = [name for name in self._metadata_entity_names(obj) if name not in set(result.names)]
        await self._repo.replace_entity_resolution(obj.id, result, extra_entity_names=extra_names, scope=obj.scope)

    def _supersession_terms(self, obj: KnowledgeObject) -> set[str]:
        return {term for term in findall(r"[a-zA-Z0-9_]+", f"{obj.title} {obj.text}".lower()) if len(term) > 2}

    async def _supersession_context_ok(self, old: KnowledgeObject, new: KnowledgeObject) -> bool:
        if old.object_type != new.object_type and old.object_type.value.split("_")[0] != new.object_type.value.split("_")[0]:
            return False
        old_entities = set(await self._repo.get_entity_names(old.id)) | set(self._metadata_entity_names(old))
        new_entities = set(await self._repo.get_entity_names(new.id)) | set(self._metadata_entity_names(new))
        if {entity.casefold() for entity in old_entities} & {entity.casefold() for entity in new_entities}:
            return True
        if set(old.source_ids) & set(new.source_ids):
            return True
        shared_title_terms = self._supersession_terms(old.model_copy(update={"text": ""})) & self._supersession_terms(
            new.model_copy(update={"text": ""})
        )
        if len(shared_title_terms) >= 2:
            return True
        return len(self._supersession_terms(old) & self._supersession_terms(new)) >= 3

    async def commit_supersession_proposal(
        self, proposal: KnowledgeSupersessionProposal, *, apply: bool = True
    ) -> KnowledgeSupersessionCommitResult:
        if proposal.superseded_object_id == proposal.superseding_object_id:
            return KnowledgeSupersessionCommitResult(proposal=proposal, committed=False, reason="same_object")
        if proposal.confidence < 0.55:
            return KnowledgeSupersessionCommitResult(proposal=proposal, committed=False, reason="low_confidence")

        old = await self.get(proposal.superseded_object_id)
        new = await self.get(proposal.superseding_object_id)
        if old is None or new is None:
            return KnowledgeSupersessionCommitResult(proposal=proposal, committed=False, reason="missing_object")
        if old.status == KnowledgeObjectStatus.SUPERSEDED:
            return KnowledgeSupersessionCommitResult(proposal=proposal, committed=False, reason="already_superseded", superseded=old)
        if old.status in {KnowledgeObjectStatus.ARCHIVED, KnowledgeObjectStatus.REJECTED}:
            return KnowledgeSupersessionCommitResult(proposal=proposal, committed=False, reason="old_not_active", superseded=old)
        if new.status in {KnowledgeObjectStatus.ARCHIVED, KnowledgeObjectStatus.REJECTED, KnowledgeObjectStatus.SUPERSEDED}:
            return KnowledgeSupersessionCommitResult(proposal=proposal, committed=False, reason="new_not_current", superseded=old)
        if not await self._supersession_context_ok(old, new):
            return KnowledgeSupersessionCommitResult(proposal=proposal, committed=False, reason="insufficient_overlap", superseded=old)
        if not apply:
            return KnowledgeSupersessionCommitResult(proposal=proposal, committed=False, reason="dry_run", superseded=old)

        now = datetime.now(UTC).isoformat()
        old_metadata = dict(old.metadata)
        superseded_by_ids = old_metadata.get("superseded_by_object_ids")
        superseded_by = [int(item) for item in superseded_by_ids] if isinstance(superseded_by_ids, list) else []
        if new.id not in superseded_by:
            superseded_by.append(new.id)
        old_metadata["superseded_by_object_id"] = new.id
        old_metadata["superseded_by_object_ids"] = superseded_by
        old_metadata["supersession"] = {
            "object_id": new.id,
            "reason": proposal.reason,
            "confidence": proposal.confidence,
            "proposed_by": proposal.proposed_by,
            "evidence_terms": proposal.evidence_terms,
        }
        updated_old = await self._repo.update(
            old.id,
            KnowledgeObjectUpdate(
                status=KnowledgeObjectStatus.SUPERSEDED,
                metadata=old_metadata,
                superseded_by_object_id=new.id,
                superseded_at=now,
                supersession_reason=proposal.reason,
            ),
        )

        new_metadata = dict(new.metadata)
        supersedes_ids = new_metadata.get("supersedes_object_ids")
        supersedes = [int(item) for item in supersedes_ids] if isinstance(supersedes_ids, list) else []
        if old.id not in supersedes:
            supersedes.append(old.id)
        new_metadata["supersedes_object_ids"] = supersedes
        new_metadata["supersedes_object_id"] = old.id
        await self._repo.update(new.id, KnowledgeObjectUpdate(metadata=new_metadata))
        await self._memory.events.create(
            actor="system",
            action="knowledge.superseded",
            target_type=old.object_type.value,
            target_id=old.id,
            reason=proposal.reason,
            policy_version="knowledge.supersession.v1",
            details={
                "superseding_object_id": new.id,
                "confidence": proposal.confidence,
                "proposed_by": proposal.proposed_by,
                "evidence_terms": proposal.evidence_terms,
            },
        )
        return KnowledgeSupersessionCommitResult(proposal=proposal, committed=True, reason="committed", superseded=updated_old)

    async def _annotate_semantic_conflicts(self, obj: KnowledgeObject) -> KnowledgeObject:
        if obj.object_type not in {
            KnowledgeObjectType.FACT,
            KnowledgeObjectType.LESSON,
            KnowledgeObjectType.PATTERN,
            KnowledgeObjectType.PROCEDURE,
        }:
            return obj
        existing = await self._repo.list_many(
            object_types={
                KnowledgeObjectType.FACT,
                KnowledgeObjectType.LESSON,
                KnowledgeObjectType.PATTERN,
                KnowledgeObjectType.PROCEDURE,
            },
            statuses={KnowledgeObjectStatus.ACTIVE, KnowledgeObjectStatus.APPROVED},
            limit=1_000,
        )
        conflicts = [conflict for other in existing if (conflict := semantic_conflict(obj, other)) is not None]
        if not conflicts:
            return obj

        obj = await self._repo.update(obj.id, KnowledgeObjectUpdate(metadata=annotate_conflicts(obj.metadata, conflicts)))
        for conflict in conflicts:
            other = await self._repo.get(conflict.object_id)
            if other is None:
                continue
            await self.commit_supersession_proposal(
                KnowledgeSupersessionProposal(
                    superseded_object_id=other.id,
                    superseding_object_id=obj.id,
                    reason=conflict.reason,
                    confidence=conflict.confidence,
                    proposed_by="knowledge.contradictions.heuristic.v1",
                    evidence_terms=conflict.shared_terms,
                )
            )
        return obj

    async def _embed_object(self, obj: KnowledgeObject) -> None:
        if obj.status in {KnowledgeObjectStatus.ARCHIVED, KnowledgeObjectStatus.REJECTED, KnowledgeObjectStatus.SUPERSEDED}:
            return
        embedder = getattr(self._memory, "embedder", None)
        if embedder is None:
            return
        try:
            embedding = await embedder.embed_one(f"{obj.title}\n{obj.text}")
            await self._repo.update_embedding(obj.id, embedding)
        except Exception:
            _logger.warning("Failed to embed knowledge object %s", obj.id, exc_info=True)

    async def refresh_entity_profile(
        self,
        entity_name: str,
        *,
        evidence_limit: int = 12,
        explicit_refresh: bool = True,
    ) -> KnowledgeObject | None:
        return await self._profiles.refresh(entity_name, evidence_limit=evidence_limit, explicit_refresh=explicit_refresh)

    async def create(self, payload: KnowledgeObjectCreate) -> KnowledgeObject:
        payload = self._apply_create_policy(payload)
        payload, entity_result = await self._with_extracted_entities(payload)
        obj = await self._repo.create(payload)
        await self._sync_entity_resolution(obj, entity_result)
        obj = await self._annotate_semantic_conflicts(obj)
        await self._embed_object(obj)
        if obj.object_type == KnowledgeObjectType.MEMORY_EPISODE and obj.status == KnowledgeObjectStatus.ACTIVE:
            await self._archive_excess_memory_episodes(obj)
        await self._memory.events.create(
            actor="user",
            action="knowledge.created",
            target_type=obj.object_type.value,
            target_id=obj.id,
            reason="knowledge object created",
            policy_version="knowledge.objects.v1",
            details={"status": obj.status.value, "scope": obj.scope},
        )
        await self._emit_event(obj, "created")
        await self._memory.db.conn.commit()
        return obj

    async def _archive_excess_memory_episodes(self, newest: KnowledgeObject) -> None:
        episodes = await self._repo.list_many(
            object_types={KnowledgeObjectType.MEMORY_EPISODE},
            statuses={KnowledgeObjectStatus.ACTIVE},
            limit=1_000,
        )
        to_archive: dict[int, KnowledgeObject] = {
            episode.id: episode for episode in episodes[MAX_ACTIVE_MEMORY_EPISODES:] if episode.id != newest.id
        }
        same_session = [episode for episode in episodes if episode.scope == newest.scope]
        for episode in same_session[MAX_ACTIVE_MEMORY_EPISODES_PER_SESSION:]:
            if episode.id != newest.id:
                to_archive[episode.id] = episode

        for episode in to_archive.values():
            metadata = {
                **episode.metadata,
                "archived_by": "knowledge.write_guardrails.v1",
                "archived_reason": "memory_episode_retention_cap",
            }
            await self._repo.update(
                episode.id,
                KnowledgeObjectUpdate(status=KnowledgeObjectStatus.ARCHIVED, metadata=metadata),
            )

    async def _emit_event(self, obj: KnowledgeObject, action: str) -> None:
        if self._event_dispatcher is None:
            return
        try:
            await self._event_dispatcher(
                KnowledgeObjectChanged(
                    action=action,
                    object_id=obj.id,
                    object_type=obj.object_type.value,
                    status=obj.status.value,
                    title=obj.title,
                    scope=obj.scope,
                    source_ids=tuple(obj.source_ids),
                    updated_at=obj.updated_at,
                )
            )
        except Exception:
            _logger.exception("Failed to dispatch knowledge event for %s#%s", obj.object_type.value, obj.id)

    async def capture_run_provenance(self, event: RunCompleted) -> KnowledgeObject | None:
        source_id = f"run:{event.run_id}"
        existing = await self._repo.get_by_source_id(source_id, KnowledgeObjectType.RUN_PROVENANCE)
        if existing is not None:
            return existing
        if not event.result and not event.messages:
            return None

        message_count = len(event.messages)
        result = event.result or "Run completed without a final result."
        title = f"Run {event.run_id}"
        text = f"Session: {event.session_id}\nRun: {event.run_id}\nMessages: {message_count}\nResult: {result}"
        return await self.create(
            KnowledgeObjectCreate(
                object_type=KnowledgeObjectType.RUN_PROVENANCE,
                title=title,
                text=text,
                status=KnowledgeObjectStatus.ARCHIVED,
                scope=f"session:{event.session_id}",
                activation="audit",
                proactiveness_level="L0",
                score=0.0,
                source_ids=[source_id, f"session:{event.session_id}"],
                metadata={
                    "run_id": event.run_id,
                    "session_id": event.session_id,
                    "message_count": message_count,
                    "usage": event.usage.to_dict() if hasattr(event.usage, "to_dict") else {},
                    "memory_role": "run_provenance",
                },
            )
        )

    async def capture_episode_from_run(self, event: RunCompleted) -> KnowledgeObject | None:
        # Compatibility alias: a completed run is provenance, not a true memory episode.
        return await self.capture_run_provenance(event)

    async def create_memory_episode(
        self,
        *,
        session_id: str,
        title: str,
        summary: str,
        turn_ids: list[str] | None = None,
        run_ids: list[str] | None = None,
        source_ids: list[str] | None = None,
        episode_status: str = "open",
        boundary_reason: str | None = None,
        boundary_confidence: float | None = None,
        outcome: str | None = None,
        metadata: dict | None = None,
    ) -> KnowledgeObject:
        """Create a true multi-turn memory episode.

        Unlike run provenance, this object groups a coherent task/event segment and
        can reference many turns and many runs. Open/closed state lives in metadata
        so the knowledge object remains retrievable as provenance/context.
        """
        turn_ids = list(dict.fromkeys(turn_ids or []))
        run_ids = list(dict.fromkeys(run_ids or []))
        all_source_ids = list(
            dict.fromkeys(
                [
                    f"session:{session_id}",
                    *(source_ids or []),
                    *(f"turn:{turn_id}" for turn_id in turn_ids),
                    *(f"run:{run_id}" for run_id in run_ids),
                ]
            )
        )
        episode_metadata = {
            **(metadata or {}),
            "memory_role": "memory_episode",
            "session_id": session_id,
            "episode_status": episode_status,
            "source_turn_ids": turn_ids,
            "source_run_ids": run_ids,
        }
        if boundary_reason is not None:
            episode_metadata["boundary_reason"] = boundary_reason
        if boundary_confidence is not None:
            episode_metadata["boundary_confidence"] = boundary_confidence
        if outcome is not None:
            episode_metadata["outcome"] = outcome

        return await self.create(
            KnowledgeObjectCreate(
                object_type=KnowledgeObjectType.MEMORY_EPISODE,
                title=title,
                text=summary,
                status=KnowledgeObjectStatus.ACTIVE,
                scope=f"session:{session_id}",
                activation="prompt",
                proactiveness_level="L0",
                source_ids=all_source_ids,
                metadata=episode_metadata,
            )
        )

    async def append_memory_episode_sources(
        self,
        object_id: int,
        *,
        turn_ids: list[str] | None = None,
        run_ids: list[str] | None = None,
        source_ids: list[str] | None = None,
        note_text: str | None = None,
    ) -> KnowledgeObject | None:
        episode = await self.get(object_id)
        if episode is None or episode.object_type != KnowledgeObjectType.MEMORY_EPISODE:
            return None

        metadata = dict(episode.metadata)
        existing_turns = [str(item) for item in metadata.get("source_turn_ids", [])]
        existing_runs = [str(item) for item in metadata.get("source_run_ids", [])]
        merged_turns = list(dict.fromkeys([*existing_turns, *(turn_ids or [])]))
        merged_runs = list(dict.fromkeys([*existing_runs, *(run_ids or [])]))
        merged_sources = list(
            dict.fromkeys(
                [
                    *episode.source_ids,
                    *(source_ids or []),
                    *(f"turn:{turn_id}" for turn_id in turn_ids or []),
                    *(f"run:{run_id}" for run_id in run_ids or []),
                ]
            )
        )
        metadata["source_turn_ids"] = merged_turns
        metadata["source_run_ids"] = merged_runs
        text = episode.text
        if note_text and note_text.strip() and note_text.strip() not in text:
            text = f"{text.rstrip()}\n\n{note_text.strip()}"
        return await self.update(object_id, KnowledgeObjectUpdate(text=text, source_ids=merged_sources, metadata=metadata))

    def _episode_source_ids(self, episode: KnowledgeObject) -> list[str]:
        return list(
            dict.fromkeys(
                [
                    *episode.source_ids,
                    f"knowledge:{episode.id}",
                    *(f"turn:{turn_id}" for turn_id in episode.metadata.get("source_turn_ids", []) or []),
                    *(f"run:{run_id}" for run_id in episode.metadata.get("source_run_ids", []) or []),
                ]
            )
        )

    async def _model_episode_memory_candidates(self, episode: KnowledgeObject) -> list[KnowledgeObjectCreate]:
        if self._model is None:
            return []
        from ntrp.llm.router import get_completion_client

        source_ids = self._episode_source_ids(episode)
        provenance = {
            "source_episode_id": episode.id,
            "source_run_ids": episode.metadata.get("source_run_ids", []) or [],
            "source_turn_ids": episode.metadata.get("source_turn_ids", []) or [],
            "extracted_from": "episode_close",
            "extractor": "episode.close.model.v2",
        }
        payload = {
            "episode": {
                "title": episode.title,
                "text": episode.text[-6000:],
                "outcome": episode.metadata.get("outcome"),
                "boundary_reason": episode.metadata.get("boundary_reason"),
                "source_run_ids": provenance["source_run_ids"],
                "source_turn_ids": provenance["source_turn_ids"],
            }
        }
        try:
            response = await get_completion_client(self._model).completion(
                model=self._model,
                temperature=0,
                max_tokens=1500,
                response_format=EpisodeMemoryExtraction,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Extract only durable, user-specific memory from a closed personal-assistant episode. "
                            "Return facts/preferences as fact, reusable observations, implementation patterns, and behavior changes as lesson, "
                            "reusable outputs as artifact, and follow-ups as action_candidate. "
                            "Be conservative: omit transient implementation steps, generic knowledge, CI noise, and weak guesses. "
                            "Every memory must be useful months later and grounded in the episode. Return strict JSON."
                        ),
                    },
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
            )
            content = response.choices[0].message.content if response.choices else None
            if not content:
                return []
            extraction = EpisodeMemoryExtraction.model_validate_json(content)
        except Exception:
            return []

        type_map = {
            "fact": KnowledgeObjectType.FACT,
            "preference": KnowledgeObjectType.FACT,
            "decision": KnowledgeObjectType.FACT,
            "lesson": KnowledgeObjectType.LESSON,
            # Legacy model outputs may still say "pattern"; keep the simplified
            # active memory model by storing those as lessons, not pattern rows.
            "pattern": KnowledgeObjectType.LESSON,
            # Legacy model outputs may still say "procedure" or
            # "procedure_candidate". Store those as lessons so extraction cannot
            # regenerate review-only procedure rows.
            "procedure": KnowledgeObjectType.LESSON,
            "procedure_candidate": KnowledgeObjectType.LESSON,
            "artifact": KnowledgeObjectType.ARTIFACT,
            "action": KnowledgeObjectType.ACTION_CANDIDATE,
            "action_candidate": KnowledgeObjectType.ACTION_CANDIDATE,
        }
        candidates: list[KnowledgeObjectCreate] = []
        for item in extraction.memories:
            if item.confidence < 0.7:
                continue
            raw_object_type = item.object_type.lower()
            object_type = type_map.get(raw_object_type)
            if object_type is None:
                continue
            status = (
                KnowledgeObjectStatus.DRAFT
                if object_type in {KnowledgeObjectType.PROCEDURE_CANDIDATE, KnowledgeObjectType.ACTION_CANDIDATE}
                else KnowledgeObjectStatus.ACTIVE
            )
            metadata = {
                **provenance,
                "kind": item.kind,
                "confidence": item.confidence,
                "source_quote": item.source_quote,
            }
            if raw_object_type != object_type.value:
                metadata["normalized_from_object_type"] = raw_object_type
            candidates.append(
                KnowledgeObjectCreate(
                    object_type=object_type,
                    title=item.title[:200],
                    text=item.text,
                    status=status,
                    scope=episode.scope,
                    activation="prompt" if status == KnowledgeObjectStatus.ACTIVE else "review",
                    proactiveness_level="L0",
                    score=min(0.5, item.confidence * 0.4),
                    source_ids=source_ids,
                    metadata=metadata,
                )
            )
        return candidates

    async def _extract_memories_from_closed_episode(self, episode: KnowledgeObject) -> list[KnowledgeObject]:
        """Conservative episode-close extraction.

        A model extractor proposes durable candidates when configured; the
        deterministic baseline still handles obvious outcome/preference signals
        for offline tests and provider failures.
        """
        if episode.object_type != KnowledgeObjectType.MEMORY_EPISODE:
            return []
        if episode.metadata.get("episode_status") != "closed":
            return []
        if episode.metadata.get("extracted_memory_ids"):
            return []

        text = f"{episode.title}\n{episode.text}\n{episode.metadata.get('outcome', '')}"
        lowered = text.lower()
        source_ids = self._episode_source_ids(episode)
        provenance = {
            "source_episode_id": episode.id,
            "source_run_ids": episode.metadata.get("source_run_ids", []) or [],
            "source_turn_ids": episode.metadata.get("source_turn_ids", []) or [],
            "extracted_from": "episode_close",
        }
        candidates: list[KnowledgeObjectCreate] = await self._model_episode_memory_candidates(episode)

        if any(marker in lowered for marker in ("tests pass", "all checks passed", "implemented", "fixed", "resolved")):
            outcome = str(episode.metadata.get("outcome") or episode.text.splitlines()[-1] if episode.text else episode.title)
            candidates.append(
                KnowledgeObjectCreate(
                    object_type=KnowledgeObjectType.LESSON,
                    title=f"Lesson from {episode.title[:80]}",
                    text=f"Episode outcome: {outcome[:1000]}",
                    status=KnowledgeObjectStatus.ACTIVE,
                    scope=episode.scope,
                    activation="prompt",
                    proactiveness_level="L0",
                    score=0.12,
                    source_ids=source_ids,
                    metadata={**provenance, "kind": "episode_outcome", "confidence": 0.65},
                )
            )

        durable_match = search(r"(?i)\b(user|i)\s+(prefer|want|like|need|always|never)\b[^.\n]{3,240}", text)
        if durable_match:
            fact = durable_match.group(0).strip()
            candidates.append(
                KnowledgeObjectCreate(
                    object_type=KnowledgeObjectType.FACT,
                    title=fact[:100],
                    text=fact,
                    status=KnowledgeObjectStatus.ACTIVE,
                    scope=episode.scope,
                    activation="prompt",
                    proactiveness_level="L0",
                    score=0.25,
                    source_ids=source_ids,
                    metadata={**provenance, "kind": "preference", "confidence": 0.72},
                )
            )

        created: list[KnowledgeObject] = []
        for payload in candidates[:3]:
            created.append(await self.create(payload))
        return created

    async def apply_explicit_memory_command(
        self,
        text: str,
        *,
        source_ids: list[str] | None = None,
        scope: str | None = None,
    ) -> list[KnowledgeObject]:
        """Immediate hot path for explicit remember/forget/always/never/correction commands."""
        raw = text.strip()
        if not raw:
            return []
        created: list[KnowledgeObject] = []
        command_match = search(r"(?is)^\s*(remember(?: that)?|always|never|actually|correction:?|forget)\s+(.+?)\s*$", raw)
        if not command_match:
            return []
        command = command_match.group(1).lower().rstrip(":")
        body = command_match.group(2).strip()
        if len(body) < 3:
            return []

        def scope_matches(obj: KnowledgeObject) -> bool:
            return obj.scope == scope

        async def command_matches(
            query: str,
            *,
            object_types: set[KnowledgeObjectType],
            limit: int = 5,
        ) -> list[KnowledgeObject]:
            statuses = {KnowledgeObjectStatus.ACTIVE, KnowledgeObjectStatus.APPROVED, KnowledgeObjectStatus.DRAFT}
            matches = await self.search_text(
                query,
                object_types=object_types,
                statuses=statuses,
                limit=limit,
            )
            scoped_matches = [match for match in matches if scope_matches(match)]
            if scoped_matches:
                return scoped_matches
            terms = {term for term in findall(r"[a-z0-9_]+", query.lower()) if len(term) > 2}
            if not terms:
                return []
            candidates = [
                candidate
                for candidate in await self.list_many(object_types=object_types, statuses=statuses, limit=200)
                if scope_matches(candidate)
            ]
            ranked: list[tuple[int, str, KnowledgeObject]] = []
            for candidate in candidates:
                haystack = f"{candidate.title} {candidate.text}".lower()
                hits = sum(1 for term in terms if term in haystack)
                if hits:
                    ranked.append((hits, candidate.updated_at, candidate))
            ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
            return [candidate for _, _, candidate in ranked[:limit]]

        if command == "forget":
            matches = await command_matches(
                body,
                object_types={
                    KnowledgeObjectType.FACT,
                    KnowledgeObjectType.LESSON,
                    KnowledgeObjectType.PATTERN,
                    KnowledgeObjectType.PROCEDURE,
                    KnowledgeObjectType.PROCEDURE_CANDIDATE,
                },
                limit=5,
            )
            archived: list[KnowledgeObject] = []
            for obj in matches:
                if not scope_matches(obj):
                    continue
                archived.append(await self.update(obj.id, KnowledgeObjectUpdate(status=KnowledgeObjectStatus.ARCHIVED)))
            return archived

        object_type = KnowledgeObjectType.FACT
        kind = "explicit_fact"
        score = 0.3
        memory_text = body
        if command == "always":
            object_type = KnowledgeObjectType.PROCEDURE
            kind = "always_directive"
            memory_text = f"Always {body}"
            score = 0.5
        elif command == "never":
            object_type = KnowledgeObjectType.PROCEDURE
            kind = "never_directive"
            memory_text = f"Never {body}"
            score = 0.5
        elif command in {"actually", "correction"}:
            kind = "correction"
            score = 0.45

        created_obj = await self.create(
            KnowledgeObjectCreate(
                object_type=object_type,
                title=memory_text[:100],
                text=memory_text,
                status=KnowledgeObjectStatus.ACTIVE,
                scope=scope,
                activation="prompt",
                proactiveness_level="L0",
                score=score,
                source_ids=list(dict.fromkeys(source_ids or [])),
                metadata={"explicit_memory_command": command, "kind": kind, "confidence": 0.95},
            )
        )
        created.append(created_obj)

        if command in {"actually", "correction"}:
            matches = await command_matches(
                body,
                object_types={KnowledgeObjectType.FACT, KnowledgeObjectType.LESSON, KnowledgeObjectType.PATTERN},
                limit=5,
            )
            for old in matches:
                if old.id == created_obj.id or not scope_matches(old):
                    continue
                await self.update(
                    old.id,
                    KnowledgeObjectUpdate(
                        status=KnowledgeObjectStatus.SUPERSEDED,
                        superseded_by_object_id=created_obj.id,
                        superseded_at=datetime.now(UTC).isoformat(),
                        supersession_reason="explicit correction",
                    ),
                )
        return created

    async def close_memory_episode(
        self,
        object_id: int,
        *,
        outcome: str | None = None,
        boundary_reason: str | None = None,
        boundary_confidence: float | None = None,
        extracted_memory_ids: list[int] | None = None,
    ) -> KnowledgeObject | None:
        episode = await self.get(object_id)
        if episode is None or episode.object_type != KnowledgeObjectType.MEMORY_EPISODE:
            return None

        metadata = dict(episode.metadata)
        metadata["episode_status"] = "closed"
        metadata["closed_at"] = datetime.now(UTC).isoformat()
        if outcome is not None:
            metadata["outcome"] = outcome
        if boundary_reason is not None:
            metadata["boundary_reason"] = boundary_reason
        if boundary_confidence is not None:
            metadata["boundary_confidence"] = boundary_confidence
        if extracted_memory_ids is not None:
            metadata["extracted_memory_ids"] = list(dict.fromkeys(int(item) for item in extracted_memory_ids))
            return await self.update(object_id, KnowledgeObjectUpdate(metadata=metadata))

        closed = await self.update(object_id, KnowledgeObjectUpdate(metadata=metadata))
        extracted = await self._extract_memories_from_closed_episode(closed)
        if not extracted:
            return closed
        metadata = dict(closed.metadata)
        metadata["extracted_memory_ids"] = list(dict.fromkeys(obj.id for obj in extracted))
        return await self.update(object_id, KnowledgeObjectUpdate(metadata=metadata))

    async def get_open_memory_episode(self, session_id: str) -> KnowledgeObject | None:
        episodes = await self._repo.list_many(
            object_types={KnowledgeObjectType.MEMORY_EPISODE},
            statuses={KnowledgeObjectStatus.ACTIVE},
            limit=200,
        )
        scoped = [
            episode
            for episode in episodes
            if episode.scope == f"session:{session_id}"
            and episode.metadata.get("session_id") == session_id
            and episode.metadata.get("episode_status") == "open"
        ]
        return max(scoped, key=lambda episode: episode.updated_at, default=None)

    def _strip_leading_tool_transcript_lines(self, text: str) -> str:
        lines = text.splitlines()
        index = 0
        while index < len(lines):
            stripped = lines[index].strip().lower()
            if not stripped or stripped.startswith("tool:"):
                index += 1
                continue
            break
        return "\n".join(lines[index:]).strip()

    def _episode_message_text(self, content: Any) -> str:
        if isinstance(content, str):
            return self._strip_leading_tool_transcript_lines(content.strip())
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item.strip())
                elif isinstance(item, dict):
                    text = item.get("text") or item.get("content")
                    if isinstance(text, str):
                        parts.append(text.strip())
            return self._strip_leading_tool_transcript_lines("\n".join(part for part in parts if part).strip())
        return ""

    def _is_synthetic_episode_text(self, text: str) -> bool:
        stripped = text.lstrip().lower()
        return (
            stripped.startswith("<goal_context>")
            or stripped.startswith("[session state handoff]")
            or stripped.startswith("tool:")
        )

    def _run_episode_text(self, event: RunCompleted) -> str:
        """Build narrative episode text from user-visible conversation only.

        Tool messages are evidence/provenance for a run, not the episode itself.
        Keeping raw tool results out of episode text prevents junk titles like
        "Episode: tool: ..." and keeps episodes centered on user intent/outcome.
        """
        visible_messages: list[str] = []
        for message in event.messages:
            role = str(message.get("role", "unknown")).lower()
            if role not in {"user", "assistant"}:
                continue
            content = self._episode_message_text(message.get("content", ""))
            if not content or self._is_synthetic_episode_text(content):
                continue
            visible_messages.append(f"{role}: {content[:500]}")

        result = (event.result or "").strip()
        if result and not self._is_synthetic_episode_text(result):
            transcript = "\n".join(visible_messages)
            if result[:200].lower() not in transcript.lower():
                visible_messages.append(f"assistant result: {result[:500]}")

        return "\n".join(visible_messages[-6:]).strip()

    async def assimilate_run_completed(
        self,
        event: RunCompleted,
        *,
        classifier: EpisodeBoundaryClassifier | None = None,
        idle_seconds: int | None = None,
    ) -> tuple[KnowledgeObject | None, EpisodeBoundaryDecision]:
        """Attach completed run evidence to the current memory episode.

        This is intentionally conservative: runs become RUN_PROVENANCE first, then
        are grouped into an open MEMORY_EPISODE. A run does not become its own
        episode unless there is no open episode yet.
        """
        provenance = await self.capture_run_provenance(event)
        event_text = self._run_episode_text(event)
        classifier = classifier or self._boundary_classifier
        current = await self.get_open_memory_episode(event.session_id)
        if not event_text:
            decision = EpisodeBoundaryDecision(
                continue_current=current is not None,
                close_current=False,
                open_new=False,
                boundary_type="non_narrative_run",
                confidence=0.9,
                evidence=["Run had no user-visible narrative messages; tool-only evidence stays in run provenance."],
            )
            if current is None:
                return None, decision
            run_source_ids = [f"run:{event.run_id}"]
            if provenance is not None:
                run_source_ids.append(f"knowledge:{provenance.id}")
            updated = await self.append_memory_episode_sources(
                current.id,
                run_ids=[event.run_id],
                source_ids=run_source_ids,
            )
            return updated, decision
        maybe_decision = classifier.decide(current_episode=current, event_text=event_text, idle_seconds=idle_seconds)
        decision = await maybe_decision if isawaitable(maybe_decision) else maybe_decision
        run_source_ids = [f"run:{event.run_id}"]
        if provenance is not None:
            run_source_ids.append(f"knowledge:{provenance.id}")
        for message in event.messages:
            if message.get("role") != "user":
                continue
            content = message.get("content", "")
            if isinstance(content, str):
                await self.apply_explicit_memory_command(
                    content,
                    source_ids=run_source_ids,
                    scope=f"session:{event.session_id}",
                )
        note_text = f"Run {event.run_id}: {event.result or 'completed without final result.'}"

        if current is None:
            created = await self.create_memory_episode(
                session_id=event.session_id,
                title=decision.episode_title or f"Episode: session {event.session_id}",
                summary=event_text,
                run_ids=[event.run_id],
                source_ids=run_source_ids,
                boundary_reason=decision.boundary_type,
                boundary_confidence=decision.confidence,
                metadata={"boundary_evidence": decision.evidence},
            )
            if decision.close_current:
                closed = await self.close_memory_episode(
                    created.id,
                    outcome=event.result,
                    boundary_reason=decision.boundary_type,
                    boundary_confidence=decision.confidence,
                )
                return closed, decision
            return created, decision

        if decision.close_current and decision.open_new:
            await self.close_memory_episode(
                current.id,
                boundary_reason=decision.boundary_type,
                boundary_confidence=decision.confidence,
            )
            created = await self.create_memory_episode(
                session_id=event.session_id,
                title=decision.episode_title or f"Episode: run {event.run_id}",
                summary=event_text,
                run_ids=[event.run_id],
                source_ids=run_source_ids,
                boundary_reason=decision.boundary_type,
                boundary_confidence=decision.confidence,
                metadata={"boundary_evidence": decision.evidence},
            )
            return created, decision

        updated = await self.append_memory_episode_sources(
            current.id,
            run_ids=[event.run_id],
            source_ids=run_source_ids,
            note_text=note_text,
        )
        if decision.close_current:
            updated = await self.close_memory_episode(
                current.id,
                outcome=event.result,
                boundary_reason=decision.boundary_type,
                boundary_confidence=decision.confidence,
            )
        return updated, decision

    async def list(
        self,
        *,
        object_type: KnowledgeObjectType | None = None,
        status: KnowledgeObjectStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[KnowledgeObject]:
        return await self._repo.list(object_type=object_type, status=status, limit=limit, offset=offset)

    async def list_many(
        self,
        *,
        object_types: set[KnowledgeObjectType] | None = None,
        statuses: set[KnowledgeObjectStatus] | None = None,
        limit: int = 500,
        offset: int = 0,
    ) -> list[KnowledgeObject]:
        return await self._repo.list_many(object_types=object_types, statuses=statuses, limit=limit, offset=offset)

    async def search_text(
        self,
        query: str,
        *,
        object_types: set[KnowledgeObjectType] | None = None,
        statuses: set[KnowledgeObjectStatus] | None = None,
        limit: int = 500,
        offset: int = 0,
    ) -> list[KnowledgeObject]:
        return await self._repo.search_text(
            query,
            object_types=object_types,
            statuses=statuses,
            limit=limit,
            offset=offset,
        )

    async def search_vector(
        self,
        query: str,
        *,
        object_types: set[KnowledgeObjectType] | None = None,
        statuses: set[KnowledgeObjectStatus] | None = None,
        limit: int = 500,
    ) -> list[tuple[KnowledgeObject, float]]:
        embedding = await self._memory.embedder.embed_one(query)
        return await self._repo.search_vector(
            embedding,
            object_types=object_types,
            statuses=statuses,
            limit=limit,
        )

    async def search_entities(
        self,
        query: str,
        *,
        object_types: set[KnowledgeObjectType] | None = None,
        statuses: set[KnowledgeObjectStatus] | None = None,
        limit: int = 500,
    ) -> list[KnowledgeObject]:
        return await self._repo.search_entities(query, object_types=object_types, statuses=statuses, limit=limit)

    async def search_temporal(
        self,
        query: str,
        *,
        object_types: set[KnowledgeObjectType] | None = None,
        statuses: set[KnowledgeObjectStatus] | None = None,
        limit: int = 500,
    ) -> list[KnowledgeObject]:
        return await self._repo.search_temporal(query, object_types=object_types, statuses=statuses, limit=limit)

    async def list_profile_entity_names(self, *, limit: int = 100) -> list[str]:
        return await self._repo.list_profile_entity_names(limit=limit)

    async def get_entity_profile(self, entity_name: str) -> KnowledgeObject | None:
        return await self._repo.get_entity_profile(entity_name)

    async def update_embedding(self, object_id: int) -> None:
        obj = await self.get(object_id)
        if obj is not None:
            await self._embed_object(obj)

    async def list_missing_embeddings(self, limit: int = 100) -> list[KnowledgeObject]:
        return await self._repo.list_missing_embeddings(limit=limit)

    async def list_all_with_embeddings(self) -> list[KnowledgeObject]:
        return await self._repo.list_all_with_embeddings()

    async def backfill_embeddings(
        self,
        *,
        limit: int = 1_000,
        batch_size: int = 100,
        apply: bool = False,
    ) -> KnowledgeEmbeddingBackfillResult:
        total_missing = await self._repo.count_missing_embeddings()
        objects = await self._repo.list_missing_embeddings(limit=max(0, limit))
        result: KnowledgeEmbeddingBackfillResult = {
            "apply": apply,
            "total_missing": total_missing,
            "selected": len(objects),
            "repaired": 0,
            "object_ids": [obj.id for obj in objects],
        }
        if not apply or not objects:
            return result

        repaired = 0
        async with self._memory.transaction():
            for i in range(0, len(objects), max(1, batch_size)):
                batch = objects[i : i + max(1, batch_size)]
                embeddings = await self._memory.embedder.embed([f"{obj.title}\n{obj.text}" for obj in batch])
                for obj, embedding in zip(batch, embeddings, strict=False):
                    await self._repo.update_embedding(obj.id, embedding)
                    repaired += 1
            await self._memory.events.create(
                actor="backend",
                action="knowledge.embeddings.backfilled",
                target_type="knowledge_objects",
                reason="production-safe knowledge object vector backfill",
                policy_version="knowledge.embeddings.backfill.v1",
                details={"object_ids": result["object_ids"], "total_missing": total_missing},
            )
        result["repaired"] = repaired
        return result

    async def get(self, object_id: int) -> KnowledgeObject | None:
        return await self._repo.get(object_id)

    async def get_batch(self, object_ids: list[int]) -> dict[int, KnowledgeObject]:
        return await self._repo.get_batch(object_ids)

    async def get_by_source_id(
        self,
        source_id: str,
        object_type: KnowledgeObjectType | None = None,
    ) -> KnowledgeObject | None:
        return await self._repo.get_by_source_id(source_id, object_type)

    async def source_trace(self, object_id: int) -> KnowledgeSourceTraceResult:
        obj = await self.get(object_id)
        if obj is None:
            raise KeyError(f"Knowledge object {object_id} not found")
        sources: list[KnowledgeSourceTrace] = []
        for source_id in obj.source_ids:
            source_obj = None
            if source_id.startswith("knowledge:"):
                try:
                    source_obj = await self.get(int(source_id.split(":", 1)[1]))
                except ValueError:
                    source_obj = None
            else:
                source_obj = await self.get_by_source_id(source_id)
            sources.append(KnowledgeSourceTrace(source_id=source_id, object=source_obj))
        return KnowledgeSourceTraceResult(object=obj, sources=sources)

    async def prune_retention(self, request: KnowledgePruneRequest) -> KnowledgePruneResult:
        cutoff = datetime.now(UTC).timestamp() - (request.older_than_days * 24 * 60 * 60)
        candidates: list[KnowledgeObject] = []
        age_prunable_types = {
            KnowledgeObjectType.RUN_PROVENANCE,
            KnowledgeObjectType.MEMORY_EPISODE,
            KnowledgeObjectType.EPISODE,
            KnowledgeObjectType.PATTERN,
            KnowledgeObjectType.PROCEDURE_CANDIDATE,
            KnowledgeObjectType.ENTITY_PROFILE,
            KnowledgeObjectType.ACTION_CANDIDATE,
            KnowledgeObjectType.ARTIFACT,
            KnowledgeObjectType.SINK_RECEIPT,
            KnowledgeObjectType.OUTCOME_FEEDBACK,
        }
        durable_types = {
            KnowledgeObjectType.FACT,
            KnowledgeObjectType.LESSON,
            KnowledgeObjectType.PROCEDURE,
        }
        for obj in await self.list(limit=request.limit):
            if obj.status in {
                KnowledgeObjectStatus.ARCHIVED,
                KnowledgeObjectStatus.REJECTED,
                KnowledgeObjectStatus.SUPERSEDED,
            }:
                continue
            expires_at = obj.metadata.get("expires_at")
            if isinstance(expires_at, str):
                try:
                    if datetime.fromisoformat(expires_at).timestamp() <= datetime.now(UTC).timestamp():
                        candidates.append(obj)
                        continue
                except ValueError:
                    pass
            if obj.object_type in durable_types:
                continue
            if obj.object_type not in age_prunable_types:
                continue
            updated = datetime.fromisoformat(obj.updated_at).timestamp()
            if updated <= cutoff:
                candidates.append(obj)

        archived: list[KnowledgeObject] = []
        if request.apply:
            for obj in candidates:
                archived.append(await self.update(obj.id, KnowledgeObjectUpdate(status=KnowledgeObjectStatus.ARCHIVED)))
        return KnowledgePruneResult(candidates=candidates, archived=archived)

    async def count_by_type(self) -> dict[str, int]:
        return await self._repo.count_by_type()

    async def count_by_type_and_status(self) -> dict[str, dict[str, int]]:
        return await self._repo.count_by_type_and_status()

    async def update(self, object_id: int, payload: KnowledgeObjectUpdate) -> KnowledgeObject:
        obj = await self._repo.update(object_id, payload)
        if payload.model_fields_set & {"title", "text", "source_ids", "metadata"}:
            entity_result = self._derived_profile_entity_result(obj.object_type, obj.metadata)
            if entity_result is None:
                entity_result = await self._entity_pipeline.extract(obj.title, obj.text, source_ids=obj.source_ids)
                metadata = merge_resolved_entity_metadata(obj.metadata, entity_result)
                if metadata != obj.metadata:
                    obj = await self._repo.update(obj.id, KnowledgeObjectUpdate(metadata=metadata))
            await self._sync_entity_resolution(obj, entity_result)
            obj = await self._annotate_semantic_conflicts(obj)
        if payload.model_fields_set & {"title", "text", "status"}:
            await self._embed_object(obj)
        await self._memory.events.create(
            actor="user",
            action="knowledge.updated",
            target_type=obj.object_type.value,
            target_id=obj.id,
            reason="knowledge object updated",
            policy_version="knowledge.objects.v1",
            details={"status": obj.status.value, "scope": obj.scope, "fields": sorted(payload.model_fields_set)},
        )
        await self._emit_event(obj, "updated")
        await self._memory.db.conn.commit()
        if obj.object_type == KnowledgeObjectType.PROCEDURE_CANDIDATE and obj.status == KnowledgeObjectStatus.APPROVED:
            source_id = f"knowledge:{obj.id}"
            existing = await self.get_by_source_id(source_id)
            if existing is None:
                raw_target_procedure_id = obj.metadata.get("target_procedure_id")
                try:
                    target_procedure_id = int(raw_target_procedure_id) if raw_target_procedure_id is not None else None
                except (TypeError, ValueError):
                    target_procedure_id = None
                if target_procedure_id is not None:
                    target = await self.get(target_procedure_id)
                    if target is not None and target.status == KnowledgeObjectStatus.ACTIVE:
                        await self._repo.update(
                            target.id,
                            KnowledgeObjectUpdate(
                                status=KnowledgeObjectStatus.SUPERSEDED,
                                superseded_by_object_id=obj.id,
                                superseded_at=datetime.now(UTC).isoformat(),
                                supersession_reason="approved procedure candidate superseded target procedure",
                            ),
                        )
                        await self._memory.events.create(
                            actor="system",
                            action="knowledge.superseded",
                            target_type=target.object_type.value,
                            target_id=target.id,
                            reason="approved procedure candidate superseded target procedure",
                            policy_version="knowledge.objects.v1",
                            details={"approved_candidate_id": obj.id},
                        )
                await self.create(
                    KnowledgeObjectCreate(
                        object_type=KnowledgeObjectType.LESSON,
                        title=obj.title.replace("candidate", "lesson").replace("Candidate", "Lesson"),
                        text=obj.text,
                        status=KnowledgeObjectStatus.ACTIVE,
                        scope=obj.scope,
                        activation="prompt",
                        proactiveness_level="L0",
                        score=max(obj.score, 0.5),
                        source_ids=[source_id, *obj.source_ids],
                        metadata={"approved_candidate_id": obj.id, "promoted_from": obj.object_type.value, **obj.metadata},
                    )
                )
        return obj


class MemoryService:
    def __init__(self, memory: FactMemory):
        self.memory = memory
        self.events = MemoryEventService(memory)
        self.access_events = MemoryAccessEventService(memory)
        self.knowledge_objects = KnowledgeObjectService(memory)
