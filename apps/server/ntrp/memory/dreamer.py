"""The cross-domain DREAM — the differentiator no commercial system ships.

Generative-Agents 3-step over the file store: (1) derive the most salient
high-level questions that span MORE THAN ONE topic, (2) retrieve cross-topic
evidence per question, (3) write up to 5 cited cross-domain insights back into
memory as src:dreamer records. This is the only flow that AUTHORS net-new
knowledge; it cites evidence ids and respects source-trust (it builds on what's
already stored, never invents).
"""

from __future__ import annotations

import re

from ntrp.logging import get_logger
from ntrp.memory.models import Kind, SourceRef, now_iso

_logger = get_logger(__name__)

MIN_RECORDS = 6
CATALOG_LIMIT = 120
OBS_CATALOG_CAP = 40  # observations are recent TEXTURE, not the backbone — cap their share so a high-volume
# integration day can't evict the durable facts that give the cross-domain questions their altitude.
_DURABLE_KINDS = [Kind.DIRECTIVE, Kind.FACT, Kind.SOURCE, Kind.CHANGELOG]
EVIDENCE_PER_Q = 8
MAX_INSIGHTS = 5

_QUESTIONS_SYSTEM = (
    "You are the reflective 'dream' pass of a personal memory system. Given a catalog "
    "of atomic memory lines spanning several topics, infer the 3 MOST SALIENT high-level "
    "questions whose answers would connect DIFFERENT topics (not a single page). "
    "Prefer questions that bridge work, health, relationships, projects, habits. "
    "Output ONLY the questions, one per line, no numbering."
)

_INSIGHTS_SYSTEM = (
    "You are the reflective 'dream' pass of a personal memory system. From the evidence "
    "below (atomic lines, each prefixed with its ^id and topic), infer up to 5 NON-OBVIOUS "
    "CROSS-DOMAIN insights — connections the user never stated explicitly, each spanning at "
    "least two different topics. Ground every insight in the evidence: cite at least two ids "
    "from DIFFERENT topics. Do not restate a single line. Do not speculate beyond the evidence.\n"
    "Format EXACTLY one insight per line:\n"
    "<insight sentence> (because of ^id1, ^id2)\n"
    "If nothing genuinely cross-domain emerges, output NOTHING.\n"
    "After the insights, on a FINAL separate line, you MAY emit "
    "`LEARNINGS: <one short factual gotcha about THIS run>` (e.g. evidence too thin to "
    "bridge two domains, or a source that keeps surfacing noise). Omit the line entirely "
    "if nothing notable."
)


def _with_preamble(system: str, conventions: str | None, learnings: str | None) -> str:
    """Prepend the shared operating manual (static, cacheable) then any prior-run
    learnings (volatile) ahead of the task system prompt."""
    parts: list[str] = []
    if conventions:
        parts.append(f"<operating_manual>\n{conventions}\n</operating_manual>")
    if learnings:
        parts.append(
            "<learnings>\nOperational gotchas from prior dream runs — avoid repeating these:\n"
            f"{learnings}\n</learnings>"
        )
    parts.append(system)
    return "\n\n".join(parts)

_CITE_RE = re.compile(r"\^?\b[0-9a-f]{6,}\b")
_LEARNINGS_RE = re.compile(r"(?i)\blearnings:\s*(.+)$")  # gotcha trailer; matched anywhere in a line


async def _build_catalog(store) -> list:
    """The question-seeding catalog: the durable backbone (facts/directives/sources)
    as the bulk — excluding prior dream insights so the dream reflects on raw memory,
    not its own output — plus a BOUNDED slice of recent integration observations as
    connective texture. The cap is load-bearing: without it a high-volume integration
    day floods the date-sorted list and evicts every durable fact, collapsing the
    cross-domain dream into gmail↔calendar noise (the starvation re-introduced)."""
    durable = [
        r for r in await store.list(limit=CATALOG_LIMIT - OBS_CATALOG_CAP, scopes=None, kinds=_DURABLE_KINDS)
        if not (r.source_ref and r.source_ref.kind == "dreamer")
    ]
    observations = await store.list(limit=OBS_CATALOG_CAP, scopes=None, kinds=[Kind.OBSERVATION])
    return durable + observations


