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
prose. Synthesis is the strong model, lazy. The model does NOT echo opaque ids — it
cites each claim by the numbered `[n]` tag it was given; the projector rewrites those
tags into anchors deterministically post-synthesis (`_inject_anchors`). Only a
genuine failure (blank output, or prose citing no claim at all) degrades the page to
a raw anchored list (`synthesized=False`); a faithful render no longer falls back.

Detail levels: `gist` (read-only paragraph), `structured` (anchored bullets, the
editable default, the ONLY level cached into `page`), `dossier` (structured + an
evidence section).
"""

import re

from ntrp.constants import NEGATIVE_EXAMPLES_HEADER
from ntrp.embedder import Embedder
from ntrp.llm.base import CompletionClient
from ntrp.logging import get_logger
from ntrp.memory.models import (
    LensDetailLevel,
    LensRenderMode,
    LensRow,
    MembershipDecision,
    MemoryItem,
    Status,
)
from ntrp.memory.pipeline.membership import LensMembership
from ntrp.memory.pipeline.prompts_project import (
    PAGE_SYNTH_SYSTEM,
    PROFILE_SYNTH_SYSTEM,
    PageSynthesis,
)
from ntrp.memory.pipeline.types import (
    LensGenStage as _GenStage,
    ProgressFn,
    ProjectedGroup,
    ProjectedPage,
    RenderedClaim,
)
from ntrp.memory.store import MemoryStore

_logger = get_logger(__name__)

_ANCHOR_RE = re.compile(r"<!--\s*claim:([0-9a-fA-F]+)\s*-->")
# Synthesis cites each claim by the numbered index tag `{{n}}` it was given (not the
# opaque id). `_inject_anchors` rewrites those tags into stable anchors after the
# model returns — structural index → id substitution, no meaning rule, no keyword.
# The double-brace token (not bare `[n]`) is collision-resistant: a claim whose
# CONTENT literally contains `[1]` ("see table [1]") can't be mistaken for a citation
# and mis-anchored/deleted.
_INDEX_CITE_RE = re.compile(r"\{\{(\d+)\}\}")


def _cite_tag(n: int) -> str:
    return "{{%d}}" % n

# NEGATIVE_EXAMPLES_HEADER (ntrp.constants): the write-back REJECT section label.
# Parsing-only here — it is NOT a subject group, so the cached-grouped
# reconstruction skips it. Decides no membership.


def _anchor(claim_id: str) -> str:
    return f"<!--claim:{claim_id}-->"


def parse_anchors(markdown: str) -> list[str]:
    """Extract claim ids from a page's anchors, in document order."""
    return _ANCHOR_RE.findall(markdown)


def _inject_anchors(markdown: str, members: list[MemoryItem]) -> tuple[str, set[str]]:
    """Rewrite the synthesizer's `{{n}}` index citations into stable claim anchors.

    The model cites each claim by the numbered tag it was given (`{{0}}`, `{{1}}`, …);
    `members[n]` is that claim. Each in-range `{{n}}` becomes `<!--claim:ID-->`
    deterministically. Out-of-range / nonexistent indexes are dropped (the model
    can't invent a member it wasn't given). A claim whose anchor the model already
    emitted verbatim is honored too, so a faithful page renders either way.
    Returns the rewritten markdown plus the set of claim ids that got an anchor —
    the projector's faithfulness check uses that set, never an opaque-id-echo
    requirement.
    """
    member_ids = {m.id for m in members}
    rendered: set[str] = {cid for cid in parse_anchors(markdown) if cid in member_ids}

    def repl(match: re.Match[str]) -> str:
        n = int(match.group(1))
        if 0 <= n < len(members):
            cid = members[n].id
            rendered.add(cid)
            return _anchor(cid)
        return ""

    # NOTE: `{{n}}` only — bare `[n]` in claim content is left untouched (the bug
    # this token switch fixes).

    return _INDEX_CITE_RE.sub(repl, markdown), rendered


def _demote_inline_h2(body: str) -> str:
    """Demote H2 (`## `) headings inside a profile body to H3 (`### `), so only the
    subject header uses `## ` and `_split_subject_sections` won't read a body field
    heading as a new subject. Exactly-two-hash headings only; `### ` is untouched."""
    return re.sub(r"(?m)^## (?!#)", "### ", body)


