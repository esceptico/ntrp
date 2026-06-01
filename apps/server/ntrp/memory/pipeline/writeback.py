"""LensWriteBack — anchored page edits -> store calls (claims + registry).

The user edits the rendered lens page; the tool/UI emits discrete `PageEditOp`s
keyed by `claim_id` (from the block ANCHOR diff, never from reparsing prose). A
lens is a VIEW: it has no member_of edges, so membership changes are projection
ops, not edge writes.

  ACCEPT(id)            -> set_feedback(CONFIRMED) + bump_corroboration
  EDIT(id, new_text)    -> supersede(old=id, successor); union evidence. The
                           successor keeps the same canonical_subject; membership
                           recomputes on the next projection.
  REJECT(id)            -> append a lens-scoped negative-example to lenses.page +
                           null the page + invalidate the membership cache. The
                           membership judge reads the negative example as worked
                           text; re-validate-at-read drops the claim from the
                           projection. The claim survives globally.
  ADD(new_text)         -> routed through the WriteSeam (the ONE prose->claim path);
                           reconcile attaches by subject; membership picks it up.
  EDIT_CRITERION(text)  -> update the registry criterion + null page + invalidate
                           cache; membership re-derives at next read.

Apply order is fixed (ACCEPT -> EDIT -> REJECT -> ADD -> EDIT_CRITERION). A stale
anchor is a no-op + `rejected`, never a silent write to a dead row.
"""

import uuid

from ntrp.logging import get_logger
from ntrp.memory.models import (
    Feedback,
    LensRow,
    MemoryItem,
    Provenance,
    SourceRef,
    Status,
    now_iso,
)
from ntrp.memory.pipeline.project import LensProjector
from ntrp.memory.pipeline.types import (
    PageEditKind,
    PageEditOp,
    WriteBackResult,
)
from ntrp.memory.store import MemoryStore

_logger = get_logger(__name__)

# The lens-scoped negative-example section appended to the lens page on REJECT.
# The membership judge reads everything under this header as worked examples; it is
# LLM-read prose, NEVER a keyword/stopword filter and NEVER a gate.
NEGATIVE_EXAMPLES_HEADER = "## Not in this lens (user-rejected)"

_APPLY_ORDER = {
    PageEditKind.ACCEPT: 0,
    PageEditKind.EDIT: 1,
    PageEditKind.REJECT: 2,
    PageEditKind.ADD: 3,
    PageEditKind.EDIT_CRITERION: 4,
}


class LensWriteBack:
    def __init__(self, store: MemoryStore, write_seam, membership, projector: LensProjector):
        self.store = store
        self.write_seam = write_seam
        self.membership = membership
        self.projector = projector

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
        if op.kind is PageEditKind.EDIT:
            return await self._edit(op)
        if op.kind is PageEditKind.REJECT:
            return await self._reject(lens, op)
        if op.kind is PageEditKind.ADD:
            return await self._add(lens, op)
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
        """Append a lens-scoped negative example + null the page + invalidate cache.
        Re-validate-at-read renders the claim `out`. The claim survives globally."""
        m = await self.store.get(op.claim_id) if op.claim_id else None
        if m is None:
            return False, "claim moved; re-open the page", False
        await self._append_negative_example(lens, m.content)
        await self.store.invalidate_lens_membership(lens.id)
        return True, m.id, True

    async def _add(self, lens: LensRow, op: PageEditOp) -> tuple[bool, str, bool]:
        if not op.new_text or not op.new_text.strip():
            return False, "add with empty text", False
        from ntrp.memory.pipeline.write import WriteRequest

        outcome = await self.write_seam.admit_and_write(
            WriteRequest(
                content=op.new_text.strip(),
                scope=lens.scope,
                provenance=Provenance.USER_AUTHORED,
                source_refs=[SourceRef(kind="lens_writeback", ref=lens.id)],
                bypass_admit=True,
            )
        )
        if not outcome.written:
            return False, f"add not written: {outcome.reason}", False
        # New claim may match this lens; drop the cached page so it re-derives.
        await self.store.update_lens(lens.id, page=None)
        return True, outcome.item_id or "", True

    async def _edit_criterion(self, lens: LensRow, op: PageEditOp) -> tuple[bool, str, bool]:
        if not op.new_text or not op.new_text.strip():
            return False, "criterion edit with empty text", False
        await self.store.invalidate_lens_membership(lens.id)
        await self.store.update_lens(lens.id, criterion=op.new_text.strip(), page=None)
        return True, lens.id, True

    # --- lens-page helper (registry UPDATE; not a memory write) ------

    async def _append_negative_example(self, lens: LensRow, content: str) -> None:
        page = lens.page or ""
        if NEGATIVE_EXAMPLES_HEADER not in page:
            page = f"{page.rstrip()}\n\n{NEGATIVE_EXAMPLES_HEADER}\n".lstrip("\n")
        marker = f"- {content}"
        if marker in page:
            return
        page = f"{page.rstrip()}\n{marker}\n"
        await self.store.update_lens(lens.id, page=page)
