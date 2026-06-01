"""LensRegistry — the lens VIEW layer (registry CRUD + computed projection).

A lens is a VIEW, not memory: a named, criterion-defined projection over claims.
This module owns the registry lifecycle (create / list / edit-criterion / delete /
split / merge) over the separate `lenses` table. It NEVER writes to `memory_items`
and NEVER writes an edge. Creating or deleting a lens touches zero claims.

Membership is a COMPUTED PROJECTION: the criterion is run over candidate claims by
the LLM judge (LensMembership), cached in `lens_membership_cache`. The cache is not
graph truth — drop it and projection just recomputes. Criterion edits null the page
and invalidate the cache so membership re-derives on next read.

The absolute ban (§0) holds structurally: this module makes NO membership decision.
Every membership question is delegated to LensMembership (the LLM judge). No
keyword/regex/threshold gate decides anything here.
"""

import uuid
from typing import Protocol

from ntrp.logging import get_logger
from ntrp.memory.models import (
    LensDetailLevel,
    LensProvenance,
    LensRow,
    Scope,
)
from ntrp.memory.pipeline.types import BackfillReport, CoverageAdvisory
from ntrp.memory.store import MemoryStore

_logger = get_logger(__name__)


class _Membership(Protocol):
    """The slice of LensMembership the registry consults for advisory coverage.

    The registry never decides membership; coverage is a pure COUNT advisory the
    membership component computes. `refresh_lens_cache` is the lazy backfill the
    projector triggers — exposed here so split/merge can warm the cache.
    """

    async def coverage(self, lens_id: str, scope: Scope) -> CoverageAdvisory: ...

    async def refresh_lens_cache(self, lens_id: str) -> BackfillReport: ...


class LensRegistry:
    def __init__(self, store: MemoryStore, membership: _Membership, projector=None):
        self.store = store
        self.membership = membership
        # The projector is the read surface the `lens` tool's `show` action uses
        # (registry CRUD + projected page behind one service slot). Set by runtime.
        self.projector = projector

    # --- create (touches zero claims) -------------------------------

    async def create_lens(
        self,
        name: str,
        criterion: str,
        scope: Scope,
        *,
        detail_level: LensDetailLevel = LensDetailLevel.STRUCTURED,
        provenance: LensProvenance = LensProvenance.USER_AUTHORED,
    ) -> LensRow:
        """Insert one registry row. NO backfill, NO edges, NO claim writes (C7).

        The page is None; membership/page are computed lazily on first projection.
        """
        lens = LensRow(
            id=uuid.uuid4().hex,
            name=name,
            criterion=criterion,
            scope=scope,
            detail_level=detail_level,
            provenance=provenance,
        )
        await self.store.create_lens_row(lens)
        _logger.info("lens created %s name=%r (view; zero claims touched)", lens.id, name)
        return lens

    # --- list (with advisory coverage) ------------------------------

    async def list_lenses(self, scope: Scope) -> list[tuple[LensRow, CoverageAdvisory]]:
        lenses = await self.store.list_lenses(scope=scope)
        out: list[tuple[LensRow, CoverageAdvisory]] = []
        for lens in lenses:
            advisory = await self.membership.coverage(lens.id, lens.scope)
            out.append((lens, advisory))
        return out

    # --- edit criterion (re-derive at next read) --------------------

    async def edit_criterion(self, lens_id: str, new_criterion: str) -> LensRow:
        """Rewrite the criterion in place + invalidate the projection.

        UPDATE the registry row (criterion + page=NULL) and drop the membership
        cache. Membership re-derives on the next projection. Zero claim impact.
        """
        lens = await self.store.get_lens(lens_id)
        if lens is None:
            raise ValueError(f"not a lens: {lens_id}")
        await self.store.invalidate_lens_membership(lens_id)
        updated = await self.store.update_lens(lens_id, criterion=new_criterion, page=None)
        assert updated is not None
        return updated

    # --- delete (the view; never the claims) ------------------------

    async def delete_lens(self, lens_id: str) -> bool:
        """Drop the registry row + cache. Claims are untouched (C7)."""
        return await self.store.delete_lens(lens_id)

    # --- split / merge (pure registry ops + cache invalidation) -----

    async def split_lens(
        self,
        lens_id: str,
        into: list[tuple[str, str]],
        *,
        archive_parent: bool = True,
    ) -> list[LensRow]:
        """Split into narrower child views: create N registry rows, optionally
        delete the parent. Re-points nothing; membership re-derives per child."""
        parent = await self.store.get_lens(lens_id)
        if parent is None:
            raise ValueError(f"not a lens: {lens_id}")
        if not into:
            raise ValueError("split requires at least one child (name, criterion)")
        children: list[LensRow] = []
        for name, criterion in into:
            child = await self.create_lens(name, criterion, parent.scope)
            children.append(child)
        if archive_parent:
            await self.store.delete_lens(parent.id)
        return children

    async def merge_lenses(
        self, lens_ids: list[str], name: str, criterion: str
    ) -> LensRow:
        """Merge into one union view: create the union row, delete the inputs.
        Re-points nothing; the union re-derives its members from the criterion."""
        if len(lens_ids) < 2:
            raise ValueError("merge requires at least two lenses")
        inputs: list[LensRow] = []
        for lid in lens_ids:
            lens = await self.store.get_lens(lid)
            if lens is None:
                raise ValueError(f"not a lens: {lid}")
            inputs.append(lens)
        scope = inputs[0].scope
        union = await self.create_lens(name, criterion, scope)
        for lens in inputs:
            await self.store.delete_lens(lens.id)
        return union
