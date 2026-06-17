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
from typing import TYPE_CHECKING

from ntrp.logging import get_logger
from ntrp.memory.artifacts import ArtifactMemoryStore
from ntrp.memory.models import now_iso

if TYPE_CHECKING:
    from collections.abc import Callable

    from ntrp.server.runtime.knowledge import KnowledgeRuntime

_logger = get_logger(__name__)

# A wide ceiling so the full chat history is enumerated (recent_session_scopes
# is the sweep's bounded worklist; re-derivation wants every chat session).
_SESSION_ENUMERATION_LIMIT = 100_000
_MAX_CONSOLIDATE_PASSES = 3

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
    progress: Callable[[str], None] | None = None,
) -> dict:
    """Re-derive the whole memory from chat transcripts + connected integrations.

    Transcript re-derivation drains every chat session regardless of recency.
    `recency_days` is an OVERRIDE: when None each integration uses its entry in
    SOURCE_RECENCY_DAYS; when set it applies uniformly to every source.
    `integration_clients` is the connected-client map (registry.clients); sources
    not present are skipped. Returns a report dict.
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
    else:
        backup_path = ""

    # --- P1: wipe + reset watermarks (FAIL-FAST) ----------------------------
    # If the wipe raises we abort BEFORE re-deriving — the half-state is
    # recoverable from backup_path, surfaced via the raised error's context.
    wipe = await record_store.wipe_except_pinned()
    await curator.reset_watermarks()
    await consolidate.reset_watermark()
    _report_progress(f"wiped {wipe['deleted']} records, kept {wipe['kept_pinned']} pinned")

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
            result = await curator.curate_session_fully(row["session_id"], max_calls=budget)
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
            items = await _fetch_source_items(source, client, window)
            result = await curator.ingest_items(
                items,
                source_kind=source,
                source_label=_INTEGRATION_LABEL,
                max_calls=budget,
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
    artifacts = ArtifactMemoryStore(knowledge.config.memory_artifacts_dir)
    await artifacts.export_from_records(record_store)
    _report_progress("rebuilt artifact projection")

    return {
        "deleted": wipe["deleted"],
        "kept_pinned": wipe["kept_pinned"],
        "sessions_processed": sessions_processed,
        "admitted": admitted,
        "capped": capped,
        "backup_path": backup_path,
        "consolidate": consolidate_summary,
        "integrations": integrations,
    }


async def _fetch_source_items(source: str, client, window_days: int) -> list:
    """Pull RawItems for one source over its recency window, then apply the cheap
    pre-LLM noise filter. Returns the survivors (the curator's worthiness gate is
    the backstop; these filters just cut volume/cost before any LLM call)."""
    if source == "calendar":
        return _filter_calendar(_fetch_calendar(client, window_days))
    if source == "gmail":
        return _filter_gmail(_fetch_gmail(client, window_days))
    if source == "slack":
        return _filter_slack(await _fetch_slack(client, window_days))
    return []


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
