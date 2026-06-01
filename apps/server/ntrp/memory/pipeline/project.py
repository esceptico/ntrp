"""LensProjector — render a lens VIEW to its editable markdown page.

Mode-2 egress, READ-ONLY with respect to claims: the projector never decides
membership directly and never writes a claim. It loads the lens's `in`-decision
members from the membership cache (refreshing the cache on a miss), re-validates
them against the CURRENT criterion (re-validate-at-read), renders only the still-
`in` claims, and caches the `structured` page back into the registry row via
`store.update_lens` (the only place it writes, and only to the lens row).

A lens is a view, not a memory row: it has no supersede chain. The dirty signal is
`page IS NULL` (set by edit_criterion / reject); a criterion edit also invalidates
the membership cache so members re-derive.

Page format: markdown where every rendered claim is a bullet carrying a hidden
stable anchor `<!--claim:ID-->`. The anchor survives a markdown round-trip and pins
each editable line to one claim, so write-back diffs BY CLAIM ID, never by reparsing
prose. Synthesis is the strong model, lazy; on failure the page degrades to a raw
anchored list (`synthesized=False`).

Detail levels: `gist` (read-only paragraph), `structured` (anchored bullets, the
editable default, the ONLY level cached into `page`), `dossier` (structured + an
evidence section).
"""

import re

from ntrp.embedder import Embedder
from ntrp.llm.base import CompletionClient
from ntrp.logging import get_logger
from ntrp.memory.models import (
    LensDetailLevel,
    LensRow,
    MembershipDecision,
    MemoryItem,
    Status,
)
from ntrp.memory.pipeline.membership import LensMembership
from ntrp.memory.pipeline.prompts_project import PAGE_SYNTH_SYSTEM, PageSynthesis
from ntrp.memory.pipeline.types import (
    ProjectedPage,
    RenderedClaim,
)
from ntrp.memory.store import MemoryStore

_logger = get_logger(__name__)

_ANCHOR_RE = re.compile(r"<!--\s*claim:([0-9a-fA-F]+)\s*-->")


def _anchor(claim_id: str) -> str:
    return f"<!--claim:{claim_id}-->"


