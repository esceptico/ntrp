"""Lens membership — the computed-projection engine (a cache, not edges).

A lens is a VIEW. Membership is a COMPUTED PROJECTION: the LLM judges each claim
against the lens criterion; `in` verdicts are written to `lens_membership_cache`,
never to a graph edge. Drop the cache and nothing breaks except latency — the
projector recomputes on miss.

Three modes keep membership cheap across the corpus:

  Mode 1  score_into_active_lenses  — incremental, per write: RRF-recall the top-K
          active lenses for the new claims, batch the claims per lens into ONE
          cheap judge call, write verdicts to the CACHE. Cache-warming only;
          correctness does not depend on it (the projector recomputes on miss).
  Mode 3  refresh_lens_cache        — lazy backfill (cache miss/dirty): bounded scan
          of the scoped active claim pool, embedding-rank to the cap (orders the
          scan, never gates), batched judge, write verdicts to the cache.
  (decider) score                   — N claims vs ONE lens, one cheap structured
          call. `defer` escalates one item to the strong model.

THE ABSOLUTE BAN (§0): membership is ALWAYS an LLM judgment against the criterion.
Embeddings/FTS/RRF/length floors only ORDER candidates into the judge — they never
gate a keep/drop verdict. `coverage` is a pure COUNT over the cache, advisory only.
No member_of edge is ever written; lenses are never graph participants.
"""

from ntrp.constants import (
    BACKFILL_SCAN_CAP,
    GENERIC_RATIO,
    MEMBERSHIP_BATCH,
    MEMBERSHIP_CANDIDATE_K,
    RRF_K,
)
from ntrp.embedder import Embedder
from ntrp.llm.base import CompletionClient
from ntrp.logging import get_logger
from ntrp.memory.models import (
    LensRow,
    MembershipDecision,
    MembershipVerdict,
    MemoryItem,
    Scope,
    Status,
)
from ntrp.memory.pipeline.prompts_criterion import (
    CRITERION_SYNTH_SYSTEM,
    SynthesizedCriterion,
)
from ntrp.memory.pipeline.prompts_reconcile import (
    MEMBERSHIP_JUDGE_SYSTEM,
    MembershipBatch,
)
from ntrp.memory.pipeline.types import (
    BackfillReport,
    CoverageAdvisory,
)
from ntrp.memory.store import MemoryStore
from ntrp.search.retrieval import rrf_merge

_logger = get_logger(__name__)

_PAGE_GIST_LIMIT = 600


def _compose_criterion(belongs: str, profile_shape: list[str]) -> str:
    """Build the lens's editable markdown criterion from its parts: a `## Belongs`
    section (the membership definition + exclusions) and an optional `## Profile
    shape` section (the fields each member's profile should capture). This is the
    structured-file format lenses use — the membership judge reads Belongs; page
    synthesis reads Profile shape."""
    parts = [f"## Belongs\n{belongs.strip()}"]
    fields = [f.strip() for f in profile_shape if f and f.strip()]
    if fields:
        parts.append("## Profile shape\n" + "\n".join(f"- {f}" for f in fields))
    return "\n\n".join(parts)


def _decision(raw: str) -> MembershipDecision:
    """Coerce a model vote to a decision, defaulting OUT on anything unexpected."""
    try:
        return MembershipDecision((raw or "").strip().lower())
    except ValueError:
        return MembershipDecision.OUT


def _salient_tokens(text: str, limit: int = 12) -> str:
    """Length-floor FTS slice: drop short tokens, cap count. Orders the FTS query;
    carries no meaning rule, decides nothing."""
    toks = [t for t in text.split() if len(t) > 2]
    return " ".join(toks[:limit])


