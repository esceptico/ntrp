"""Reconcile — resolve a claim's subject, then ADD/UPDATE/NOOP/CONTRADICT.

The ONLY claim writer in the pipeline. Subject coreference is a claim ATTRIBUTE
(`canonical_subject`), not an entity row. Four phases per call:

  1. Subject candidate recall (no LLM): embedding + FTS over existing claims'
     canonical_subject + content, RRF-merged, scope-filtered. Signals only — they
     order candidate claims, they never gate.
  2. Subject identity (LLM judge): 0 candidates -> keep the extractor's subject
     (NEW); >=1 candidate -> one cheap MATCH/NEW judge that returns the canonical
     subject STRING to assign (reuse an existing one verbatim, or keep NEW). Group
     the batch by resolved canonical_subject string. There is NO row to mint.
  3. Profile recall (no LLM): the subject's existing active claims
     (store.query(subject=...)), capped/topic-sliced.
  4. Batch reconcile (LLM, one cheap call per subject): per-claim
     ADD/UPDATE/NOOP/CONTRADICT, with strong-model escalation on contested or
     high-trust targets.

Identity is decided by the LLM judge, never by a lexical rule, a pronoun list, a
proper-noun regex, or a cosine threshold (the ABSOLUTE BAN). No lens rows, no
member_of edges are ever written here. The store is frozen; this module lives
entirely above its public API.
"""

import uuid
from dataclasses import dataclass

from ntrp.constants import RRF_K
from ntrp.embedder import Embedder
from ntrp.llm.base import CompletionClient
from ntrp.logging import get_logger
from ntrp.memory.models import (
    EdgeRole,
    Feedback,
    MemoryEdge,
    MemoryItem,
    Provenance,
    Scope,
    Status,
    now_iso,
)
from ntrp.memory.pipeline.prompts_reconcile import (
    BATCH_RECONCILE_SYSTEM,
    SUBJECT_RESOLUTION_SYSTEM,
    BatchReconcile,
    ReconcileRow,
    SubjectResolution,
)
from ntrp.memory.pipeline.types import ClaimCandidate, Op, ReconcileResult
from ntrp.memory.store import MemoryStore
from ntrp.search.retrieval import rrf_merge

_logger = get_logger(__name__)

# Routing signals (signals route, they never gate an outcome).
SUBJECT_RECALL_K = 8
PROFILE_MEMBER_CAP = 30
# Sample claims shown per candidate subject in the identity-judge profile gist.
SUBJECT_PROFILE_SAMPLE = 3


@dataclass
class SubjectProfile:
    """A candidate existing subject offered to the identity judge: the subject
    string plus a profile gist (how many claims accumulated, a few sample facts).
    The judge reasons over accumulation, not a single raw claim (spec §4.4 / Lens
    §4: resolve against the full profile, not a name match)."""

    subject: str
    claim_count: int
    samples: list[str]


def _parse[T](response, model: type[T]) -> T:
    content = response.choices[0].message.content
    if not content:
        raise ValueError("empty structured response")
    return model.model_validate_json(content)


def _salient_tokens(text: str, limit: int = 12) -> str:
    """Length-based FTS slice — drop short tokens, cap count. Orders the FTS query;
    it carries no meaning rule (a length floor that routes, never a keyword set)."""
    toks = [t for t in text.split() if len(t) > 2]
    return " ".join(toks[:limit])