def _split_subject_sections(markdown: str) -> list[tuple[str, str]]:
    """Split a grouped page's markdown into (subject, body) per `## {subject}` section.

    The leading `# {name}` header is dropped (it precedes the first `## `). The
    write-back negative-examples section is not a subject group and is excluded.
    Structural parse of the page layout only — no meaning rule, no decision.
    """
    sections: list[tuple[str, str]] = []
    subject: str | None = None
    body: list[str] = []
    for line in markdown.splitlines():
        if line.startswith("## "):
            if subject is not None:
                sections.append((subject, "\n".join(body).strip()))
            heading = line[3:].strip()
            subject = None if heading == NEGATIVE_EXAMPLES_HEADER[3:] else heading
            body = []
        elif subject is not None:
            body.append(line)
    if subject is not None:
        sections.append((subject, "\n".join(body).strip()))
    return sections


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

    async def cached_page(
        self, lens_id: str, *, detail: LensDetailLevel | None = None
    ) -> ProjectedPage | None:
        """The materialized page if it is a clean cache hit, else None.

        Pure cache read: NO synthesis, NO membership judge. A grouped page rebuilds
        its groups from the cached markdown's `## {subject}` sections. Returns None
        when the lens is missing, dirty (`page is None`), or the detail level is not
        the cached `structured` level — those need (background) generation. This is
        the fast path the GET endpoint serves directly (Lens spec §6).
        """
        lens = await self.store.get_lens(lens_id)
        if lens is None:
            return None
        level = detail or lens.detail_level or LensDetailLevel.STRUCTURED
        if level is not LensDetailLevel.STRUCTURED or not lens.page:
            return None
        if lens.render_mode is LensRenderMode.GROUPED_BY_SUBJECT:
            return await self._cached_grouped(lens, level)
        # STALENESS GUARD (mirrors _cached_grouped): background consolidation can
        # supersede/invalidate a cited claim WITHOUT nulling this page (consolidate
        # never touches lenses). _blocks_for drops inactive/missing claims, so if the
        # live active set no longer covers every distinct anchor the cached markdown
        # still cites, the page text and blocks disagree. Re-derive instead of
        # serving that inconsistency.
        anchors = parse_anchors(lens.page)
        blocks = await self._blocks_for(anchors)
        # Stale iff a cited anchor no longer resolves to an active claim. An
        # anchor-less page is a legitimately-empty lens (no members), NOT stale —
        # `or not blocks` would wrongly reject it and force re-synthesis on every
        # view, so guard only when there are anchors to verify.
        if anchors and len(blocks) != len(set(anchors)):
            return None
        coverage = await self.membership.coverage(lens_id, lens.scope)
        return ProjectedPage(
            lens_id=lens_id,
            detail=level,
            markdown=lens.page,
            blocks=blocks,
            synthesized=True,
            coverage=coverage,
        )

    async def project(
        self,
        lens_id: str,
        *,
        detail: LensDetailLevel | None = None,
        refresh: bool = False,
        progress: ProgressFn | None = None,
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
        grouped = lens.render_mode is LensRenderMode.GROUPED_BY_SUBJECT

        # Cache hit: serve the materialized page directly (zero synthesis, zero judge
        # calls — Lens spec §6). Only the cached `structured` level qualifies.
        if not refresh and not dirty:
            cached = await self.cached_page(lens_id, detail=level)
            if cached is not None:
                return cached

        # Miss / dirty / refresh: load members from the cache (recompute on empty),
        # re-validate against the CURRENT criterion, render only still-`in`.
        if progress is not None:
            progress(_GenStage.SCORING)
        members = await self._members(lens, refresh=refresh or dirty)
        valid = await self._revalidate(members, lens)
        coverage = await self.membership.coverage(lens_id, lens.scope)
        blocks = [self._to_block(m) for m in valid]

        if grouped:
            markdown, synthesized, groups = await self._render_grouped(
                lens, valid, level, progress=progress
            )
            # Cache the concatenated markdown (same `page` slot as flat). It is the
            # human surface AND fully reconstructs the groups on the next read. Only a
            # fully-synthesized structured page is cached, mirroring the flat path.
            if synthesized and level is LensDetailLevel.STRUCTURED and markdown != lens.page:
                await self.store.update_lens(lens_id, page=markdown)
            return ProjectedPage(
                lens_id=lens_id,
                detail=level,
                markdown=markdown,
                # Top-level blocks must be the anchor-filtered per-group blocks, NOT
                # the unfiltered `valid` list — else a fresh grouped render exposes
                # uncited claims that the cached re-read (_cached_grouped) does not,
                # so the two reads disagree. Mirrors _cached_grouped's accumulation.
                blocks=[b for g in groups for b in g.blocks],
                synthesized=synthesized,
                coverage=coverage,
                groups=groups,
            )

        if progress is not None and valid:
            progress(_GenStage.SYNTHESIZING)
        markdown, synthesized = await self._render(lens, valid, level)

        # Only flat `structured` is cached into the registry page.
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

    async def _cached_grouped(self, lens: LensRow, level: LensDetailLevel) -> ProjectedPage | None:
        """Reconstruct a grouped page from its cached markdown — no LLM, no judge.

        The cached `page` is the same concatenated markdown `_render_grouped` returns:
        a header followed by `## {subject}` sections. Each section's anchors recover
        that subject's claims.

        STALENESS GUARD: background consolidation can supersede/invalidate a claim
        WITHOUT nulling citing lens pages (consolidate never touches lenses). If any
        cited claim is no longer active, the cached markdown (which still shows it)
        would disagree with the filtered blocks/groups. Rather than serve that
        inconsistency, return None so the caller re-derives the page from live claims.
        """
        groups: list[ProjectedGroup] = []
        blocks: list[RenderedClaim] = []
        for subject, body in _split_subject_sections(lens.page):
            anchors = parse_anchors(body)
            section_blocks = await self._blocks_for(anchors)
            # _blocks_for dedupes + drops inactive claims; if the live active set no
            # longer covers every distinct cited anchor, the cache is stale. Guard
            # only when there are anchors — an anchor-less `## Profile` placeholder is
            # a legitimately-empty lens, not stale (mirrors the flat guard above).
            if anchors and len(section_blocks) != len(set(anchors)):
                return None
            groups.append(
                ProjectedGroup(
                    subject=subject,
                    markdown=body,
                    blocks=section_blocks,
                    synthesized=True,
                )
            )
            blocks.extend(section_blocks)
        coverage = await self.membership.coverage(lens.id, lens.scope)
        return ProjectedPage(
            lens_id=lens.id,
            detail=level,
            markdown=lens.page,
            blocks=blocks,
            synthesized=True,
            coverage=coverage,
            groups=groups,
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
        # A durable user REJECT keeps a claim OUT regardless of cache state. The
        # backfill pool filters rejections, but Mode-1 scoring can leave a stale IN
        # row for a re-written rejected claim that a refresh-upsert never purges —
        # so enforce the override here, at the single read path. Not a heuristic gate:
        # get_rejections is an explicit user override, not an LLM/embedding decision.
        rejected = await self.store.get_rejections(lens.id)
        members: list[MemoryItem] = []
        for v in cached:
            if v.claim_id in rejected:
                continue
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
            raw = await self._synthesize(lens, members, level)
        except Exception as e:
            _logger.warning("lens project: synthesis failed for %s: %s", lens.id, e)
            return self._raw_list(lens, members, level), False
        if level is LensDetailLevel.GIST:
            # Gist is a prose paragraph with no anchors by contract — accept as-is.
            return raw, True
        markdown, rendered = _inject_anchors(raw, members)
        if not rendered:
            # Genuine failure: faithful prose always cites at least one claim. Zero
            # citations means the synthesis carried no usable claim reference.
            _logger.warning("lens project: synthesis cited no claims for %s; raw fallback", lens.id)
            return self._raw_list(lens, members, level), False
        return markdown, True

    async def _synthesize(
        self, lens: LensRow, members: list[MemoryItem], level: LensDetailLevel
    ) -> str:
        numbered = "\n".join(
            f"{_cite_tag(n)} subject={m.canonical_subject!r} content={m.content!r} "
            f"prov={m.provenance} corrob={m.corroboration} feedback={m.feedback}"
            for n, m in enumerate(members)
        )
        user = (
            f"LENS: name={lens.name!r}\n"
            f"CRITERION: {lens.criterion!r}\n"
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
        )
        content = resp.choices[0].message.content
        if not content:
            raise ValueError("empty synthesis response")
        page = PageSynthesis.model_validate_json(content)
        text = (page.markdown or "").strip()
        if not text:
            raise ValueError("blank synthesized markdown")
        return text

    # --- grouped-by-subject rendering (presentation only) ------------

    async def _render_grouped(
        self,
        lens: LensRow,
        members: list[MemoryItem],
        level: LensDetailLevel,
        *,
        progress: ProgressFn | None = None,
    ) -> tuple[str, bool, list[ProjectedGroup]]:
        """Bucket members by `canonical_subject`, synthesize a profile per bucket.

        Grouping reads only the claim attribute (no entity rows). Each bucket is a
        ProjectedGroup; the page markdown concatenates `## {subject}` sections so the
        flat markdown/tool path still works. Per-subject synthesis failure degrades
        that one bucket to an anchored raw list (synthesized=False for the bucket).
        """
        buckets: dict[str, list[MemoryItem]] = {}
        for m in members:
            buckets.setdefault(m.canonical_subject, []).append(m)
        # Largest buckets first — the most-supported subjects lead the page.
        ordered = sorted(buckets.items(), key=lambda kv: len(kv[1]), reverse=True)

        groups: list[ProjectedGroup] = []
        sections: list[str] = [self._header(lens)]
        all_synth = True
        total = len(ordered)
        for i, (subject, claims) in enumerate(ordered):
            if progress is not None:
                progress(_GenStage.SYNTHESIZING, subject=subject, progress=f"{i + 1}/{total}")
            body, synthesized, rendered = await self._render_profile(lens, subject, claims, level)
            # Reserve `## ` for the subject header: demote any H2 the synthesizer
            # emitted inside the body to H3, so the cached re-read's
            # `_split_subject_sections` can't mistake a body field heading for a new
            # subject (which would split one bucket into phantom duplicate subjects).
            body = _demote_inline_h2(body)
            all_synth = all_synth and synthesized
            # Blocks must match the claims the markdown actually cites — else a fresh
            # page (all bucket claims) and the cached re-read (anchor-filtered via
            # _cached_grouped) disagree, surfacing uncited claims as editable blocks.
            groups.append(
                ProjectedGroup(
                    subject=subject,
                    markdown=body,
                    blocks=[self._to_block(m) for m in claims if m.id in rendered],
                    synthesized=synthesized,
                )
            )
            sections.append(f"## {subject}\n{body}")

        if not groups:
            return self._empty_page(lens, level), True, []
        return "\n\n".join(sections), all_synth, groups

    async def _render_profile(
        self, lens: LensRow, subject: str, claims: list[MemoryItem], level: LensDetailLevel
    ) -> tuple[str, bool, set[str]]:
        """Returns (markdown, synthesized, cited_ids). cited_ids is the set of claim
        ids the markdown actually anchors — the raw fallback anchors every claim."""
        all_ids = {m.id for m in claims}
        try:
            raw = await self._synthesize_profile(lens, subject, claims, level)
        except Exception as e:
            _logger.warning("lens project: profile synthesis failed for %s/%r: %s", lens.id, subject, e)
            return self._raw_profile(claims), False, all_ids
        markdown, rendered = _inject_anchors(raw, claims)
        if not rendered:
            _logger.warning("lens project: profile cited no claims for %s/%r; raw fallback", lens.id, subject)
            return self._raw_profile(claims), False, all_ids
        return markdown, True, rendered

    async def _synthesize_profile(
        self, lens: LensRow, subject: str, claims: list[MemoryItem], level: LensDetailLevel
    ) -> str:
        numbered = "\n".join(
            f"{_cite_tag(n)} content={m.content!r} prov={m.provenance} "
            f"corrob={m.corroboration} feedback={m.feedback}"
            for n, m in enumerate(claims)
        )
        user = (
            f"SUBJECT: {subject!r}\n"
            f"LENS: name={lens.name!r}\n"
            f"CRITERION: {lens.criterion!r}\n"
            f"DETAIL: {level}\n\n"
            f"CLAIMS:\n{numbered}"
        )
        resp = await self.strong_llm.completion(
            messages=[
                {"role": "system", "content": PROFILE_SYNTH_SYSTEM},
                {"role": "user", "content": user},
            ],
            model=self.strong_model,
            response_format=PageSynthesis,
        )
        content = resp.choices[0].message.content
        if not content:
            raise ValueError("empty profile-synthesis response")
        text = (PageSynthesis.model_validate_json(content).markdown or "").strip()
        if not text:
            raise ValueError("blank synthesized profile")
        return text

    @staticmethod
    def _raw_profile(claims: list[MemoryItem]) -> str:
        return "\n".join(f"- {m.content} {_anchor(m.id)}" for m in claims)

    def _header(self, lens: LensRow) -> str:
        # Just the title. The criterion is multi-section markdown (## Belongs /
        # ## Profile shape) shown+edited in the lens header UI — dumping it into the
        # page body printed the raw markdown as a garbled subtitle.
        return f"# {lens.name}\n"

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
        # Grouped pages reconstruct subjects by splitting on `## ` headers, so an empty
        # grouped page must emit NO `## ` section — else the cached re-read parses the
        # `## Profile` placeholder as a phantom subject group (fresh path returns []).
        if level is LensDetailLevel.GIST or lens.render_mode is LensRenderMode.GROUPED_BY_SUBJECT:
            return f"{self._header(lens)}\n_No members yet._"
        return f"{self._header(lens)}\n## Profile\n_No members yet._"

    # --- blocks (the write-back spine) -------------------------------

    async def _blocks_for(self, claim_ids: list[str]) -> list[RenderedClaim]:
        # Dedupe by claim id, first occurrence wins. A synthesized profile cites the
        # SAME claim across several lines (intro + each Profile-shape field), so its
        # anchors repeat that id — without this, one claim renders as N identical
        # blocks under the profile.
        blocks: list[RenderedClaim] = []
        seen: set[str] = set()
        for cid in claim_ids:
            if cid in seen:
                continue
            seen.add(cid)
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
