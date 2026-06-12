"""The sleep-time Dreamer — the background memory writer.

ONE LLM call per session: reads new transcript turns since a per-session
watermark, reconciles them against existing similar records (ADD/UPDATE/
SUPERSEDE/NOOP), and applies the ops — text AND labels — to the flat record
pool. Labels are open-vocabulary names (referents and categories) decided once
at write time; the prompt carries the existing vocabulary so names get reused
instead of re-minted. No docs, no scope, no lens write path.

The watermark lives in a tiny `meta(key, value)` table the Dreamer OWNS inside
`config.memory_db_path`. Key form: `curate_watermark:{session_id}`. Anti-heartbeat:
a session with no new turns costs one DB read and no LLM call.
"""

import asyncio
import json
import os
from pathlib import Path

from ntrp.database import connect as db_connect
from ntrp.logging import get_logger
from ntrp.memory.models import Record, SourceRef
from ntrp.memory.records import RecordStore

_logger = get_logger(__name__)

# Periodic backstop: sessions that never complete a chat run (automations, idle
# chats, abandoned mid-run sessions) still get curated. Cheap: already-curated
# sessions cost one DB read, no LLM.
SWEEP_INTERVAL_SECONDS = 600
SWEEP_SESSION_LIMIT = 50
CURATION_BATCH_MAX_TURNS = 40
CURATION_BATCH_MAX_CHARS = 6_000
CURATION_TURN_MAX_CHARS = 2_000
CURATION_ROLES = {"user", "assistant"}
LABEL_VOCAB_LIMIT = 40
MAX_LABELS_PER_RECORD = 4

# consolidate.run_once() is a heavy FTS+LLM sweep over the record pool. Running
# it INLINE on the chat server (after every curation) saturates CPU/SQLite and
# times out chat — especially right after a bulk consolidation, when the delta
# is the whole pool. Default OFF: consolidation runs out-of-process
# (scripts.run_consolidation). Set NTRP_INLINE_CONSOLIDATE=1 to re-enable inline.
_INLINE_CONSOLIDATE = os.environ.get("NTRP_INLINE_CONSOLIDATE", "0").lower() in ("1", "true", "yes")

_SYSTEM_PROMPT = (
    "You maintain a set of atomic memory RECORDS about the user (and their world). "
    "Given the EXISTING SIMILAR RECORDS and NEW CONVERSATION TURNS, return a SINGLE "
    "JSON object:\n"
    "{\n"
    '  "records": [\n'
    '    {"op": "ADD",       "text": "<self-contained statement>", "kind": "fact|action|preference|note", "labels": ["..."]},\n'
    '    {"op": "UPDATE",    "id": "<existing id>", "text": "<corrected statement>", "labels": ["..."]},\n'
    '    {"op": "SUPERSEDE", "id": "<existing id>", "text": "<replacement statement>", "kind": "...", "labels": ["..."]},\n'
    '    {"op": "NOOP",      "id": "<existing id>"}\n'
    "  ]\n"
    "}\n"
    "Rules:\n"
    "(1) ADMIT GATE — the bar is HIGH. Most exchanges contain NOTHING worth "
    'remembering: return "records": []. Operational/automation runs (the agent '
    "doing its job, SOPs, routine tool output) admit NOTHING unless they reveal "
    "durable user-level knowledge. Never turn one short task or debugging "
    "segment into a global fact or pattern. Explicit user corrections are "
    "maximal signal — always admit them, keep the user's wording.\n"
    "(2) Records are atomic, self-contained (resolve pronouns inline), typed by "
    "FUNCTION not subject. Choose the op against the EXISTING SIMILAR RECORDS: "
    "ADD (new), UPDATE (edit an existing one), SUPERSEDE (replace a now-wrong "
    "one), NOOP (reconfirm an unchanged one). Use ONLY ids that appear in "
    "EXISTING SIMILAR RECORDS; never invent an id.\n"
    "(3) LABELS — attach 1-4 labels to every ADD/UPDATE/SUPERSEDE. A label is a "
    "short name, not a sentence: a referent the record is about (a person, "
    "project, tool, substance) or a category it belongs to (traits, bugs, open "
    "loops, health). REUSE a name from LABEL VOCABULARY whenever it fits, with "
    "its exact casing; mint a new one only when nothing fits. UPDATE labels "
    "REPLACE the record's labels; omit the field to keep them.\n"
    "(4) Output ONLY the JSON object, no preamble."
)