class Reconciler:
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

    async def reconcile(
        self,
        candidates: list[ClaimCandidate],
        scope: Scope,
        *,
        prior_candidates: list[MemoryItem] | None = None,
    ) -> list[ReconcileResult]:
        if not candidates:
            return []

        results: list[ReconcileResult | None] = [None] * len(candidates)

        # Phase 1+2: resolve each claim's canonical subject, then group by subject.
        groups: dict[str, list[int]] = {}
        for i, cand in enumerate(candidates):
            subject, is_new = await self._resolve_subject(cand, scope, prior_candidates)
            results[i] = ReconcileResult(
                claim_index=i,
                op=Op.ADD,  # provisional; overwritten in Phase 4
                canonical_subject=subject,
                subject_is_new=is_new,
            )
            groups.setdefault(subject, []).append(i)

        # Phase 3+4: per resolved subject, recall profile and batch-reconcile.
        for subject, idxs in groups.items():
            await self._reconcile_group(subject, idxs, candidates, results, scope)

        return [r for r in results if r is not None]

    # --- Phase 1 + 2: subject coreference (a claim attribute) --------

    async def _resolve_subject(
        self,
        cand: ClaimCandidate,
        scope: Scope,
        prior_candidates: list[MemoryItem] | None,
    ) -> tuple[str, bool]:
        """Return (canonical_subject, is_new). Recall claims that might share the
        subject, judge by LLM which existing subject (if any) is the same referent.

        The only categorical branch is the empty recalled set (0 candidates ->
        keep the extractor's subject as NEW). Every non-empty set goes to the LLM
        judge — no cosine shortcut, no lexical rule decides identity.
        """
        recalled = await self._recall_subject_profiles(cand, scope, prior_candidates)
        if not recalled:
            return cand.canonical_subject, True
        return await self._resolve_subject_llm(cand, recalled)

    async def _recall_subject_profiles(
        self,
        cand: ClaimCandidate,
        scope: Scope,
        prior_candidates: list[MemoryItem] | None,
    ) -> list[SubjectProfile]:
        """Recall existing subjects that might be the same referent, as profiles.

        The bug lives in recall, not scoring (Lens spec §4): User != Timur fragments
        when the existing canonical subject is never surfaced to the judge. So the
        candidate set is the FULL distinct-subject roster in scope (capped for cost
        only), ORDERED by fused signals — never trimmed by an FTS/embedding cutoff.

        Recall channels (signals ORDER, they never gate):
          - subject-name/alias FTS over canonical_subject (names + observed surfaces),
          - body FTS over the claim content,
          - embedding cosine over subject+content,
        RRF-merged to rank distinct subjects; the roster then guarantees every
        distinct subject reaches the judge with a profile gist (count + samples).
        """
        # The authoritative roster: EVERY distinct subject in scope, with no recency
        # or volume limit. A claim-window LIMIT here is a hidden recency gate that
        # drops long-established subjects (their oldest claims fall outside the
        # window) and fragments them (User != Timur). distinct_subjects has no cap.
        roster = await self.store.distinct_subjects(scope)
        if not roster:
            return []
        counts = dict(roster)

        # The recent active pool drives recall-channel ORDERING (signals only) and
        # gives cheap sample gists for recent subjects; it does NOT define the roster.
        scoped = await self.store.query(scope=scope, status=Status.ACTIVE, limit=500)
        for it in prior_candidates or []:
            if it.status is Status.ACTIVE and it.id not in {s.id for s in scoped}:
                scoped.append(it)

        by_id = {it.id: it for it in scoped}
        id_list = list(by_id)
        id_index = {iid: n for n, iid in enumerate(id_list)}

        # Sample facts per subject for the gist (from the recent pool where available).
        by_subject: dict[str, list[MemoryItem]] = {}
        for it in scoped:
            by_subject.setdefault(it.canonical_subject, []).append(it)

        rankings: list[list[tuple[int, float]]] = []

        name_query = " ".join([cand.canonical_subject, *cand.subject_surfaces]).strip()
        if name_query:
            name_hits = await self.store.search_subjects(name_query, limit=SUBJECT_RECALL_K * 4)
            rankings.append(self._rank(name_hits, by_id, id_index))
            body_hits = await self.store.search(name_query, limit=SUBJECT_RECALL_K * 2)
            rankings.append(self._rank(body_hits, by_id, id_index))

        content_hits = await self.store.search(
            _salient_tokens(cand.content), limit=SUBJECT_RECALL_K * 2
        )
        rankings.append(self._rank(content_hits, by_id, id_index))

        margins = await self._embedding_margins(cand, by_id)
        if margins:
            emb_ranking = sorted(margins.items(), key=lambda kv: kv[1], reverse=True)
            rankings.append([(id_index[iid], s) for iid, s in emb_ranking])

        # Fuse signals into a per-subject order; a subject's best-ranked claim wins.
        fused = rrf_merge(rankings, k=RRF_K) if any(rankings) else {}
        subject_score: dict[str, float] = {}
        for idx, score in fused.items():
            subj = by_id[id_list[idx]].canonical_subject
            if score > subject_score.get(subj, float("-inf")):
                subject_score[subj] = score

        # Order: signal-scored subjects first (by score), then by claim count — this
        # only ORDERS the prompt for readability. EVERY distinct subject in `counts`
        # (the full roster) reaches the judge; nothing is truncated.
        def sort_key(subj: str) -> tuple[float, int]:
            return (subject_score.get(subj, float("-inf")), counts.get(subj, 0))

        ordered_subjects = sorted(counts, key=sort_key, reverse=True)

        out: list[SubjectProfile] = []
        for subj in ordered_subjects:
            claims = by_subject.get(subj)
            if claims is None:
                # Subject not in the recent pool — fetch a few samples directly so an
                # old subject still gets a profile gist for the judge.
                claims = await self.store.query(
                    scope=scope, status=Status.ACTIVE, subject=subj, limit=SUBJECT_PROFILE_SAMPLE
                )
            out.append(
                SubjectProfile(
                    subject=subj,
                    claim_count=counts.get(subj, len(claims)),
                    samples=[c.content[:160] for c in claims[:SUBJECT_PROFILE_SAMPLE]],
                )
            )
        return out

    def _rank(
        self, hits: list[MemoryItem], by_id: dict[str, MemoryItem], id_index: dict[str, int]
    ) -> list[tuple[int, float]]:
        ranked: list[tuple[int, float]] = []
        for rank, h in enumerate(hits):
            if h.id in by_id:
                ranked.append((id_index[h.id], 1.0 / (rank + 1)))
        return ranked

    async def _embedding_margins(
        self, cand: ClaimCandidate, by_id: dict[str, MemoryItem]
    ) -> dict[str, float]:
        query = f"{cand.canonical_subject} {cand.content}".strip()
        texts = [f"{it.canonical_subject} {it.content}".strip() for it in by_id.values()]
        if not texts:
            return {}
        try:
            q = await self.embed.embed_one(query)
            mat = await self.embed.embed(texts)
        except Exception as e:
            _logger.warning("reconcile: embedding recall failed: %s", e)
            return {}
        sims = (mat @ q).tolist()  # both L2-normalized -> cosine
        return {it.id: float(s) for it, s in zip(by_id.values(), sims)}

    async def _resolve_subject_llm(
        self, cand: ClaimCandidate, profiles: list[SubjectProfile]
    ) -> tuple[str, bool]:
        cards = "\n".join(self._render_profile(p) for p in profiles)
        surfaces = ", ".join(cand.subject_surfaces) if cand.subject_surfaces else ""
        user = (
            f"NEW SUBJECT: {cand.canonical_subject!r}\n"
            f"SURFACES: {surfaces!r}\n"
            f"NEW CONTENT: {cand.content!r}\n\n"
            f"EXISTING SUBJECTS (with profile gist):\n{cards}"
        )
        resp = await self.cheap_llm.completion(
            messages=[
                {"role": "system", "content": SUBJECT_RESOLUTION_SYSTEM},
                {"role": "user", "content": user},
            ],
            model=self.cheap_model,
            response_format=SubjectResolution,
        )
        try:
            decision = _parse(resp, SubjectResolution)
        except Exception as e:
            # Malformed/empty cheap-model output must not crash the write; degrade to
            # NEW (keep the extractor's subject), the same conservative default used
            # when recall is empty.
            _logger.warning("reconcile: subject-resolution parse failed -> NEW: %s", e)
            return cand.canonical_subject, True
        known = {p.subject for p in profiles}
        if decision.decision.upper() == "MATCH" and decision.canonical_subject in known:
            return decision.canonical_subject, False
        # NEW, or a hallucinated subject -> keep the extractor's (self-correcting).
        return cand.canonical_subject, True

    @staticmethod
    def _render_profile(p: SubjectProfile) -> str:
        samples = "; ".join(repr(s) for s in p.samples)
        return f"- subject={p.subject!r} claims={p.claim_count} sample_facts=[{samples}]"

    # --- Phase 3 + 4 -------------------------------------------------

    async def _reconcile_group(
        self,
        subject: str,
        idxs: list[int],
        candidates: list[ClaimCandidate],
        results: list[ReconcileResult | None],
        scope: Scope,
    ) -> None:
        profile = await self._recall_profile(subject, idxs, candidates, scope)
        rows, escalated = await self._batch_reconcile(subject, profile, idxs, candidates)

        for row in rows:
            local = row.claim_index
            if local < 0 or local >= len(idxs):
                _logger.warning("reconcile: row claim_index %s out of range", local)
                continue
            global_idx = idxs[local]
            cand = candidates[global_idx]
            res = results[global_idx]
            assert res is not None
            res.escalated = local in escalated
            target = self._resolve_target(row, profile)
            await self._apply(row, cand, subject, target, res)

    async def _recall_profile(
        self, subject: str, idxs: list[int], candidates: list[ClaimCandidate], scope: Scope
    ) -> list[MemoryItem]:
        members = await self.store.query(
            scope=scope, status=Status.ACTIVE, subject=subject, limit=PROFILE_MEMBER_CAP * 4
        )
        if len(members) <= PROFILE_MEMBER_CAP:
            return members
        return await self._topic_slice(members, idxs, candidates)

    async def _topic_slice(
        self, members: list[MemoryItem], idxs: list[int], candidates: list[ClaimCandidate]
    ) -> list[MemoryItem]:
        query = " ".join(candidates[i].content for i in idxs)
        try:
            q = await self.embed.embed_one(query)
            mat = await self.embed.embed([m.content for m in members])
            sims = (mat @ q).tolist()
        except Exception as e:
            _logger.warning("reconcile: profile slice embed failed: %s", e)
            return members[:PROFILE_MEMBER_CAP]
        ranked = sorted(zip(members, sims), key=lambda ms: ms[1], reverse=True)
        return [m for m, _ in ranked[:PROFILE_MEMBER_CAP]]

    async def _batch_reconcile(
        self,
        subject: str,
        profile: list[MemoryItem],
        idxs: list[int],
        candidates: list[ClaimCandidate],
    ) -> tuple[list[ReconcileRow], set[int]]:
        if not profile:
            return [ReconcileRow(claim_index=i, op="add") for i in range(len(idxs))], set()

        profile_lines = "\n".join(
            f"[{n}] {m.content!r} prov={m.provenance} corrob={m.corroboration} "
            f"feedback={m.feedback} valid_from={m.valid_from}"
            for n, m in enumerate(profile)
        )
        new_lines = "\n".join(
            f"[{n}] {candidates[gi].content!r} prov={candidates[gi].provenance}"
            for n, gi in enumerate(idxs)
        )
        user = (
            f"SUBJECT: {subject!r}\n\n"
            f"EXISTING CLAIMS:\n{profile_lines}\n\n"
            f"NEW FACTS:\n{new_lines}"
        )
        resp = await self.cheap_llm.completion(
            messages=[
                {"role": "system", "content": BATCH_RECONCILE_SYSTEM},
                {"role": "user", "content": user},
            ],
            model=self.cheap_model,
            response_format=BatchReconcile,
        )
        try:
            parsed = _parse(resp, BatchReconcile)
            rows = self._validate_rows(parsed.rows, len(idxs), len(profile))
        except Exception as e:
            # A malformed/empty cheap-model batch response must not crash the whole
            # reconcile (which would leave every claim in the call unwritten). Degrade
            # to all-ADD — never merges/supersedes blindly; a later consolidate pass
            # cleans any duplicate this creates. Mirrors the escalation fallback.
            _logger.warning("reconcile: batch parse failed -> all-ADD: %s", e)
            return [ReconcileRow(claim_index=i, op="add") for i in range(len(idxs))], set()

        escalated_idxs: set[int] = set()
        for row in rows:
            if self._needs_escalation(row, profile):
                better = await self._escalate(subject, profile, idxs, candidates, row)
                if better is not None:
                    row.op = better.op
                    row.target_idx = better.target_idx
                    row.merged_text = better.merged_text
                    escalated_idxs.add(row.claim_index)
        return rows, escalated_idxs

    def _validate_rows(
        self, rows: list[ReconcileRow], n_new: int, n_profile: int
    ) -> list[ReconcileRow]:
        """Drop out-of-range claim indices; coerce bad target_idx to ADD."""
        seen: set[int] = set()
        out: list[ReconcileRow] = []
        for row in rows:
            if row.claim_index < 0 or row.claim_index >= n_new:
                continue
            if row.claim_index in seen:
                continue
            seen.add(row.claim_index)
            if row.op != "add":
                if row.target_idx is None or not (0 <= row.target_idx < n_profile):
                    _logger.warning(
                        "reconcile: %s with invalid target_idx %s -> ADD", row.op, row.target_idx
                    )
                    row.op = "add"
                    row.target_idx = None
            out.append(row)
        for i in range(n_new):
            if i not in seen:
                out.append(ReconcileRow(claim_index=i, op="add"))
        return out

    def _needs_escalation(self, row: ReconcileRow, profile: list[MemoryItem]) -> bool:
        if row.op == "add":
            return False
        if row.contested:
            return True
        if row.op in ("update", "contradict") and row.target_idx is not None:
            t = profile[row.target_idx]
            if t.provenance is Provenance.USER_AUTHORED or t.corroboration >= 3:
                return True
        return False

    async def _escalate(
        self,
        subject: str,
        profile: list[MemoryItem],
        idxs: list[int],
        candidates: list[ClaimCandidate],
        row: ReconcileRow,
    ) -> ReconcileRow | None:
        gi = idxs[row.claim_index]
        target = profile[row.target_idx] if row.target_idx is not None else None
        target_content = repr(target.content) if target else None
        target_prov = target.provenance if target else None
        target_corrob = target.corroboration if target else None
        user = (
            f"Re-judge ONE reconciliation decision carefully.\n"
            f"SUBJECT: {subject!r}\n"
            f"NEW FACT: {candidates[gi].content!r} (prov={candidates[gi].provenance})\n"
            f"TARGET EXISTING CLAIM: {target_content} "
            f"(prov={target_prov}, corrob={target_corrob})\n"
            f"Proposed op was {row.op!r}. Return the corrected single-row decision "
            f"with claim_index={row.claim_index} and target_idx referring to the same "
            f"target (index {row.target_idx})."
        )
        try:
            resp = await self.strong_llm.completion(
                messages=[
                    {"role": "system", "content": BATCH_RECONCILE_SYSTEM},
                    {"role": "user", "content": user},
                ],
                model=self.strong_model,
                response_format=BatchReconcile,
            )
            parsed = _parse(resp, BatchReconcile)
        except Exception as e:
            _logger.warning("reconcile: escalation failed, keeping cheap decision: %s", e)
            return None
        for r in parsed.rows:
            if r.claim_index == row.claim_index:
                if r.op != "add" and (r.target_idx is None or not (0 <= r.target_idx < len(profile))):
                    r.target_idx = row.target_idx
                return r
        return None

    def _resolve_target(self, row: ReconcileRow, profile: list[MemoryItem]) -> MemoryItem | None:
        if row.op == "add" or row.target_idx is None:
            return None
        if 0 <= row.target_idx < len(profile):
            return profile[row.target_idx]
        return None

    # --- store op application ----------------------------------------

    async def _apply(
        self,
        row: ReconcileRow,
        cand: ClaimCandidate,
        subject: str,
        target: MemoryItem | None,
        res: ReconcileResult,
    ) -> None:
        # Honor the LLM's op verbatim. A prior heuristic here flipped NOOP -> UPDATE
        # whenever the incoming claim out-ranked the target on provenance — a rule
        # silently overriding the judge and superseding (destroying) an identical
        # claim. Higher-provenance corroboration is already recorded by _do_noop
        # (bump_corroboration + CONFIRMED feedback) without rewriting the claim.
        op = row.op

        if op == "add" or target is None:
            await self._do_add(cand, subject, res)
        elif op == "update":
            await self._do_update(row, cand, subject, target, res)
        elif op == "contradict":
            await self._do_contradict(row, cand, subject, target, res)
        elif op == "noop":
            await self._do_noop(cand, target, res)
        else:
            await self._do_add(cand, subject, res)

    def _new_claim(self, content: str, subject: str, cand: ClaimCandidate) -> MemoryItem:
        return MemoryItem(
            id=uuid.uuid4().hex,
            content=content,
            canonical_subject=subject,
            scope=cand.scope,
            provenance=cand.provenance,
            # Honor a caller-supplied event/validity time (e.g. remember(valid_from=...));
            # default to now only when none was given. (valid_from is the bi-temporal
            # event axis, distinct from created_at's transaction time.)
            valid_from=cand.valid_from or now_iso(),
            source_refs=list(cand.source_refs),
        )

    async def _do_add(self, cand: ClaimCandidate, subject: str, res: ReconcileResult) -> None:
        claim = self._new_claim(cand.content, subject, cand)
        await self.store.create_item(claim)
        res.op = Op.ADD
        res.written_id = claim.id

    async def _do_update(
        self,
        row: ReconcileRow,
        cand: ClaimCandidate,
        subject: str,
        target: MemoryItem,
        res: ReconcileResult,
    ) -> None:
        successor = self._new_claim(row.merged_text or cand.content, subject, cand)
        successor.source_refs = self._union_refs(target.source_refs, cand.source_refs)
        await self.store.supersede(old_id=target.id, new_item=successor)
        res.op = Op.UPDATE
        res.written_id = successor.id
        res.target_claim_id = target.id

    async def _do_contradict(
        self,
        row: ReconcileRow,
        cand: ClaimCandidate,
        subject: str,
        target: MemoryItem,
        res: ReconcileResult,
    ) -> None:
        # A contradiction is NOT a successor-chain (vision §4.4: "no successor-chain").
        # Write the new claim, ARCHIVE the contradicted target (close its validity),
        # and link a CONTRADICTS edge — no SUPERSEDED status, no SUPERSEDES edge.
        # Mirrors the consolidate path; supersede() (used by UPDATE) would wrongly
        # stamp SUPERSEDED + add a SUPERSEDES edge, misrepresenting it as a clean
        # replacement.
        new_claim = self._new_claim(row.merged_text or cand.content, subject, cand)
        new_claim.source_refs = list(cand.source_refs)
        await self.store.create_item(new_claim)
        await self.store.invalidate(target.id, status=Status.ARCHIVED)
        await self.store.add_edge(
            MemoryEdge(child_id=new_claim.id, parent_id=target.id, role=EdgeRole.CONTRADICTS)
        )
        res.op = Op.CONTRADICT
        res.written_id = new_claim.id
        res.target_claim_id = target.id

    async def _do_noop(
        self, cand: ClaimCandidate, target: MemoryItem, res: ReconcileResult
    ) -> None:
        await self.store.bump_corroboration(target.id)
        if (
            cand.provenance is Provenance.USER_AUTHORED
            and target.provenance is Provenance.INFERRED
        ):
            await self.store.set_feedback(target.id, Feedback.CONFIRMED)
        res.op = Op.NOOP
        res.target_claim_id = target.id

    @staticmethod
    def _union_refs(a, b):
        seen = set()
        out = []
        for ref in [*a, *b]:
            key = (ref.kind, ref.ref)
            if key not in seen:
                seen.add(key)
                out.append(ref)
        return out
