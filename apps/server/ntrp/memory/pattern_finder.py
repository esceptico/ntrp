from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import numpy as np

from ntrp.logging import get_logger
from ntrp.memory.connectors.episode_close import SummaryClient
from ntrp.memory.contradictions import ContradictionWatcher
from ntrp.memory.items_store import MemoryItem, MemoryItemInsert, MemoryItemsRepository

DEFAULT_PATTERN_FINDER_SIM_THRESHOLD = 0.70
DEFAULT_PATTERN_FINDER_PASS2_THRESHOLD = 0.72
PATTERN_FINDER_CONFIDENCE = 0.6
_PROMPT_PATH = Path(__file__).with_name("prompts") / "pass1.txt"
_PASS2_PROMPT_PATH = Path(__file__).with_name("prompts") / "pass2.txt"
_logger = get_logger(__name__)


@dataclass(slots=True)
class ObservationDraft:
    content: str
    tags: list[str]
    source_refs: list[dict[str, Any]]
    evidence_episode_ids: list[str]


@dataclass(slots=True)
class ClaimDraft:
    content: str
    tags: list[str]
    confidence: float
    evidence_item_ids: list[str]


@dataclass(slots=True)
class PatternFinderRunResult:
    window_days: int
    scope: str
    episodes_considered: int
    clusters_found: int
    observations_written: int
    observations_superseded: int
    elapsed_ms: int

    def to_dict(self) -> dict[str, int | str]:
        return {
            "window_days": self.window_days,
            "scope": self.scope,
            "episodes_considered": self.episodes_considered,
            "clusters_found": self.clusters_found,
            "observations_written": self.observations_written,
            "observations_superseded": self.observations_superseded,
            "elapsed_ms": self.elapsed_ms,
        }


@dataclass(slots=True)
class PatternFinderPass2RunResult:
    window_days: int
    scope: str
    observations_considered: int
    existing_claims_considered: int
    clusters_found: int
    claims_written: int
    claims_superseded: int
    elapsed_ms: int

    def to_dict(self) -> dict[str, int | str]:
        return {
            "window_days": self.window_days,
            "scope": self.scope,
            "observations_considered": self.observations_considered,
            "existing_claims_considered": self.existing_claims_considered,
            "clusters_found": self.clusters_found,
            "claims_written": self.claims_written,
            "claims_superseded": self.claims_superseded,
            "elapsed_ms": self.elapsed_ms,
        }


