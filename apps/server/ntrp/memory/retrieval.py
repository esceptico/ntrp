from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import numpy as np

from ntrp.database import serialize_embedding
from ntrp.embedder import Embedder
from ntrp.logging import get_logger
from ntrp.memory.activation import (
    MemoryActivationBundle,
    MemoryActivationCandidate,
    MemoryActivationRequest,
    MemoryItemKind,
)
from ntrp.memory.contradictions import CROSS_SCOPE_OVERRIDE_TAG

if TYPE_CHECKING:
    import aiosqlite

_logger = get_logger(__name__)

_SCORE_KEYS = ("fts", "vector", "recency", "feedback", "confidence")


@dataclass(slots=True)
class _ScoreBreakdown:
    fts: float
    vector: float
    recency: float
    feedback: float
    confidence: float


@dataclass(slots=True)
class _CandidateRow:
    item_id: str
    kind: MemoryItemKind
    content: str
    confidence: float
    scope: str
    tags: list[str]
    source_refs: list[dict[str, Any]]
    valid_from: str
    invalid_at: str | None
    created_at: str
    usage: dict[str, Any]
    fts_bm25: float | None = None
    vector_distance: float | None = None


class MemoryRetrieval:
    def __init__(
        self,
        conn: aiosqlite.Connection,
        embedder: Embedder,
        *,
        w_fts: float = 0.35,
        w_vec: float = 0.35,
        w_recency: float = 0.10,
        w_feedback: float = 0.10,
        w_confidence: float = 0.10,
        recency_tau_days: float = 30.0,
        fts_top_k: int = 100,
        vec_top_k: int = 100,
    ):
        self.conn = conn
        self.embedder = embedder
        self.w_fts = w_fts
        self.w_vec = w_vec
        self.w_recency = w_recency
        self.w_feedback = w_feedback
        self.w_confidence = w_confidence
        self.recency_tau_days = recency_tau_days
        self.fts_top_k = fts_top_k
        self.vec_top_k = vec_top_k

    async def search(
        self,
        request: MemoryActivationRequest,
        *,
        now: datetime | None = None,
    ) -> MemoryActivationBundle:
        timestamp = _as_utc(now or datetime.now(UTC))
        fts_rows = await self._fts_candidates(request, timestamp)
        query_embedding = await self._query_embedding(request.query)
        vec_distances = await self._vector_distances(query_embedding)
        vec_rows = await self._fetch_vector_rows(vec_distances, request, timestamp)

        rows_by_id: dict[str, _CandidateRow] = {}
        for row in fts_rows:
            rows_by_id[row.item_id] = row
        for row in vec_rows:
            existing = rows_by_id.get(row.item_id)
            if existing is None:
                rows_by_id[row.item_id] = row
            else:
                existing.vector_distance = row.vector_distance

        candidates = self._score_candidates(list(rows_by_id.values()), timestamp)
        candidates.sort(key=lambda candidate: (candidate.score, candidate.created_at, candidate.item_id), reverse=True)
        selected, omitted, prompt_context, used_chars = await self._fit_budget(candidates, request)

        if request.record_access:
            _logger.info(
                "memory_activation",
                query=request.query,
                scope=request.scope,
                kinds=request.kinds,
                task=request.task,
                task_id=request.task_id,
                session_id=request.session_id,
                run_id=request.run_id,
                surface=request.surface,
                candidate_count=len(selected),
                omitted_count=len(omitted),
                used_chars=used_chars,
            )

        return MemoryActivationBundle(
            query=request.query,
            scope=request.scope,
            kinds=request.kinds,
            candidates=selected,
            omitted=omitted,
            used_chars=used_chars,
            prompt_context=prompt_context,
            skills_to_use=[],
        )

    async def _fts_candidates(self, request: MemoryActivationRequest, now: datetime) -> list[_CandidateRow]:
        match = _fts_query(request.query)
        if match is None:
            return []
        filters, params = _sql_filters(request, now, alias="m")
        rows = await self.conn.execute_fetchall(
            f"""
            SELECT
                m.id,
                m.kind,
                m.content,
                m.confidence,
                m.scope,
                m.tags,
                m.source_refs,
                m.valid_from,
                m.invalid_at,
                m.created_at,
                m.usage,
                bm25(memory_items_fts) AS bm25_score
            FROM memory_items_fts
            JOIN memory_items m ON m.id = memory_items_fts.item_id
            WHERE memory_items_fts MATCH ?
              AND {filters}
            ORDER BY bm25_score
            LIMIT ?
            """,
            (match, *params, self.fts_top_k),
        )
        return [_candidate_row(row, fts_bm25=float(row["bm25_score"])) for row in rows]

    async def _query_embedding(self, query: str) -> np.ndarray:
        embedding = np.asarray(await self.embedder.embed_one(query), dtype=np.float32)
        if embedding.ndim != 1:
            raise ValueError(f"query embedding must be one-dimensional, got shape {embedding.shape}")
        expected_dim = await self._embedding_dim()
        if expected_dim is not None and len(embedding) != expected_dim:
            raise ValueError(
                f"query embedding dimension {len(embedding)} does not match memory_items_vec dimension {expected_dim}"
            )
        return embedding

    async def _embedding_dim(self) -> int | None:
        rows = await self.conn.execute_fetchall("SELECT value FROM meta WHERE key = 'embedding_dim'")
        if not rows:
            return None
        return int(rows[0]["value"])

    async def _vector_distances(self, query_embedding: np.ndarray) -> dict[str, float]:
        query_bytes = serialize_embedding(query_embedding)
        rows = await self.conn.execute_fetchall(
            """
            SELECT v.item_id, v.distance
            FROM memory_items_vec v
            WHERE v.embedding MATCH ? AND k = ?
            ORDER BY v.distance
            """,
            (query_bytes, self.vec_top_k),
        )
        return {str(row["item_id"]): float(row["distance"]) for row in rows}

    async def _fetch_vector_rows(
        self,
        distances: dict[str, float],
        request: MemoryActivationRequest,
        now: datetime,
    ) -> list[_CandidateRow]:
        if not distances:
            return []
        ids = list(distances)
        placeholders = ",".join("?" for _ in ids)
        filters, params = _sql_filters(request, now, alias="m")
        rows = await self.conn.execute_fetchall(
            f"""
            SELECT
                m.id,
                m.kind,
                m.content,
                m.confidence,
                m.scope,
                m.tags,
                m.source_refs,
                m.valid_from,
                m.invalid_at,
                m.created_at,
                m.usage
            FROM memory_items m
            WHERE m.id IN ({placeholders})
              AND {filters}
            """,
            (*ids, *params),
        )
        rows_by_id = {str(row["id"]): row for row in rows}
        return [
            _candidate_row(rows_by_id[item_id], vector_distance=distances[item_id])
            for item_id in ids
            if item_id in rows_by_id
        ]

    def _score_candidates(self, rows: list[_CandidateRow], now: datetime) -> list[MemoryActivationCandidate]:
        fts_values = [row.fts_bm25 for row in rows if row.fts_bm25 is not None]
        fts_norms = _normalize_bm25(fts_values)
        fts_by_value = dict(zip(fts_values, fts_norms, strict=False))
        candidates: list[MemoryActivationCandidate] = []
        for row in rows:
            breakdown = _ScoreBreakdown(
                fts=fts_by_value.get(row.fts_bm25, 0.0) if row.fts_bm25 is not None else 0.0,
                vector=_clamp01(1.0 - row.vector_distance) if row.vector_distance is not None else 0.0,
                recency=_recency_score(row.created_at, now, self.recency_tau_days),
                feedback=_usage_score(row.usage),
                confidence=_clamp01(row.confidence),
            )
            score = (
                self.w_fts * breakdown.fts
                + self.w_vec * breakdown.vector
                + self.w_recency * breakdown.recency
                + self.w_feedback * breakdown.feedback
                + self.w_confidence * breakdown.confidence
            )
            reasons: list[str] = []
            if row.kind == "claim" and (row.fts_bm25 is not None or row.vector_distance is not None):
                reasons.append("claim_match")
            if row.fts_bm25 is not None:
                reasons.append("fts_match")
            if row.vector_distance is not None:
                reasons.append("vector_match")
            candidates.append(
                MemoryActivationCandidate(
                    item_id=row.item_id,
                    kind=row.kind,
                    content=row.content,
                    score=score,
                    score_breakdown={key: getattr(breakdown, key) for key in _SCORE_KEYS},
                    reasons=reasons,
                    confidence=row.confidence,
                    scope=row.scope,
                    tags=row.tags,
                    source_refs=row.source_refs,
                    valid_from=row.valid_from,
                    invalid_at=row.invalid_at,
                    created_at=row.created_at,
                )
            )
        return candidates

    async def _fit_budget(
        self,
        candidates: list[MemoryActivationCandidate],
        request: MemoryActivationRequest,
    ) -> tuple[list[MemoryActivationCandidate], list[MemoryActivationCandidate], str, int]:
        selected: list[MemoryActivationCandidate] = []
        omitted: list[MemoryActivationCandidate] = []
        blocks: list[str] = []
        used_chars = 0
        separator = "\n\n"
        for candidate in candidates:
            if len(selected) >= request.limit:
                omitted.append(candidate)
                continue
            prefix = len(separator) if blocks else 0
            block = await self._candidate_block(candidate)
            remaining = request.budget_chars - used_chars - prefix
            if remaining <= 0:
                omitted.append(candidate)
                continue
            if len(block) > remaining:
                if selected:
                    omitted.append(candidate)
                    continue
                block = await self._candidate_block(candidate, max_chars=remaining)
                if len(block) > remaining:
                    omitted.append(candidate)
                    continue
            selected.append(candidate)
            blocks.append(block)
            used_chars += prefix + len(block)
        omitted.extend(candidates[len(selected) + len(omitted) :])
        return selected, omitted[:50], separator.join(blocks), used_chars

    async def _candidate_block(self, candidate: MemoryActivationCandidate, *, max_chars: int | None = None) -> str:
        header = f"[{candidate.kind} · conf={_confidence_bucket(candidate.confidence)}]"
        content = await self._render_cross_scope_annotation(candidate)
        if max_chars is None:
            return f"{header}\n{content}"
        content_budget = max_chars - len(header) - 1
        if content_budget <= 0:
            return header[:max_chars]
        return f"{header}\n{content[:content_budget]}"

    async def _render_cross_scope_annotation(self, item: MemoryActivationCandidate) -> str:
        if item.kind != "claim" or CROSS_SCOPE_OVERRIDE_TAG not in item.tags:
            return item.content
        rows = await self.conn.execute_fetchall(
            """
            SELECT m.content, m.scope, m.status
            FROM memory_item_parents p
            JOIN memory_items m ON m.id = p.parent_id
            WHERE p.child_id = ?
              AND p.role = 'contradicts'
            ORDER BY m.scope, m.id
            """,
            (item.item_id,),
        )
        other = [row for row in rows if row["scope"] != item.scope and row["status"] == "active"]
        if not other:
            return item.content
        parts = [f"general ({row['scope']}): {row['content']}" for row in other]
        parts.append(f"in current scope ({item.scope}): {item.content}")
        return "\n".join(parts)