async def run_dream(
    store, llm, model: str, *, reasoning_effort: str | None = None,
    conventions: str | None = None, learnings: str | None = None,
) -> tuple[str, list[str]]:
    """Returns (summary, new_learnings). new_learnings are operational gotchas the run
    surfaced (for the handler to append to .maintenance/) — NEVER ingested as records."""
    if llm is None or not model:
        return ("dream skipped: no memory model configured", [])

    recent = await _build_catalog(store)
    if len(recent) < MIN_RECORDS:
        return (f"dream skipped: only {len(recent)} non-insight records", [])

    def _page(rid: str) -> str:
        path = store._loc.get(rid)
        return path.stem if path is not None else "?"

    catalog = "\n".join(f"- ^{r.id} [{_page(r.id)}] {r.text}" for r in recent)

    questions = await _ask(
        llm, model, reasoning_effort, _with_preamble(_QUESTIONS_SYSTEM, conventions, None),
        f"MEMORY CATALOG:\n{catalog}", "memory.dream.questions",
    )
    qs = [q.strip("-• ").strip() for q in (questions or "").splitlines() if q.strip()][:3]
    if not qs:
        return ("dream produced no questions", [])

    seen: dict[str, str] = {}
    for q in qs:
        for hit in await store.search(q, limit=EVIDENCE_PER_Q, scopes=None):
            seen[hit.id] = f"- ^{hit.id} [{_page(hit.id)}] {hit.text}"
    if len(seen) < 2:
        return ("dream found too little evidence", [])
    evidence = "\n".join(seen.values())

    raw = await _ask(
        llm, model, reasoning_effort, _with_preamble(_INSIGHTS_SYSTEM, conventions, learnings),
        f"QUESTIONS:\n" + "\n".join(qs) + f"\n\nEVIDENCE:\n{evidence}", "memory.dream.insights",
    )
    insight_lines = [ln.strip("-• ").strip() for ln in (raw or "").splitlines() if ln.strip()]

    # Strip any LEARNINGS: trailer BEFORE the ingest loop — a gotcha must never become a
    # Kind.FACT insight. Match anywhere in the line (not just line-start): models often
    # collapse the trailer inline onto the final insight, so split there and keep only the
    # insight head for ingest.
    learnings_out: list[str] = []
    kept: list[str] = []
    for ln in insight_lines:
        m = _LEARNINGS_RE.search(ln)
        if m:
            gotcha = m.group(1).strip()
            if gotcha:
                learnings_out.append(gotcha)
            head = ln[: m.start()].strip()
            if head:
                kept.append(head)
        else:
            kept.append(ln)
    insight_lines = kept

    written = 0
    today = now_iso()
    for line in insight_lines[:MAX_INSIGHTS]:
        cited = {c.lstrip("^") for c in _CITE_RE.findall(line)}
        # require >=2 citations that resolve to real records on >=2 different pages
        pages = {store._loc[c].stem for c in cited if c in store._loc}
        if len(pages) < 2:
            continue
        await store.add(
            line,
            kind=Kind.FACT,
            source_ref=SourceRef(kind="dreamer", ref=today),
        )  # file_store routes src=dreamer -> insights/<month>.md (OKF insights/)
        written += 1

    msg = f"dream: {len(qs)} questions, {len(seen)} evidence, {written} insights written"
    _logger.info(msg)
    return (msg, learnings_out)


async def _ask(llm, model, effort, system: str, user: str, name: str) -> str | None:
    try:
        resp = await llm.completion(
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            model=model,
            reasoning_effort=effort,
            langfuse_name=name,
        )
    except Exception:
        _logger.warning("dream LLM call failed", exc_info=True)
        return None
    return resp.choices[0].message.content if resp.choices else None