class PatternFinder:
    def __init__(
        self,
        *,
        repo: MemoryItemsRepository,
        summary_client: SummaryClient,
        embedder: Any,
        sim_threshold: float | None = None,
        contradiction_watcher: Any | None = None,
    ):
        self.repo = repo
        self.summary_client = summary_client
        self.embedder = embedder
        self.sim_threshold = sim_threshold if sim_threshold is not None else _threshold_from_env()
        self.contradiction_watcher = contradiction_watcher

    async def run_pass1(
        self,
        *,
        window_days: int = 7,
        scope: str = "user",
        limit: int = 500,
        now: datetime | None = None,
    ) -> PatternFinderRunResult:
        started = time.perf_counter()
        timestamp = _as_utc(now or datetime.now(UTC))
        episodes = await self.repo.list_recent_items(kind="episode", window_days=window_days, limit=limit, scope=scope)
        clusters = cluster_episodes(episodes, threshold=self.sim_threshold)
        existing = await _existing_observation_evidence(self.repo, window_days=window_days, scope=scope, limit=limit)

        observations_written = 0
        observations_superseded = 0
        for cluster in clusters:
            evidence_ids = frozenset(item.id for item in cluster)
            if evidence_ids in existing:
                continue

            superseded_ids = [
                observation_id
                for observed_ids, observation_id in existing.items()
                if observed_ids < evidence_ids
            ]
            draft = await summarize_cluster(cluster, self.summary_client)
            if _reject_summary(draft.content):
                continue

            observation_id = await self._persist_observation(
                draft,
                scope=scope,
                superseded_ids=superseded_ids,
                now=timestamp,
            )
            observations_written += 1
            observations_superseded += len(superseded_ids)
            existing[evidence_ids] = observation_id
            for superseded in superseded_ids:
                existing = {ids: oid for ids, oid in existing.items() if oid != superseded}

        return PatternFinderRunResult(
            window_days=window_days,
            scope=scope,
            episodes_considered=len(episodes),
            clusters_found=len(clusters),
            observations_written=observations_written,
            observations_superseded=observations_superseded,
            elapsed_ms=int((time.perf_counter() - started) * 1000),
        )

    async def run_pass2(
        self,
        *,
        window_days: int = 30,
        scope: str = "user",
        limit: int = 500,
        now: datetime | None = None,
    ) -> PatternFinderPass2RunResult:
        started = time.perf_counter()
        timestamp = _as_utc(now or datetime.now(UTC))
        observations = await self.repo.list_recent_items(kind="observation", window_days=window_days, limit=limit, scope=scope)
        existing_claims = await self.repo.list_recent_items(kind="claim", window_days=window_days, limit=limit, scope=scope)
        observations = [item for item in observations if item.status == "active"]
        existing_claims = [item for item in existing_claims if item.status == "active"]
        clusters = cluster_observations(
            observations + existing_claims,
            threshold=_pass2_threshold_from_env(),
        )
        existing = await _existing_evidence(self.repo, kind="claim", window_days=window_days, scope=scope, limit=limit)

        claims_written = 0
        claims_superseded = 0
        for cluster in clusters:
            evidence_ids = await _cluster_evidence_ids(self.repo, cluster)
            if len(evidence_ids) < 2:
                continue
            evidence_key = frozenset(evidence_ids)
            if evidence_key in existing:
                continue

            superseded_ids = [claim_id for observed_ids, claim_id in existing.items() if observed_ids < evidence_key]
            draft = await summarize_observation_cluster(
                cluster,
                self.summary_client,
                evidence_item_ids=evidence_ids,
            )
            if _reject_summary(draft.content):
                continue

            claim_id = await self._persist_claim(
                draft,
                scope=scope,
                superseded_ids=superseded_ids,
                now=timestamp,
            )
            claims_written += 1
            claims_superseded += len(superseded_ids)
            existing[evidence_key] = claim_id
            for superseded in superseded_ids:
                existing = {ids: oid for ids, oid in existing.items() if oid != superseded}

        return PatternFinderPass2RunResult(
            window_days=window_days,
            scope=scope,
            observations_considered=len(observations),
            existing_claims_considered=len(existing_claims),
            clusters_found=len(clusters),
            claims_written=claims_written,
            claims_superseded=claims_superseded,
            elapsed_ms=int((time.perf_counter() - started) * 1000),
        )

    async def _persist_observation(
        self,
        draft: ObservationDraft,
        *,
        scope: str,
        superseded_ids: list[str],
        now: datetime,
    ) -> str:
        embedding = await self.embedder.embed_one(draft.content)
        await self.repo.conn.execute("BEGIN")
        try:
            observation_id = await self.repo.insert_item(
                MemoryItemInsert(
                    kind="observation",
                    content=draft.content,
                    provenance="inferred",
                    source_refs=draft.source_refs,
                    # TODO(slice 5): derive observation confidence from evidence-parent signals.
                    confidence=PATTERN_FINDER_CONFIDENCE,
                    status="active",
                    scope=scope,
                    tags=draft.tags,
                    embedding=embedding,
                    valid_from=now,
                ),
                commit=False,
            )
            for episode_id in draft.evidence_episode_ids:
                await self.repo.insert_parent_edge(observation_id, episode_id, "evidence", commit=False)
            for old_observation_id in superseded_ids:
                await self.repo.insert_parent_edge(observation_id, old_observation_id, "supersedes", commit=False)
                await self.repo.conn.execute(
                    """
                    UPDATE memory_items
                    SET status = 'superseded',
                        invalid_at = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (now.isoformat(), now.isoformat(), old_observation_id),
                )
            await self.repo.conn.commit()
            return observation_id
        except BaseException:
            await self.repo.conn.rollback()
            raise

    async def _persist_claim(
        self,
        draft: ClaimDraft,
        *,
        scope: str,
        superseded_ids: list[str],
        now: datetime,
    ) -> str:
        embedding = await self.embedder.embed_one(draft.content)
        await self.repo.conn.execute("BEGIN")
        try:
            claim_id = await self.repo.insert_item(
                MemoryItemInsert(
                    kind="claim",
                    content=draft.content,
                    provenance="inferred",
                    source_refs=[],
                    confidence=draft.confidence,
                    status="active",
                    scope=scope,
                    tags=draft.tags,
                    embedding=embedding,
                    valid_from=now,
                ),
                commit=False,
            )
            for evidence_id in draft.evidence_item_ids:
                await self.repo.insert_parent_edge(claim_id, evidence_id, "evidence", commit=False)
            for old_claim_id in superseded_ids:
                await self.repo.insert_parent_edge(claim_id, old_claim_id, "supersedes", commit=False)
                await self.repo.conn.execute(
                    """
                    UPDATE memory_items
                    SET status = 'superseded',
                        invalid_at = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (now.isoformat(), now.isoformat(), old_claim_id),
                )
            await self.repo.conn.commit()
        except BaseException:
            await self.repo.conn.rollback()
            raise
        if self.contradiction_watcher is not None:
            try:
                await cast("ContradictionWatcher", self.contradiction_watcher).scan_for_new_claim(claim_id, scope=scope)
            except Exception:
                _logger.exception("Contradiction watcher scan failed for claim %s", claim_id)
        return claim_id


