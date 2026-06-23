"""Deterministic nightly retention: TTL-by-kind + salience floor.

No LLM. No read-time last_used. Staleness = line.date (last_confirmed_at, bumped
by confirm()/update()). Tombstones (supersedes) lines past TTL that are below the
floor, and unindexes them so the vector leg stays clean. Idempotent.

TTL (from line.kind): directive -> permanent; fact/changelog -> durable (730d);
source -> transient (180d). Floor (either exempts permanently): line.pinned, or
kind == directive.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from ntrp.constants import (
    MEMORY_RETENTION_TTL_DURABLE_DAYS,
    MEMORY_RETENTION_TTL_OBSERVATION_DAYS,
    MEMORY_RETENTION_TTL_TRANSIENT_DAYS,
)
from ntrp.logging import get_logger
from ntrp.memory.models import Kind

_logger = get_logger(__name__)

_TTL: dict[str, int | None] = {
    Kind.DIRECTIVE: None,
    Kind.FACT: MEMORY_RETENTION_TTL_DURABLE_DAYS,
    Kind.CHANGELOG: MEMORY_RETENTION_TTL_DURABLE_DAYS,
    Kind.SOURCE: MEMORY_RETENTION_TTL_TRANSIENT_DAYS,
    Kind.OBSERVATION: MEMORY_RETENTION_TTL_OBSERVATION_DAYS,  # raw integration items age out fast
}
_DEFAULT_TTL = MEMORY_RETENTION_TTL_DURABLE_DAYS  # unknown kinds -> durable
_DREAMER_TTL = MEMORY_RETENTION_TTL_TRANSIENT_DAYS  # machine-authored insights are provisional


@dataclass
class RetentionReport:
    examined: int = 0
    superseded: int = 0
    pages_touched: int = 0
    by_class: dict[str, int] = field(default_factory=dict)

    def summary(self) -> str:
        if self.superseded == 0:
            return f"retention: examined {self.examined}, nothing pruned"
        detail = ", ".join(f"{k} {v}" for k, v in sorted(self.by_class.items()) if v)
        return f"retention: examined {self.examined}, superseded {self.superseded} ({detail}), pages {self.pages_touched}"


def _is_stale(line_date: str, ttl_days: int | None, today: date) -> bool:
    if ttl_days is None:
        return False
    try:
        written = date.fromisoformat(line_date)
    except ValueError:
        return False  # malformed date is treated as fresh (safe)
    return (today - written) > timedelta(days=ttl_days)


async def run_retention(store) -> RetentionReport:
    """Run the retention pass over an open FilePageStore in-place.
    store needs _pages: dict[Path, Page], _persist(path), and _unindex_line(id)."""
    today = datetime.now(UTC).date()  # line dates are UTC (now_iso); match to avoid TTL off-by-one
    report = RetentionReport()
    for path, page in store._pages.items():
        dirty = False
        for line in page.lines:
            if line.superseded:
                continue  # idempotent skip
            report.examined += 1
            if line.pinned:
                continue  # salience floor
            ttl = _DREAMER_TTL if line.src == "dreamer" else _TTL.get(line.kind, _DEFAULT_TTL)
            if not _is_stale(line.date, ttl, today):
                continue
            line.superseded = True
            dirty = True
            report.superseded += 1
            report.by_class[line.kind] = report.by_class.get(line.kind, 0) + 1
            store._unindex_line(line.id)  # keep the vector leg consistent
            _logger.info("retention: superseded stale line", id=line.id, kind=line.kind, date=line.date, ttl_days=ttl)
        if dirty:
            store._persist(path)
            report.pages_touched += 1
    _logger.info(report.summary())
    return report


if __name__ == "__main__":
    import asyncio
    import tempfile
    from pathlib import Path

    from ntrp.memory.file_store import FilePageStore
    from ntrp.memory.models import SourceRef

    async def _check():
        with tempfile.TemporaryDirectory() as d:
            store = FilePageStore(Path(d))  # no search_index -> _unindex_line no-ops
            await store.open()
            today = date.today().isoformat()
            d400 = (date.today() - timedelta(days=400)).isoformat()
            d800 = (date.today() - timedelta(days=800)).isoformat()
            r_recent = await store.add("recent fact", kind="fact", source_ref=SourceRef("user", ""), date=today)
            r_old = await store.add("old fact", kind="fact", source_ref=SourceRef("user", ""), date=d800)
            r_src = await store.add("old source", kind="source", source_ref=SourceRef("user", ""), date=d400)
            r_pin = await store.add("pinned old", kind="fact", pinned=True, source_ref=SourceRef("user", ""), date=d800)
            r_dir = await store.add("old directive", kind="directive", source_ref=SourceRef("user", ""), date=d800)
            r_gone = await store.add("already gone", kind="fact", source_ref=SourceRef("user", ""), date=d800)
            await store.supersede(r_gone.id, "x")
            rep = await run_retention(store)
            assert not store._find(r_recent.id)[1].superseded
            assert store._find(r_old.id)[1].superseded
            assert store._find(r_src.id)[1].superseded
            assert not store._find(r_pin.id)[1].superseded
            assert not store._find(r_dir.id)[1].superseded
            assert rep.superseded == 2, rep.superseded
            assert (await run_retention(store)).superseded == 0  # idempotent
            assert _is_stale("2025-01-01", 180, date(2026, 6, 22))
            assert not _is_stale("not-a-date", 180, date(2026, 6, 22))
            # dreamer insights are provisional: a 200-day-old dreamer fact expires (>180),
            # a 200-day-old user fact does not (<730 durable).
            d200 = (date.today() - timedelta(days=200)).isoformat()
            r_dream = await store.add("dreamed insight", kind="fact", source_ref=SourceRef("dreamer", ""), date=d200)
            r_userfact = await store.add("durable user fact", kind="fact", source_ref=SourceRef("user", ""), date=d200)
            await run_retention(store)
            assert store._find(r_dream.id)[1].superseded, "dreamer fact expires at transient TTL"
            assert not store._find(r_userfact.id)[1].superseded, "durable user fact survives 200d"
            # observations age out fast: a 100-day-old one expires (>90), a fresh one survives.
            d100 = (date.today() - timedelta(days=100)).isoformat()
            r_obs_old = await store.add("old gmail observation", kind="observation", source_ref=SourceRef("gmail", ""), date=d100)
            r_obs_new = await store.add("fresh gmail observation", kind="observation", source_ref=SourceRef("gmail", ""), date=today)
            await run_retention(store)
            assert store._find(r_obs_old.id)[1].superseded, "observation expires at 90d"
            assert not store._find(r_obs_new.id)[1].superseded, "fresh observation survives"
            print("retention.py self-check OK")

    asyncio.run(_check())