def _sql_filters(
    request: MemoryActivationRequest,
    now: datetime,
    *,
    alias: str,
) -> tuple[str, list[object]]:
    clauses = [
        f"{alias}.status = 'active'",
        f"julianday({alias}.valid_from) <= julianday(?)",
        f"({alias}.invalid_at IS NULL OR julianday({alias}.invalid_at) > julianday(?))",
    ]
    params: list[object] = [now.isoformat(), now.isoformat()]
    if request.scope is None:
        clauses.append(f"{alias}.scope = 'user'")
    else:
        clauses.append(f"({alias}.scope = 'user' OR {alias}.scope = ?)")
        params.append(request.scope)
    if request.kinds:
        placeholders = ",".join("?" for _ in request.kinds)
        clauses.append(f"{alias}.kind IN ({placeholders})")
        params.extend(request.kinds)
    return " AND ".join(clauses), params


def _candidate_row(
    row: aiosqlite.Row,
    *,
    fts_bm25: float | None = None,
    vector_distance: float | None = None,
) -> _CandidateRow:
    return _CandidateRow(
        item_id=str(row["id"]),
        kind=row["kind"],
        content=str(row["content"]),
        confidence=float(row["confidence"]),
        scope=str(row["scope"]),
        tags=_json_list(row["tags"]),
        source_refs=_json_list(row["source_refs"]),
        valid_from=str(row["valid_from"]),
        invalid_at=str(row["invalid_at"]) if row["invalid_at"] is not None else None,
        created_at=str(row["created_at"]),
        usage=_json_dict(row["usage"]),
        fts_bm25=fts_bm25,
        vector_distance=vector_distance,
    )


