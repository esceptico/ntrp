"""Capture — bounding + durability (CONTRACTS §4).

Owns: turning the raw stream into discrete, scoped, evidence-anchored
CaptureUnits. NEVER summarizes, extracts, judges worth, or writes memory_items.

Boundaries (priority): EXPLICIT (/close, remember()) → SESSION/run-close → IDLE
→ SEMANTIC (background-only). A CAP force-cut bounds runaway never-closing
streams. Interactive + idle boundaries are zero-LLM; the semantic-shift call runs
ONLY in the background sweep.

Scope assignment is deterministic from structural metadata, never LLM-inferred:
  chat session with project_id → PROJECT scope (key=project_id)
  bare chat session           → USER scope (key=None)
  automation/scheduled run     → SESSION scope (key=origin_automation_id|session_id)

Durability: record `swept_at` before work; advance the watermark ONLY after Admit
durably accepts the unit (commit_watermark). Crash mid-sweep re-reads from the
un-advanced cursor → at-least-once, idempotent on stable source_refs.

Store usage: reads the raw stores + the memory `meta(key, value)` table for
watermarks (keys `capture:wm:<source_id>`). Writes NOTHING to memory_items/edges.
"""

import json
from dataclasses import dataclass
from typing import Protocol

from ntrp.logging import get_logger
from ntrp.memory.models import Scope, ScopeKind, SourceRef, now_iso
from ntrp.memory.pipeline.prompts_capture import (
    SEMANTIC_BOUNDARY_SYSTEM,
    SEMANTIC_BOUNDARY_USER,
    SemanticBoundary,
    render_batch,
)
from ntrp.memory.pipeline.types import (
    BoundaryKind,
    CaptureUnit,
    ExchangeRole,
    RawExchange,
    Watermark,
)

_logger = get_logger(__name__)

WATERMARK_KEY_PREFIX = "capture:wm:"

# Idle window: a chat session untouched for this long is treated as closed by a
# background sweep (zero-LLM). A routing/timing signal, never a worth gate.
DEFAULT_IDLE_SECONDS = 30 * 60
# Force-cut a runaway never-closing stream once a unit reaches this many
# exchanges, even if no boundary was otherwise detected.
DEFAULT_MAX_WINDOW_EXCHANGES = 40
# Background sweep batch size handed to the semantic-shift check.
DEFAULT_SWEEP_BATCH = 20


@dataclass
class CaptureConfig:
    idle_seconds: int = DEFAULT_IDLE_SECONDS
    max_window_exchanges: int = DEFAULT_MAX_WINDOW_EXCHANGES
    sweep_batch: int = DEFAULT_SWEEP_BATCH
    semantic_model: str | None = None  # cheap model id for the background shift call


class BoundaryJudge(Protocol):
    """Minimal LLM seam for the SEMANTIC boundary check.

    CONTRACTS types this as `cheap_llm: CompletionClient`. The concrete completion
    signature is the LLM client's API contract (owned elsewhere); Capture only
    needs a structured boundary decision. The integration phase binds a thin
    adapter from the real CompletionClient to this Protocol. Keeping the seam
    narrow lets the unit tests run the hot/idle paths with ZERO LLM and exercise
    the background path with a trivial fake.
    """

    async def detect_boundary(
        self, *, system: str, user: str, model: str | None
    ) -> SemanticBoundary: ...


