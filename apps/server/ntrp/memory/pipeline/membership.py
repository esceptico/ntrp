"""Lens membership — the scale-orchestration engine (LENS_CONTRACTS §3.1, §3.6).

`LensMembership` is the generalization of reconcile's recall+judge with the two
entity-specific narrowings relaxed (criterion is arbitrary, recall is filtered to
`lens_kind in {"topic","user"}` instead of `"entity"`). It is the SOLE membership
decision channel for topic/user lenses; reconcile keeps owning the entity axis
inline, so the two never score the same (claim, lens) pair (§2 axis split).

Three modes keep membership cheap across the corpus (§3.6):

  Mode 1  score_into_active_lenses  — incremental, per write: RRF-recall the top-K
          topic/user lenses for the new claims, batch the claims per lens into ONE
          cheap judge call, add_edge on `in`. O(new x K), never O(corpus).
  Mode 3  backfill_lens             — once per new lens: bounded scan of the scoped
          active claim pool, embedding-rank to the cap (orders the scan, never
          gates), batched judge, add_edge on `in`.
  (decider) score                   — N claims vs ONE lens, one cheap structured
          call (LLooM multiple-choice). `defer` escalates one item to the strong
          model; still `defer` leaves it unwritten (surfaced to the user).

THE ABSOLUTE BAN (§0): membership is ALWAYS an LLM judgment against the criterion.
Embeddings/FTS/RRF/length floors only ORDER candidates into the judge — they never
gate a keep/drop/membership verdict. `in` -> add_edge; `out` -> nothing (absence is
OUT, no negative rows); `defer` -> escalate, never a numeric cutoff. The store is
frozen and add-only: there is no edge delete (§1.1); a claim leaves a lens only via
re-validate-at-read in the projector, never here. `coverage` is a pure COUNT ratio,
advisory only (§7) — never a gate, never a word list.
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
    EdgeRole,
    Kind,
    MemoryEdge,
    MemoryItem,
    Scope,
    Status,
)
from ntrp.memory.pipeline.prompts_reconcile import (
    MEMBERSHIP_JUDGE_SYSTEM,
    MembershipBatch,
)
from ntrp.memory.pipeline.types import (
    BackfillReport,
    CoverageAdvisory,
    MembershipDecision,
    MembershipVerdict,
)
from ntrp.memory.store import MemoryStore
from ntrp.search.retrieval import rrf_merge

_logger = get_logger(__name__)

# Topic/user is the unconstrained axis LensMembership owns; entity stays inline in
# reconcile (§2). The split is by lens_kind, never by a lexical rule.
_TOPIC_USER = ("topic", "user")
_PAGE_GIST_LIMIT = 600


def _decision(raw: str) -> MembershipDecision:
    """Coerce a model vote to a decision, defaulting OUT on anything unexpected
    (§4.1: hallucinated/empty -> out)."""
    try:
        return MembershipDecision((raw or "").strip().lower())
    except ValueError:
        return MembershipDecision.OUT


def _salient_tokens(text: str, limit: int = 12) -> str:
    """Length-floor FTS slice (LENS_CONTRACTS §0-legal): drop short tokens, cap
    count. Orders the FTS query; carries no meaning rule, decides nothing."""
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

    # --- Mode 1: incremental (hot, per write) ------------------------

    async def score_into_active_lenses(
        self, claim_ids: list[str], scope: Scope
    ) -> list[MembershipVerdict]:
        """Score freshly-written claims into the scope's active topic/user lenses.

        Called from runtime.ingest_unit right after reconcile. Per the recalled
        candidate lenses (top-K, ordered by RRF — never gated), batch the claims
        into ONE cheap judge call and add_edge on `in`. The fan-out is bounded by
        MEMBERSHIP_CANDIDATE_K, so cost is O(new x K), never O(corpus) (§3.6).
        """
        claims = [c for c in await self._load_claims(claim_ids) if c is not None]
        if not claims:
            return []

        lenses = await self._active_topic_user_lenses(scope)
        if not lenses:
            return []

        # Per lens, collect the claims that recalled it; one judge call per such
        # lens over exactly its recall subset. At most one call per touched lens, so
        # cost stays O(new x K) — the K-bound the test asserts (§3.6).
        touched: dict[str, MemoryItem] = {}
        batches: dict[str, list[MemoryItem]] = {}
        for claim in claims:
            for lens in await self._recall_lenses(claim, lenses):
                touched.setdefault(lens.id, lens)
                batches.setdefault(lens.id, []).append(claim)

        verdicts: list[MembershipVerdict] = []
        for lens_id, lens in touched.items():
            verdicts.extend(await self._judge_and_write(batches[lens_id], lens))
        return verdicts

    # --- Mode 3: backfill (cold, once per new lens) ------------------

    async def backfill_lens(self, lens_id: str) -> BackfillReport:
        """One bounded pass over the scoped active claim pool for a new lens.

        Scan is capped at BACKFILL_SCAN_CAP and embedding-ranked to the cap
        (ordering only — never a gate); the capped set is batched into cheap judge
        calls (MEMBERSHIP_BATCH each) and `in` claims get a MEMBER_OF edge. The
        single expensive pass per lens; thereafter Mode 1 maintains it (§3.6).
        """
        lens = await self.store.get(lens_id)
        if lens is None or lens.kind is not Kind.LENS or lens.status is not Status.ACTIVE:
            _logger.warning("backfill_lens: %s missing/inactive/non-lens", lens_id)
            return BackfillReport(lens_id=lens_id, scanned=0, members_added=0, capped=False)

        pool = await self.store.query(
            kind=Kind.CLAIM, scope=lens.scope, status=Status.ACTIVE, limit=BACKFILL_SCAN_CAP + 1
        )
        capped = len(pool) > BACKFILL_SCAN_CAP
        if capped:
            pool = await self._rank_to_cap(lens, pool, BACKFILL_SCAN_CAP)

        added = 0
        for start in range(0, len(pool), MEMBERSHIP_BATCH):
            batch = pool[start : start + MEMBERSHIP_BATCH]
            verdicts = await self._judge_and_write(batch, lens)
            added += sum(1 for v in verdicts if v.decision is MembershipDecision.IN)
        return BackfillReport(
            lens_id=lens_id, scanned=len(pool), members_added=added, capped=capped
        )

    # --- the decider -------------------------------------------------

    async def score(
        self, claims: list[MemoryItem], lens: MemoryItem
    ) -> list[MembershipVerdict]:
        """Judge N claims against ONE lens criterion (LLooM multiple-choice).

        One cheap structured call. Out-of-range index -> ignored, default `out`.
        Parse failure / empty output -> the whole batch is `out` (§4.1; lint
        re-scores later). `defer` escalates that single item to the strong model;
        if still `defer`, the verdict stays DEFER (left unwritten, surfaced to the
        user). No numeric cutoff ever decides keep/drop — the band only routes who
        re-judges (§0).
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
                    claim_id=claim.id,
                    lens_id=lens.id,
                    decision=decision,
                    rationale=rationale,
                )
            )
        return verdicts

    # --- generic guard: advisory coverage ratio (§7) -----------------

    async def coverage(self, lens_id: str, scope: Scope) -> CoverageAdvisory:
        """Pure COUNT(member_of) / COUNT(scoped active claims). No LLM, no lexical
        anything. `generic = ratio >= GENERIC_RATIO`; advisory only — never a gate,
        never an auto-split/drop (§0, §7). scope_pool == 0 -> ratio 0.0, no banner.
        """
        edges = await self.store.list_edges(
            lens_id, direction="to", role=EdgeRole.MEMBER_OF
        )
        member_count = 0
        for e in edges:
            m = await self.store.get(e.child_id)
            if m is not None and m.status is Status.ACTIVE and m.kind is Kind.CLAIM:
                member_count += 1

        pool = await self.store.query(
            kind=Kind.CLAIM, scope=scope, status=Status.ACTIVE, limit=BACKFILL_SCAN_CAP
        )
        scope_pool = len(pool)
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

    # --- recall (legal: orders candidates, never gates) --------------

    async def _active_topic_user_lenses(self, scope: Scope) -> dict[str, MemoryItem]:
        scoped = await self.store.query(
            kind=Kind.LENS, scope=scope, status=Status.ACTIVE, limit=200
        )
        return {le.id: le for le in scoped if le.lens_kind in _TOPIC_USER}

    async def _recall_lenses(
        self, claim: MemoryItem, scoped: dict[str, MemoryItem]
    ) -> list[MemoryItem]:
        """RRF-merge the recall channels for one claim, capped at the candidate-K.

        Three signal-only channels over the claim content + the lens
        name/page/criterion text: content FTS, lens-text FTS, embedding cosine.
        RRF-fused, scope-filtered, capped. Every channel ORDERS candidates into the
        judge; none gates membership (§0). With FTS or the embedder down, recall
        degrades to the surviving channels — never the decision (§9.8)."""
        if not scoped:
            return []

        id_list = list(scoped)
        id_index = {iid: n for n, iid in enumerate(id_list)}
        rankings: list[list[tuple[int, float]]] = []

        # Channel 1+2: FTS over claim content, projected onto the scoped lenses
        # (matches against lens_name/criterion/page indexed columns).
        hits = await self.store.search(
            _salient_tokens(claim.content), limit=MEMBERSHIP_CANDIDATE_K * 2
        )
        rankings.append(self._rank(hits, scoped, id_index))

        # Channel 3: embedding cosine over lens text (ranking signal only).
        margins = await self._embedding_margins(claim, scoped)
        if margins:
            ordered = sorted(margins.items(), key=lambda kv: kv[1], reverse=True)
            rankings.append([(id_index[iid], s) for iid, s in ordered])

        if not any(rankings):
            return []

        fused = rrf_merge(rankings, k=RRF_K)
        top = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)[
            :MEMBERSHIP_CANDIDATE_K
        ]
        return [scoped[id_list[idx]] for idx, _ in top]

    def _rank(
        self,
        hits: list[MemoryItem],
        scoped: dict[str, MemoryItem],
        id_index: dict[str, int],
    ) -> list[tuple[int, float]]:
        ranked: list[tuple[int, float]] = []
        for rank, h in enumerate(hits):
            if h.id in scoped:
                ranked.append((id_index[h.id], 1.0 / (rank + 1)))
        return ranked

    async def _embedding_margins(
        self, claim: MemoryItem, scoped: dict[str, MemoryItem]
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
        self, lens: MemoryItem, pool: list[MemoryItem], cap: int
    ) -> list[MemoryItem]:
        """Embedding-rank the over-cap pool to the cap (orders the scan, never
        gates — the judge still decides every survivor). Embedder down -> keep the
        first `cap` by recency (the query already returns created_at DESC)."""
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
    def _lens_text(lens: MemoryItem) -> str:
        return " ".join(
            t
            for t in (
                lens.lens_name,
                lens.lens_criterion,
                lens.lens_page,
            )
            if t
        ).strip()

    # --- judge + write -----------------------------------------------

    async def _judge_and_write(
        self, claims: list[MemoryItem], lens: MemoryItem
    ) -> list[MembershipVerdict]:
        verdicts = await self.score(claims, lens)
        for v in verdicts:
            if v.decision is MembershipDecision.IN:
                # add_edge is INSERT OR IGNORE: duplicate is a no-op (§9.9).
                # `out`/`defer` write nothing — absence is OUT (§3.1).
                await self.store.add_edge(
                    MemoryEdge(
                        child_id=v.claim_id, parent_id=lens.id, role=EdgeRole.MEMBER_OF
                    )
                )
        return verdicts

    async def _judge(
        self,
        claims: list[MemoryItem],
        lens: MemoryItem,
        llm: CompletionClient,
        model: str,
    ) -> dict[int, tuple[MembershipDecision, str]]:
        """One structured judge call -> {item_index: (decision, rationale)}.

        Out-of-range / duplicate indices are dropped; any item with no in-range
        vote defaults OUT (resolved by the caller via .get). Parse failure / empty
        output -> {} so every item falls through to OUT (§4.1)."""
        user = self._judge_prompt(claims, lens)
        try:
            resp = await llm.completion(
                messages=[
                    {"role": "system", "content": MEMBERSHIP_JUDGE_SYSTEM},
                    {"role": "user", "content": user},
                ],
                model=model,
                response_format=MembershipBatch,
                temperature=0.0,
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

    def _judge_prompt(self, claims: list[MemoryItem], lens: MemoryItem) -> str:
        gist = (lens.lens_page or lens.lens_criterion or "")[:_PAGE_GIST_LIMIT]
        negatives = self._negative_examples(lens)
        items = "\n".join(f"  [{i}] {c.content!r}" for i, c in enumerate(claims))
        return (
            f"LENS: name={lens.lens_name!r} kind={lens.lens_kind!r}\n"
            f"CRITERION: {(lens.lens_criterion or '')!r}\n"
            f"PAGE_GIST: {gist!r}\n"
            f"NEGATIVE_EXAMPLES: {negatives!r}\n"
            f"ITEMS:\n{items}"
        )

    @staticmethod
    def _negative_examples(lens: MemoryItem) -> str:
        """Lens-scoped REJECT corrections live in a section of lens_page, appended
        by write-back (§3.3). Read as worked examples by the judge, NEVER parsed as
        a keyword filter (§0). Returns the raw section text or '' if none."""
        page = lens.lens_page or ""
        marker = "## Negative examples"
        idx = page.find(marker)
        return page[idx + len(marker) :].strip() if idx >= 0 else ""

    async def _escalate(
        self, claim: MemoryItem, lens: MemoryItem, prior_rationale: str
    ) -> tuple[MembershipDecision, str]:
        """Re-judge one `defer` item on the strong model (§4.2). Still `defer` ->
        stays DEFER (left unwritten, surfaced to the user). The band routes who
        decides; it never applies a numeric cutoff to the outcome (§0)."""
        votes = await self._judge([claim], lens, self.strong_llm, self.strong_model)
        decision, rationale = votes.get(0, (MembershipDecision.DEFER, prior_rationale))
        return decision, rationale or prior_rationale

    # --- helpers -----------------------------------------------------

    async def _load_claims(self, claim_ids: list[str]) -> list[MemoryItem | None]:
        loaded: list[MemoryItem | None] = []
        for cid in claim_ids:
            m = await self.store.get(cid)
            if m is not None and m.status is Status.ACTIVE and m.kind is Kind.CLAIM:
                loaded.append(m)
        return loaded