async def summarize_cluster(episodes: list[MemoryItem], client: SummaryClient) -> ObservationDraft:
    prompt = render_pass1_prompt(episodes)
    body = (await client(prompt)).strip()
    return ObservationDraft(
        content=body,
        tags=sorted({tag for episode in episodes for tag in episode.tags}),
        source_refs=_merge_source_refs(episodes),
        evidence_episode_ids=[episode.id for episode in episodes],
    )


def render_pass1_prompt(episodes: list[MemoryItem]) -> str:
    bullets = "\n".join(
        f"- id={episode.id}; valid_from={episode.valid_from.isoformat()}; tags={episode.tags}; content={episode.content}"
        for episode in episodes
    )
    return _PROMPT_PATH.read_text().format(episode_bullets=bullets)


async def summarize_observation_cluster(
    items: list[MemoryItem],
    client: SummaryClient,
    *,
    evidence_item_ids: list[str] | None = None,
) -> ClaimDraft:
    prompt = render_pass2_prompt(items)
    body = (await client(prompt)).strip()
    evidence_ids = evidence_item_ids or [item.id for item in items]
    evidence_id_set = set(evidence_ids)
    confidences = [item.confidence for item in items if item.id in evidence_id_set]
    if not confidences:
        confidences = [item.confidence for item in items]
    mean_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    cluster_size_factor = min(1.0, 0.5 + 0.1 * len(evidence_ids))
    return ClaimDraft(
        content=body,
        tags=sorted({tag for item in items for tag in item.tags}),
        confidence=_clamp01(mean_confidence * cluster_size_factor),
        evidence_item_ids=evidence_ids,
    )


def render_pass2_prompt(items: list[MemoryItem]) -> str:
    bullets = "\n".join(
        f"- [{item.kind}] {item.content}"
        for item in sorted(items, key=lambda item: (_as_utc(item.created_at), getattr(item, "id", "")))
    )
    return _PASS2_PROMPT_PATH.read_text().format(item_bullets=bullets)