class Curator:
    """The sleep-time Dreamer. ONE LLM call per session: read new transcript
    turns since a per-session watermark, reconcile them into the flat record
    pool, labeling each written record from the open vocabulary."""

    def __init__(
        self,
        llm,                      # completion client for config.memory_model
        sessions,                 # SessionService — reads transcript turns via messages_since
        *,
        model: str,               # config.memory_model id (for the call)
        db_path: Path,            # config.memory_db_path — the Dreamer owns this meta DB
        record_store: RecordStore,  # the flat record pool; ops land here
        consolidate=None,         # Consolidate — the CONSOLIDATE/LINT step (None -> skip)
        reasoning_effort: str | None = None,
    ) -> None:
        self._llm = llm
        self._sessions = sessions
        self._model = model
        self._record_store = record_store
        self._consolidate = consolidate
        self._reasoning_effort = reasoning_effort

        # The Dreamer owns this meta DB (watermark). Co-located with the records.
        self._db_path = db_path
        self._conn = None  # type: ignore[assignment]
        self._conn_lock = asyncio.Lock()

        # De-dupe in-flight curations per session.
        self._tasks: dict[str, asyncio.Task] = {}

        # The periodic curation sweep (started by knowledge.connect()).
        self._sweep_task: asyncio.Task | None = None

    # -- public API ----------------------------------------------------------

    def schedule_curation(self, session_id: str) -> None:
        """Fire-and-forget: spawn a tracked asyncio task running curate_session.
        Called from chat.py end-of-run. Swallows + logs errors; never blocks the
        response path. De-dupes: if a curation for this session is already
        in-flight, no-op."""
        existing = self._tasks.get(session_id)
        if existing is not None and not existing.done():
            return

        task = asyncio.create_task(self._run_curation(session_id))
        self._tasks[session_id] = task

    def start_sweep(self) -> None:
        """Start the periodic curation sweep (idempotent). The backstop for
        sessions that never complete a chat run, so they still reach memory."""
        if self._sweep_task is None or self._sweep_task.done():
            self._sweep_task = asyncio.create_task(self._sweep_loop())

    async def sweep_once(self) -> int:
        """Schedule curation for the most-recent live USER CHATS. Automation
        channels and spawned agent sessions are operational transcripts —
        memory never reads them. Cheap: relies on schedule_curation's in-flight
        de-dupe and curate_session's no-new-turns no-op, so already-curated
        sessions cost one DB read and no LLM call. Returns the number of
        sessions scheduled."""
        rows = await self._sessions.recent_session_scopes(SWEEP_SESSION_LIMIT)
        scheduled = 0
        for row in rows:
            if row["session_type"] != "chat" or row["origin_automation_id"] is not None:
                continue
            self.schedule_curation(row["session_id"])
            scheduled += 1
        return scheduled

    async def curate_session(self, session_id: str) -> bool:
        """1. Read watermark (max seq already curated for this session).
        2. Load new transcript turns (seq > watermark) via the sessions store.
        3. If no new substantive turns -> advance watermark, return False.
        4. ONE LLM call emitting record ops (text + labels). Admit gate: empty
           ops + advance.
        5. Apply ops to the flat pool.
        6. Advance watermark ONLY after a successful apply (or confirmed no-change)."""
        watermark = await self._read_watermark(session_id)
        rows = await self._sessions.messages_since(session_id, watermark)

        turns, max_seq = self._select_batch(rows, watermark)

        if not turns:
            await self._write_watermark(session_id, max_seq)
            return False

        ops = await self._complete(turns, watermark)
        if ops is None:
            # The LLM call failed (or returned nothing usable); do NOT advance the
            # watermark so the same turns are retried next time (idempotent — the
            # model dedupes against the existing records).
            return False

        # Apply ADD/UPDATE/SUPERSEDE/NOOP. Isolate per-op — one bad op must not
        # abort the rest or block the watermark advance.
        new_records: list[Record] = []
        for op in ops:
            try:
                record = await self._apply_op(op, session_id)
                if record is not None:
                    new_records.append(record)
            except Exception:
                _logger.warning("record op failed; skipping", op=op.get("op"), exc_info=True)

        # CONSOLIDATE/LINT — THE memory step: turn the raw record pile into a small,
        # clean, current body (merge duplicates, supersede stale, drop orphans).
        # Best-effort + O(delta): no-ops cheaply when nothing changed since its own
        # watermark, so this is safe to call on every curation.
        if new_records and self._consolidate is not None and _INLINE_CONSOLIDATE:
            try:
                await self._consolidate.run_once()
            except Exception:
                _logger.warning("consolidation failed", exc_info=True)

        await self._write_watermark(session_id, max_seq)
        return bool(ops)

    async def stop(self) -> None:
        """Cancel the sweep loop and await/cancel in-flight curation tasks.
        Called from knowledge.stop()."""
        if self._sweep_task is not None and not self._sweep_task.done():
            self._sweep_task.cancel()
            await asyncio.gather(self._sweep_task, return_exceptions=True)
        self._sweep_task = None
        tasks = [t for t in self._tasks.values() if not t.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    # -- internals -----------------------------------------------------------

    async def _run_curation(self, session_id: str) -> None:
        try:
            await self.curate_session(session_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            _logger.warning("curation failed", session_id=session_id, exc_info=True)
        finally:
            current = self._tasks.get(session_id)
            if current is asyncio.current_task():
                self._tasks.pop(session_id, None)

    async def _sweep_loop(self) -> None:
        # Sleep first so startup isn't a thundering herd of curations.
        while True:
            await asyncio.sleep(SWEEP_INTERVAL_SECONDS)
            try:
                await self.sweep_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                _logger.warning("curation sweep failed", exc_info=True)

    async def _complete(self, turns: list[str], watermark: int) -> list[dict] | None:
        """ONE LLM call emitting the record-ops. Pre-searches the flat record pool
        for the candidate set so the model picks from REAL ids only, and carries
        the label vocabulary (top names by count + the recalled records' labels)
        so names get reused instead of re-minted. Returns the parsed op list, or
        None on a content-less/failed reply (no-advance)."""
        existing = await self._record_store.search("\n".join(turns), limit=20)
        existing_labels = await self._record_store.labels_for([r.id for r in existing])
        existing_block = (
            "\n".join(
                f"- {r.id} [{', '.join(existing_labels[r.id])}]: {r.text}"
                if existing_labels[r.id]
                else f"- {r.id}: {r.text}"
                for r in existing
            )
            if existing
            else "(none)"
        )

        vocabulary = [row["label"] for row in (await self._record_store.list_labels())[:LABEL_VOCAB_LIMIT]]
        for labels in existing_labels.values():
            vocabulary.extend(label for label in labels if label not in vocabulary)
        vocabulary_block = ", ".join(vocabulary) if vocabulary else "(none yet)"

        user_prompt = (
            f"EXISTING SIMILAR RECORDS (id [labels]: text — use these ids only):\n"
            f"{existing_block}\n\n"
            f"LABEL VOCABULARY (reuse before minting):\n"
            f"{vocabulary_block}\n\n"
            f"NEW TURNS (since seq {watermark}):\n"
            f"{chr(10).join(turns)}"
        )
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
        try:
            resp = await self._llm.completion(
                messages=messages,
                model=self._model,
                reasoning_effort=self._reasoning_effort,
            )
        except Exception:
            _logger.warning("curator LLM call failed", exc_info=True)
            return None
        content = resp.choices[0].message.content if resp.choices else None
        # A content-less but non-erroring completion (refusal, content filter,
        # truncation, reasoning-only finish) must NOT advance the watermark.
        if not content or not content.strip():
            return None
        return self._parse_completion(content)

    @staticmethod
    def _parse_completion(content: str) -> list[dict] | None:
        """Parse the LLM's single JSON object into the op list. Tolerates a
        ```json fence. A reply we cannot parse as the expected object is a failure
        (None, no-advance), distinct from a legitimate empty op list ([])."""
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
        if not isinstance(data, dict):
            return None
        raw_ops = data.get("records")
        if not isinstance(raw_ops, list):
            return None
        return [op for op in raw_ops if isinstance(op, dict)]

    async def _apply_op(self, op: dict, session_id: str) -> Record | None:
        """Apply one reconciliation op (text + labels) against the flat record
        pool. Returns the added/updated record, or None for NOOP/no-op."""
        verb = str(op.get("op", "")).upper()
        source = SourceRef(kind="curator", ref=session_id)
        labels = self._op_labels(op)
        if verb == "ADD":
            text = op.get("text")
            if text:
                record = await self._record_store.add(
                    text, kind=op.get("kind", "note"), source_ref=source
                )
                if labels:
                    await self._record_store.set_labels(record.id, labels)
                return record
        elif verb == "UPDATE":
            rid, text = op.get("id"), op.get("text")
            if rid and text:
                if await self._record_store.update(rid, text):
                    # UPDATE labels REPLACE; an absent field keeps the old set.
                    if labels is not None:
                        await self._record_store.set_labels(rid, labels)
                    return await self._record_store.get(rid)
                # Stale/hallucinated id -> land the correction as an ADD.
                _logger.warning("UPDATE on unknown record id; landing as ADD", record_id=rid)
                record = await self._record_store.add(
                    text, kind=op.get("kind", "note"), source_ref=source
                )
                if labels:
                    await self._record_store.set_labels(record.id, labels)
                return record
        elif verb == "SUPERSEDE":
            rid, text = op.get("id"), op.get("text")
            if rid and text:
                record = await self._record_store.supersede_with(
                    rid, text=text, kind=op.get("kind", "note"), source_ref=source
                )
                # The successor takes the op's labels; without any it keeps the
                # old record's set (supersede_with already copied it).
                if labels:
                    await self._record_store.set_labels(record.id, labels)
                return record
        elif verb == "NOOP":
            rid = op.get("id")
            if rid and not await self._record_store.confirm(rid):
                _logger.warning("NOOP on unknown record id; skipped", record_id=rid)
        return None

    @staticmethod
    def _op_labels(op: dict) -> list[str] | None:
        """The op's labels sanitized (stripped, deduped, capped), or None when
        the field is absent/malformed — None means 'keep' on UPDATE."""
        raw = op.get("labels")
        if not isinstance(raw, list):
            return None
        labels: list[str] = []
        for item in raw:
            if isinstance(item, str) and (name := item.strip()) and name not in labels:
                labels.append(name)
        return labels[:MAX_LABELS_PER_RECORD]

    @classmethod
    def _select_batch(cls, rows: list[dict], watermark: int) -> tuple[list[str], int]:
        turns: list[str] = []
        total_chars = 0
        max_seq = watermark
        for row in sorted(rows, key=lambda r: r.get("seq", watermark)):
            seq = row.get("seq")
            if seq is None:
                continue
            turn = cls._flatten_turn(row)
            if not turn:
                max_seq = max(max_seq, seq)
                continue
            if turns and (
                len(turns) >= CURATION_BATCH_MAX_TURNS
                or total_chars + len(turn) > CURATION_BATCH_MAX_CHARS
            ):
                break
            turns.append(turn)
            total_chars += len(turn)
            max_seq = max(max_seq, seq)
        return turns, max_seq

    @staticmethod
    def _flatten_turn(row) -> str:
        """Compact `role: text` projection of one transcript turn. Drops empty
        turns and image/base64 noise (mirrors the store's flatten projection)."""
        message = row.get("message") if isinstance(row, dict) else None
        role = (row.get("role") if isinstance(row, dict) else "") or ""
        if role not in CURATION_ROLES:
            return ""
        text = Curator._flatten_content(message)
        if not text:
            return ""
        if len(text) > CURATION_TURN_MAX_CHARS:
            text = text[:CURATION_TURN_MAX_CHARS].rstrip()
        return f"{role}: {text}" if role else text

    @staticmethod
    def _flatten_content(message) -> str:
        def walk(raw) -> list[str]:
            if raw is None:
                return []
            if isinstance(raw, str):
                return [raw]
            if isinstance(raw, list):
                out: list[str] = []
                for block in raw:
                    if isinstance(block, dict):
                        t = block.get("type")
                        if t == "text" and block.get("text"):
                            out.append(str(block["text"]))
                    elif isinstance(block, str):
                        out.append(block)
                return out
            if isinstance(raw, dict):
                return walk(raw.get("content"))
            return [str(raw)]

        content = message.get("content") if isinstance(message, dict) else message
        return "\n".join(p for p in walk(content) if p).strip()

    @staticmethod
    def _max_seq(rows, *, default: int) -> int:
        seqs = [row["seq"] for row in rows if isinstance(row, dict) and row.get("seq") is not None]
        return max(seqs, default=default)

    # -- watermark (the Dreamer's own meta table) ----------------------------

    async def _ensure_conn(self):
        if self._conn is not None:
            return self._conn
        async with self._conn_lock:
            if self._conn is None:
                conn = await db_connect(self._db_path)
                await conn.execute(
                    "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)"
                )
                await conn.commit()
                self._conn = conn
        return self._conn

    @staticmethod
    def _watermark_key(session_id: str) -> str:
        return f"curate_watermark:{session_id}"

    async def _read_watermark(self, session_id: str) -> int:
        conn = await self._ensure_conn()
        rows = await conn.execute_fetchall(
            "SELECT value FROM meta WHERE key = ?", (self._watermark_key(session_id),)
        )
        if not rows:
            return -1
        try:
            return int(rows[0]["value"])
        except (TypeError, ValueError):
            return -1

    async def _write_watermark(self, session_id: str, value: int) -> None:
        conn = await self._ensure_conn()
        await conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (self._watermark_key(session_id), str(value)),
        )
        await conn.commit()
