"""Reconcile — resolve subject, then ADD/UPDATE/NOOP/CONTRADICT (CONTRACTS §7).

The ONLY claim writer in the pipeline. Four phases per call:

  1. Subject candidate recall (no LLM): embedding + alias/name-FTS + content-FTS
     over the extractor's LLM-emitted canonical_subject (+ surfaces), RRF-merged,
     scope-intersected to entity lenses. Signals only — they order candidates,
     they never gate.
  2. Subject identity (LLM judge): 0 candidates -> NEW (categorical empty set,
     no call); >=1 candidate -> exactly one cheap MATCH/NEW judge call (no margin
     shortcut). Group claims by resolved subject.
  3. Profile recall (no LLM): the subject's active MEMBER_OF claims.
  4. Batch reconcile (LLM, one cheap call per subject): per-claim
     ADD/UPDATE/NOOP/CONTRADICT, with strong-model escalation on contested or
     high-trust targets.

Identity is decided by the LLM judge, never by a lexical rule, a pronoun list, a
proper-noun regex, or a cosine threshold (the ABSOLUTE BAN). The store is frozen;
this module lives entirely above its public API. NOOP does NOT touch
last_relevant_at (no setter exists — CONTRACTS §11).
"""

import uuid

from ntrp.constants import RRF_K
from ntrp.embedder import Embedder
from ntrp.llm.base import CompletionClient
from ntrp.logging import get_logger
from ntrp.memory.models import (
    EdgeRole,
    Feedback,
    Kind,
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

# Routing signals (CONTRACTS §2: signals route, they never gate an outcome).
SUBJECT_RECALL_K = 8
PROFILE_MEMBER_CAP = 30

_PROVENANCE_ORD = {
    Provenance.USER_AUTHORED: 3,
    Provenance.RECORDED: 2,
    Provenance.INFERRED: 1,
    Provenance.EXTERNAL: 0,
    Provenance.INDUCED: 0,
}


def _parse[T](response, model: type[T]) -> T:
    content = response.choices[0].message.content
    if not content:
        raise ValueError("empty structured response")
    return model.model_validate_json(content)


def _salient_tokens(text: str, limit: int = 12) -> str:
    """Length-based FTS slice — drop short tokens, cap count. Orders the FTS query;
    it carries no meaning rule (CONTRACTS §0.2-legal: a length floor that routes,
    never a word/keyword set that decides)."""
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

        # Phase 1+2: resolve each claim's subject, then group by resolved lens.
        groups: dict[str, list[int]] = {}
        for i, cand in enumerate(candidates):
            lens, created = await self._resolve_subject(cand, scope, prior_candidates)
            results[i] = ReconcileResult(
                claim_index=i,
                op=Op.ADD,  # provisional; overwritten in Phase 4
                subject_lens_id=lens.id,
                subject_created=created,
            )
            groups.setdefault(lens.id, []).append(i)

        # Phase 3+4: per resolved subject, recall profile and batch-reconcile.
        for lens_id, idxs in groups.items():
            subject = await self.store.get(lens_id)
            if subject is None:  # mint failed / hallucinated id guard
                _logger.warning("reconcile: subject lens %s missing; ADDing claims", lens_id)
            await self._reconcile_group(
                lens_id, subject, idxs, candidates, results, scope
            )

        return [r for r in results if r is not None]

    # --- Phase 1 + 2 -------------------------------------------------

    async def _resolve_subject(
        self,
        cand: ClaimCandidate,
        scope: Scope,
        prior_candidates: list[MemoryItem] | None,
    ) -> tuple[MemoryItem, bool]:
        """Return (entity_lens, created). Recall by embedding+FTS, judge by LLM.

        The only categorical branch is the empty recalled set (0 candidates ->
        NEW). Every non-empty set goes to the LLM judge — no cosine shortcut, no
        lexical rule decides identity. Bias-to-NEW under doubt lives in the judge.
        """
        recalled = await self._recall_subjects(cand, scope, prior_candidates)
        if not recalled:
            return await self._mint_subject(cand.canonical_subject, scope), True
        return await self._resolve_subject_llm(cand, scope, [r[0] for r in recalled])

    async def _recall_subjects(
        self,
        cand: ClaimCandidate,
        scope: Scope,
        prior_candidates: list[MemoryItem] | None,
    ) -> list[tuple[MemoryItem, float]]:
        """Union the recall channels, RRF-merge, scope+kind filter to entity lenses.

        Three signal-only channels over the LLM-emitted canonical_subject (+ its
        observed surfaces) and the claim content: alias/name FTS, embedding cosine,
        content FTS. Returns [(lens, embedding_cosine)] ordered by RRF; the cosine
        is a ranking signal that orders candidates into the judge — it NEVER gates.
        """
        scoped_lenses = await self.store.query(
            kind=Kind.LENS, scope=scope, status=Status.ACTIVE, limit=200
        )
        scoped = {le.id: le for le in scoped_lenses if le.lens_kind == "entity"}
        # Seed from Admit's prior_candidates that happen to be entity lenses in scope.
        for it in prior_candidates or []:
            if it.kind is Kind.LENS and it.lens_kind == "entity" and it.id in scoped:
                scoped.setdefault(it.id, it)
        if not scoped:
            return []

        id_list = list(scoped)
        id_index = {iid: n for n, iid in enumerate(id_list)}

        rankings: list[list[tuple[int, float]]] = []

        # Channel 1: alias/name FTS keyed on the canonical subject + every observed
        # surface (the accrued lens_criterion alias text IS the alias index).
        subject_query = " ".join([cand.canonical_subject, *cand.subject_surfaces]).strip()
        if subject_query:
            hits = await self.store.search(subject_query, limit=SUBJECT_RECALL_K * 2)
            rankings.append(self._rank(hits, scoped, id_index))

        # Channel 3: content-FTS.
        hits = await self.store.search(_salient_tokens(cand.content), limit=SUBJECT_RECALL_K * 2)
        rankings.append(self._rank(hits, scoped, id_index))

        # Channel 2: embedding cosine over lens name/page (ranking signal only).
        margins = await self._embedding_margins(cand, scoped)
        if margins:
            emb_ranking = sorted(margins.items(), key=lambda kv: kv[1], reverse=True)
            rankings.append([(id_index[iid], s) for iid, s in emb_ranking])

        if not any(rankings):
            return []

        fused = rrf_merge(rankings, k=RRF_K)
        ordered = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)[:SUBJECT_RECALL_K]
        out: list[tuple[MemoryItem, float]] = []
        for idx, _ in ordered:
            iid = id_list[idx]
            out.append((scoped[iid], margins.get(iid, 0.0)))
        return out

    def _rank(
        self, hits: list[MemoryItem], scoped: dict[str, MemoryItem], id_index: dict[str, int]
    ) -> list[tuple[int, float]]:
        """Project FTS hits to scoped-lens indices, preserving FTS order."""
        ranked: list[tuple[int, float]] = []
        for rank, h in enumerate(hits):
            if h.id in scoped:
                ranked.append((id_index[h.id], 1.0 / (rank + 1)))
        return ranked

    async def _embedding_margins(
        self, cand: ClaimCandidate, scoped: dict[str, MemoryItem]
    ) -> dict[str, float]:
        query = f"{cand.canonical_subject} {cand.content}".strip()
        lens_texts = [
            f"{le.lens_name or ''} {le.lens_page or le.lens_criterion or ''}".strip()
            for le in scoped.values()
        ]
        if not lens_texts:
            return {}
        try:
            q = await self.embed.embed_one(query)
            mat = await self.embed.embed(lens_texts)
        except Exception as e:
            _logger.warning("reconcile: embedding recall failed: %s", e)
            return {}
        sims = (mat @ q).tolist()  # both L2-normalized -> cosine
        return {le.id: float(s) for le, s in zip(scoped.values(), sims)}

    async def _resolve_subject_llm(
        self, cand: ClaimCandidate, scope: Scope, cands: list[MemoryItem]
    ) -> tuple[MemoryItem, bool]:
        cards = "\n".join(
            f"- lens_id={le.id} name={le.lens_name!r} "
            f"criterion={(le.lens_criterion or '')!r} "
            f"gist={(le.lens_page or '')[:200]!r}"
            for le in cands
        )
        surfaces = ", ".join(cand.subject_surfaces) if cand.subject_surfaces else ""
        user = (
            f"SUBJECT: {cand.canonical_subject!r}\n"
            f"SURFACES: {surfaces!r}\n"
            f"CONTENT: {cand.content!r}\n\n"
            f"CANDIDATES:\n{cards}"
        )
        resp = await self.cheap_llm.completion(
            messages=[
                {"role": "system", "content": SUBJECT_RESOLUTION_SYSTEM},
                {"role": "user", "content": user},
            ],
            model=self.cheap_model,
            response_format=SubjectResolution,
            temperature=0.0,
        )
        decision = _parse(resp, SubjectResolution)
        valid = {le.id: le for le in cands}
        if decision.decision.upper() == "MATCH" and decision.lens_id in valid:
            matched = valid[decision.lens_id]
            if decision.alias_to_add:
                await self._append_alias(matched, decision.alias_to_add)
            return matched, False
        # NEW, or a hallucinated lens_id -> bias to NEW (self-correcting; repairable by lint).
        return await self._mint_subject(cand.canonical_subject, scope), True

    async def _mint_subject(self, subject: str, scope: Scope) -> MemoryItem:
        lens = MemoryItem(
            id=uuid.uuid4().hex,
            kind=Kind.LENS,
            content=subject,
            scope=scope,
            provenance=Provenance.INDUCED,
            lens_kind="entity",
            lens_name=subject,
            lens_criterion=f"this item is about {subject}",
            lens_exclusive=True,
        )
        return await self.store.create_item(lens)

    async def _append_alias(self, lens: MemoryItem, alias: str) -> None:
        existing = lens.lens_criterion or ""
        if alias.lower() in existing.lower():
            return
        merged = MemoryItem(
            id=uuid.uuid4().hex,
            kind=Kind.LENS,
            content=lens.content,
            scope=lens.scope,
            provenance=lens.provenance,
            valid_from=lens.valid_from,
            source_refs=lens.source_refs,
            corroboration=lens.corroboration,
            feedback=lens.feedback,
            lens_name=lens.lens_name,
            lens_criterion=f"{existing}; also known as {alias}".strip("; "),
            lens_kind=lens.lens_kind,
            lens_page=lens.lens_page,
            lens_detail_level=lens.lens_detail_level,
            lens_exclusive=lens.lens_exclusive,
        )
        await self.store.supersede(old_id=lens.id, new_item=merged)

    # --- Phase 3 + 4 -------------------------------------------------

    async def _reconcile_group(
        self,
        lens_id: str,
        subject: MemoryItem | None,
        idxs: list[int],
        candidates: list[ClaimCandidate],
        results: list[ReconcileResult | None],
        scope: Scope,
    ) -> None:
        # Phase 3: profile recall — the subject's active MEMBER_OF claims.
        profile = await self._recall_profile(lens_id, idxs, candidates)

        # Phase 4: one batch call per subject.
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
            await self._apply(row, cand, lens_id, target, res)

    async def _recall_profile(
        self, lens_id: str, idxs: list[int], candidates: list[ClaimCandidate]
    ) -> list[MemoryItem]:
        edges = await self.store.list_edges(lens_id, direction="to", role=EdgeRole.MEMBER_OF)
        members: list[MemoryItem] = []
        for e in edges:
            m = await self.store.get(e.child_id)
            if m is not None and m.status is Status.ACTIVE and m.kind is Kind.CLAIM:
                members.append(m)
        if len(members) <= PROFILE_MEMBER_CAP:
            return members
        # Large-subject guard: topic-slice members by relevance to this group's claims.
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
        subject: MemoryItem | None,
        profile: list[MemoryItem],
        idxs: list[int],
        candidates: list[ClaimCandidate],
    ) -> tuple[list[ReconcileRow], set[int]]:
        if not profile:
            # No existing claims -> every new claim is an ADD; no LLM needed.
            return [ReconcileRow(claim_index=i, op="add") for i in range(len(idxs))], set()

        page = (subject.lens_page or subject.lens_criterion or "") if subject else ""
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
            f"SUBJECT PROFILE: {page[:600]!r}\n\n"
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
            temperature=0.0,
        )
        parsed = _parse(resp, BatchReconcile)
        rows = self._validate_rows(parsed.rows, len(idxs), len(profile))

        # Escalate contested / high-trust-target rows to the strong model.
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
        # Any new claim the model skipped defaults to ADD.
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
        subject: MemoryItem | None,
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
                temperature=0.0,
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
        lens_id: str,
        target: MemoryItem | None,
        res: ReconcileResult,
    ) -> None:
        op = row.op
        # Provenance guard: a user-authored fact never NOOPs against a weaker claim.
        if (
            op == "noop"
            and target is not None
            and _PROVENANCE_ORD[cand.provenance] > _PROVENANCE_ORD[target.provenance]
        ):
            op = "update"

        if op == "add" or target is None:
            await self._do_add(cand, lens_id, res)
        elif op == "update":
            await self._do_update(row, cand, lens_id, target, res)
        elif op == "contradict":
            await self._do_contradict(row, cand, lens_id, target, res)
        elif op == "noop":
            await self._do_noop(cand, target, res)
        else:
            await self._do_add(cand, lens_id, res)

    def _new_claim(self, content: str, cand: ClaimCandidate) -> MemoryItem:
        return MemoryItem(
            id=uuid.uuid4().hex,
            kind=Kind.CLAIM,
            content=content,
            scope=cand.scope,
            provenance=cand.provenance,
            valid_from=now_iso(),
            source_refs=list(cand.source_refs),
        )

    async def _do_add(self, cand: ClaimCandidate, lens_id: str, res: ReconcileResult) -> None:
        claim = self._new_claim(cand.content, cand)
        await self.store.create_item(claim)
        await self.store.add_edge(
            MemoryEdge(child_id=claim.id, parent_id=lens_id, role=EdgeRole.MEMBER_OF)
        )
        res.op = Op.ADD
        res.written_id = claim.id

    async def _do_update(
        self,
        row: ReconcileRow,
        cand: ClaimCandidate,
        lens_id: str,
        target: MemoryItem,
        res: ReconcileResult,
    ) -> None:
        successor = self._new_claim(row.merged_text or cand.content, cand)
        # Successor unions the predecessor's evidence so re-grounding stays possible.
        successor.source_refs = self._union_refs(target.source_refs, cand.source_refs)
        await self.store.supersede(old_id=target.id, new_item=successor)
        await self.store.add_edge(
            MemoryEdge(child_id=successor.id, parent_id=lens_id, role=EdgeRole.MEMBER_OF)
        )
        res.op = Op.UPDATE
        res.written_id = successor.id
        res.target_claim_id = target.id

    async def _do_contradict(
        self,
        row: ReconcileRow,
        cand: ClaimCandidate,
        lens_id: str,
        target: MemoryItem,
        res: ReconcileResult,
    ) -> None:
        successor = self._new_claim(row.merged_text or cand.content, cand)
        successor.source_refs = list(cand.source_refs)
        await self.store.supersede(old_id=target.id, new_item=successor)
        await self.store.add_edge(
            MemoryEdge(child_id=successor.id, parent_id=target.id, role=EdgeRole.CONTRADICTS)
        )
        await self.store.add_edge(
            MemoryEdge(child_id=successor.id, parent_id=lens_id, role=EdgeRole.MEMBER_OF)
        )
        res.op = Op.CONTRADICT
        res.written_id = successor.id
        res.target_claim_id = target.id

    async def _do_noop(
        self, cand: ClaimCandidate, target: MemoryItem, res: ReconcileResult
    ) -> None:
        await self.store.bump_corroboration(target.id)
        # User assertion confirming an inferred claim stamps CONFIRMED.
        if (
            cand.provenance is Provenance.USER_AUTHORED
            and target.provenance is Provenance.INFERRED
        ):
            await self.store.set_feedback(target.id, Feedback.CONFIRMED)
        res.op = Op.NOOP
        res.target_claim_id = target.id
        # NOTE: cannot freshen last_relevant_at — no store setter (CONTRACTS §11).

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
