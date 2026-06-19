"""/init — full memory re-derivation driver.

Wipes every record EXCEPT pinned, resets the curator + consolidate watermarks,
re-derives memory from ALL chat transcripts through the worthiness curator,
consolidates the resulting pile, and rebuilds the artifact projection.

Re-derives from chat transcripts AND the connected integrations (calendar,
gmail, slack) via the source-agnostic curator (`ingest_items`).

Order matters: backup first (P0), then a FAIL-FAST wipe (P1 — abort the whole
run if it raises, surfacing the backup path), then per-session transcript
re-derivation (P2, isolated so one bad session can't abort the rest), the
integration pass (P2.5, each source isolated so one failing source — incl. a
missing OAuth scope — can't abort the others or the run), consolidation (P3),
and the artifact rebuild (P4). The shared `max_llm_calls` budget is threaded
across transcripts + every source.
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from ntrp.constants import INTEGRATION_INGEST_MAX_LLM_CALLS
from ntrp.logging import get_logger
from ntrp.memory.artifacts import ArtifactMemoryStore
from ntrp.memory.models import now_iso

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from ntrp.server.runtime.knowledge import KnowledgeRuntime

_logger = get_logger(__name__)

# A wide ceiling so the full chat history is enumerated (recent_session_scopes
# is the sweep's bounded worklist; re-derivation wants every chat session).
_SESSION_ENUMERATION_LIMIT = 100_000
_MAX_CONSOLIDATE_PASSES = 3
# Keep only the most recent N pre-wipe backups; older ones are pruned each /init
# so they don't accumulate unbounded (every run mints a uniquely-named copy).
INIT_BACKUP_KEEP = 3


def _prune_init_backups(db_path: Path, *, keep: int) -> None:
    backups = sorted(db_path.parent.glob(f"{db_path.name}.init-bak-*"))
    for stale in backups[:-keep] if keep > 0 else backups:
        try:
            stale.unlink()
        except OSError:
            _logger.warning("failed to prune old init backup %s", stale, exc_info=True)

# Per-source recency windows for the integration pass. Calendar is cheap and
# spans planning horizons (180d); gmail is the highest-volume source so its
# window is tightest (30d); slack sits in between (90d). A caller-supplied
# `recency_days` overrides ALL of these.
SOURCE_RECENCY_DAYS = {"calendar": 180, "gmail": 30, "slack": 90}
# How many items to pull per source before the pre-LLM filter. Gmail is highest
# volume so it gets the tightest cap.
_SOURCE_FETCH_LIMIT = {"calendar": 200, "gmail": 150, "slack": 300}
# Gmail labels whose messages are bulk/noise — dropped before any LLM call.
_GMAIL_NOISE_LABELS = frozenset(
    {"CATEGORY_PROMOTIONS", "CATEGORY_SOCIAL", "CATEGORY_UPDATES", "SPAM"}
)
_INTEGRATION_LABEL = "NEW DOCUMENTS"


async def run_memory_init(
    knowledge: KnowledgeRuntime,
    *,
    recency_days: int | None = None,
    max_llm_calls: int = 400,
    integration_clients: dict[str, object] | None = None,
    wipe: bool = False,
    progress: Callable[[str], None] | None = None,
) -> dict:
    """(Re)derive memory from chat transcripts + connected integrations.

    ADDITIVE by default (`wipe=False`): existing records are KEPT and the
    re-derivation reconciles against them (ADD/UPDATE/SUPERSEDE/NOOP), so /init can
    only enrich memory, never make it thinner. The re-derivation runs the curator
    in BULK mode — a generous gate that captures the user's durable history
    comprehensively, instead of the brutal turn-by-turn worthiness bar that admits
    almost nothing over a full-history pass. `wipe=True` is the destructive reset
    (wipe-except-pinned first) for when the pool is genuinely corrupt.

    Transcript re-derivation drains every chat session regardless of recency.
    `recency_days` overrides each integration's window. Returns a report dict.
    """

    def _report_progress(message: str) -> None:
        if progress is not None:
            progress(message)

    record_store = knowledge._record_store
    curator = knowledge.memory_curator
    consolidate = knowledge._consolidate
    if record_store is None or curator is None:
        raise RuntimeError("memory not ready: record store / curator unavailable")

    sessions = curator._sessions
    db_path = knowledge.config.memory_db_path

    # --- P0: backup ---------------------------------------------------------
    backup_path = f"{db_path}.init-bak-{now_iso().replace(':', '').replace('-', '')}"
    if db_path.exists():
        shutil.copy2(db_path, backup_path)
        _report_progress(f"backed up memory.db to {backup_path}")
        _prune_init_backups(db_path, keep=INIT_BACKUP_KEEP)
    else:
        backup_path = ""

    # --- P1: (optional wipe) + reset watermarks (FAIL-FAST) -----------------
    # Additive by default: keep existing records and let the bulk re-derivation
    # reconcile against them. A wipe is destructive and opt-in; if it raises we
    # abort BEFORE re-deriving (recoverable from backup_path). Watermarks are
    # always reset so the curator re-reads the FULL history of every transcript /
    # source rather than only new turns.
    wipe_result = {"deleted": 0, "kept_pinned": 0}
    if wipe:
        wipe_result = await record_store.wipe_except_pinned()
    await curator.reset_watermarks()
    await consolidate.reset_watermark()
    if wipe:
        _report_progress(f"wiped {wipe_result['deleted']} records, kept {wipe_result['kept_pinned']} pinned")
    else:
        _report_progress("additive run — keeping existing records, re-reading full history")

    # --- P2: re-derive from ALL chat transcripts ----------------------------
    scopes = await sessions.recent_session_scopes(_SESSION_ENUMERATION_LIMIT)
    sessions_processed = 0
    admitted = 0
    llm_calls = 0
    capped = False
    for row in scopes:
        if row["session_type"] != "chat" or row["origin_automation_id"] is not None:
            continue
        if llm_calls >= max_llm_calls:
            capped = True
            break
        budget = max_llm_calls - llm_calls
        try:
            result = await curator.curate_session_fully(row["session_id"], max_calls=budget, bulk=True)
        except Exception:
            _logger.warning("init: session curation failed", session_id=row["session_id"], exc_info=True)
            continue
        sessions_processed += 1
        admitted += result["admitted"]
        llm_calls += result["calls"]
        if result["capped"]:
            capped = True
            break
    _report_progress(f"re-derived from {sessions_processed} session(s): {admitted} records admitted")

    # --- P2.5: re-derive from connected integrations ------------------------
    # Each source is isolated: a fetch/scope/curation failure records an error in
    # the report and moves on — one bad source can NEVER abort the others or the
    # run. The shared budget continues from where transcripts left off.
    integrations: dict[str, dict] = {}
    clients = integration_clients or {}
    for source in ("calendar", "gmail", "slack"):
        client = clients.get(source)
        if client is None:
            continue  # not connected — skip silently
        if llm_calls >= max_llm_calls:
            capped = True
            integrations[source] = {"admitted": 0, "calls": 0, "capped": True}
            continue
        window = recency_days if recency_days is not None else SOURCE_RECENCY_DAYS[source]
        budget = max_llm_calls - llm_calls
        try:
            # /init re-derives the FULL window (since=None — watermarks were just
            # reset in P1); _ingest_one_source advances the watermark afterwards so
            # the periodic ingest that follows is incremental.
            result = await _ingest_one_source(
                curator, source, client, window_days=window, since=None, budget=budget,
                label=_INTEGRATION_LABEL, bulk=True,
            )
            integrations[source] = {"admitted": result["admitted"], "calls": result["calls"]}
            admitted += result["admitted"]
            llm_calls += result["calls"]
            if result["capped"]:
                capped = True
            _report_progress(f"{source}: {result['admitted']} records admitted")
        except Exception as e:
            _logger.warning("init: integration source failed", source=source, exc_info=True)
            integrations[source] = {"admitted": 0, "calls": 0, "error": str(e)}
            _report_progress(f"{source}: failed ({e})")

    # --- P3: consolidate (bounded loop) -------------------------------------
    consolidate_summary = {"merged": 0, "pruned": 0, "passes": 0}
    for _ in range(_MAX_CONSOLIDATE_PASSES):
        report = await consolidate.run_once()
        consolidate_summary["merged"] += report.merged
        consolidate_summary["pruned"] += report.pruned
        consolidate_summary["passes"] += 1
        if report.pruned == 0 and report.merged == 0:
            break
    _report_progress(f"consolidated in {consolidate_summary['passes']} pass(es)")

    # --- P4: rebuild artifact projection ------------------------------------
    # Full LLM synthesis (me.md + dossiers + active-work) when any LLM budget
    # remains; once the curation/ingestion budget is spent, fall back to the
    # mechanical projection so /init never blows past max_llm_calls.
    artifacts = ArtifactMemoryStore(knowledge.config.memory_artifacts_dir)
    synth_llm, synth_model = knowledge._memory_llm()
    if llm_calls >= max_llm_calls:
        synth_llm, synth_model = None, ""
    await artifacts.export_from_records(record_store, llm=synth_llm, model=synth_model)
    _report_progress("rebuilt artifact projection")

    return {
        "wiped": wipe,
        "deleted": wipe_result["deleted"],
        "kept_pinned": wipe_result["kept_pinned"],
        "sessions_processed": sessions_processed,
        "admitted": admitted,
        "capped": capped,
        "backup_path": backup_path,
        "consolidate": consolidate_summary,
        "integrations": integrations,
    }


async def run_integration_ingest(
    knowledge: KnowledgeRuntime,
    *,
    integration_clients: dict[str, object] | None = None,
    recency_days: int | None = None,
    max_llm_calls: int = INTEGRATION_INGEST_MAX_LLM_CALLS,
    progress: Callable[[str], None] | None = None,
) -> dict:
    """Incremental, NON-destructive integration ingest — the periodic counterpart
    to /init's P2.5. Per connected source, fetch only items newer than the stored
    per-source watermark, curate them into the pool, and advance the watermark. It
    does NOT wipe, reset, or rebuild artifacts; the nightly maintenance pass folds
    the new records into consolidation + the artifact projection.

    Each source is isolated (a fetch/scope/curation failure is recorded and the
    others continue). `max_llm_calls` caps the run across all sources. Returns
    {"admitted", "capped", "integrations"}."""
    curator = knowledge.memory_curator
    if curator is None:
        raise RuntimeError("memory not ready: curator unavailable")

    def _report(message: str) -> None:
        if progress is not None:
            progress(message)

    integrations: dict[str, dict] = {}
    clients = integration_clients or {}
    admitted = 0
    llm_calls = 0
    capped = False
    for source in ("calendar", "gmail", "slack"):
        client = clients.get(source)
        if client is None:
            continue  # not connected — skip silently
        if llm_calls >= max_llm_calls:
            capped = True
            integrations[source] = {"admitted": 0, "calls": 0, "capped": True}
            continue
        window = recency_days if recency_days is not None else SOURCE_RECENCY_DAYS[source]
        budget = max_llm_calls - llm_calls
        watermark = await curator.read_ingest_watermark(source)
        since = datetime.fromisoformat(watermark) if watermark else None
        try:
            result = await _ingest_one_source(
                curator, source, client, window_days=window, since=since, budget=budget, label=_INTEGRATION_LABEL
            )
            integrations[source] = {"admitted": result["admitted"], "calls": result["calls"]}
            admitted += result["admitted"]
            llm_calls += result["calls"]
            if result["capped"]:
                capped = True
            _report(f"{source}: {result['admitted']} new records")
        except Exception as e:
            _logger.warning("ingest: integration source failed", source=source, exc_info=True)
            integrations[source] = {"admitted": 0, "calls": 0, "error": str(e)}
            _report(f"{source}: failed ({e})")
    return {"admitted": admitted, "capped": capped, "integrations": integrations}


def _item_ts(item) -> datetime:
    """A RawItem's source timestamp as an aware-UTC datetime (the watermark axis).
    updated_at catches both new and edited items; naive datetimes are read as UTC."""
    ts = item.updated_at
    return ts if ts.tzinfo is not None else ts.replace(tzinfo=UTC)


def _effective_window(window_days: int, since: datetime | None) -> int:
    """Shrink the fetch window to just past the watermark so an incremental run
    pulls a day or two, not the full recency horizon. Capped by window_days."""
    if since is None:
        return window_days
    days = (datetime.now(UTC) - since).days + 1
    return max(1, min(window_days, days))


async def _ingest_one_source(
    curator, source: str, client, *, window_days: int, since: datetime | None, budget: int, label: str,
    bulk: bool = False,
) -> dict:
    """Fetch (incrementally, if `since`), curate, and advance the watermark for one
    source. Shared by /init (since=None, full window, bulk gate) and the periodic
    incremental ingest (since=watermark, default gate)."""
    items = await _fetch_source_items(source, client, _effective_window(window_days, since), since=since)
    result = await curator.ingest_items(items, source_kind=source, source_label=label, max_calls=budget, bulk=bulk)
    # Advance the watermark to the newest item seen — but only on a clean (not
    # capped) pass, so a capped source re-fetches its tail next run.
    # ponytail: the max is over kept (post-noise-filter) items, so a window of
    # pure noise won't advance the watermark; bounded by window_days, no LLM cost.
    if not result["capped"]:
        newest = max((_item_ts(it) for it in items), default=None)
        if newest is not None:
            await curator.write_ingest_watermark(source, newest.isoformat())
    return result


async def _fetch_source_items(source: str, client, window_days: int, *, since: datetime | None = None) -> list:
    """Pull RawItems for one source over its recency window, apply the cheap
    pre-LLM noise filter, then drop anything at/older than `since` (the watermark).
    Returns the survivors (the curator's worthiness gate is the backstop; these
    filters just cut volume/cost before any LLM call)."""
    if source == "calendar":
        items = _filter_calendar(_fetch_calendar(client, window_days))
    elif source == "gmail":
        items = _filter_gmail(_fetch_gmail(client, window_days))
    elif source == "slack":
        items = _filter_slack(await _fetch_slack(client, window_days))
    else:
        return []
    if since is not None:
        items = [it for it in items if _item_ts(it) > since]
    return items


# -- calendar ----------------------------------------------------------------


def _fetch_calendar(client, window_days: int) -> list:
    """Calendar exposes get_past/get_upcoming (both -> list[RawItem]); /init wants
    the recent past, so pull get_past over the window."""
    limit = _SOURCE_FETCH_LIMIT["calendar"]
    return list(client.get_past(days=window_days, limit=limit))


def _filter_calendar(items: list) -> list:
    """Drop events the user declined, when the per-attendee response status is
    surfaced in metadata (defensive — absent on the current RawItem shape)."""
    kept = []
    for item in items:
        meta = getattr(item, "metadata", {}) or {}
        response = str(meta.get("response_status") or meta.get("self_response_status") or "").lower()
        if response == "declined":
            continue
        kept.append(item)
    return kept


# -- gmail --------------------------------------------------------------------


def _fetch_gmail(client, window_days: int) -> list:
    """Gmail's search returns metadata-only RawItems (snippet as content, labelIds
    in metadata) — the cheap metadata gate. `newer_than:Nd` bounds the window."""
    limit = _SOURCE_FETCH_LIMIT["gmail"]
    return list(client.search(f"newer_than:{window_days}d", limit=limit))


def _filter_gmail(items: list) -> list:
    """Drop bulk/category mail (promotions/social/updates/spam) BEFORE any LLM
    call — highest-volume source, so the label gate is the main cost lever."""
    kept = []
    for item in items:
        meta = getattr(item, "metadata", {}) or {}
        labels = {str(label) for label in (meta.get("labels") or [])}
        if labels & _GMAIL_NOISE_LABELS:
            continue
        kept.append(item)
    return kept


# -- slack --------------------------------------------------------------------


async def _fetch_slack(client, window_days: int) -> list:
    """Slack has no cross-DM 'recent' enumerator; list the open DMs (1-on-1,
    private) then read each channel's recent history. A missing-scope error
    (list_dms needs im:read, read_channel needs the relevant history scope)
    raises RuntimeError, which the caller records as a degraded source."""
    items: list = []
    dms = await client.list_dms(limit=_SOURCE_FETCH_LIMIT["slack"])
    per_dm = max(_SOURCE_FETCH_LIMIT["slack"] // max(len(dms), 1), 20)
    for dm in dms:
        channel_id = dm.get("channel_id") if isinstance(dm, dict) else None
        if not channel_id:
            continue
        items.extend(await client.read_channel(channel_id, limit=per_dm))
    return items


def _filter_slack(items: list) -> list:
    """Keep only real human DM/private messages: skip bot messages and system
    subtypes (joins/leaves/topic changes), and empty-body messages."""
    kept = []
    for item in items:
        meta = getattr(item, "metadata", {}) or {}
        if meta.get("subtype"):
            continue
        if meta.get("is_bot") or meta.get("bot_id"):
            continue
        if not meta.get("user_id"):
            continue  # bot/system message with no human author
        if not (getattr(item, "content", "") or "").strip():
            continue
        kept.append(item)
    return kept