def _json_list(raw: object) -> list:
    if not isinstance(raw, str):
        return []
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return value if isinstance(value, list) else []


def _json_dict(raw: object) -> dict[str, Any]:
    if not isinstance(raw, str):
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _fts_query(query: str) -> str | None:
    terms = [term for term in re.findall(r"[A-Za-z0-9_]+", query.lower()) if len(term) > 1]
    if not terms:
        return None
    return " OR ".join(f'"{term}"' for term in terms[:32])


def _normalize_bm25(values: list[float]) -> list[float]:
    if not values:
        return []
    if all(value == 0 for value in values):
        return [0.0 for _ in values]
    low = min(values)
    high = max(values)
    if high == low:
        return [1.0 for _ in values]
    return [_clamp01(0.5 + 0.5 * ((high - value) / (high - low))) for value in values]


def _recency_score(raw_created_at: str, now: datetime, tau_days: float) -> float:
    created_at = _parse_dt(raw_created_at)
    age_days = max(0.0, (now - created_at).total_seconds() / 86_400)
    return _clamp01(math.exp(-age_days / tau_days))


def _usage_score(usage: dict[str, Any]) -> float:
    helped = _float_value(usage.get("helped"))
    hurt = _float_value(usage.get("hurt"))
    return _clamp01(math.tanh((helped - hurt) / 3.0) / 2.0 + 0.5)


def _float_value(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _candidate_block(candidate: MemoryActivationCandidate, *, max_chars: int | None = None) -> str:
    header = f"[{candidate.kind} · conf={_confidence_bucket(candidate.confidence)}]"
    if max_chars is None:
        return f"{header}\n{candidate.content}"
    content_budget = max_chars - len(header) - 1
    if content_budget <= 0:
        return header[:max_chars]
    return f"{header}\n{candidate.content[:content_budget]}"


def _confidence_bucket(confidence: float) -> str:
    if confidence < 0.4:
        return "low"
    if confidence < 0.7:
        return "med"
    return "high"


def _parse_dt(raw: str) -> datetime:
    value = raw.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(value)
    return _as_utc(parsed)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))
