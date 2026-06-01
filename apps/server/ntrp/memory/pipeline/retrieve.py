"""Retrieve — read + query-aware compression (CONTRACTS §9).

Read-only. Produces a small, scope/validity-filtered, query-aware-compressed
bundle to inject. Never writes, mutates trust, scores lens membership, or runs
Admit/Reconcile/Lint.

Sits on top of the frozen Stage-2 store reads + search/'s Embedder. Reuses
rrf_merge from search/retrieval.py (it is generic over hashable ids). No vector
column is added to the store: the vector leg re-ranks an over-fetched FTS pool by
cosine of the goal against candidate content, computed on the fly.

Ranking is a transparent scalar that ORDERS, never gates. The only exclusion is
the hard categorical filter (scope + validity + status), applied as a recall
predicate via store.query id-sets — no superseded/archived/out-of-scope/expired
claim ever reaches ranking.
"""

import math

import numpy as np

from ntrp.embedder import Embedder
from ntrp.llm.base import CompletionClient
from ntrp.logging import get_logger
from ntrp.memory.models import MemoryItem, Provenance, Status, now_iso
from ntrp.memory.pipeline.prompts_retrieve import (
    RETRIEVE_COMPRESS_SYSTEM,
    CompressionResult,
    build_compression_user_prompt,
)
from ntrp.memory.pipeline.types import RankedItem, Retrieval, RetrievedContext
from ntrp.search.retrieval import rrf_merge

_logger = get_logger(__name__)

# Recall sizing (CONTRACTS §9.1: over-fetch the FTS pool for the vector leg).
N_FTS = 20
VECTOR_OVERFETCH = 4
# RRF fusion weights — FTS-weight > vector-weight (entity-dense rows favor lexical).
FTS_WEIGHT = 0.6
VECTOR_WEIGHT = 0.4
RRF_K = 60
# order_score term weights (transparent scalar; orders, never gates).
W_RRF = 1.0
W_FRESHNESS = 0.15
W_PROVENANCE = 0.10
W_CORROBORATION = 0.08
# Provenance ordinal, high→low (CONTRACTS §1.3).
_PROVENANCE_ORD = {
    Provenance.USER_AUTHORED: 3,
    Provenance.RECORDED: 2,
    Provenance.INFERRED: 1,
    Provenance.EXTERNAL: 0,
}
# Freshness half-life in days — monotone recency, NOT a decay gate.
_FRESHNESS_HALFLIFE_DAYS = 90.0
# Compression only fires over budget AND when the pool is large.
_COMPRESSION_MIN_POOL = 8
# ~4 chars/token heuristic for the no-LLM budget pass.
_CHARS_PER_TOKEN = 4


