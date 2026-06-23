"""The always-resident memory profile rendered into the system prompt.

Directives + durable user facts + anything explicitly pinned, in the read
scopes — a small, char-bounded projection of the flat record pool. Pure DB I/O,
zero LLM. The same block feeds interactive chat and operator/automation runs so
both see the same standing memory. Deeper recall stays pull-only via Recall.
"""

from pathlib import Path

from ntrp.logging import get_logger
from ntrp.memory.scopes import scopes_for_read

_logger = get_logger(__name__)

PROFILE_RECORD_LIMIT = 60
# Separate slices so verbose directives can't starve durable facts (or vice
# versa) — each kind is guaranteed its own room every turn.
DIRECTIVE_CHAR_BUDGET = 3000
FACT_CHAR_BUDGET = 2000
SYNTHESIZED_PROSE_CHAR_LIMIT = 4000


def _synthesized_prose(memory_records: object) -> str | None:
    """The synthesized me.md prose (the wiki view of the user), if the file store
    has produced one. Duck-typed: a non-FilePageStore (tests) returns None and the
    caller falls back to the bullet dump. Cheap — reads already-synthesized prose,
    no LLM."""
    pages = getattr(memory_records, "_pages", None)
    root = getattr(memory_records, "_root", None)
    if pages is None or root is None:
        return None
    page = pages.get(Path(root) / "me.md")
    if page is None or not getattr(page, "prose", ""):
        return None
    prose = page.prose.strip()
    if prose.startswith("# "):  # drop the synthesizer's own `# Name` h1 (the block is already under ## MEMORY CONTEXT)
        prose = prose.split("\n", 1)[1].lstrip() if "\n" in prose else ""
    if not prose:
        return None
    if len(prose) > SYNTHESIZED_PROSE_CHAR_LIMIT:
        head = prose[:SYNTHESIZED_PROSE_CHAR_LIMIT].rsplit("\n", 1)[0]
        prose = head or prose[:SYNTHESIZED_PROSE_CHAR_LIMIT]  # one-giant-line guard
    return prose


def _take(records: list, budget: int) -> list[str]:
    lines: list[str] = []
    used = 0
    for record in records:
        line = f"- [{record.kind}] {record.text}"
        if lines and used + len(line) > budget:
            break
        lines.append(line)
        used += len(line)
    return lines


async def resident_profile(
    memory_records: object | None,
    *,
    project_context=None,
    session_id: str | None = None,
) -> str | None:
    """Project the standing memory the agent should carry every turn. Directives
    sort first so behaviour rules survive the char budget; the pool is small
    after the LINT pass, so durable facts ride along without a manual pin."""
    if memory_records is None:
        return None
    # Prefer the synthesized me.md prose (clean wiki block); fall back to the
    # recency/char-budget bullet dump only before the first synthesis has run.
    prose = _synthesized_prose(memory_records)
    if prose is not None:
        return prose
    try:
        scopes = [(s.kind, s.key) for s in scopes_for_read(project=project_context, session_id=session_id)]
        # Directives queried on their own so a flood of recent facts can't evict
        # behaviour rules by recency before the char budget even applies.
        directives = await memory_records.list(kinds=["directive"], scopes=scopes, limit=PROFILE_RECORD_LIMIT)
        facts = await memory_records.list(kinds=["fact"], scopes=scopes, limit=PROFILE_RECORD_LIMIT)
        pinned = await memory_records.list(pinned_only=True, scopes=scopes, limit=PROFILE_RECORD_LIMIT)
    except Exception:
        _logger.warning("profile records load failed", exc_info=True)
        return None

    seen: set[str] = set()

    def _dedup(records: list) -> list:
        out = []
        for record in records:
            if record.id in seen:
                continue
            seen.add(record.id)
            out.append(record)
        return out

    # Pinned records join their own kind's slice (a pinned summary/source rides
    # with the facts), so an explicit pin is always honoured.
    dir_recs = _dedup([*directives, *(p for p in pinned if p.kind == "directive")])
    fact_recs = _dedup([*(p for p in pinned if p.kind != "directive"), *facts])

    lines = _take(dir_recs, DIRECTIVE_CHAR_BUDGET) + _take(fact_recs, FACT_CHAR_BUDGET)
    if not lines:
        return None
    return "## Profile\n\n" + "\n".join(lines)
