"""Two-zone OKF memory page: synthesized prose ABOVE a sentinel, an append-only
dated TIMELINE of record lines below. The timeline line is the canonical record —
it round-trips a Record. Prose is human-facing and optional (filled later by
synthesis); the store reads the timeline.

Line shape (readable, parseable):
    - 2026-06-21 ^a1b2c3d4 [fact] (src:curator) Tim rides a gravel bike.
    - 2026-06-21 ^a1b2c3d4 [fact] [pin] (src:user) Tim's wife is Lena.
    - ~~2026-04-02 ^7a1b2c3d [fact] (src:chat) old claim~~   (superseded)

Scope is positional (derived from the page + kind), not encoded per line:
directives -> global; projects/<key>.md -> (project, key); everything else -> user.
ponytail: minimal frontmatter parser (we control what we write); no yaml dep.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

SENTINEL = "<!-- timeline (append-only; edit prose above, not below) -->"

# Greedy text + bracket tags only (incl. [superseded]) so the text body can
# contain ANYTHING — trailing ~~, "(superseded)", brackets — without ambiguity.
_LINE_RE = re.compile(
    r"^- "
    r"(?P<date>\d{4}-\d{2}-\d{2}) "
    r"\^(?P<id>\w+) "
    r"\[(?P<kind>[\w-]+)\]"
    r"(?P<pin> \[pin\])?(?P<imp> \[imp:\d+\])?(?P<sup> \[superseded\])?(?P<ent> \[ent:[a-z0-9-]+\])? "
    r"\(src:(?P<src>[^)]*)\) "
    r"(?P<text>.*)$"
)


@dataclass
class Line:
    id: str
    text: str
    kind: str = "fact"
    date: str = ""  # YYYY-MM-DD (last_confirmed)
    src: str = "unknown"
    pinned: bool = False
    superseded: bool = False
    imp: int | None = None  # 1-10 poignancy; None = unscored (ranks as neutral 5)
    entity: str | None = None  # slug of the primary entity; drives page promotion (None = no entity)


def format_line(line: Line) -> str:
    pin = " [pin]" if line.pinned else ""
    imp = f" [imp:{line.imp}]" if line.imp is not None else ""
    sup = " [superseded]" if line.superseded else ""
    ent = f" [ent:{line.entity}]" if line.entity else ""
    return f"- {line.date} ^{line.id} [{line.kind}]{pin}{imp}{sup}{ent} (src:{line.src}) {line.text}"


def parse_line(raw: str) -> Line | None:
    # rstrip only the newline, not spaces — an empty text body keeps its trailing
    # separator space so the line still round-trips.
    m = _LINE_RE.match(raw.rstrip("\r\n"))
    if not m:
        return None
    return Line(
        id=m["id"],
        text=m["text"],
        kind=m["kind"],
        date=m["date"],
        src=m["src"],
        pinned=bool(m["pin"]),
        superseded=bool(m["sup"]),
        imp=(int(m["imp"].strip().removeprefix("[imp:").removesuffix("]")) if m["imp"] else None),
        entity=(m["ent"].strip().removeprefix("[ent:").removesuffix("]") if m["ent"] else None),
    )


# -- frontmatter (tiny; scalars + JSON-list values) --------------------------


def _parse_frontmatter(block: str) -> dict:
    fm: dict = {}
    for ln in block.splitlines():
        if not ln.strip() or ":" not in ln:
            continue
        key, _, val = ln.partition(":")
        key, val = key.strip(), val.strip()
        if val.startswith("[") and val.endswith("]"):
            try:
                fm[key] = json.loads(val)
            except ValueError:
                fm[key] = []
        else:
            fm[key] = val
    return fm


def _dump_frontmatter(fm: dict) -> str:
    out = []
    for key, val in fm.items():
        if isinstance(val, list):
            out.append(f"{key}: {json.dumps(val, ensure_ascii=False)}")
        else:
            out.append(f"{key}: {val}")
    return "\n".join(out)


@dataclass
class Page:
    frontmatter: dict = field(default_factory=dict)
    prose: str = ""
    lines: list[Line] = field(default_factory=list)

    def active_lines(self) -> list[Line]:
        return [ln for ln in self.lines if not ln.superseded]


def parse_page(text: str) -> Page:
    fm: dict = {}
    body = text
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            fm = _parse_frontmatter(text[4:end])
            body = text[end + 5 :]
    prose, _, timeline = body.partition(SENTINEL)
    lines = [ln for ln in (parse_line(r) for r in timeline.splitlines()) if ln]
    return Page(frontmatter=fm, prose=prose.strip(), lines=lines)


def render_page(page: Page) -> str:
    parts = []
    if page.frontmatter:
        parts.append("---\n" + _dump_frontmatter(page.frontmatter) + "\n---")
    if page.prose:
        parts.append(page.prose)
    parts.append(SENTINEL)
    parts.append("\n".join(format_line(ln) for ln in page.lines))
    return "\n\n".join(parts).rstrip() + "\n"


if __name__ == "__main__":
    # ponytail: round-trip self-check
    src = Line(id="a1b2c3d4", text="Tim rides a gravel bike.", kind="fact", date="2026-06-21", src="curator")
    assert parse_line(format_line(src)) == src, parse_line(format_line(src))
    pinned = Line(id="ff00", text="Wife is Lena.", kind="fact", date="2026-06-21", src="user", pinned=True)
    assert parse_line(format_line(pinned)).pinned
    dead = Line(id="7a1b", text="old claim", kind="fact", date="2026-04-02", src="chat", superseded=True)
    rt = parse_line(format_line(dead))
    assert rt.superseded and rt.text == "old claim", rt
    scored = Line(id="bb11", text="scored fact", kind="fact", date="2026-06-21", src="user", pinned=True, imp=7)
    assert parse_line(format_line(scored)) == scored, parse_line(format_line(scored))
    legacy = parse_line("- 2026-06-21 ^cc22 [fact] (src:curator) no imp tag")  # back-compat
    assert legacy is not None and legacy.imp is None and legacy.entity is None, legacy
    # per-line entity slug round-trips and coexists with other tags
    ent = Line(id="9911", text="works at Dex.", kind="fact", date="2026-06-21", src="curator", entity="dex-nexus")
    assert parse_line(format_line(ent)) == ent, parse_line(format_line(ent))
    ent_pin = Line(id="9922", text="pinned + entity.", kind="fact", date="2026-06-21", src="user", pinned=True, imp=6, entity="regina-lin")
    assert parse_line(format_line(ent_pin)) == ent_pin, parse_line(format_line(ent_pin))
    # the entity tag lives in the positionally-locked bracket region, so a text body
    # that itself starts with a "(ent:..)"/"[ent:..]"-shaped token round-trips verbatim
    bait1 = Line(id="9933", text="(ent:roadmap) blockers cleared", kind="fact", date="2026-06-21", src="chat")
    assert parse_line(format_line(bait1)) == bait1, parse_line(format_line(bait1))
    bait2 = Line(id="9944", text="[ent:foo] is just prose", kind="fact", date="2026-06-21", src="chat")
    assert parse_line(format_line(bait2)) == bait2, parse_line(format_line(bait2))
    # regression: text ending in ~~ or containing "(superseded)" must survive verbatim
    tricky = Line(id="dd33", text="deprecated ~~old API~~", kind="fact", date="2026-06-21", src="curator")
    assert parse_line(format_line(tricky)) == tricky, parse_line(format_line(tricky))
    paren = Line(id="ee44", text="issue resolved (superseded) per Lena", kind="fact", date="2026-06-21", src="chat")
    assert parse_line(format_line(paren)) == paren, parse_line(format_line(paren))
    page = Page(frontmatter={"type": "topic", "title": "Bicycles", "entity_labels": ["Bicycles"]}, prose="Tim's bikes.", lines=[src, pinned, dead])
    rp = parse_page(render_page(page))
    assert rp.frontmatter["title"] == "Bicycles"
    assert rp.frontmatter["entity_labels"] == ["Bicycles"]
    assert len(rp.lines) == 3 and len(rp.active_lines()) == 2
    assert rp.prose == "Tim's bikes."
    print("pages.py self-check OK")