def cluster_episodes(
    episodes: list[MemoryItem],
    *,
    threshold: float = DEFAULT_PATTERN_FINDER_SIM_THRESHOLD,
) -> list[list[MemoryItem]]:
    if len(episodes) < 2:
        return []
    parent = list(range(len(episodes)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for i, left in enumerate(episodes):
        for j in range(i + 1, len(episodes)):
            if combined_similarity(left, episodes[j]) >= threshold:
                union(i, j)

    clusters: dict[int, list[MemoryItem]] = {}
    for index, episode in enumerate(episodes):
        clusters.setdefault(find(index), []).append(episode)
    return [cluster for cluster in clusters.values() if len(cluster) >= 2]


def combined_similarity(a: MemoryItem, b: MemoryItem) -> float:
    return 0.70 * _cosine(a.embedding, b.embedding) + 0.20 * _tag_jaccard(a.tags, b.tags) + 0.10 * _temporal(
        a.valid_from,
        b.valid_from,
    )


def cluster_observations(
    items: list[MemoryItem],
    *,
    threshold: float = DEFAULT_PATTERN_FINDER_PASS2_THRESHOLD,
    max_cluster_size: int = 8,
) -> list[list[MemoryItem]]:
    if len(items) < 2:
        return []
    parent = list(range(len(items)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for i, left in enumerate(items):
        for j in range(i + 1, len(items)):
            if claim_similarity(left, items[j]) >= threshold:
                union(i, j)

    components: dict[int, list[MemoryItem]] = {}
    for index, item in enumerate(items):
        components.setdefault(find(index), []).append(item)

    clusters: list[list[MemoryItem]] = []
    for component in components.values():
        ordered = sorted(component, key=lambda item: (_as_utc(item.created_at), item.id))
        for start in range(0, len(ordered), max_cluster_size):
            chunk = ordered[start : start + max_cluster_size]
            if len(chunk) >= 2:
                clusters.append(chunk)
    return clusters


def claim_similarity(a: MemoryItem, b: MemoryItem) -> float:
    return 0.65 * _cosine(a.embedding, b.embedding) + 0.20 * _tag_jaccard(a.tags, b.tags) + 0.15 * _temporal(
        a.created_at,
        b.created_at,
    )


def _entity_overlap(a: MemoryItem, b: MemoryItem) -> float:
    return 0.0


def _cosine(a: np.ndarray | None, b: np.ndarray | None) -> float:
    if a is None or b is None or len(a) == 0 or len(b) == 0:
        return 0.0
    left = np.asarray(a, dtype=np.float32)
    right = np.asarray(b, dtype=np.float32)
    left_norm = float(np.linalg.norm(left))
    right_norm = float(np.linalg.norm(right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return _clamp01(float(np.dot(left, right) / (left_norm * right_norm)))


def _tag_jaccard(a: list[str], b: list[str]) -> float:
    left = set(a)
    right = set(b)
    if not left and not right:
        return 0.0
    return len(left & right) / len(left | right)


def _temporal(a: datetime, b: datetime) -> float:
    days_apart = abs((_as_utc(a) - _as_utc(b)).total_seconds()) / 86400
    return _clamp01(1.0 - days_apart / 7.0)


def _merge_source_refs(episodes: list[MemoryItem]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    refs: list[dict[str, Any]] = []
    for episode in episodes:
        for ref in episode.source_refs:
            key = _source_ref_key(ref)
            if key in seen:
                continue
            seen.add(key)
            refs.append(ref)
    return refs


def _source_ref_key(ref: dict[str, Any]) -> str:
    return "|".join(str(ref.get(key, "")) for key in ("kind", "ref", "captured_at"))


def _reject_summary(content: str) -> bool:
    stripped = content.strip()
    return stripped in {"NO_PATTERN", "NO_CLAIM"} or len(stripped) < 20 or stripped.startswith("I cannot")


async def _existing_observation_evidence(
    repo: MemoryItemsRepository,
    *,
    window_days: int,
    scope: str,
    limit: int,
) -> dict[frozenset[str], str]:
    return await _existing_evidence(repo, kind="observation", window_days=window_days, scope=scope, limit=limit)


async def _existing_evidence(
    repo: MemoryItemsRepository,
    *,
    kind: str,
    window_days: int,
    scope: str,
    limit: int,
) -> dict[frozenset[str], str]:
    observations = await repo.list_recent_items(kind=kind, window_days=window_days, limit=limit, scope=scope)
    evidence: dict[frozenset[str], str] = {}
    for observation in observations:
        edges = await repo.list_parent_edges(observation.id)
        episode_ids = frozenset(edge.parent_id for edge in edges if edge.role == "evidence")
        if episode_ids:
            evidence[episode_ids] = observation.id
    return evidence


async def _cluster_evidence_ids(repo: MemoryItemsRepository, cluster: list[MemoryItem]) -> list[str]:
    seen: set[str] = set()
    evidence_ids: list[str] = []
    for item in sorted(cluster, key=lambda value: (_as_utc(value.created_at), value.id)):
        item_evidence_ids: list[str] = []
        if item.kind == "claim":
            edges = await repo.list_parent_edges(item.id)
            item_evidence_ids = [edge.parent_id for edge in edges if edge.role == "evidence"]
        for item_id in item_evidence_ids or [item.id]:
            if item_id in seen:
                continue
            seen.add(item_id)
            evidence_ids.append(item_id)
    return evidence_ids


def _threshold_from_env() -> float:
    raw = os.getenv("PATTERN_FINDER_SIM_THRESHOLD")
    if raw is None:
        return DEFAULT_PATTERN_FINDER_SIM_THRESHOLD
    try:
        return float(raw)
    except ValueError:
        return DEFAULT_PATTERN_FINDER_SIM_THRESHOLD


def _pass2_threshold_from_env() -> float:
    raw = os.getenv("NTRP_PATTERN_FINDER_PASS2_THRESHOLD")
    if raw is None:
        return DEFAULT_PATTERN_FINDER_PASS2_THRESHOLD
    try:
        return float(raw)
    except ValueError:
        return DEFAULT_PATTERN_FINDER_PASS2_THRESHOLD


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))
