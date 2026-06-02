"""LensWriteBack — anchored page edits -> store calls (claims + registry).

The user edits the rendered lens page; the tool/UI emits discrete `PageEditOp`s
keyed by `claim_id` (from the block ANCHOR diff, never from reparsing prose). A
lens is a VIEW: it has no member_of edges, so membership changes are projection
ops, not edge writes.

  ACCEPT(id)            -> set_feedback(CONFIRMED) + bump_corroboration
  INCLUDE(id)           -> record a durable lens_inclusion, write an IN cache row,
                           null the page, and force re-derive.
  EDIT(id, new_text)    -> supersede(old=id, successor); union evidence. The
                           successor keeps the same canonical_subject; membership
                           recomputes on the next projection.
  REJECT(id)            -> record a durable lens_rejection, null the page, and
                           invalidate the membership cache. The claim survives
                           globally.
  EDIT_CRITERION(text)  -> update the registry criterion + null page + invalidate
                           cache; membership re-derives at next read.

Apply order is fixed (ACCEPT -> INCLUDE -> EDIT -> REJECT -> EDIT_CRITERION). A
stale anchor is a no-op + `rejected`, never a silent write to a dead row.
"""

import uuid

from ntrp.logging import get_logger
from ntrp.memory.models import (
    Feedback,
    LensRow,
    MembershipDecision,
    MembershipVerdict,
    MemoryItem,
    Provenance,
    Status,
    now_iso,
)
from ntrp.memory.pipeline.types import (
    PageEditKind,
    PageEditOp,
    WriteBackResult,
)
from ntrp.memory.store import MemoryStore

_logger = get_logger(__name__)

_APPLY_ORDER = {
    PageEditKind.ACCEPT: 0,
    PageEditKind.INCLUDE: 1,
    PageEditKind.EDIT: 2,
    PageEditKind.REJECT: 3,
    PageEditKind.EDIT_CRITERION: 4,
}


class LensWriteBack:
    def __init__(self, store: MemoryStore):
        self.store = store

    async def apply(self, lens_id: str, ops: list[PageEditOp]) -> WriteBackResult:
        lens = await self.store.get_lens(lens_id)
        applied: list[tuple[PageEditKind, str]] = []
        rejected: list[tuple[PageEditOp, str]] = []

        if lens is None:
            return WriteBackResult(
                applied=[],
                rejected=[(op, "lens not found") for op in ops],
                rederive_triggered=False,
            )

        rederive = False
        for op in sorted(ops, key=lambda o: _APPLY_ORDER.get(o.kind, 99)):
            try:
                ok, note, dirty = await self._apply_one(lens, op)
            except Exception as e:
                _logger.warning("lens writeback: op %s failed: %s", op.kind, e)
                rejected.append((op, f"failed: {e}"))
                continue
            if ok:
                applied.append((op.kind, note))
                rederive = rederive or dirty
            else:
                rejected.append((op, note))

        return WriteBackResult(applied=applied, rejected=rejected, rederive_triggered=rederive)

    # --- one op -> one store primitive -------------------------------

    async def _apply_one(self, lens: LensRow, op: PageEditOp) -> tuple[bool, str, bool]:
        if op.kind is PageEditKind.ACCEPT:
            return await self._accept(op)
        if op.kind is PageEditKind.INCLUDE:
            return await self._include(lens, op)
        if op.kind is PageEditKind.EDIT:
            return await self._edit(op)
        if op.kind is PageEditKind.REJECT:
            return await self._reject(lens, op)
        if op.kind is PageEditKind.EDIT_CRITERION:
            return await self._edit_criterion(lens, op)
        return False, f"unknown op kind {op.kind}", False

    async def _live_claim(self, claim_id: str | None) -> MemoryItem | None:
        if not claim_id:
            return None
        m = await self.store.get(claim_id)
        if m is None or m.status is not Status.ACTIVE:
            return None
        return m

    async def _accept(self, op: PageEditOp) -> tuple[bool, str, bool]:
        m = await self._live_claim(op.claim_id)
        if m is None:
            return False, "claim moved; re-open the page", False
        await self.store.set_feedback(m.id, Feedback.CONFIRMED)
        await self.store.bump_corroboration(m.id)
        return True, m.id, False

    async def _include(self, lens: LensRow, op: PageEditOp) -> tuple[bool, str, bool]:
        m = await self._live_claim(op.claim_id)
        if m is None:
            return False, "claim moved; re-open the page", False
        await self.store.add_inclusion(lens.id, m.id)
        await self.store.put_membership(
            [
                MembershipVerdict(
                    lens_id=lens.id,
                    claim_id=m.id,
                    decision=MembershipDecision.IN,
                    rationale="explicitly included by user",
                )
            ]
        )
        await self.store.update_lens(lens.id, page=None)
        return True, m.id, True

    async def _edit(self, op: PageEditOp) -> tuple[bool, str, bool]:
        m = await self._live_claim(op.claim_id)
        if m is None:
            return False, "claim moved; re-open the page", False
        if not op.new_text or not op.new_text.strip():
            return False, "edit with empty text", False
        successor = MemoryItem(
            id=uuid.uuid4().hex,
            content=op.new_text.strip(),
            canonical_subject=m.canonical_subject,
            scope=m.scope,
            provenance=Provenance.USER_AUTHORED,
            valid_from=now_iso(),
            source_refs=list(m.source_refs),
            corroboration=m.corroboration,
            feedback=Feedback.CORRECTED,
        )
        await self.store.supersede(old_id=m.id, new_item=successor)
        return True, successor.id, True

    async def _reject(self, lens: LensRow, op: PageEditOp) -> tuple[bool, str, bool]:
        """Durably reject the claim from this lens, then force a re-derive.

        Records a lens_rejection (survives cache purges; membership keeps it OUT),
        nulls the cached page so the next read re-derives without it, and clears the
        membership cache. The claim survives globally — it is only removed from THIS
        view. (The previous version appended a 'negative example' to the page but
        left the page non-None, so the read served the stale page and the rejected
        claim kept re-rendering.)"""
        m = await self.store.get(op.claim_id) if op.claim_id else None
        if m is None:
            return False, "claim moved; re-open the page", False
        await self.store.add_rejection(lens.id, m.id)
        await self.store.update_lens(lens.id, page=None)
        await self.store.invalidate_lens_membership(lens.id)
        return True, m.id, True

    async def _edit_criterion(self, lens: LensRow, op: PageEditOp) -> tuple[bool, str, bool]:
        if not op.new_text or not op.new_text.strip():
            return False, "criterion edit with empty text", False
        # Write the criterion file FIRST, invalidate LAST (mirrors
        # registry.edit_criterion). Invalidating first would let a concurrent
        # refresh_lens_cache repopulate stale verdicts before updated_at bumps,
        # defeating refresh's mid-pass guard.
        await self.store.update_lens(lens.id, criterion=op.new_text.strip(), page=None)
        await self.store.invalidate_lens_membership(lens.id)
        return True, lens.id, True
