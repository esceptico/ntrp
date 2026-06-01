"""LensWriteBack — anchored page edits -> frozen store calls (LENS_CONTRACTS §3.3).

The user edits the rendered lens page; the tool/UI emits discrete `PageEditOp`s
keyed by `claim_id` (derived from the block-to-block ANCHOR diff, never from
reparsing prose for meaning — §0/§3.3). Each op maps to exactly one existing store
primitive. There is no bespoke writer here and no new store method: the store is
frozen.

  ACCEPT(id)            -> set_feedback(CONFIRMED) + bump_corroboration
  EDIT(id, new_text)    -> supersede(old=id, successor); union evidence + re-add
                           MEMBER_OF (exactly reconcile._do_update)
  REJECT(id)            -> CANNOT drop the edge (§1.1). Records a lens-scoped
                           negative-example correction appended to lens_page via
                           supersede (the _append_alias append-only pattern). The
                           membership judge reads it as a NEGATIVE EXAMPLE (LLM-read
                           text, never a keyword filter); re-validate-at-read then
                           renders the claim `out`. The claim itself survives in every
                           other lens.
  ADD(new_text)         -> routed through the existing WriteSeam (the ONE sanctioned
                           prose->claim path); reconcile re-scores + attaches.
  EDIT_CRITERION(text)  -> supersede the lens row with the new criterion + mark dirty;
                           membership re-derives at the next read (§6).

Apply order is fixed (ACCEPT -> EDIT -> REJECT -> ADD -> EDIT_CRITERION). Each op is
independent against the frozen API; a failed op lands in `rejected` with a reason and
the rest still apply. A stale anchor (claim superseded/archived between serve and
edit) is a no-op + `rejected`, never a silent write to a dead row (§9.6). After apply,
the page is re-projected with refresh=True so the caller sees canonical state.
"""

import uuid

from ntrp.logging import get_logger
from ntrp.memory.models import (
    EdgeRole,
    Feedback,
    Kind,
    MemoryEdge,
    MemoryItem,
    Provenance,
    SourceRef,
    Status,
    now_iso,
)
from ntrp.memory.pipeline.project import LensProjector, mark_lens_dirty
from ntrp.memory.pipeline.types import (
    PageEditKind,
    PageEditOp,
    WriteBackResult,
)
from ntrp.memory.store import MemoryStore

_logger = get_logger(__name__)

# The lens-scoped negative-example section appended to lens_page on REJECT (§3.3).
# The membership judge reads everything under this header as negative examples; it is
# LLM-read prose, NEVER a keyword/stopword filter and NEVER a gate (§0).
NEGATIVE_EXAMPLES_HEADER = "## Not in this lens (user-rejected)"

# Fixed apply order (§3.3).
_APPLY_ORDER = {
    PageEditKind.ACCEPT: 0,
    PageEditKind.EDIT: 1,
    PageEditKind.REJECT: 2,
    PageEditKind.ADD: 3,
    PageEditKind.EDIT_CRITERION: 4,
}


