from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from ntrp.memory.connectors.episode_close import SummaryClient
from ntrp.memory.items_store import MemoryItem, MemoryItemInsert, MemoryItemsRepository

DEFAULT_PATTERN_FINDER_SIM_THRESHOLD = 0.70
PATTERN_FINDER_CONFIDENCE = 0.6
_PROMPT_PATH = Path(__file__).with_name("prompts") / "pass1.txt"


@dataclass(slots=True)
class ObservationDraft:
    content: str
    tags: list[str]
    source_refs: list[dict[str, Any]]
    evidence_episode_ids: list[str]


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


class PatternFinder:
    def __init__(
        self,
        *,
        repo: MemoryItemsRepository,
        summary_client: SummaryClient,
        embedder: Any,
        sim_threshold: float | None = None,
    ):
        self.repo = repo
        self.summary_client = summary_client
        self.embedder = embedder
        self.sim_threshold = sim_threshold if sim_threshold is not None else _threshold_from_env()

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
    return stripped == "NO_PATTERN" or len(stripped) < 20 or stripped.startswith("I cannot")


async def _existing_observation_evidence(
    repo: MemoryItemsRepository,
    *,
    window_days: int,
    scope: str,
    limit: int,
) -> dict[frozenset[str], str]:
    observations = await repo.list_recent_items(kind="observation", window_days=window_days, limit=limit, scope=scope)
    evidence: dict[frozenset[str], str] = {}
    for observation in observations:
        edges = await repo.list_parent_edges(observation.id)
        episode_ids = frozenset(edge.parent_id for edge in edges if edge.role == "evidence")
        if episode_ids:
            evidence[episode_ids] = observation.id
    return evidence


def _threshold_from_env() -> float:
    raw = os.getenv("PATTERN_FINDER_SIM_THRESHOLD")
    if raw is None:
        return DEFAULT_PATTERN_FINDER_SIM_THRESHOLD
    try:
        return float(raw)
    except ValueError:
        return DEFAULT_PATTERN_FINDER_SIM_THRESHOLD


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))
