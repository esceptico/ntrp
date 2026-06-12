"""Lenses v2 — saved natural-language QUERIES over the flat record pool,
evaluated in the BACKGROUND, read from cache.

A lens is just {name, criterion}. There is NO write-path scoring and NO LLM on
ANY read path: create() and a criterion edit KICK a background evaluation
(recall candidates -> ONE judge call -> replace the `lens_members` cache ->
synthesize the page). members()/page() only ever read the cache; status()
reports an in-flight kick so the surface shows "evaluating", not an empty view.

Banding routes each candidate: high -> member, mid -> uncertain (still shown),
low -> omitted. The band is EXPLICIT (the judge returns it), never a silent
score cutoff, and the judge only ever picks from the candidate ids we hand it —
it never invents ids. With no LLM configured, evaluation degrades to raw hybrid
search of the criterion — NEVER a wordlist heuristic.

A lens that proves durable can be PROMOTED to a label: promote_to_label() tags
every CACHED member record and marks the lens with the label
(`lenses.promoted_to`). The lens stays viewable; thereafter the curator tags
new records because the label is in vocabulary.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import uuid4

from ntrp.database import connect as db_connect
from ntrp.logging import get_logger
from ntrp.memory.lens_page import LensPage
from ntrp.memory.models import Record, now_iso
from ntrp.memory.records import RecordStore

if TYPE_CHECKING:
    from pathlib import Path

_logger = get_logger(__name__)

# How many candidates evaluate() recalls for the judge.
CANDIDATE_K = 100
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


def _criterion_from_markdown(text: str) -> str:
    """The old draft path stored a whole markdown fragment as the criterion.
    Recover the plain-prose criterion: every non-heading line, joined."""
    lines = (line.strip() for line in text.split("\n"))
    return " ".join(s for s in lines if s and not s.startswith("#"))


@dataclass
class Lens:
    """A saved query over records, defined by a natural-language criterion."""

    id: str
    name: str
    criterion: str
    created_at: str
    promoted_to: str | None


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
        self._evals: dict[str, asyncio.Task] = {}  # lens_id -> in-flight kick

    # -- background evaluation (the ONLY place lens LLM work happens) ---------

    def kick(self, lens: Lens) -> None:
        """Start a background evaluate+render for this lens (idempotent while one
        is in flight). Reads stay LLM-free: they serve the cache and report
        status() until this lands."""
        running = self._evals.get(lens.id)
        if running is not None and not running.done():
            return
        task = asyncio.create_task(self._evaluate_and_render(lens))
        self._evals[lens.id] = task
        task.add_done_callback(
            lambda t: (
                self._evals.pop(lens.id, None),
                None if t.cancelled() or not t.exception()
                else _logger.warning("lens evaluation failed", exc_info=t.exception()),
            )
        )

    def status(self, lens_id: str) -> str:
        """'generating' while a kick is in flight, else 'idle'."""
        task = self._evals.get(lens_id)
        return "generating" if task is not None and not task.done() else "idle"

    async def wait(self) -> None:
        """Await all in-flight evaluations (tests + orderly shutdown)."""
        tasks = [t for t in self._evals.values() if not t.done()]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _evaluate_and_render(self, lens: Lens) -> None:
        members = await self.evaluate(lens)
        if not members:
            return
        md = await self._page_synth.synthesize(
            lens.name, lens.criterion, members, detail="structured"
        )
        conn = await self._ensure_conn()
        await conn.execute(
            "UPDATE lenses SET page = ?, page_detail = 'structured' WHERE id = ?",
            (md, lens.id),
        )
        await conn.commit()

    # -- public API ----------------------------------------------------------

    async def create(self, name: str, criterion: str) -> Lens:
        """INSERT + kick: the request returns instantly; membership + page
        materialize in the background."""
        conn = await self._ensure_conn()
        lens = Lens(
            id=uuid4().hex, name=name, criterion=criterion,
            created_at=now_iso(), promoted_to=None,
        )
        await conn.execute(
            "INSERT INTO lenses (id, name, criterion, created_at) VALUES (?, ?, ?, ?)",
            (lens.id, lens.name, lens.criterion, lens.created_at),
        )
        await conn.commit()
        self.kick(lens)
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
        self, name: str, *, criterion: str | None = None, new_name: str | None = None
    ) -> Lens | None:
        """Edit a lens. A criterion change clears the membership cache + page
        ONLY — the next open re-evaluates (no write-path work here)."""
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
            await conn.execute("UPDATE lenses SET page = NULL WHERE id = ?", (lens.id,))
        await conn.commit()
        updated = Lens(
            id=lens.id, name=next_name, criterion=next_criterion,
            created_at=lens.created_at, promoted_to=lens.promoted_to,
        )
        if criterion_changed:
            self.kick(updated)  # re-derive in the background; reads stay cheap
        return updated

    async def evaluate(self, lens: Lens, *, limit: int = 200) -> list[Record]:
        """The background worker: recall candidates for the criterion, judge them
        in ONE LLM call, REPLACE the membership cache, return the members. Runs
        inside kick() — never on a read path. With no LLM the candidates ARE the
        members (banded mid). On a failed judge the old cache is kept."""
        candidates = await self._records.search(lens.criterion, limit=CANDIDATE_K)
        if self._llm is None:
            bands = {r.id: "mid" for r in candidates}
        elif candidates:
            bands = await self._judge(lens.criterion, candidates)
            if bands is None:
                return await self._cached_members(lens, limit=limit)
        else:
            bands = {}
        conn = await self._ensure_conn()
        scored_at = now_iso()
        await conn.execute("DELETE FROM lens_members WHERE lens_id = ?", (lens.id,))
        for rid, band in bands.items():
            if band == "low":
                continue
            await conn.execute(
                "INSERT OR REPLACE INTO lens_members (lens_id, record_id, band, scored_at) "
                "VALUES (?, ?, ?, ?)",
                (lens.id, rid, band, scored_at),
            )
        # Membership moved — the synthesized page is stale; dirty it.
        await conn.execute("UPDATE lenses SET page = NULL WHERE id = ?", (lens.id,))
        await conn.commit()
        return await self._cached_members(lens, limit=limit)

    async def members(self, name: str, *, limit: int = 200) -> list[Record]:
        """The render/retrieval unit: the lens's member records (bands high+mid),
        newest-confirmed first. CACHE-ONLY — an empty cache means the lens hasn't
        been evaluated yet (check status(); kick() fills it in the background)."""
        lens = await self.get(name)
        if lens is None:
            return []
        return await self._cached_members(lens, limit=limit)

    async def page(self, name: str, *, detail: str = "structured") -> str | None:
        """The synthesized lens PAGE, served from the `lenses.page` cache. NEVER
        synthesizes inline — the background kick renders it; None means missing
        lens, no members, or not rendered yet (pair with status())."""
        lens = await self.get(name)
        if lens is None:
            return None
        conn = await self._ensure_conn()
        rows = await conn.execute_fetchall(
            "SELECT page, page_detail FROM lenses WHERE id = ?", (lens.id,)
        )
        if rows[0]["page"] and rows[0]["page_detail"] == detail:
            return rows[0]["page"]
        return None

    async def promote_to_label(self, lens_id: str, label: str) -> int:
        """Graduate a durable lens into a LABEL: tag every CACHED member record
        (you promote the membership you're looking at), mark the lens promoted.
        Raises if the lens was never evaluated — there is nothing to promote."""
        lens = await self.get_by_id(lens_id)
        if lens is None:
            raise ValueError(f"lens {lens_id!r} not found")
        members = await self._cached_members(lens, limit=1000)
        if not members:
            raise ValueError(f"lens {lens.name!r} has no evaluated members yet")
        for record in members:
            await self._records.add_labels(record.id, [label])
        conn = await self._ensure_conn()
        await conn.execute(
            "UPDATE lenses SET promoted_to = ? WHERE id = ?", (label, lens_id)
        )
        await conn.commit()
        return len(members)

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

    async def close(self) -> None:
        for task in self._evals.values():
            task.cancel()
        self._evals.clear()
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    # -- internals -----------------------------------------------------------

    async def _cached_members(self, lens: Lens, *, limit: int) -> list[Record]:
        conn = await self._ensure_conn()
        rows = await conn.execute_fetchall(
            "SELECT r.* FROM lens_members m "
            "JOIN records r ON r.id = m.record_id "
            f"WHERE m.lens_id = ? AND m.band IN ({','.join('?' * len(_MEMBER_BANDS))}) "
            "AND r.superseded_by IS NULL "
            "ORDER BY r.last_confirmed_at DESC LIMIT ?",
            (lens.id, *_MEMBER_BANDS, limit),
        )
        return [RecordStore._row_to_record(r) for r in rows]

    async def _judge(self, criterion: str, candidates: list[Record]) -> dict[str, str] | None:
        """ONE LLM call: hand the model the candidate {id: text} set + the
        criterion, get back a per-id band. Returns {id: band} for ids in the
        candidate set, or None on failure (caller keeps the old cache)."""
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
            promoted_to=row["promoted_to"],
        )

    async def _ensure_conn(self):
        if self._conn is not None:
            return self._conn
        async with self._conn_lock:
            if self._conn is None:
                # Every lens query joins `records` — materialize the RecordStore
                # schema first (it lazy-creates on its own connection).
                await self._records.count_active()
                conn = await db_connect(self._db_path)
                await conn.execute(
                    "CREATE TABLE IF NOT EXISTS lenses ("
                    "    id TEXT PRIMARY KEY,"
                    "    name TEXT NOT NULL UNIQUE,"
                    "    criterion TEXT NOT NULL,"
                    "    created_at TEXT NOT NULL,"
                    "    page TEXT,"
                    "    page_detail TEXT,"
                    "    promoted_to TEXT"
                    ")"
                )
                # Existing DBs predate the page/promoted_to columns; add them
                # idempotently.
                for col in ("page TEXT", "page_detail TEXT", "promoted_to TEXT"):
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
                # Drop cache rows whose record was superseded or deleted — the
                # joins hide them anyway, but the rows would make an all-stale
                # cache look populated and block the lazy re-evaluate.
                await conn.execute(
                    "DELETE FROM lens_members WHERE record_id NOT IN "
                    "(SELECT id FROM records WHERE superseded_by IS NULL)"
                )
                # Repair criteria corrupted by the old draft path (a markdown
                # fragment like '## Belongs\n...' stored verbatim): keep the
                # plain prose, drop the headings, force a re-evaluate.
                rows = await conn.execute_fetchall(
                    "SELECT id, name, criterion FROM lenses WHERE criterion LIKE '#%'"
                )
                for row in rows:
                    criterion = (
                        _criterion_from_markdown(row["criterion"])
                        or f"Records about {row['name']}."
                    )
                    await conn.execute(
                        "DELETE FROM lens_members WHERE lens_id = ?", (row["id"],)
                    )
                    await conn.execute(
                        "UPDATE lenses SET criterion = ?, page = NULL WHERE id = ?",
                        (criterion, row["id"]),
                    )
                await conn.commit()
                self._conn = conn
        return self._conn
