from collections.abc import Callable
from datetime import UTC, datetime

from ntrp.knowledge.contradictions import semantic_conflict
from ntrp.knowledge.models import (
    KnowledgeFactConflictProposal,
    KnowledgeFactConsolidationCommitResult,
    KnowledgeFactConsolidationProposal,
    KnowledgeFactConsolidationResult,
    KnowledgeObject,
    KnowledgeObjectStatus,
    KnowledgeObjectType,
    KnowledgeObjectUpdate,
    KnowledgeSupersessionProposal,
)
from ntrp.knowledge.similarity import knowledge_similarity, knowledge_tokens
from ntrp.knowledge.store import KnowledgeObjectRepository


class KnowledgeFactConsolidationService:
    def __init__(
        self,
        *,
        repo: KnowledgeObjectRepository,
        objects,
        metadata_entity_names: Callable[[KnowledgeObject], list[str]],
    ):
        self._repo = repo
        self._objects = objects
        self._metadata_entity_names = metadata_entity_names

    @staticmethod
    def _canonical(objects: list[KnowledgeObject]) -> KnowledgeObject:
        return max(objects, key=lambda obj: (obj.score, len(obj.source_ids), len(obj.text), obj.updated_at, obj.id))

    async def propose(
        self,
        *,
        limit: int = 1_000,
        min_confidence: float = 0.86,
        max_proposals: int = 50,
    ) -> KnowledgeFactConsolidationResult:
        facts = await self._repo.list_many(
            object_types={KnowledgeObjectType.FACT},
            statuses={KnowledgeObjectStatus.ACTIVE},
            limit=limit,
        )
        if len(facts) < 2:
            return KnowledgeFactConsolidationResult(scanned=len(facts))

        parent = {fact.id: fact.id for fact in facts}
        pair_terms: dict[tuple[int, int], list[str]] = {}
        pair_scores: dict[tuple[int, int], float] = {}
        conflicts: list[KnowledgeFactConflictProposal] = []
        token_cache = {fact.id: knowledge_tokens(fact) for fact in facts}

        def find(object_id: int) -> int:
            while parent[object_id] != object_id:
                parent[object_id] = parent[parent[object_id]]
                object_id = parent[object_id]
            return object_id

        def union(left_id: int, right_id: int) -> None:
            left_root = find(left_id)
            right_root = find(right_id)
            if left_root != right_root:
                parent[right_root] = left_root

        for index, left in enumerate(facts):
            for right in facts[index + 1 :]:
                conflict = semantic_conflict(left, right) or semantic_conflict(right, left)
                if conflict is not None:
                    conflicts.append(
                        KnowledgeFactConflictProposal(
                            object_ids=[left.id, right.id],
                            reason=conflict.reason,
                            confidence=conflict.confidence,
                            evidence_terms=conflict.shared_terms,
                        )
                    )
                    continue
                confidence, evidence_terms = knowledge_similarity(token_cache[left.id], token_cache[right.id])
                if set(left.source_ids) & set(right.source_ids):
                    confidence = min(0.99, confidence + 0.04)
                left_entities = {entity.casefold() for entity in self._metadata_entity_names(left)}
                right_entities = {entity.casefold() for entity in self._metadata_entity_names(right)}
                if left_entities and left_entities & right_entities:
                    confidence = min(0.99, confidence + 0.04)
                if confidence < min_confidence:
                    continue
                pair = tuple(sorted((left.id, right.id)))
                pair_terms[pair] = evidence_terms
                pair_scores[pair] = confidence
                union(left.id, right.id)

        grouped: dict[int, list[KnowledgeObject]] = {}
        for fact in facts:
            grouped.setdefault(find(fact.id), []).append(fact)

        proposals: list[KnowledgeFactConsolidationProposal] = []
        for group in grouped.values():
            if len(group) < 2:
                continue
            canonical = self._canonical(group)
            group_ids = {obj.id for obj in group}
            duplicate_ids = sorted(obj.id for obj in group if obj.id != canonical.id)
            source_ids = sorted({source_id for obj in group for source_id in obj.source_ids})
            evidence_terms = sorted(
                {
                    term
                    for left in group
                    for right in group
                    for term in pair_terms.get(tuple(sorted((left.id, right.id))), [])
                }
            )[:50]
            group_scores = [
                score
                for (left_id, right_id), score in pair_scores.items()
                if left_id in group_ids and right_id in group_ids
            ]
            proposals.append(
                KnowledgeFactConsolidationProposal(
                    canonical_object_id=canonical.id,
                    duplicate_object_ids=duplicate_ids,
                    reason="Likely duplicate active facts; review then supersede duplicates into the canonical fact.",
                    confidence=min(group_scores) if group_scores else min_confidence,
                    evidence_terms=evidence_terms,
                    source_ids=source_ids,
                )
            )

        proposals.sort(key=lambda proposal: (proposal.confidence, len(proposal.duplicate_object_ids)), reverse=True)
        return KnowledgeFactConsolidationResult(
            proposals=proposals[:max_proposals],
            conflicts=conflicts,
            scanned=len(facts),
            skipped=max(0, len(proposals) - max_proposals),
        )

    async def commit(
        self,
        proposal: KnowledgeFactConsolidationProposal,
        *,
        apply: bool = True,
    ) -> KnowledgeFactConsolidationCommitResult:
        canonical = await self._objects.get(proposal.canonical_object_id)
        if canonical is None:
            return KnowledgeFactConsolidationCommitResult(proposal=proposal, committed=False, reason="missing_canonical")
        if canonical.object_type != KnowledgeObjectType.FACT or canonical.status != KnowledgeObjectStatus.ACTIVE:
            return KnowledgeFactConsolidationCommitResult(
                proposal=proposal,
                committed=False,
                reason="canonical_not_active_fact",
                canonical=canonical,
            )

        duplicate_objects: list[KnowledgeObject] = []
        for duplicate_id in proposal.duplicate_object_ids:
            duplicate = await self._objects.get(duplicate_id)
            if duplicate is None:
                return KnowledgeFactConsolidationCommitResult(
                    proposal=proposal,
                    committed=False,
                    reason="missing_duplicate",
                    canonical=canonical,
                )
            if duplicate.object_type != KnowledgeObjectType.FACT:
                return KnowledgeFactConsolidationCommitResult(
                    proposal=proposal,
                    committed=False,
                    reason="duplicate_not_fact",
                    canonical=canonical,
                )
            duplicate_objects.append(duplicate)

        supersession_proposals = [
            KnowledgeSupersessionProposal(
                superseded_object_id=duplicate.id,
                superseding_object_id=canonical.id,
                reason=proposal.reason,
                confidence=proposal.confidence,
                proposed_by=proposal.proposed_by,
                evidence_terms=proposal.evidence_terms,
            )
            for duplicate in duplicate_objects
        ]

        preflight = [await self._objects.commit_supersession_proposal(item, apply=False) for item in supersession_proposals]
        failed_preflight = next((item for item in preflight if item.reason != "dry_run"), None)
        if failed_preflight is not None:
            return KnowledgeFactConsolidationCommitResult(
                proposal=proposal,
                committed=False,
                reason=failed_preflight.reason,
                commits=preflight,
                canonical=canonical,
            )
        if not apply:
            return KnowledgeFactConsolidationCommitResult(
                proposal=proposal,
                committed=False,
                reason="dry_run",
                commits=preflight,
                canonical=canonical,
            )

        commits = []
        for item in supersession_proposals:
            commit = await self._objects.commit_supersession_proposal(item, apply=True)
            commits.append(commit)
            if not commit.committed:
                return KnowledgeFactConsolidationCommitResult(
                    proposal=proposal,
                    committed=False,
                    reason=commit.reason,
                    commits=commits,
                    canonical=canonical,
                )

        source_ids = sorted(
            {source_id for obj in [canonical, *duplicate_objects] for source_id in obj.source_ids}
            | set(proposal.source_ids)
        )[:200]
        metadata = dict(canonical.metadata)
        consolidations = metadata.get("fact_consolidations")
        if not isinstance(consolidations, list):
            consolidations = []
        consolidations.append(
            {
                "duplicate_object_ids": proposal.duplicate_object_ids,
                "reason": proposal.reason,
                "confidence": proposal.confidence,
                "proposed_by": proposal.proposed_by,
                "evidence_terms": proposal.evidence_terms,
                "source_ids": source_ids,
                "committed_at": datetime.now(UTC).isoformat(),
            }
        )
        metadata["fact_consolidations"] = consolidations[-20:]
        updated_canonical = await self._repo.update(
            canonical.id,
            KnowledgeObjectUpdate(source_ids=source_ids, metadata=metadata),
        )
        return KnowledgeFactConsolidationCommitResult(
            proposal=proposal,
            committed=True,
            reason="committed",
            commits=commits,
            canonical=updated_canonical,
        )