class LensMembership:
    def __init__(
        self,
        store: MemoryStore,
        cheap_llm: CompletionClient,
        strong_llm: CompletionClient,
        embed: Embedder,
        *,
        cheap_model: str,
        strong_model: str,
    ):
        self.store = store
        self.cheap_llm = cheap_llm
        self.strong_llm = strong_llm
        self.embed = embed
        self.cheap_model = cheap_model
        self.strong_model = strong_model

    # --- Mode 1: incremental cache-warming (hot, per write) ----------

    async def score_into_active_lenses(
        self, claim_ids: list[str], scope: Scope
    ) -> list[MembershipVerdict]:
        """Score freshly-written claims into the scope's active lenses (cache-warming).

        Best-effort: writes verdicts to the cache. Correctness does not depend on
        this — the projector recomputes on a cache miss. O(new x K), never O(corpus).
        """
        claims = [c for c in await self._load_claims(claim_ids) if c is not None]
        if not claims:
            return []

        lenses = await self._active_lenses(scope)
        if not lenses:
            return []

        touched: dict[str, LensRow] = {}
        batches: dict[str, list[MemoryItem]] = {}
        for claim in claims:
            for lens in await self._recall_lenses(claim, lenses):
                touched.setdefault(lens.id, lens)
                batches.setdefault(lens.id, []).append(claim)

        verdicts: list[MembershipVerdict] = []
        for lens_id, lens in touched.items():
            verdicts.extend(await self._judge_and_cache(batches[lens_id], lens))
        return verdicts

    # --- Mode 3: lazy backfill (cold, on cache miss / dirty) ---------

    async def refresh_lens_cache(self, lens_id: str) -> BackfillReport:
        """One bounded pass over the scoped active claim pool, writing the membership
        cache. Called lazily by the projector on cache-miss/dirty — NOT eagerly at
        create_lens (creating a lens touches zero claims)."""
        lens = await self.store.get_lens(lens_id)
        if lens is None:
            _logger.warning("refresh_lens_cache: %s missing", lens_id)
            return BackfillReport(lens_id=lens_id, scanned=0, members_added=0, capped=False)

        pool = await self.store.query(
            scope=lens.scope, status=Status.ACTIVE, limit=BACKFILL_SCAN_CAP + 1
        )
        # Honor durable user REJECTions: a rejected claim is never a member, full
        # stop. This is a user override (explicit feedback), not a heuristic gate —
        # it removes the claim from the judge's pool so it can't re-enter on re-derive.
        rejected = await self.store.get_rejections(lens_id)
        if rejected:
            pool = [c for c in pool if c.id not in rejected]

        capped = len(pool) > BACKFILL_SCAN_CAP
        if capped:
            pool = await self._rank_to_cap(lens, pool, BACKFILL_SCAN_CAP)

        added = 0
        for start in range(0, len(pool), MEMBERSHIP_BATCH):
            batch = pool[start : start + MEMBERSHIP_BATCH]
            verdicts = await self._judge_and_cache(batch, lens)
            added += sum(1 for v in verdicts if v.decision is MembershipDecision.IN)
        return BackfillReport(
            lens_id=lens_id, scanned=len(pool), members_added=added, capped=capped
        )

    # --- the decider -------------------------------------------------

    async def score(
        self, claims: list[MemoryItem], lens: LensRow
    ) -> list[MembershipVerdict]:
        """Judge N claims against ONE lens criterion. One cheap structured call.

        Parse failure / empty output -> the whole batch is `out`. `defer` escalates
        that single item to the strong model. No numeric cutoff ever decides; the
        band only routes who re-judges.
        """
        if not claims:
            return []

        votes = await self._judge(claims, lens, self.cheap_llm, self.cheap_model)

        verdicts: list[MembershipVerdict] = []
        for i, claim in enumerate(claims):
            decision, rationale = votes.get(i, (MembershipDecision.OUT, ""))
            if decision is MembershipDecision.DEFER:
                decision, rationale = await self._escalate(claim, lens, rationale)
            verdicts.append(
                MembershipVerdict(
                    lens_id=lens.id,
                    claim_id=claim.id,
                    decision=decision,
                    rationale=rationale,
                )
            )
        return verdicts

    # --- criterion authoring (text only; no membership decision) -----

    async def synthesize_criterion(
        self, name: str, intent: str | None = None
    ) -> tuple[str, str, str]:
        """Draft a criterion body + render mode + entity_type from a lens NAME.

        One cheap structured call. Authors TEXT only — makes no membership call.
        Returns (criterion, render_mode, entity_type): the criterion is the file
        body (## Belongs [+ ## Profile shape]); render_mode is "grouped_by_subject"
        for people/entity lenses else "flat". On empty/parse failure, degrade to a
        faithful echo criterion + flat (still not a keyword gate; decides no
        membership, just gives the user editable text).
        """
        user = f"LENS_NAME: {name!r}\nINTENT: {intent!r}"
        try:
            resp = await self.cheap_llm.completion(
                messages=[
                    {"role": "system", "content": CRITERION_SYNTH_SYSTEM},
                    {"role": "user", "content": user},
                ],
                model=self.cheap_model,
                response_format=SynthesizedCriterion,
            )
            content = resp.choices[0].message.content
            if not content:
                raise ValueError("empty criterion-synthesis response")
            parsed = SynthesizedCriterion.model_validate_json(content)
            belongs = parsed.belongs.strip()
            if not belongs:
                raise ValueError("blank synthesized criterion")
            criterion = _compose_criterion(belongs, parsed.profile_shape)
            mode = parsed.render_mode if parsed.render_mode in ("grouped_by_subject", "flat") else "flat"
            entity_type = parsed.entity_type.strip() or "thing"
            return criterion, mode, entity_type
        except Exception as e:
            _logger.warning("lens: criterion synthesis failed for %r, echoing: %s", name, e)
            return f"## Belongs\nThis item is about {name}.", "flat", "thing"

    # --- generic guard: advisory coverage ratio ---------------------

    async def coverage(self, lens_id: str, scope: Scope) -> CoverageAdvisory:
        """Pure COUNT(`in` cache rows) / COUNT(scoped active claims). No LLM, no
        lexical anything. `generic = ratio >= GENERIC_RATIO`; advisory only."""
        cached = await self.store.get_membership(lens_id, decision=MembershipDecision.IN)
        member_count = len(cached)

        # TRUE corpus size (no recency cap) — len(query(limit=N)) would saturate at N
        # and inflate the ratio, falsely flagging a big-corpus lens as "generic".
        scope_pool = await self.store.count_active(scope)
        ratio = member_count / scope_pool if scope_pool else 0.0
        generic = scope_pool > 0 and ratio >= GENERIC_RATIO
        return CoverageAdvisory(
            lens_id=lens_id,
            scope_pool=scope_pool,
            member_count=member_count,
            ratio=ratio,
            generic=generic,
            suggestion="split" if generic else "",
        )

    # --- recall (legal: orders candidates, never gates) -------------

    async def _active_lenses(self, scope: Scope) -> dict[str, LensRow]:
        scoped = await self.store.list_lenses(scope=scope)
        return {le.id: le for le in scoped}

    async def _recall_lenses(
        self, claim: MemoryItem, scoped: dict[str, LensRow]
    ) -> list[LensRow]:
        """RRF-merge recall channels for one claim, capped at the candidate-K.

        Channels over the claim content + the lens name/criterion/page text: lens-
        registry FTS, embedding cosine. Every channel ORDERS candidates into the
        judge; none gates membership."""
        if not scoped:
            return []

        id_list = list(scoped)
        id_index = {iid: n for n, iid in enumerate(id_list)}
        rankings: list[list[tuple[int, float]]] = []

        hits = await self.store.search_lenses(
            _salient_tokens(claim.content), limit=MEMBERSHIP_CANDIDATE_K * 2
        )
        rankings.append(self._rank(hits, scoped, id_index))

        margins = await self._embedding_margins(claim, scoped)
        if margins:
            ordered = sorted(margins.items(), key=lambda kv: kv[1], reverse=True)
            rankings.append([(id_index[iid], s) for iid, s in ordered])

        if not any(rankings):
            return []

        fused = rrf_merge(rankings, k=RRF_K)
        top = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)[:MEMBERSHIP_CANDIDATE_K]
        return [scoped[id_list[idx]] for idx, _ in top]

    def _rank(
        self,
        hits: list[LensRow],
        scoped: dict[str, LensRow],
        id_index: dict[str, int],
    ) -> list[tuple[int, float]]:
        ranked: list[tuple[int, float]] = []
        for rank, h in enumerate(hits):
            if h.id in scoped:
                ranked.append((id_index[h.id], 1.0 / (rank + 1)))
        return ranked

    async def _embedding_margins(
        self, claim: MemoryItem, scoped: dict[str, LensRow]
    ) -> dict[str, float]:
        lens_texts = [self._lens_text(le) for le in scoped.values()]
        if not lens_texts:
            return {}
        try:
            q = await self.embed.embed_one(claim.content)
            mat = await self.embed.embed(lens_texts)
        except Exception as e:
            _logger.warning("membership: embedding recall failed: %s", e)
            return {}
        sims = (mat @ q).tolist()  # both L2-normalized -> cosine
        return {le.id: float(s) for le, s in zip(scoped.values(), sims)}

    async def _rank_to_cap(
        self, lens: LensRow, pool: list[MemoryItem], cap: int
    ) -> list[MemoryItem]:
        """Embedding-rank the over-cap pool to the cap (orders the scan, never gates).
        Embedder down -> keep the first `cap` by recency."""
        try:
            q = await self.embed.embed_one(self._lens_text(lens))
            mat = await self.embed.embed([c.content for c in pool])
        except Exception as e:
            _logger.warning("membership: backfill rank embed failed: %s", e)
            return pool[:cap]
        sims = (mat @ q).tolist()
        ranked = sorted(zip(pool, sims), key=lambda cs: cs[1], reverse=True)
        return [c for c, _ in ranked[:cap]]

    @staticmethod
    def _lens_text(lens: LensRow) -> str:
        return " ".join(t for t in (lens.name, lens.criterion, lens.page) if t).strip()

    # --- judge + cache -----------------------------------------------

    async def _judge_and_cache(
        self, claims: list[MemoryItem], lens: LensRow
    ) -> list[MembershipVerdict]:
        verdicts = await self.score(claims, lens)
        # Write every verdict to the cache (in/out/defer) so the projector can read
        # a cached decision without re-judging. The cache is not graph truth.
        if verdicts:
            await self.store.put_membership(verdicts)
        return verdicts

    async def _judge(
        self,
        claims: list[MemoryItem],
        lens: LensRow,
        llm: CompletionClient,
        model: str,
    ) -> dict[int, tuple[MembershipDecision, str]]:
        """One structured judge call -> {item_index: (decision, rationale)}."""
        user = self._judge_prompt(claims, lens)
        try:
            resp = await llm.completion(
                messages=[
                    {"role": "system", "content": MEMBERSHIP_JUDGE_SYSTEM},
                    {"role": "user", "content": user},
                ],
                model=model,
                response_format=MembershipBatch,
            )
            content = resp.choices[0].message.content
            if not content:
                raise ValueError("empty structured response")
            batch = MembershipBatch.model_validate_json(content)
        except Exception as e:
            _logger.warning("membership: judge parse failed -> batch all-out: %s", e)
            return {}

        out: dict[int, tuple[MembershipDecision, str]] = {}
        for vote in batch.votes:
            if vote.item_index < 0 or vote.item_index >= len(claims):
                continue
            if vote.item_index in out:
                continue
            out[vote.item_index] = (_decision(vote.decision), vote.rationale)
        return out

    def _judge_prompt(self, claims: list[MemoryItem], lens: LensRow) -> str:
        # REJECTed claims are enforced durably (membership pool excludes them via
        # store.get_rejections before judging), so no negative-examples prompt slot
        # is needed — the old one read a page section that REJECT no longer writes.
        gist = (lens.page or lens.criterion or "")[:_PAGE_GIST_LIMIT]
        items = "\n".join(f"  [{i}] {c.content!r}" for i, c in enumerate(claims))
        return (
            f"LENS: name={lens.name!r}\n"
            f"CRITERION: {lens.criterion!r}\n"
            f"PAGE_GIST: {gist!r}\n"
            f"ITEMS:\n{items}"
        )

    async def _escalate(
        self, claim: MemoryItem, lens: LensRow, prior_rationale: str
    ) -> tuple[MembershipDecision, str]:
        """Re-judge one `defer` item on the strong model. Still `defer` -> stays
        DEFER (left out of the projection). The band routes who decides."""
        votes = await self._judge([claim], lens, self.strong_llm, self.strong_model)
        decision, rationale = votes.get(0, (MembershipDecision.DEFER, prior_rationale))
        return decision, rationale or prior_rationale

    # --- helpers -----------------------------------------------------

    async def _load_claims(self, claim_ids: list[str]) -> list[MemoryItem | None]:
        loaded: list[MemoryItem | None] = []
        for cid in claim_ids:
            m = await self.store.get(cid)
            if m is not None and m.status is Status.ACTIVE:
                loaded.append(m)
        return loaded
