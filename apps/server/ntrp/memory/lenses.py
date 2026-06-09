"""Lenses — named VIEWS over the flat record pool, defined by a natural-language
CRITERION whose membership is decided by the LLM scoring each record.

ANYTHING is a lens: a person ("Regina"), a disease, a trait, an action, a theme
("bugs"), a project ("ntrp"). ENTITY == LENS. A lens is just {name, criterion}.

Membership is CACHED (the `lens_members` join table) so a lens is cheap to read:
  - create -> backfill ONCE (recall candidates over the whole pool, judge, cache).
  - dreamer -> score NEW/changed records into active lenses incrementally.
  - members() -> read the cache; top up any un-scored recent records on demand.

Banding routes each candidate: high -> member, mid -> LLM/defer (still shown),
low -> omitted. The band is EXPLICIT (the judge returns it), never a silent score
cutoff. The judge only ever picks from the candidate ids we hand it — it never
invents ids. With no LLM configured, membership degrades to raw hybrid search of
the criterion (no banding) — NEVER a wordlist heuristic.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from ntrp.database import connect as db_connect
from ntrp.logging import get_logger
from ntrp.memory.lens_page import LensPage
from ntrp.memory.models import Record, now_iso
from ntrp.memory.records import RecordStore

_logger = get_logger(__name__)

# How many candidates to recall when backfilling a freshly-created lens.
BACKFILL_K = 200
# Bands written into lens_members. "low" is never written (omission).
_MEMBER_BANDS = ("high", "mid")

_JUDGE_SYSTEM = (
    "You decide which memory RECORDS belong to a VIEW defined by a CRITERION. "
    "The criterion may name a person, a topic, a trait, an action, a project, a "
    "status — read it carefully. For EACH candidate record, assign a band:\n"
    '  "high" — clearly satisfies the criterion (a member),\n'
    '  "mid"  — plausibly related but uncertain (still shown, defer),\n'
    '  "low"  — does not satisfy it (omit).\n'
    'Return ONLY a JSON object {"members": [{"id": "<id>", "band": "high|mid|low"}, ...]}. '
    "Use ONLY ids present in the candidate set; never invent an id. Omit ids you "
    "would band low (or band them low explicitly). Output ONLY the JSON object, "
    "no preamble."
)


@dataclass
class Lens:
    """A named view over records, defined by a natural-language criterion."""

    id: str
    name: str
    criterion: str
    created_at: str


class LensStore:
    """Owns `lenses` + `lens_members` in `config.memory_db_path` (the same DB the
    Curator and RecordStore use). Lazy-connect mirrors curator._ensure_conn."""

    def __init__(
        self,
        db_path: Path,
        records: RecordStore,
        llm=None,                      # completion client; None -> no judging
        model: str | None = None,
        reasoning_effort: str | None = None,
    ) -> None:
        self._db_path = db_path
        self._records = records
        self._llm = llm
        self._model = model
        self._reasoning_effort = reasoning_effort
        self._page_synth = LensPage(llm, model=model, reasoning_effort=reasoning_effort)
        self._conn = None
        self._conn_lock = asyncio.Lock()
        self._bg: set[asyncio.Task] = set()  # tracked backfill tasks (no GC, errors logged)

    def _track(self, coro) -> None:
        """Fire-and-forget membership backfill, keeping a ref (no GC) and logging
        failures — backfill is a long LLM pass that must not block the HTTP request
        that created/edited the lens (else the client times out)."""
        task = asyncio.create_task(coro)
        self._bg.add(task)
        task.add_done_callback(
            lambda t: (
                self._bg.discard(t),
                None if t.cancelled() or not t.exception()
                else _logger.warning("lens backfill failed", exc_info=t.exception()),
            )
        )

    # -- public API ----------------------------------------------------------

    async def create(self, name: str, criterion: str, *, background_backfill: bool = False) -> Lens:
        conn = await self._ensure_conn()
        lens = Lens(id=uuid4().hex, name=name, criterion=criterion, created_at=now_iso())
        await conn.execute(
            "INSERT INTO lenses (id, name, criterion, created_at) VALUES (?, ?, ?, ?)",
            (lens.id, lens.name, lens.criterion, lens.created_at),
        )
        await conn.commit()
        # Backfill (recall + LLM banding over the pool) is a long pass. The HTTP
        # create path runs it in the BACKGROUND so the request returns immediately
        # (else the client times out); programmatic/test callers await it.
        if background_backfill:
            self._track(self.backfill(lens))
        else:
            await self.backfill(lens)
        return lens

    async def list(self) -> list[Lens]:
        conn = await self._ensure_conn()
        rows = await conn.execute_fetchall("SELECT * FROM lenses ORDER BY created_at DESC")
        return [self._row_to_lens(r) for r in rows]

    async def get(self, name: str) -> Lens | None:
        conn = await self._ensure_conn()
        rows = await conn.execute_fetchall("SELECT * FROM lenses WHERE name = ?", (name,))
        return self._row_to_lens(rows[0]) if rows else None

    async def get_by_id(self, lens_id: str) -> Lens | None:
        """Id-keyed lookup — the REST surface addresses lenses by uuid, while the
        name-keyed methods take `name`. Resolve id -> lens here, then call the
        name-keyed API with `lens.name`."""
        conn = await self._ensure_conn()
        rows = await conn.execute_fetchall("SELECT * FROM lenses WHERE id = ?", (lens_id,))
        return self._row_to_lens(rows[0]) if rows else None

    async def member_count(self, lens_id: str) -> int:
        """Count of CURRENT (high+mid, non-superseded) members — the coverage
        numerator. Joins records so a superseded member is never counted."""
        conn = await self._ensure_conn()
        rows = await conn.execute_fetchall(
            "SELECT COUNT(*) AS n FROM lens_members m JOIN records r ON r.id = m.record_id "
            f"WHERE m.lens_id = ? AND m.band IN ({','.join('?' * len(_MEMBER_BANDS))}) "
            "AND r.superseded_by IS NULL",
            (lens_id, *_MEMBER_BANDS),
        )
        return rows[0]["n"] if rows else 0

    async def delete(self, name: str) -> bool:
        """Delete a lens (and its membership rows). NEVER deletes records."""
        conn = await self._ensure_conn()
        lens = await self.get(name)
        if lens is None:
            return False
        await conn.execute("DELETE FROM lens_members WHERE lens_id = ?", (lens.id,))
        cur = await conn.execute("DELETE FROM lenses WHERE id = ?", (lens.id,))
        await conn.commit()
        return cur.rowcount > 0

    async def update(
        self, name: str, *, criterion: str | None = None, new_name: str | None = None,
        background_backfill: bool = False,
    ) -> Lens | None:
        """Edit a lens. A criterion change clears the membership cache and
        re-backfills (the old bands no longer apply)."""
        conn = await self._ensure_conn()
        lens = await self.get(name)
        if lens is None:
            return None
        criterion_changed = criterion is not None and criterion != lens.criterion
        next_name = new_name or lens.name
        next_criterion = criterion if criterion is not None else lens.criterion
        await conn.execute(
            "UPDATE lenses SET name = ?, criterion = ? WHERE id = ?",
            (next_name, next_criterion, lens.id),
        )
        if criterion_changed:
            await conn.execute("DELETE FROM lens_members WHERE lens_id = ?", (lens.id,))
            # The page is synthesized from the old members — dirty it so the next
            # read re-synthesizes against the re-derived membership.
            await conn.execute("UPDATE lenses SET page = NULL WHERE id = ?", (lens.id,))
        await conn.commit()
        updated = Lens(id=lens.id, name=next_name, criterion=next_criterion, created_at=lens.created_at)
        if criterion_changed:
            if background_backfill:
                self._track(self.backfill(updated))  # don't block the edit request
            else:
                await self.backfill(updated)
        return updated

    async def members(self, name: str, *, limit: int = 200) -> list[Record]:
        """The render/retrieval unit: the lens's member records (bands high+mid),
        newest-confirmed first. Reads the membership cache, dropping rows whose
        record was superseded/deleted. No per-call LLM (membership is maintained
        incrementally by create/backfill/the dreamer)."""
        lens = await self.get(name)
        if lens is None:
            return []
        conn = await self._ensure_conn()
        rows = await conn.execute_fetchall(
            "SELECT r.* FROM lens_members m "
            "JOIN records r ON r.id = m.record_id "
            f"WHERE m.lens_id = ? AND m.band IN ({','.join('?' * len(_MEMBER_BANDS))}) "
            "AND r.superseded_by IS NULL "
            "ORDER BY r.last_confirmed_at DESC LIMIT ?",
            (lens.id, *_MEMBER_BANDS, limit),
        )
        members = [RecordStore._row_to_record(r) for r in rows]
        if members:
            return members
        # Empty cache + no LLM -> degrade to raw hybrid search of the criterion
        # (no banding). With an LLM, an empty cache means a backfill genuinely
        # found no members; trust it.
        if self._llm is None:
            return await self._records.search(lens.criterion, limit=limit)
        return members

    async def page(
        self, name: str, *, detail: str = "structured", refresh: bool = False
    ) -> str | None:
        """The synthesized, editable lens PAGE: member records rendered into one
        markdown directory. Cached in the `lenses.page` column; the cache is
        nulled when membership or the criterion changes (so the next read
        re-synthesizes). Returns None when the lens is missing or has no members."""
        conn = await self._ensure_conn()
        rows = await conn.execute_fetchall(
            "SELECT id, page, page_detail FROM lenses WHERE name = ?", (name,)
        )
        if not rows:
            return None
        lens_id, cached, cached_detail = rows[0]["id"], rows[0]["page"], rows[0]["page_detail"]
        if not refresh and cached and cached_detail == detail:
            return cached
        lens = await self.get(name)
        members = await self.members(name, limit=BACKFILL_K)
        if not members:
            return None
        md = await self._page_synth.synthesize(lens.name, lens.criterion, members, detail=detail)
        await conn.execute(
            "UPDATE lenses SET page = ?, page_detail = ? WHERE id = ?", (md, detail, lens_id)
        )
        await conn.commit()
        return md

    async def add_member(self, lens_id: str, record_id: str, *, band: str = "high") -> None:
        """Force a record into a lens's membership cache (the `include` write-back).
        Dirties the page so the next read re-synthesizes with the new member."""
        conn = await self._ensure_conn()
        await conn.execute(
            "INSERT OR REPLACE INTO lens_members (lens_id, record_id, band, scored_at) "
            "VALUES (?, ?, ?, ?)",
            (lens_id, record_id, band, now_iso()),
        )
        await conn.execute("UPDATE lenses SET page = NULL WHERE id = ?", (lens_id,))
        await conn.commit()

    async def remove_member(self, lens_id: str, record_id: str) -> bool:
        """Drop a record from a lens's membership cache (the `reject` write-back —
        the record itself survives). Dirties the page."""
        conn = await self._ensure_conn()
        cur = await conn.execute(
            "DELETE FROM lens_members WHERE lens_id = ? AND record_id = ?",
            (lens_id, record_id),
        )
        if cur.rowcount:
            await conn.execute("UPDATE lenses SET page = NULL WHERE id = ?", (lens_id,))
        await conn.commit()
        return cur.rowcount > 0

    async def replace_member(self, lens_id: str, old_id: str, new_id: str) -> None:
        """Re-point a lens member at a record's successor (the `edit` write-back:
        the old record was superseded, the successor takes its membership slot)."""
        conn = await self._ensure_conn()
        rows = await conn.execute_fetchall(
            "SELECT band FROM lens_members WHERE lens_id = ? AND record_id = ?",
            (lens_id, old_id),
        )
        band = rows[0]["band"] if rows else "high"
        await conn.execute(
            "DELETE FROM lens_members WHERE lens_id = ? AND record_id = ?", (lens_id, old_id)
        )
        await conn.execute(
            "INSERT OR REPLACE INTO lens_members (lens_id, record_id, band, scored_at) "
            "VALUES (?, ?, ?, ?)",
            (lens_id, new_id, band, now_iso()),
        )
        await conn.execute("UPDATE lenses SET page = NULL WHERE id = ?", (lens_id,))
        await conn.commit()

    async def backfill(self, lens: Lens) -> None:
        """Score the existing pool into this lens's membership ONCE: recall
        candidates for the criterion, judge them, persist the bands."""
        candidates = await self._records.search(lens.criterion, limit=BACKFILL_K)
        await self._route(lens, candidates)

    async def score_records(self, records: list[Record]) -> None:
        """The dreamer hook: route a batch of new/changed records into EVERY
        active lens. Cheap + best-effort (one judge call per lens over the small
        batch). No-op without an LLM or without records."""
        if not records or self._llm is None:
            return
        for lens in await self.list():
            try:
                await self._route(lens, records)
            except Exception:
                _logger.warning("scoring records into lens failed", lens=lens.name, exc_info=True)

    async def close(self) -> None:
        for task in self._bg:
            task.cancel()
        self._bg.clear()
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    # -- internals -----------------------------------------------------------

    async def _route(self, lens: Lens, candidates: list[Record]) -> None:
        """Judge candidates against the criterion and persist their bands. With
        no LLM, every candidate is banded 'mid' (best-effort, no silent drop)."""
        if not candidates:
            return
        if self._llm is None:
            bands = {r.id: "mid" for r in candidates}
        else:
            bands = await self._judge(lens.criterion, candidates)
            if bands is None:
                return  # judge failed — leave the cache untouched (retried later)
        conn = await self._ensure_conn()
        scored_at = now_iso()
        changed = False
        for rid, band in bands.items():
            if band == "low":
                cur = await conn.execute(
                    "DELETE FROM lens_members WHERE lens_id = ? AND record_id = ?",
                    (lens.id, rid),
                )
                changed = changed or cur.rowcount > 0
                continue
            await conn.execute(
                "INSERT OR REPLACE INTO lens_members (lens_id, record_id, band, scored_at) "
                "VALUES (?, ?, ?, ?)",
                (lens.id, rid, band, scored_at),
            )
            changed = True
        if changed:
            # Membership moved — the synthesized page is stale; dirty it.
            await conn.execute("UPDATE lenses SET page = NULL WHERE id = ?", (lens.id,))
        await conn.commit()

    async def _judge(self, criterion: str, candidates: list[Record]) -> dict[str, str] | None:
        """ONE LLM call: hand the model the candidate {id: text} set + the
        criterion, get back a per-id band. Returns {id: band} for ids in the
        candidate set, or None on failure (caller leaves the cache untouched)."""
        valid_ids = {r.id for r in candidates}
        payload = {r.id: r.text for r in candidates}
        user_prompt = (
            f"CRITERION:\n{criterion}\n\n"
            f"CANDIDATE RECORDS (id -> text):\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
        )
        messages = [
            {"role": "system", "content": _JUDGE_SYSTEM},
            {"role": "user", "content": user_prompt},
        ]
        try:
            resp = await self._llm.completion(
                messages=messages,
                model=self._model,
                reasoning_effort=self._reasoning_effort,
            )
        except Exception:
            _logger.warning("lens judge LLM call failed", exc_info=True)
            return None
        content = resp.choices[0].message.content if resp.choices else None
        members = self._parse_members(content)
        if members is None:
            return None
        return {rid: band for rid, band in members.items() if rid in valid_ids}

    @staticmethod
    def _parse_members(content: str | None) -> dict[str, str] | None:
        if not content or not content.strip():
            return None
        body = content.strip()
        if body.startswith("```"):
            body = body.split("\n", 1)[-1]
            if body.endswith("```"):
                body = body[: body.rfind("```")]
            body = body.strip()
        try:
            data = json.loads(body)
        except (ValueError, TypeError):
            return None
        rows = data.get("members") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            return None
        out: dict[str, str] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            rid = row.get("id")
            band = str(row.get("band", "")).lower()
            if rid and band in ("high", "mid", "low"):
                out[str(rid)] = band
        return out

    @staticmethod
    def _row_to_lens(row) -> Lens:
        return Lens(
            id=row["id"],
            name=row["name"],
            criterion=row["criterion"],
            created_at=row["created_at"],
        )

    async def _ensure_conn(self):
        if self._conn is not None:
            return self._conn
        async with self._conn_lock:
            if self._conn is None:
                conn = await db_connect(self._db_path)
                await conn.execute(
                    "CREATE TABLE IF NOT EXISTS lenses ("
                    "    id TEXT PRIMARY KEY,"
                    "    name TEXT NOT NULL UNIQUE,"
                    "    criterion TEXT NOT NULL,"
                    "    created_at TEXT NOT NULL,"
                    "    page TEXT,"
                    "    page_detail TEXT"
                    ")"
                )
                # Existing DBs predate the page columns; add them idempotently.
                for col in ("page TEXT", "page_detail TEXT"):
                    try:
                        await conn.execute(f"ALTER TABLE lenses ADD COLUMN {col}")
                    except Exception:
                        pass  # column already present
                await conn.execute(
                    "CREATE TABLE IF NOT EXISTS lens_members ("
                    "    lens_id TEXT NOT NULL,"
                    "    record_id TEXT NOT NULL,"
                    "    band TEXT NOT NULL,"
                    "    scored_at TEXT NOT NULL,"
                    "    PRIMARY KEY (lens_id, record_id)"
                    ")"
                )
                await conn.commit()
                self._conn = conn
        return self._conn