def parse_anchors(markdown: str) -> list[str]:
    """Extract claim ids from a page's anchors, in document order."""
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
        lens = await self.store.get_lens(lens_id)
        if lens is None:
            return ProjectedPage(
                lens_id=lens_id,
                detail=detail or LensDetailLevel.STRUCTURED,
                markdown="",
                blocks=[],
                synthesized=False,
                coverage=None,
            )

        level = detail or lens.detail_level or LensDetailLevel.STRUCTURED
        dirty = lens.page is None

        # Cache hit: structured page materialized, lens not dirty, no refresh forced.
        if level is LensDetailLevel.STRUCTURED and lens.page and not refresh and not dirty:
            blocks = await self._blocks_for(parse_anchors(lens.page))
            coverage = await self.membership.coverage(lens_id, lens.scope)
            return ProjectedPage(
                lens_id=lens_id,
                detail=level,
                markdown=lens.page,
                blocks=blocks,
                synthesized=True,
                coverage=coverage,
            )

        # Miss / dirty / refresh: load members from the cache (recompute on empty),
        # re-validate against the CURRENT criterion, render only still-`in` claims.
        members = await self._members(lens, refresh=refresh or dirty)
        valid = await self._revalidate(members, lens)
        coverage = await self.membership.coverage(lens_id, lens.scope)
        blocks = [self._to_block(m) for m in valid]

        markdown, synthesized = await self._render(lens, valid, level)

        # Only `structured` is cached into the registry page.
        if synthesized and level is LensDetailLevel.STRUCTURED and markdown != lens.page:
            await self.store.update_lens(lens_id, page=markdown)

        return ProjectedPage(
            lens_id=lens_id,
            detail=level,
            markdown=markdown,
            blocks=blocks,
            synthesized=synthesized,
            coverage=coverage,
        )

    # --- members from the cache (recompute on miss) ------------------

    async def _members(self, lens: LensRow, *, refresh: bool) -> list[MemoryItem]:
        """The lens's `in`-decision members from the cache.

        On refresh or empty cache, recompute via membership.refresh_lens_cache
        first. Stale (now-`out`) cache rows are filtered by re-validation; superseded
        claims are filtered by status.
        """
        cached = await self.store.get_membership(lens.id, decision=MembershipDecision.IN)
        if refresh or not cached:
            await self.membership.refresh_lens_cache(lens.id)
            cached = await self.store.get_membership(lens.id, decision=MembershipDecision.IN)
        members: list[MemoryItem] = []
        for v in cached:
            m = await self.store.get(v.claim_id)
            if m is not None and m.status is Status.ACTIVE:
                members.append(m)
        return members

    async def _revalidate(
        self, members: list[MemoryItem], lens: LensRow
    ) -> list[MemoryItem]:
        """Re-judge current members against the CURRENT criterion. Renders only
        still-`in`. `defer` is treated conservatively as not-rendered."""
        if not members:
            return []
        verdicts = await self.membership.score(members, lens)
        await self.store.put_membership(verdicts)
        keep: dict[str, MembershipDecision] = {v.claim_id: v.decision for v in verdicts}
        return [m for m in members if keep.get(m.id) is MembershipDecision.IN]

    # --- rendering ---------------------------------------------------

    async def _render(
        self, lens: LensRow, members: list[MemoryItem], level: LensDetailLevel
    ) -> tuple[str, bool]:
        if not members:
            return self._empty_page(lens, level), True
        try:
            markdown = await self._synthesize(lens, members, level)
        except Exception as e:
            _logger.warning("lens project: synthesis failed for %s: %s", lens.id, e)
            return self._raw_list(lens, members, level), False
        echoed = set(parse_anchors(markdown))
        expected = {m.id for m in members}
        if level is not LensDetailLevel.GIST and not expected.issubset(echoed):
            _logger.warning("lens project: synthesis dropped anchors for %s; raw fallback", lens.id)
            return self._raw_list(lens, members, level), False
        return markdown, True

    async def _synthesize(
        self, lens: LensRow, members: list[MemoryItem], level: LensDetailLevel
    ) -> str:
        numbered = "\n".join(
            f"[{n}] claim:{m.id} subject={m.canonical_subject!r} content={m.content!r} "
            f"prov={m.provenance} corrob={m.corroboration} feedback={m.feedback}"
            for n, m in enumerate(members)
        )
        user = (
            f"LENS: name={lens.name!r}\n"
            f"CRITERION: {lens.criterion}\n"
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

    def _header(self, lens: LensRow) -> str:
        return f"# {lens.name}\n*Lens · criterion: {lens.criterion}*\n"

    def _raw_list(
        self, lens: LensRow, members: list[MemoryItem], level: LensDetailLevel
    ) -> str:
        """Degraded but honest fallback: header + every member as an anchored bullet."""
        lines = [self._header(lens), "\n## Profile"]
        for m in members:
            lines.append(f"- {m.content} {_anchor(m.id)}")
        if level is LensDetailLevel.DOSSIER:
            lines.append("\n## Evidence")
            for m in members:
                refs = ", ".join(f"{r.kind}:{r.ref}" for r in m.source_refs) or "—"
                lines.append(
                    f"- {_anchor(m.id)} prov={m.provenance} corrob={m.corroboration} refs={refs}"
                )
        return "\n".join(lines)

    def _empty_page(self, lens: LensRow, level: LensDetailLevel) -> str:
        if level is LensDetailLevel.GIST:
            return f"{self._header(lens)}\n_No members yet._"
        return f"{self._header(lens)}\n## Profile\n_No members yet._"

    # --- blocks (the write-back spine) -------------------------------

    async def _blocks_for(self, claim_ids: list[str]) -> list[RenderedClaim]:
        blocks: list[RenderedClaim] = []
        for cid in claim_ids:
            m = await self.store.get(cid)
            if m is not None and m.status is Status.ACTIVE:
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