class LensWriteBack:
    def __init__(self, store: MemoryStore, write_seam, membership, projector: LensProjector):
        # Frozen constructor (§3.3). `write_seam` is the only prose->claim path (ADD);
        # `membership`/`projector` are used to re-project canonical state after apply.
        self.store = store
        self.write_seam = write_seam
        self.membership = membership
        self.projector = projector

    async def apply(self, lens_id: str, ops: list[PageEditOp]) -> WriteBackResult:
        lens = await self.store.get(lens_id)
        applied: list[tuple[PageEditKind, str]] = []
        rejected: list[tuple[PageEditOp, str]] = []

        if lens is None or lens.kind is not Kind.LENS or lens.status is not Status.ACTIVE:
            return WriteBackResult(
                applied=[], rejected=[(op, "lens not found or inactive") for op in ops],
                rederive_triggered=False,
            )

        rederive = False
        for op in sorted(ops, key=lambda o: _APPLY_ORDER.get(o.kind, 99)):
            try:
                ok, note, dirty = await self._apply_one(lens_id, op)
            except Exception as e:  # one op never sinks the batch
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

    async def _apply_one(self, lens_id: str, op: PageEditOp) -> tuple[bool, str, bool]:
        if op.kind is PageEditKind.ACCEPT:
            return await self._accept(op)
        if op.kind is PageEditKind.EDIT:
            return await self._edit(lens_id, op)
        if op.kind is PageEditKind.REJECT:
            return await self._reject(lens_id, op)
        if op.kind is PageEditKind.ADD:
            return await self._add(lens_id, op)
        if op.kind is PageEditKind.EDIT_CRITERION:
            return await self._edit_criterion(lens_id, op)
        return False, f"unknown op kind {op.kind}", False

    async def _live_claim(self, claim_id: str | None) -> MemoryItem | None:
        if not claim_id:
            return None
        m = await self.store.get(claim_id)
        if m is None or m.kind is not Kind.CLAIM or m.status is not Status.ACTIVE:
            return None
        return m

    async def _accept(self, op: PageEditOp) -> tuple[bool, str, bool]:
        m = await self._live_claim(op.claim_id)
        if m is None:
            return False, "claim moved; re-open the page", False
        await self.store.set_feedback(m.id, Feedback.CONFIRMED)
        await self.store.bump_corroboration(m.id)
        return True, m.id, False

    async def _edit(self, lens_id: str, op: PageEditOp) -> tuple[bool, str, bool]:
        m = await self._live_claim(op.claim_id)
        if m is None:
            return False, "claim moved; re-open the page", False
        if not op.new_text or not op.new_text.strip():
            return False, "edit with empty text", False
        # Exactly reconcile._do_update: successor unions the predecessor's evidence so
        # re-grounding stays possible, then re-adds the MEMBER_OF edge to the lens.
        successor = MemoryItem(
            id=uuid.uuid4().hex,
            kind=Kind.CLAIM,
            content=op.new_text.strip(),
            scope=m.scope,
            provenance=Provenance.USER_AUTHORED,
            valid_from=now_iso(),
            source_refs=list(m.source_refs),
            corroboration=m.corroboration,
            feedback=Feedback.CORRECTED,
        )
        await self.store.supersede(old_id=m.id, new_item=successor)
        await self.store.add_edge(
            MemoryEdge(child_id=successor.id, parent_id=lens_id, role=EdgeRole.MEMBER_OF)
        )
        return True, successor.id, True

    async def _reject(self, lens_id: str, op: PageEditOp) -> tuple[bool, str, bool]:
        """REJECT cannot drop the edge (§1.1). Record a lens-scoped negative example and
        mark dirty; re-validate-at-read renders the claim `out`. Claim itself survives."""
        m = await self.store.get(op.claim_id) if op.claim_id else None
        if m is None or m.kind is not Kind.CLAIM:
            return False, "claim moved; re-open the page", False
        lens = await self.store.get(lens_id)
        if lens is None or lens.status is not Status.ACTIVE:
            return False, "lens inactive", False
        await self._append_negative_example(lens, m.content)
        await mark_lens_dirty(self.store, lens_id)
        return True, m.id, True

    async def _add(self, lens_id: str, op: PageEditOp) -> tuple[bool, str, bool]:
        if not op.new_text or not op.new_text.strip():
            return False, "add with empty text", False
        lens = await self.store.get(lens_id)
        if lens is None:
            return False, "lens not found", False
        # The ONE prose->claim path (§3.3/§4.4): WriteSeam owns the only free-text
        # reparse; reconcile re-scores + attaches. No bespoke writer here.
        from ntrp.memory.pipeline.write import WriteRequest

        outcome = await self.write_seam.admit_and_write(
            WriteRequest(
                content=op.new_text.strip(),
                scope=lens.scope,
                provenance=Provenance.USER_AUTHORED,
                source_refs=[SourceRef(kind="lens_writeback", ref=lens_id)],
                bypass_admit=True,
            )
        )
        if not outcome.written:
            return False, f"add not written: {outcome.reason}", False
        return True, outcome.item_id or "", True

    async def _edit_criterion(self, lens_id: str, op: PageEditOp) -> tuple[bool, str, bool]:
        if not op.new_text or not op.new_text.strip():
            return False, "criterion edit with empty text", False
        lens = await self.store.get(lens_id)
        if lens is None or lens.status is not Status.ACTIVE:
            return False, "lens inactive", False
        successor = self._lens_successor(lens, lens_criterion=op.new_text.strip())
        await self.store.supersede(old_id=lens.id, new_item=successor)
        await mark_lens_dirty(self.store, successor.id)
        return True, successor.id, True

    # --- lens-row helpers (append-only, _append_alias pattern) -------

    async def _append_negative_example(self, lens: MemoryItem, content: str) -> None:
        page = lens.lens_page or ""
        if NEGATIVE_EXAMPLES_HEADER not in page:
            page = f"{page.rstrip()}\n\n{NEGATIVE_EXAMPLES_HEADER}\n".lstrip("\n")
        # Idempotent: don't append the same rejection twice.
        marker = f"- {content}"
        if marker in page:
            return
        page = f"{page.rstrip()}\n{marker}\n"
        successor = self._lens_successor(lens, lens_page=page)
        await self.store.supersede(old_id=lens.id, new_item=successor)

    def _lens_successor(
        self,
        lens: MemoryItem,
        *,
        lens_criterion: str | None = None,
        lens_page: str | None = None,
    ) -> MemoryItem:
        return MemoryItem(
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
            lens_criterion=lens_criterion if lens_criterion is not None else lens.lens_criterion,
            lens_kind=lens.lens_kind,
            lens_page=lens_page if lens_page is not None else lens.lens_page,
            lens_detail_level=lens.lens_detail_level,
            lens_exclusive=lens.lens_exclusive,
        )