class CaptureService:
    """See module docstring. Constructor matches CONTRACTS §3 (raw stores + store
    + cheap_llm + config)."""

    def __init__(
        self,
        raw_sessions,
        raw_automations,
        store,
        cheap_llm: BoundaryJudge | None,
        *,
        config: CaptureConfig,
    ):
        self.raw_sessions = raw_sessions
        self.raw_automations = raw_automations
        self.store = store
        self.cheap_llm = cheap_llm
        self.config = config

    # --- watermark persistence (existing meta table, no schema change) ----------

    async def _read_watermark(self, source_id: str) -> Watermark | None:
        """Read a stored watermark from the store's existing `meta` table.

        CONTRACT ISSUE (surfaced, not freelanced): the FROZEN MemoryStore exposes
        no public get/set for the `meta` table — only the table in its DDL. The
        watermark datum CONTRACTS §0.6 says lives in `meta(key,value)` therefore
        has no store API to reach it. Capture reads/writes it via the store's
        connection against the already-existing table: NO schema change, NO new
        column, NO new invariant. A read-only `get_meta`/`set_meta` pair on the
        store would be the clean home; raised for the store-owner, not patched in
        here.
        """
        key = WATERMARK_KEY_PREFIX + source_id
        rows = await self.store.conn.execute_fetchall(
            "SELECT value FROM meta WHERE key = ?", (key,)
        )
        if not rows or rows[0]["value"] is None:
            return None
        data = json.loads(rows[0]["value"])
        return Watermark(
            source_id=data["source_id"], cursor=data["cursor"], swept_at=data["swept_at"]
        )

    async def _write_watermark(self, wm: Watermark) -> None:
        key = WATERMARK_KEY_PREFIX + wm.source_id
        value = json.dumps(
            {"source_id": wm.source_id, "cursor": wm.cursor, "swept_at": wm.swept_at}
        )
        await self.store.conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        await self.store.conn.commit()

    async def commit_watermark(self, wm: Watermark) -> None:
        """Advance-after-success: Admit invokes this on durable acceptance of the
        unit. Advancing only here is what makes capture at-least-once."""
        await self._write_watermark(wm)

    # --- scope assignment (deterministic, never LLM-inferred) -------------------

    @staticmethod
    def _scope_for_session(session) -> Scope:
        session_type = getattr(session, "session_type", "chat")
        origin_automation_id = getattr(session, "origin_automation_id", None)
        project_id = getattr(session, "project_id", None)
        session_id = getattr(session, "session_id", None)

        if session_type != "chat" or origin_automation_id:
            # automation / scheduled run → session scope keyed by its origin.
            key = origin_automation_id or session_id
            if not key:
                raise ValueError("automation session lacks an origin/session key for scoping")
            return Scope(kind=ScopeKind.SESSION, key=key)
        if project_id:
            return Scope(kind=ScopeKind.PROJECT, key=project_id)
        return Scope(kind=ScopeKind.USER)

    @staticmethod
    def _role_for_session(session) -> ExchangeRole:
        session_type = getattr(session, "session_type", "chat")
        if session_type == "scheduled":
            return ExchangeRole.SCHEDULED
        if session_type != "chat" or getattr(session, "origin_automation_id", None):
            return ExchangeRole.AUTOMATION
        return ExchangeRole.LIVE_CHAT

    # --- raw → exchanges --------------------------------------------------------

    @staticmethod
    def _flatten_content(content) -> str:
        """Plain text from a message content field (str or block list)."""
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text" and block.get("text"):
                        parts.append(str(block["text"]))
                    elif block.get("type") == "tool_result":
                        parts.append(CaptureService._flatten_content(block.get("content")))
                elif isinstance(block, str):
                    parts.append(block)
            return "\n".join(p for p in parts if p).strip()
        return ""

    def _exchanges_from_session(self, session) -> list[RawExchange]:
        """Build evidence-anchored exchanges from a session's transcript.

        Each turn becomes one RawExchange whose source_ref points back into the
        immutable raw layer (kind="chat_turn", ref="<session_id>:<seq>"). Capture
        never edits or stores the raw text as memory — only points at it.
        """
        session_id = getattr(session, "session_id", None)
        messages = getattr(session, "messages", None) or []
        captured_at = now_iso()
        exchanges: list[RawExchange] = []
        for seq, msg in enumerate(messages):
            if not isinstance(msg, dict):
                continue
            text = self._flatten_content(msg.get("content"))
            if not text:
                continue
            ref = f"{session_id}:{seq}"
            exchanges.append(
                RawExchange(
                    turn_id=ref,
                    text=text,
                    source_ref=SourceRef(kind="chat_turn", ref=ref, captured_at=captured_at),
                )
            )
        return exchanges

    @staticmethod
    def _unit_cursor(exchanges: list[RawExchange]) -> str:
        """Monotonic cursor = the last exchange's ref. Empty → empty string."""
        return exchanges[-1].turn_id if exchanges else ""

    def _make_unit(
        self,
        *,
        scope: Scope,
        role: ExchangeRole,
        exchanges: list[RawExchange],
        boundary: BoundaryKind,
        source_id: str,
        forced: bool,
        swept_at: str,
    ) -> CaptureUnit:
        return CaptureUnit(
            scope=scope,
            role=role,
            exchanges=exchanges,
            source_refs=[e.source_ref for e in exchanges],
            boundary=boundary,
            watermark=Watermark(
                source_id=source_id, cursor=self._unit_cursor(exchanges), swept_at=swept_at
            ),
            forced=forced,
        )

    # --- interactive boundaries (zero-LLM) --------------------------------------

    async def close(self, session_id: str, boundary: BoundaryKind) -> CaptureUnit | None:
        """Bound a session at an interactive boundary (EXPLICIT /close, SESSION
        close, or IDLE). Zero LLM. Returns None if there is nothing new to bound.

        Only exchanges past the stored watermark cursor are included, so a
        re-close after a partial sweep is idempotent on stable source_refs.
        """
        session = await self.raw_sessions.load_session(session_id)
        if session is None:
            return None
        swept_at = now_iso()
        scope = self._scope_for_session(session)
        role = self._role_for_session(session)
        source_id = f"session:{session_id}"

        all_exchanges = self._exchanges_from_session(session)
        wm = await self._read_watermark(source_id)
        new_exchanges = self._after_cursor(all_exchanges, wm.cursor if wm else None)
        if not new_exchanges:
            return None

        forced = boundary is BoundaryKind.EXPLICIT
        return self._make_unit(
            scope=scope,
            role=role,
            exchanges=new_exchanges,
            boundary=boundary,
            source_id=source_id,
            forced=forced,
            swept_at=swept_at,
        )

    @staticmethod
    def _after_cursor(
        exchanges: list[RawExchange], cursor: str | None
    ) -> list[RawExchange]:
        if not cursor:
            return list(exchanges)
        for i, e in enumerate(exchanges):
            if e.turn_id == cursor:
                return exchanges[i + 1 :]
        # cursor not found (raw rewritten/compacted) → take all; re-grounding is
        # always possible and at-least-once is the durability guarantee.
        return list(exchanges)

    # --- remember() entry (zero-LLM, forced) ------------------------------------

    async def on_remember(
        self, text: str, scope: Scope, source_ref: SourceRef
    ) -> CaptureUnit:
        """A remember() write is a forced, single-exchange EXPLICIT unit. Capture
        does not judge it; Admit will pin it through (forced) and Reconcile runs.
        No watermark advances for a one-shot remember (no stream cursor)."""
        swept_at = now_iso()
        exchange = RawExchange(turn_id=source_ref.ref, text=text, source_ref=source_ref)
        return CaptureUnit(
            scope=scope,
            role=ExchangeRole.LIVE_CHAT,
            exchanges=[exchange],
            source_refs=[source_ref],
            boundary=BoundaryKind.EXPLICIT,
            watermark=Watermark(
                source_id=f"remember:{source_ref.ref}",
                cursor=source_ref.ref,
                swept_at=swept_at,
            ),
            forced=True,
        )

    # --- background watermark-driven sweep (safety net; never-closing streams) ---

    async def sweep(self, source_id: str) -> list[CaptureUnit]:
        """Background sweep for one source. Reads everything past the stored
        watermark, then segments it into units:

        - CAP force-cut once a pending window exceeds max_window_exchanges.
        - SEMANTIC cut where the (background-only) shift check fires.
        - A trailing remainder is emitted as a SESSION-bounded unit only when the
          session is itself closed/idle; otherwise it stays pending (no premature
          cut of an open stream) and the watermark is NOT advanced past it.

        The watermark on each returned unit is the cursor Admit must commit on
        durable acceptance. Advancing is the caller's job (commit_watermark),
        which is what keeps the sweep at-least-once across crashes.
        """
        if not source_id.startswith("session:"):
            raise ValueError(f"unsupported sweep source_id: {source_id!r}")
        session_id = source_id[len("session:") :]
        session = await self.raw_sessions.load_session(session_id)
        if session is None:
            return []

        swept_at = now_iso()
        scope = self._scope_for_session(session)
        role = self._role_for_session(session)
        all_exchanges = self._exchanges_from_session(session)
        wm = await self._read_watermark(source_id)
        pending = self._after_cursor(all_exchanges, wm.cursor if wm else None)
        if not pending:
            return []

        closed = self._session_is_closed(session, swept_at)
        units: list[CaptureUnit] = []
        i = 0
        while i < len(pending):
            window = pending[i:]

            # CAP: bound a runaway window deterministically (zero-LLM).
            if len(window) > self.config.max_window_exchanges:
                head = window[: self.config.max_window_exchanges]
                units.append(
                    self._make_unit(
                        scope=scope,
                        role=role,
                        exchanges=head,
                        boundary=BoundaryKind.CAP,
                        source_id=source_id,
                        forced=False,
                        swept_at=swept_at,
                    )
                )
                i += len(head)
                continue

            # SEMANTIC: background-only topic-shift cut within the batch.
            cut = await self._semantic_cut(window[: self.config.sweep_batch], role, scope)
            if cut is not None:
                head = window[: cut + 1]
                units.append(
                    self._make_unit(
                        scope=scope,
                        role=role,
                        exchanges=head,
                        boundary=BoundaryKind.SEMANTIC,
                        source_id=source_id,
                        forced=False,
                        swept_at=swept_at,
                    )
                )
                i += len(head)
                continue

            # No internal boundary left. Emit the remainder only if the stream is
            # actually closed/idle; otherwise leave it pending (don't cut an open
            # stream — that is what a later close/idle boundary is for).
            if closed:
                units.append(
                    self._make_unit(
                        scope=scope,
                        role=role,
                        exchanges=window,
                        boundary=BoundaryKind.SESSION,
                        source_id=source_id,
                        forced=False,
                        swept_at=swept_at,
                    )
                )
            break

        return units

    def _session_is_closed(self, session, now: str) -> bool:
        """A session counts as closed for sweep purposes when it has been idle
        past the idle window. Pure timing signal, zero LLM."""
        last_activity = getattr(session, "last_activity", None)
        if last_activity is None:
            return False
        last_iso = last_activity.isoformat() if hasattr(last_activity, "isoformat") else str(
            last_activity
        )
        # ISO TEXT compares chronologically (same UTC offset convention as the
        # store). Compute the idle threshold by string-safe parse where possible.
        try:
            from datetime import datetime

            last_dt = datetime.fromisoformat(last_iso)
            now_dt = datetime.fromisoformat(now)
            return (now_dt - last_dt).total_seconds() >= self.config.idle_seconds
        except Exception:
            return False

    async def _semantic_cut(
        self, window: list[RawExchange], role: ExchangeRole, scope: Scope
    ) -> int | None:
        """Background-only SEMANTIC check. Returns the index within `window` of
        the last exchange in the current unit, or None for no shift. Zero call
        when the window is too short to split or the judge is unavailable."""
        if self.cheap_llm is None or len(window) < 2:
            return None
        continuity = window[0].text.splitlines()[0] if window[0].text else ""
        batch = render_batch([(i, e.text) for i, e in enumerate(window)])
        user = SEMANTIC_BOUNDARY_USER.format(
            source_kind=role.value, continuity=continuity, batch=batch
        )
        try:
            decision = await self.cheap_llm.detect_boundary(
                system=SEMANTIC_BOUNDARY_SYSTEM, user=user, model=self.config.semantic_model
            )
        except Exception as e:
            _logger.warning("capture semantic boundary check failed: %s", e)
            return None
        if not decision.shift or decision.cut_after_index is None:
            return None
        idx = decision.cut_after_index
        # Validate: in range and not the final index (a cut after the last
        # element segments nothing). Drop-on-doubt.
        if 0 <= idx < len(window) - 1:
            return idx
        return None
