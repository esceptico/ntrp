"""Retrieval-by-lens — Mode-2 egress, read-only.

A lens is a VIEW over claims. When a recall goal names a lens (or chat scope *is*
a lens), the cheapest path is to inject that lens's cached `page` directly: it is
pre-compressed and query-shaped. When the page is missing/stale or the goal is
narrower, fall back to hybrid retrieve but pre-filter the candidate pool to the
lens's `in`-decision member claims (from the membership cache).

The absolute ban governs this file: nothing here gates a membership outcome. Lens
resolution uses FTS + exact-name match (recall channels that ORDER, never decide);
member pre-filtering is a categorical predicate (the claim is `in` the cache or it
is not), never a similarity/length cutoff on meaning.

This component never scores membership, never writes, never calls the strong model.
Re-validating stale members is the projector's job; the expander consumes what
membership/projector already cached.
"""

from dataclasses import dataclass

from ntrp.embedder import Embedder
from ntrp.logging import get_logger
from ntrp.memory.models import LensRow, MembershipDecision, Scope, Status

_logger = get_logger(__name__)

LENS_RESOLVE_K = 8


@dataclass
class LensExpansion:
    """Result of expanding a recall goal/hint against the active lens registry.

    `page` is the cached lens page to inject verbatim when present (the 0-LLM fast
    path). `member_ids` is the active `in`-decision member set used to pre-filter
    the hybrid fallback pool. `lens` is None when no lens resolved.
    """

    lens: LensRow | None
    page: str | None
    member_ids: frozenset[str]


class LensExpander:
    """Read-only lens resolution + member pre-filtering for retrieve.

    Constructed with `(store, embed)` only — no LLM client. Lens expansion is pure
    store reads + an FTS recall channel; any judgment lives in the projector.
    """

    def __init__(self, store, embed: Embedder):
        self.store = store
        self.embed = embed

    async def expand(
        self, *, hint: str | None, goal: str, scopes: list[Scope], valid_at: str | None = None
    ) -> LensExpansion | None:
        """Resolve a lens for this recall and report its page + member set.

        Returns None when no lens resolves. Resolution prefers the explicit `hint`
        (a lens name or id); absent a hint we do NOT guess from the goal prose.
        """
        if not hint:
            return None

        lens = await self._resolve(hint, scopes)
        if lens is None:
            return None

        member_ids = await self._active_member_ids(lens)
        page = (lens.page or "").strip() or None
        return LensExpansion(lens=lens, page=page, member_ids=frozenset(member_ids))

    # --- lens resolution (recall channels — order, never gate) -------

    async def _resolve(self, hint: str, scopes: list[Scope]) -> LensRow | None:
        """Resolve a hint to one active lens within the requested scopes.

        Channel A (exact): the hint is a lens id or an exact `name`.
        Channel B (recall): FTS over lens name/criterion/page; the first scoped
        active match wins. The categorical scope/status filter is the only exclusion.
        """
        scoped = await self._scoped_lenses(scopes)
        if not scoped:
            return None

        by_id = {le.id: le for le in scoped}
        if hint in by_id:
            return by_id[hint]
        hint_norm = hint.strip().casefold()
        for le in scoped:
            if le.name.strip().casefold() == hint_norm:
                return le

        if not self.store.has_fts:
            return None
        hits = await self.store.search_lenses(hint, limit=LENS_RESOLVE_K)
        for hit in hits:
            if hit.id in by_id:
                return by_id[hit.id]
        return None

    async def _scoped_lenses(self, scopes: list[Scope]) -> list[LensRow]:
        scoped: dict[str, LensRow] = {}
        for scope in scopes:
            for le in await self.store.list_lenses(scope=scope):
                scoped[le.id] = le
        return list(scoped.values())

    # --- member pre-filter (categorical predicate) -------------------

    async def _active_member_ids(self, lens: LensRow) -> set[str]:
        """Active `in`-decision member claims of the lens, from the membership cache.

        A categorical existence predicate (the claim is `in` the cache and still
        active), identical in spirit to retrieve's scope/validity filter — NOT a
        similarity gate.
        """
        cached = await self.store.get_membership(lens.id, decision=MembershipDecision.IN)
        active: set[str] = set()
        for v in cached:
            claim = await self.store.get(v.claim_id)
            if claim is not None and claim.status is Status.ACTIVE:
                active.add(claim.id)
        return active
