# --- Content Truncation Limits ---

EMBEDDING_TEXT_LIMIT = 8000  # for embedder input only — see embedder.py
DIFF_PREVIEW_LINES = 20


# --- Default Pagination ---

DEFAULT_READ_LINES = 500
DEFAULT_LIST_LIMIT = 50


# --- Agent Limits ---

AGENT_MAX_DEPTH = 8
AGENT_MAX_ITERATIONS = None
AGENT_MAX_TOOL_CALLS = None
AGENT_MAX_WALL_TIME_SECONDS = None
AGENT_MAX_COST = None

BASH_TIMEOUT = 120  # seconds — safety brake against runaway commands

RESEARCH_TIMEOUT = None
SUBAGENT_DEFAULT_TIMEOUT = None
BACKGROUND_AGENT_TIMEOUT = None
COMPACTION_TIMEOUT = 600
DEFAULT_EXTERNAL_TOOL_TIMEOUT_SECONDS = 120


# --- Text Processing ---

WEB_SEARCH_MAX_RESULTS = 20


# --- Conversation ---

CONVERSATION_GAP_THRESHOLD = 1800  # seconds (30 min) - show time gap note if exceeded


# --- Outbox ---

OUTBOX_BATCH_SIZE = 20
OUTBOX_MAX_RETRIES = 5
OUTBOX_POLL_INTERVAL = 1.0
OUTBOX_RETRY_BASE_SECONDS = 5
OUTBOX_RETRY_MAX_SECONDS = 300
OUTBOX_STALE_LOCK_SECONDS = 300
OUTBOX_COMPLETED_RETENTION_DAYS = 30
OUTBOX_PRUNE_BATCH_SIZE = 1000
OUTBOX_PRUNE_INTERVAL_SECONDS = 3600


# --- Session ---

HISTORY_MESSAGE_LIMIT = 50  # max user/assistant messages returned for UI history

# Iteration-mode loops re-enter the target session and would otherwise see
# the entire prior history. Cap to the last N messages (system row at
# index 0 is preserved). Runtime-only; disk history is untouched.
LOOP_ITERATION_HISTORY_WINDOW = 50


# --- Context Compaction ---

COMPRESSION_THRESHOLD = 0.8  # % of model token limit to trigger compaction
COMPRESSION_TOKEN_HEADROOM = 0.95  # compact before the next prompt can push past threshold
MAX_MESSAGES = 120  # message count ceiling — compress regardless of tokens
COMPRESSION_KEEP_RATIO = 0.2  # the most recent % of messages to keep uncompressed
SESSION_HANDOFF_MARKER = "[Session State Handoff]"

# Tool result offloading: large results stored externally, compact reference in context.
# Manus pattern: full representation → file, compact representation → context.
#
# This is the ONE knob that gates tool-result truncation. Tools must not
# trim their own output without leaving a continuation path — any such
# in-tool truncation is a bug. NtrpToolExecutor._maybe_offload moves the
# full content to NTRP_TMP_BASE/<session>/results/<tool>_<n>.txt and
# returns a head preview + file path so the agent can grep/read it.
NTRP_TMP_BASE = "/tmp/ntrp"
OFFLOAD_THRESHOLD = 50000  # chars — results above this are offloaded to temp files
OFFLOAD_PREVIEW_LINES = 30  # lines kept in compact reference (structural summary, not raw chars)
OFFLOAD_PREVIEW_CHARS = 12000  # hard cap for compact references; full content remains in the offload file


# --- Display Truncation ---

EMAIL_SUBJECT_TRUNCATE = 40
EMAIL_FROM_TRUNCATE = 30
SNIPPET_TRUNCATE = 120


# --- Knowledge ---

KNOWLEDGE_REFLECTION_EVERY_N_TURNS = 10
OBSERVATION_HISTORY_LIMIT = 10  # max history entries kept per observation


# --- Search & Retrieval ---

RRF_K = 60
RRF_OVERFETCH_FACTOR = 2

# --- Context Compression (Summarizer) ---

SUMMARY_MAX_TOKENS = 1500

# --- Automation ---

FRIDAY_WEEKDAY = 4
DAYS_IN_WEEK = 7
SCHEDULER_POLL_INTERVAL = 60  # seconds; safety-net poll. Real fire timing is
# event-driven: `handle_run_completed` fires session-bound loops the moment the
# target session goes idle, and `_start_run` advances `next_run_at` before the
# task body so the UI countdown ticks during long runs. This poll is the
# fallback for non-session-bound automations and post-crash reconciliation.
SCHEDULER_STOP_TIMEOUT = 5
SCHEDULER_DEDUP_TTL = 86400  # 24 hours
SCHEDULER_EVENT_MAX_RETRIES = 5
SCHEDULER_EVENT_RETRY_BASE_SECONDS = 30
SCHEDULER_EVENT_RETRY_MAX_SECONDS = 1800

# Builtin knowledge automations
BUILTIN_KNOWLEDGE_REFLECTION_ID = "builtin:knowledge-reflection"
BUILTIN_KNOWLEDGE_REFLECTION_SWEEP_ID = "builtin:knowledge-reflection-sweep"
BUILTIN_KNOWLEDGE_PROFILE_REFRESH_ID = "builtin:knowledge-profile-refresh"
BUILTIN_KNOWLEDGE_RETENTION_ID = "builtin:knowledge-retention"
BUILTIN_KNOWLEDGE_HEALTH_ID = "builtin:knowledge-health"
BUILTIN_PATTERN_FINDER_DAILY_ID = "builtin:pattern-finder-daily"
DEFAULT_KNOWLEDGE_REFLECTION_IDLE_MINUTES = 5
DEFAULT_KNOWLEDGE_REFLECTION_SWEEP_IDLE_MINUTES = 5
DEFAULT_KNOWLEDGE_REFLECTION_SWEEP_COOLDOWN_MINUTES = 30
DEFAULT_KNOWLEDGE_PROFILE_REFRESH_IDLE_MINUTES = 15
DEFAULT_KNOWLEDGE_PROFILE_REFRESH_COOLDOWN_MINUTES = 2 * 60
DEFAULT_KNOWLEDGE_RETENTION_COOLDOWN_MINUTES = 24 * 60
DEFAULT_KNOWLEDGE_HEALTH_COOLDOWN_MINUTES = 24 * 60

# --- Monitor ---

MONITOR_POLL_INTERVAL = 300  # 5 minutes
MONITOR_EVENT_APPROACHING_HORIZON_MINUTES = 5 * 60  # 5 hours
AUTOMATION_EVENT_APPROACHING_DEFAULT_LEAD_MINUTES = 60
MONITOR_CALENDAR_DAYS = 1
MONITOR_CALENDAR_LIMIT = 50

assert AUTOMATION_EVENT_APPROACHING_DEFAULT_LEAD_MINUTES <= MONITOR_EVENT_APPROACHING_HORIZON_MINUTES, (
    f"{AUTOMATION_EVENT_APPROACHING_DEFAULT_LEAD_MINUTES=} must be <= {MONITOR_EVENT_APPROACHING_HORIZON_MINUTES=}"
)
