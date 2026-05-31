"""Learnings store.

User corrections to automated memory decisions, persisted as editable markdown —
one file per adjudicator at ``~/.ntrp/memory/learnings/<adjudicator>.md`` (mirrors
the lens-file pattern in :mod:`ntrp.memory.lenses`). The file is canonical: the user
can read, edit, or hand-write entries. The system appends an entry on each correction
and reads the file back to condition the adjudicator's next decision.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

from ntrp.settings import NTRP_DIR

if TYPE_CHECKING:
    from pathlib import Path

ADJUDICATORS = frozenset({"dedup", "contradiction", "entity_link"})

_NOT_SAME_HEADING = re.compile(r"^##\s.*—\s*not_same\s*$")
_SUBJECTS_LINE = re.compile(r"^-\s*subjects:\s*(.+)$")

_HEADERS = {
    "dedup": "Learnings: episode dedup",
    "contradiction": "Learnings: contradiction judging",
    "entity_link": "Learnings: entity linking",
}


def get_learnings_dir() -> Path:
    return NTRP_DIR / "memory" / "learnings"


@dataclass(frozen=True)
class Correction:
    adjudicator: str
    action: str  # approve | reject | undo | edit | merge | not_same
    summary: str
    subjects: tuple[str, ...] = ()
    proposed: str = ""
    correct: str = ""
    reason: str = ""


class LearningsStore:
    def __init__(self, base_dir: Path | None = None):
        self._base = base_dir or get_learnings_dir()

    def path(self, adjudicator: str) -> Path:
        _require(adjudicator)
        return self._base / f"{adjudicator}.md"

    def record(self, correction: Correction, *, on: date | None = None) -> None:
        path = self.path(correction.adjudicator)
        if not path.exists():
            self._base.mkdir(parents=True, exist_ok=True)
            header = _HEADERS.get(correction.adjudicator, f"Learnings: {correction.adjudicator}")
            path.write_text(
                f"# {header}\n\nCorrections you made to past {correction.adjudicator} "
                "decisions. Honor them.\n",
                encoding="utf-8",
            )
        entry = _render(correction, on or datetime.now(UTC).date())
        with path.open("a", encoding="utf-8") as f:
            f.write(entry)

    def load(self, adjudicator: str) -> str:
        path = self.path(adjudicator)
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def list_adjudicators(self) -> list[str]:
        if not self._base.is_dir():
            return []
        return sorted(p.stem for p in self._base.glob("*.md") if p.stem in ADJUDICATORS)

    def load_block(self, adjudicator: str) -> str:
        """The recorded entries (everything from the first ``## `` heading), ready to drop
        into an adjudicator prompt. Empty string when nothing has been recorded yet."""
        text = self.load(adjudicator)
        idx = text.find("\n## ")
        return text[idx:].strip() if idx != -1 else ""

    def load_not_same_pairs(self) -> frozenset[frozenset[str]]:
        """Every recorded ``not_same`` correction as an unordered id-pair, across all
        adjudicators. This is the one sanctioned hard rule: a do-not-merge / never-opposed
        set checked *before* the LLM is ever asked about the pair. Entries whose
        ``- subjects:`` line does not name exactly two distinct ids are ignored."""
        pairs: set[frozenset[str]] = set()
        for adjudicator in ADJUDICATORS:
            pairs.update(_parse_not_same_pairs(self.load(adjudicator)))
        return frozenset(pairs)


def _parse_not_same_pairs(text: str) -> set[frozenset[str]]:
    pairs: set[frozenset[str]] = set()
    in_not_same = False
    for line in text.splitlines():
        if line.startswith("## "):
            in_not_same = bool(_NOT_SAME_HEADING.match(line.strip()))
            continue
        if not in_not_same:
            continue
        match = _SUBJECTS_LINE.match(line.strip())
        if match is None:
            continue
        subjects = [s.strip() for s in match.group(1).split(",") if s.strip()]
        if len(set(subjects)) == 2:
            pairs.add(frozenset(subjects))
    return pairs


def _require(adjudicator: str) -> None:
    if adjudicator not in ADJUDICATORS:
        raise ValueError(f"unknown adjudicator: {adjudicator!r}")


def _render(c: Correction, on: date) -> str:
    lines = [f"\n## {on.isoformat()} — {c.action}", c.summary]
    if c.subjects:
        lines.append(f"- subjects: {', '.join(c.subjects)}")
    if c.proposed:
        lines.append(f"- proposed: {c.proposed}")
    if c.correct:
        lines.append(f"- correct: {c.correct}")
    if c.reason:
        lines.append(f"- reason: {c.reason}")
    return "\n".join(lines) + "\n"