class Retriever:
    def __init__(
        self,
        store,
        embed: Embedder,
        cheap_llm: CompletionClient,
        *,
        model: str | None = None,
        lens_expander=None,
    ):
        # CONTRACTS §3 freezes the positional signature (store, embed, cheap_llm).
        # `model` is an additive keyword: the cheap model id for the optional
        # compression call. completion() requires a model and the frozen
        # signature supplies none (see CONTRACT ISSUE in the report). When model
        # is None, compression is skipped and the no-LLM verbatim budget pass is
        # used — Retrieve stays fully functional.
        #
        # `lens_expander` is the additive read-only Stage-4 egress (LENS_CONTRACTS
        # §3.7). When present and the request carries a `lens_hint`, retrieve first
        # tries the lens path: inject the cached lens page verbatim (0 LLM), else
        # pre-filter the candidate pool to the lens's cached `in` members and rank
        # as usual (orders, never gates). None -> unconstrained recall, unchanged.
        self.store = store
        self.embed = embed
        self.cheap_llm = cheap_llm
        self.model = model
        self.lens_expander = lens_expander

    async def retrieve(self, req: Retrieval) -> RetrievedContext:
        scopes = [req.scope, *req.also_scopes]
        valid_at = req.valid_at or now_iso()

        # Stage-4 lens egress (read-only, §3.7). Resolve a lens from the hint; if
        # its cached page is present, inject it verbatim (the cheapest recall path).
        # Otherwise carry its active member set forward to pre-filter the pool.
        member_filter: frozenset[str] | None = None
        if self.lens_expander is not None and req.lens_hint:
            expansion = await self._expand_lens(req, scopes, valid_at)
            if expansion is not None:
                if expansion.page:
                    return RetrievedContext(
                        rendered=expansion.page,
                        items=[],
                        degraded=False,
                        diagnostics={"lens_id": expansion.lens.id, "lens_page_inject": True},
                    )
                member_filter = expansion.member_ids

        allowed = await self._scoped_active_ids(req, scopes, valid_at)
        if member_filter is not None:
            # Member-constrained fallback: keep only the lens's active members. A
            # categorical edge-existence predicate (identical to the scope/validity
            # filter), NEVER a similarity/length gate on meaning (§0/§3.7).
            allowed = {i: it for i, it in allowed.items() if i in member_filter}
        diagnostics: dict = {
            "has_fts": bool(self.store.has_fts),
            "scoped_pool": len(allowed),
            "scopes": len(scopes),
            "lens_member_filter": member_filter is not None,
        }

        if not allowed:
            return RetrievedContext(
                rendered="", items=[], degraded=not self.store.has_fts, diagnostics=diagnostics
            )

        fts_hits, vector_hits, degraded = await self._recall(req, allowed)
        diagnostics["fts_hits"] = len(fts_hits)
        diagnostics["vector_hits"] = len(vector_hits)
        diagnostics["degraded"] = degraded

        fused = self._fuse(fts_hits, vector_hits)
        if not fused:
            return RetrievedContext(
                rendered="", items=[], degraded=degraded, diagnostics=diagnostics
            )

        ranked = self._rank(fused, allowed, valid_at)
        rendered = await self._compress(req, ranked)
        diagnostics["ranked"] = len(ranked)

        return RetrievedContext(
            rendered=rendered, items=ranked, degraded=degraded, diagnostics=diagnostics
        )

    # --- lens egress (read-only, §3.7) ----------------------------------

    async def _expand_lens(self, req: Retrieval, scopes: list, valid_at: str):
        """Resolve req.lens_hint to a lens via the expander (read-only).

        Returns a LensExpansion or None. Failures degrade to unconstrained recall
        (None) — the lens path is a fast lane, never a hard dependency."""
        try:
            return await self.lens_expander.expand(
                hint=req.lens_hint, goal=req.goal, scopes=scopes, valid_at=valid_at
            )
        except Exception as e:
            _logger.warning("memory retrieve lens expansion failed: %s", e)
            return None

    # --- recall predicate: scope + validity + status + kind -------------

    async def _scoped_active_ids(
        self, req: Retrieval, scopes: list, valid_at: str
    ) -> dict[str, MemoryItem]:
        """The hard categorical filter as a recall predicate.

        Union over requested scopes of active, in-validity claims. This is the ONLY
        exclusion gate; everything past it is ordering.
        """
        allowed: dict[str, MemoryItem] = {}
        for scope in scopes:
            items = await self.store.query(
                scope=scope,
                status=Status.ACTIVE,
                valid_at=valid_at,
                limit=500,
            )
            for it in items:
                allowed[it.id] = it
        return allowed

    # --- candidate recall (hybrid, FTS-leaning) -------------------------

    async def _recall(
        self, req: Retrieval, allowed: dict[str, MemoryItem]
    ) -> tuple[list[str], list[str], bool]:
        """Return (fts_ranking_ids, vector_ranking_ids, degraded).

        Each list is ordered best-first within the scoped/valid pool. Vector leg
        re-ranks an over-fetched FTS pool by cosine of the goal against content.
        """
        if self.store.has_fts:
            fts_pool = await self.store.search(req.goal, limit=N_FTS * VECTOR_OVERFETCH)
            fts_pool = [it for it in fts_pool if it.id in allowed]
            fts_ids = [it.id for it in fts_pool[:N_FTS]]
            # Vector leg ranks the over-fetched FTS pool, falling back to the full
            # scoped pool when FTS matched nothing (genuinely-empty FTS case).
            vector_source = fts_pool if fts_pool else list(allowed.values())
            vector_ids = await self._vector_rank(req.goal, vector_source)
            degraded = False
        else:
            # FTS unavailable: recall = the scoped pool, ranked by vector + trust.
            fts_ids = []
            vector_ids = await self._vector_rank(req.goal, list(allowed.values()))
            degraded = True
        return fts_ids, vector_ids, degraded

    async def _vector_rank(self, goal: str, items: list[MemoryItem]) -> list[str]:
        if not items:
            return []
        try:
            goal_vec = await self.embed.embed_one(goal)
            texts = [it.content for it in items]
            mat = await self.embed.embed(texts)
        except Exception as e:  # embedder optional; recall still works on FTS/query
            _logger.warning("memory retrieve vector leg failed: %s", e)
            return []
        if mat.size == 0:
            return []
        sims = mat @ np.asarray(goal_vec)
        order = np.argsort(-sims)
        return [items[i].id for i in order]

    # --- fusion ---------------------------------------------------------

    def _fuse(self, fts_ids: list[str], vector_ids: list[str]) -> dict[str, dict]:
        """Weighted RRF over the two legs. Reuses rrf_merge per leg, then weights.

        Returns id -> {rrf, fts_rank, vector_rank}. FTS-weight > vector-weight.
        """
        fts_rrf = rrf_merge([[(i, 0.0) for i in fts_ids]], k=RRF_K) if fts_ids else {}
        vec_rrf = rrf_merge([[(i, 0.0) for i in vector_ids]], k=RRF_K) if vector_ids else {}
        fts_rank = {i: r for r, i in enumerate(fts_ids)}
        vec_rank = {i: r for r, i in enumerate(vector_ids)}

        fused: dict[str, dict] = {}
        for item_id in set(fts_rrf) | set(vec_rrf):
            score = FTS_WEIGHT * fts_rrf.get(item_id, 0.0) + VECTOR_WEIGHT * vec_rrf.get(
                item_id, 0.0
            )
            fused[item_id] = {
                "rrf": score,
                "fts_rank": fts_rank.get(item_id),
                "vector_rank": vec_rank.get(item_id),
            }
        return fused

    # --- ranking (transparent scalar — ORDERS, never gates) -------------

    def _rank(
        self, fused: dict[str, dict], pool: dict[str, MemoryItem], valid_at: str
    ) -> list[RankedItem]:
        ranked = [
            self._build_ranked(item_id, legs, pool, valid_at)
            for item_id, legs in fused.items()
        ]
        ranked = [r for r in ranked if r is not None]
        ranked.sort(key=lambda r: r.order_score, reverse=True)
        return ranked

    def _build_ranked(
        self, item_id: str, legs: dict, pool: dict[str, MemoryItem], valid_at: str
    ) -> RankedItem | None:
        item = pool.get(item_id)
        if item is None:
            return None
        prov_ord = _PROVENANCE_ORD.get(item.provenance, 0)
        freshness = self._freshness(item, valid_at)
        corro = item.corroboration
        order_score = (
            W_RRF * legs["rrf"]
            + W_FRESHNESS * freshness
            + W_PROVENANCE * (prov_ord / 4.0)
            + W_CORROBORATION * math.log1p(corro)
        )
        return RankedItem(
            item=item,
            fts_rank=legs["fts_rank"],
            vector_rank=legs["vector_rank"],
            rrf=legs["rrf"],
            freshness=freshness,
            provenance_ord=prov_ord,
            corroboration=corro,
            order_score=order_score,
        )

    def _freshness(self, item: MemoryItem, valid_at: str) -> float:
        """Monotone recency in [0, 1] from last_relevant_at, else valid_from.

        Half-life decay shape used only to ORDER (newer first); it is never a
        cutoff. Missing timestamps → neutral 0.5 (no recency signal).
        """
        ts = item.last_relevant_at or item.valid_from
        if not ts:
            return 0.5
        try:
            anchor = np.datetime64(valid_at[:19])
            point = np.datetime64(ts[:19])
        except Exception:
            return 0.5
        age_days = max(0.0, (anchor - point) / np.timedelta64(1, "D"))
        return float(0.5 ** (age_days / _FRESHNESS_HALFLIFE_DAYS))

    # --- query-aware compression at recall ------------------------------

    async def _compress(self, req: Retrieval, ranked: list[RankedItem]) -> str:
        budget_chars = req.token_budget * _CHARS_PER_TOKEN
        verbatim = self._render_to_budget(ranked, budget_chars)
        all_fit = len(verbatim) == len(ranked)
        if all_fit or len(ranked) < _COMPRESSION_MIN_POOL or not self.model:
            return "\n".join(verbatim)
        return await self._llm_compress(req, ranked, budget_chars)

    def _render_to_budget(self, ranked: list[RankedItem], budget_chars: int) -> list[str]:
        """Cheap default: top-ranked claims verbatim; drop whole low-rank claims."""
        lines: list[str] = []
        used = 0
        for r in ranked:
            line = f"- {r.item.content}"
            cost = len(line) + 1
            if used + cost > budget_chars and lines:
                break
            lines.append(line)
            used += cost
        return lines

    async def _llm_compress(
        self, req: Retrieval, ranked: list[RankedItem], budget_chars: int
    ) -> str:
        numbered = [f"{i}: {r.item.content}" for i, r in enumerate(ranked)]
        try:
            response = await self.cheap_llm.completion(
                messages=[
                    {"role": "system", "content": RETRIEVE_COMPRESS_SYSTEM},
                    {
                        "role": "user",
                        "content": build_compression_user_prompt(
                            req.goal, numbered, req.token_budget
                        ),
                    },
                ],
                model=self.model,
                response_format=CompressionResult,
                temperature=0.0,
            )
            parsed = self._parse_compression(response)
        except Exception as e:
            _logger.warning("memory retrieve compression call failed: %s", e)
            return "\n".join(self._render_to_budget(ranked, budget_chars))

        lines: list[str] = []
        used = 0
        for kept in parsed.kept:
            if kept.index < 0 or kept.index >= len(ranked):
                continue  # self-correcting: ignore out-of-range indices
            text = kept.rendered.strip() or ranked[kept.index].item.content
            line = f"- {text}"
            cost = len(line) + 1
            if used + cost > budget_chars and lines:
                break
            lines.append(line)
            used += cost
        if not lines:
            return "\n".join(self._render_to_budget(ranked, budget_chars))
        return "\n".join(lines)

    def _parse_compression(self, response) -> CompressionResult:
        content = response.choices[0].message.content
        if isinstance(content, CompressionResult):
            return content
        return CompressionResult.model_validate_json(content)
