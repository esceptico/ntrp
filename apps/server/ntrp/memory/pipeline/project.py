"""LensProjector — render a lens to its editable markdown page (LENS_CONTRACTS §3.2).

Mode-2 egress, READ-ONLY with respect to claims and membership: the projector
never decides membership and never mints a member_of edge. It re-validates the
lens's CURRENT members against the CURRENT criterion (re-validate-at-read, §6),
renders only the still-`in` claims, and caches the `structured` page back into the
lens row via `supersede` (the only place it writes, and only to the lens row).

Re-validate-at-read is the §1.1/§6 resolution: the store has no `remove_edge`, so a
criterion edit or a REJECT cannot drop a member_of edge. Stale edges dangle
harmlessly; the projector filters them out by re-judging current members through the
sole membership channel (LensMembership.score — an LLM judgment against the
criterion, never a lexical/cosine gate, §0). now-`out` claims simply never render.

Page format (§3.2): markdown where every rendered claim is a bullet carrying a
hidden stable anchor `<!--claim:ID-->`. The anchor survives a markdown round-trip
and pins each editable line to one claim, so write-back diffs BY CLAIM ID, never by
reparsing prose. Synthesis is the strong model, lazy; on failure the page degrades
to a raw anchored list (`synthesized=False`) — never blank, never hallucinated (§9.5).

Detail levels (the `lens_detail_level` column): `gist` (read-only paragraph),
`structured` (anchored bullets, the editable default, the ONLY level cached into
`lens_page`), `dossier` (structured + an evidence section).
"""

import re
import uuid

from ntrp.embedder import Embedder
from ntrp.llm.base import CompletionClient
from ntrp.logging import get_logger
from ntrp.memory.models import (
    EdgeRole,
    Kind,
    LensDetailLevel,
    MemoryItem,
    Status,
)
from ntrp.memory.pipeline.membership import LensMembership
from ntrp.memory.pipeline.prompts_project import PAGE_SYNTH_SYSTEM, PageSynthesis
from ntrp.memory.pipeline.types import (
    MembershipDecision,
    ProjectedPage,
    RenderedClaim,
)
from ntrp.memory.store import MemoryStore

_logger = get_logger(__name__)

# A dirty watermark per lens, written to the meta table on criterion edit (§6).
# Mirrors consolidate's existing watermark pattern — no schema change. The
# projector reads it only to decide whether the cached page is stale; it never
# gates membership.
DIRTY_META_PREFIX = "lens_dirty:"

# The anchor that pins each editable bullet to its claim (§3.2). Invisible when the
# markdown renders; survives a round-trip; the entire write-back contract keys on it.
_ANCHOR_RE = re.compile(r"<!--\s*claim:([0-9a-fA-F]+)\s*-->")


def _anchor(claim_id: str) -> str:
    return f"<!--claim:{claim_id}-->"


def parse_anchors(markdown: str) -> list[str]:
    """Extract claim ids from a page's anchors, in document order.

    A length/format reader over a structural HTML comment — NOT a meaning rule and
    NOT a membership gate (§0). Write-back uses this to diff blocks by id.
    """
    return _ANCHOR_RE.findall(markdown)


