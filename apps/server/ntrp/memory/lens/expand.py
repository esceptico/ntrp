"""Retrieval-by-lens — Mode-2 egress, read-only (LENS_CONTRACTS §3.7).

A lens is a materialized view over the knowledge graph. When a recall goal names
a lens (or chat scope *is* a lens), the cheapest recall path is to inject that
lens's cached `lens_page` directly: it is pre-compressed and query-shaped. When
the page is missing/stale or the goal is narrower, we fall back to the existing
hybrid retrieve path but pre-filter the candidate pool to the lens's active
`member_of` members.

The absolute ban (LENS_CONTRACTS §0) governs this file: nothing here gates a
keep/drop/membership outcome. Lens resolution uses FTS + exact-name match (recall
channels that ORDER candidates, never decide); member pre-filtering is a hard
*categorical* predicate (an edge either exists or it does not — identical to the
scope/validity predicate retrieve already applies), never a similarity/length
cutoff on meaning.

This component never scores membership, never writes, never calls the strong
model (LENS_CONTRACTS §3.7, §11.3). Re-validating stale members against the
current criterion is the projector's job; the expander consumes what membership/
projector already produced.
"""

from dataclasses import dataclass

from ntrp.embedder import Embedder
from ntrp.logging import get_logger
from ntrp.memory.models import EdgeRole, Kind, MemoryItem, Scope, Status, now_iso

_logger = get_logger(__name__)

# Recall channel sizing for lens-name resolution. Orders candidates into the
# match step; it never gates which lens is chosen (§0). A small fan-out: a goal
# names at most a handful of lenses.
LENS_RESOLVE_K = 8


@dataclass
class LensExpansion:
    """Result of expanding a recall goal/hint against the active lens set.

    `page` is the cached `lens_page` to inject verbatim when present (the 0-LLM
    fast path). `member_ids` is the active `member_of` member set used to
    pre-filter the hybrid fallback pool. Exactly one of the two paths is taken by
    the caller: page-inject when `page` is non-empty, else member-constrained
    hybrid recall. `lens` is None when no lens resolved (caller runs unconstrained
    recall unchanged).
    """

    lens: MemoryItem | None
    page: str | None
    member_ids: frozenset[str]


class LensExpander:
    """Read-only lens resolution + member pre-filtering for retrieve (§3.7).

    Constructed with `(store, embed)` only — no LLM client, no model id. The
    contract freezes the *Retriever* signature as `(store, embed, cheap_llm,
    model)` with NO strong model (§11.3); this helper deliberately takes even
    less, because lens expansion is pure store reads + an FTS recall channel. Any
    synthesis/judgment lives in the projector/membership components, not here.
    """

    def __init__(self, store, embed: Embedder):
        self.store = store
        self.embed = embed

    async def expand(
        self, *, hint: str | None, goal: str, scopes: list[Scope], valid_at: str | None = None
    ) -> LensExpansion | None:
        """Resolve a lens for this recall and report its page + member set.

        Returns None when no lens resolves — the caller then runs its normal
        unconstrained hybrid recall, unchanged. When a lens resolves:
          - `page` carries the cached `lens_page` for the verbatim-inject fast
            path (0 LLM, §5);
          - `member_ids` carries the active member set for the member-constrained
            hybrid fallback (ranks, never gates — §3.7).

        Resolution prefers the explicit `hint` (a lens name or chat-scope lens
        id); absent a hint we do NOT guess from the goal prose (that would be an
        implicit lexical decision). Goal-driven resolution is intentionally left
        to the explicit `hint` the caller supplies from structural scope.
        """
        if not hint:
            return None

        lens = await self._resolve(hint, scopes, valid_at)
        if lens is None:
            return None

        member_ids = await self._active_member_ids(lens)
        page = (lens.lens_page or "").strip() or None
        return LensExpansion(lens=lens, page=page, member_ids=frozenset(member_ids))

    # --- lens resolution (recall channels — order, never gate §0) -------

    async def _resolve(
        self, hint: str, scopes: list[Scope], valid_at: str | None
    ) -> MemoryItem | None:
        """Resolve a hint to one active lens within the requested scopes.

        Channel A (exact): the hint is a lens id or an exact `lens_name`.
        Channel B (recall): FTS over lens name/criterion/page surfaces candidate
        lenses; the first scoped active match wins. FTS orders candidates into the
        match; the categorical scope/kind/status filter is the only exclusion — no
        cosine/length cutoff decides which lens (§0).
        """
        valid_at = valid_at or now_iso()
        scoped = await self._scoped_lenses(scopes, valid_at)
        if not scoped:
            return None

        # Channel A: id match, then exact (case-insensitive) name match.
        by_id = {le.id: le for le in scoped}
        if hint in by_id:
            return by_id[hint]
        hint_norm = hint.strip().casefold()
        for le in scoped:
            if (le.lens_name or "").strip().casefold() == hint_norm:
                return le

        # Channel B: FTS recall over lens text, filtered to the scoped active set.
        if not self.store.has_fts:
            return None
        hits = await self.store.search(hint, limit=LENS_RESOLVE_K)
        for hit in hits:
            if hit.kind is Kind.LENS and hit.id in by_id:
                return by_id[hit.id]
        return None

    async def _scoped_lenses(self, scopes: list[Scope], valid_at: str) -> list[MemoryItem]:
        scoped: dict[str, MemoryItem] = {}
        for scope in scopes:
            lenses = await self.store.query(
                kind=Kind.LENS,
                scope=scope,
                status=Status.ACTIVE,
                valid_at=valid_at,
                limit=200,
            )
            for le in lenses:
                scoped[le.id] = le
        return list(scoped.values())

    # --- member pre-filter (categorical predicate, never a meaning gate) -

    async def _active_member_ids(self, lens: MemoryItem) -> set[str]:
        """Active `member_of` members of the lens (child claims pointing at it).

        Edges where the lens is the PARENT (direction='to'); the lens row is the
        parent, each member claim is the child. Stale edges to superseded/archived
        claims are filtered by re-fetching the child and keeping only active ones
        (§1.1: edges dangle harmlessly; reads filter by current status). This is a
        categorical existence predicate, identical in spirit to retrieve's
        scope/validity filter — NOT a similarity gate (§0).
        """
        edges = await self.store.list_edges(lens.id, direction="to", role=EdgeRole.MEMBER_OF)
        active: set[str] = set()
        for edge in edges:
            child = await self.store.get(edge.child_id)
            if child is not None and child.status is Status.ACTIVE:
                active.add(child.id)
        return active