class LensProjector:
    def __init__(
        self,
        store: MemoryStore,
        embed: Embedder,
        cheap_llm: CompletionClient,
        strong_llm: CompletionClient,
        *,
        cheap_model: str,
        strong_model: str,
    ):
        # Frozen constructor (§3.2). The projector re-validates members through the
        # SOLE membership channel; it owns a LensMembership built from the exact same
        # injected deps (LensMembership's constructor, §3.1) rather than re-implementing
        # the judge — one decision channel, no fork. See the CONTRACT NOTE in the report.
        self.store = store
        self.embed = embed
        self.cheap_llm = cheap_llm
        self.strong_llm = strong_llm
        self.cheap_model = cheap_model
        self.strong_model = strong_model
        self.membership = LensMembership(
            store,
            cheap_llm,
            strong_llm,
            embed,
            cheap_model=cheap_model,
            strong_model=strong_model,
        )

    async def project(
        self,
        lens_id: str,
        *,
        detail: LensDetailLevel | None = None,
        refresh: bool = False,
    ) -> ProjectedPage:
        lens = await self.store.get(lens_id)
        if lens is None or lens.kind is not Kind.LENS or lens.status is not Status.ACTIVE:
            return ProjectedPage(
                lens_id=lens_id,
                detail=detail or LensDetailLevel.STRUCTURED,
                markdown="",
                blocks=[],
                synthesized=False,
                coverage=None,
            )

        level = detail or lens.lens_detail_level or LensDetailLevel.STRUCTURED
        dirty = await self._is_dirty(lens_id)

        # Cache hit: structured page already materialized, lens not dirty, no refresh
        # forced. 0 LLM, 0 re-validation — the cheapest egress (§5).
        if (
            level is LensDetailLevel.STRUCTURED
            and lens.lens_page
            and not refresh
            and not dirty
        ):
            blocks = await self._blocks_for(parse_anchors(lens.lens_page))
            coverage = await self.membership.coverage(lens_id, lens.scope)
            return ProjectedPage(
                lens_id=lens_id,
                detail=level,
                markdown=lens.lens_page,
                blocks=blocks,
                synthesized=True,
                coverage=coverage,
            )

        # Miss / dirty / refresh: re-validate members against the CURRENT criterion,
        # render only the still-`in` claims, cache the structured page.
        members = await self._active_members(lens_id)
        valid = await self._revalidate(members, lens)
        coverage = await self.membership.coverage(lens_id, lens.scope)
        blocks = [self._to_block(m) for m in valid]

        markdown, synthesized = await self._render(lens, valid, level)

        # Only `structured` is cached into lens_page (what reconcile recall + retrieve
        # read). gist/dossier are derived on demand and never overwrite the cache.
        if synthesized and level is LensDetailLevel.STRUCTURED and markdown != lens.lens_page:
            await self._cache_page(lens, markdown)
        if dirty and level is LensDetailLevel.STRUCTURED:
            await self._clear_dirty(lens_id)

        return ProjectedPage(
            lens_id=lens_id,
            detail=level,
            markdown=markdown,
            blocks=blocks,
            synthesized=synthesized,
            coverage=coverage,
        )

    # --- member gathering + re-validate-at-read (§6) -----------------

    async def _active_members(self, lens_id: str) -> list[MemoryItem]:
        """The lens's current member_of claims that are still active.

        Edges are gathered across the lens's WHOLE supersede history: editing a
        criterion / recording a REJECT supersedes the lens ROW (the append-only
        `_append_alias` pattern, §3.3), minting a NEW lens id, but the store has no
        `remove_edge` (§1.1), so prior members stay anchored to the predecessor ids.
        Walking the SUPERSEDES chain re-unites them under the current head WITHOUT
        moving an edge — exactly the frozen-store-faithful resolution.

        Stale (now-`out`) edges may dangle (§1.1); they are filtered by re-validation
        downstream, not here. This is just the active-claim membership cache as it
        stands across the lens row's history.
        """
        members: list[MemoryItem] = []
        seen: set[str] = set()
        for lid in await self._lens_history(lens_id):
            edges = await self.store.list_edges(lid, direction="to", role=EdgeRole.MEMBER_OF)
            for e in edges:
                if e.child_id in seen:
                    continue
                seen.add(e.child_id)
                m = await self.store.get(e.child_id)
                if m is not None and m.status is Status.ACTIVE and m.kind is Kind.CLAIM:
                    members.append(m)
        return members

    async def _lens_history(self, lens_id: str) -> list[str]:
        """The lens row id + every predecessor id, walking SUPERSEDES backward.

        A `successor --SUPERSEDES--> predecessor` edge has the successor as child, so
        the predecessor of `current` is the parent of its outgoing SUPERSEDES edge.
        History is finite and walkable (no row deleted); a seen-set guards cycles.
        """
        ids: list[str] = []
        current: str | None = lens_id
        seen: set[str] = set()
        while current and current not in seen:
            seen.add(current)
            ids.append(current)
            edges = await self.store.list_edges(current, direction="from", role=EdgeRole.SUPERSEDES)
            current = edges[0].parent_id if edges else None
        return ids

    async def _revalidate(
        self, members: list[MemoryItem], lens: MemoryItem
    ) -> list[MemoryItem]:
        """Re-judge current members against the CURRENT criterion (§6).

        The sole membership channel (LensMembership.score — LLM, not lexical/cosine).
        Renders only still-`in`. `defer` is treated conservatively as not-rendered: the
        page never shows an unresolved member (it is surfaced via membership's escalation
        path, not invented onto the page). Empty member set short-circuits with no call.
        """
        if not members:
            return []
        verdicts = await self.membership.score(members, lens)
        keep: dict[str, MembershipDecision] = {v.claim_id: v.decision for v in verdicts}
        return [m for m in members if keep.get(m.id) is MembershipDecision.IN]

    # --- rendering (§4.3) --------------------------------------------

    async def _render(
        self, lens: MemoryItem, members: list[MemoryItem], level: LensDetailLevel
    ) -> tuple[str, bool]:
        if not members:
            return self._empty_page(lens, level), True
        try:
            markdown = await self._synthesize(lens, members, level)
        except Exception as e:
            _logger.warning("lens project: synthesis failed for %s: %s", lens.id, e)
            return self._raw_list(lens, members, level), False
        # Guard the recursion/anchor contract: every member's anchor must survive. A
        # synthesis that dropped or invented anchors is untrustworthy -> raw fallback.
        echoed = set(parse_anchors(markdown))
        expected = {m.id for m in members}
        if level is not LensDetailLevel.GIST and not expected.issubset(echoed):
            _logger.warning("lens project: synthesis dropped anchors for %s; raw fallback", lens.id)
            return self._raw_list(lens, members, level), False
        return markdown, True

    async def _synthesize(
        self, lens: MemoryItem, members: list[MemoryItem], level: LensDetailLevel
    ) -> str:
        numbered = "\n".join(
            f"[{n}] claim:{m.id} content={m.content!r} prov={m.provenance} "
            f"corrob={m.corroboration} feedback={m.feedback}"
            for n, m in enumerate(members)
        )
        user = (
            f"LENS: name={lens.lens_name!r} kind={lens.lens_kind}\n"
            f"CRITERION: {lens.lens_criterion or ''}\n"
            f"DETAIL: {level}\n\n"
            f"MEMBERS:\n{numbered}"
        )
        resp = await self.strong_llm.completion(
            messages=[
                {"role": "system", "content": PAGE_SYNTH_SYSTEM},
                {"role": "user", "content": user},
            ],
            model=self.strong_model,
            response_format=PageSynthesis,
            temperature=0.0,
        )
        content = resp.choices[0].message.content
        if not content:
            raise ValueError("empty synthesis response")
        page = PageSynthesis.model_validate_json(content)
        text = (page.markdown or "").strip()
        if not text:
            raise ValueError("blank synthesized markdown")
        return text

    def _header(self, lens: MemoryItem) -> str:
        crit = lens.lens_criterion or ""
        return f"# {lens.lens_name or lens.content}\n*Lens · {lens.lens_kind} · criterion: {crit}*\n"

    def _raw_list(
        self, lens: MemoryItem, members: list[MemoryItem], level: LensDetailLevel
    ) -> str:
        """Degraded but honest fallback (§9.5): the header + every member as an anchored
        bullet, verbatim content. Never blank, never invented; the anchor contract holds
        so write-back still works against a degraded page."""
        lines = [self._header(lens), "\n## Profile"]
        for m in members:
            lines.append(f"- {m.content} {_anchor(m.id)}")
        if level is LensDetailLevel.DOSSIER:
            lines.append("\n## Evidence")
            for m in members:
                refs = ", ".join(f"{r.kind}:{r.ref}" for r in m.source_refs) or "—"
                lines.append(f"- {_anchor(m.id)} prov={m.provenance} corrob={m.corroboration} refs={refs}")
        return "\n".join(lines)

    def _empty_page(self, lens: MemoryItem, level: LensDetailLevel) -> str:
        if level is LensDetailLevel.GIST:
            return f"{self._header(lens)}\n_No members yet._"
        return f"{self._header(lens)}\n## Profile\n_No members yet._"

    # --- caching the structured page into the lens row ---------------

    async def _cache_page(self, lens: MemoryItem, markdown: str) -> None:
        """Persist the structured page into `lens_page` via supersede (the append-only
        lens-row history pattern, §3.2 / `_append_alias`). The successor is the same
        lens with a fresh page; the predecessor stays walkable. No member edge touched."""
        successor = MemoryItem(
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
            lens_criterion=lens.lens_criterion,
            lens_kind=lens.lens_kind,
            lens_page=markdown,
            lens_detail_level=LensDetailLevel.STRUCTURED,
            lens_exclusive=lens.lens_exclusive,
        )
        await self.store.supersede(old_id=lens.id, new_item=successor)

    # --- blocks (the write-back spine) -------------------------------

    async def _blocks_for(self, claim_ids: list[str]) -> list[RenderedClaim]:
        blocks: list[RenderedClaim] = []
        for cid in claim_ids:
            m = await self.store.get(cid)
            if m is not None and m.status is Status.ACTIVE and m.kind is Kind.CLAIM:
                blocks.append(self._to_block(m))
        return blocks

    @staticmethod
    def _to_block(m: MemoryItem) -> RenderedClaim:
        return RenderedClaim(
            claim_id=m.id,
            content=m.content,
            provenance=m.provenance,
            corroboration=m.corroboration,
            feedback=m.feedback,
            source_refs=list(m.source_refs),
        )

    # --- dirty watermark (§6) ----------------------------------------

    async def _is_dirty(self, lens_id: str) -> bool:
        rows = await self.store.conn.execute_fetchall(
            "SELECT value FROM meta WHERE key = ?", (DIRTY_META_PREFIX + lens_id,)
        )
        return bool(rows)

    async def _clear_dirty(self, lens_id: str) -> None:
        await self.store.conn.execute(
            "DELETE FROM meta WHERE key = ?", (DIRTY_META_PREFIX + lens_id,)
        )
        await self.store.conn.commit()


async def mark_lens_dirty(store: MemoryStore, lens_id: str) -> None:
    """Set the §6 dirty watermark so the next project re-derives the page.

    Module-level helper (not a store method — the store is frozen) so `edit_criterion`
    (LensService) and write-back can mark a lens dirty after superseding its row. Uses
    the existing `meta` table, no schema change.
    """
    from ntrp.memory.models import now_iso

    await store.conn.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
        (DIRTY_META_PREFIX + lens_id, now_iso()),
    )
    await store.conn.commit()
