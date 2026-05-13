# --- Content Truncation Limits ---

EMBEDDING_TEXT_LIMIT = 8000  # for embedder input only — see embedder.py
DIFF_PREVIEW_LINES = 20


# --- Default Pagination ---

DEFAULT_READ_LINES = 500
DEFAULT_LIST_LIMIT = 50


# --- Agent Limits ---

AGENT_MAX_DEPTH = 8
AGENT_MAX_ITERATIONS = None

BASH_TIMEOUT = 120  # seconds — safety brake against runaway commands

RESEARCH_TIMEOUT = None
SUBAGENT_DEFAULT_TIMEOUT = None
BACKGROUND_AGENT_TIMEOUT = None
CONSOLIDATION_PASS_TIMEOUT = None
COMPACTION_TIMEOUT = None


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
CONSOLIDATION_INTERVAL = 1800.0  # seconds between consolidation batches (30 min)

# Iteration-mode loops re-enter the target session and would otherwise see
# the entire prior history. Cap to the last N messages (system row at
# index 0 is preserved). Runtime-only; disk history is untouched.
LOOP_ITERATION_HISTORY_WINDOW = 50


# --- Context Compaction ---

COMPRESSION_THRESHOLD = 0.8  # % of model token limit to trigger compaction
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


# --- Display Truncation ---

EMAIL_SUBJECT_TRUNCATE = 40
EMAIL_FROM_TRUNCATE = 30
SNIPPET_TRUNCATE = 120


# --- Chat Extraction ---

EXTRACTION_EVERY_N_TURNS = 10  # extract after every N completed runs
EXTRACTION_CONTEXT_MESSAGES = 10  # preceding messages included for LLM understanding


# --- Memory ---

# Decay formula: score = DECAY_RATE ^ (hours / strength)
# where strength = log(access_count + 1) + 1
# Reference: Park et al. (2023) "Generative Agents" https://arxiv.org/abs/2304.03442
MEMORY_DECAY_RATE = 0.99

# Consolidation: per-fact LLM-driven consolidation into observations
CONSOLIDATION_SEARCH_LIMIT = 5  # observation candidates to consider

# Entity Resolution
ENTITY_EXPANSION_MAX_FACTS = 50  # max facts returned from entity expansion
ENTITY_EXPANSION_PER_ENTITY_LIMIT = 20  # max facts per entity during expansion
ENTITY_EXPANSION_IDF_FLOOR = 0.2  # skip entities with IDF below this (freq > ~30)
TEMPORAL_EXPANSION_LIMIT = 10  # facts fetched by temporal proximity search
TEMPORAL_EXPANSION_BASE_SCORE = 0.3  # base score for temporally expanded facts

# LLM temperatures
EXTRACTION_TEMPERATURE = 0.0  # deterministic extraction
CONSOLIDATION_TEMPERATURE = 0.1  # very deterministic for consolidation decisions

# Fact dedup: skip storing near-identical facts at ingest time
# Two independent paths — either one triggers dedup:
FACT_DEDUP_TEXT_RATIO = 0.85  # SequenceMatcher ratio — model-independent, catches near-exact text
FACT_DEDUP_EMBEDDING_SIMILARITY = 0.95  # cosine similarity — catches semantic duplicates

# Forget operation
FORGET_SIMILARITY_THRESHOLD = 0.8
FORGET_SEARCH_LIMIT = 10

# Recall: search and expand graph context
RECALL_SEARCH_LIMIT = 5  # seed nodes from search
RECALL_OBSERVATION_LIMIT = 5  # max observations in context
RECALL_STANDALONE_FACT_LIMIT = 10  # max standalone facts (not bundled with observations)
CONSOLIDATED_FACT_RECALL_WEIGHT = 0.85  # processed facts remain recallable, just slightly lower priority
SYSTEM_PROMPT_OBSERVATION_LIMIT = 5  # max observations in system prompt memory context
OBSERVATION_HISTORY_LIMIT = 10  # max history entries kept per observation


# V2 Retrieval Recency
RECENCY_SIGMA_HOURS = 72  # Exponential boost: recency = exp(-hours_since_event / σ)


# --- Search & Retrieval ---

RRF_K = 60
RRF_OVERFETCH_FACTOR = 2

# --- Context Compression (Summarizer) ---

SUMMARY_MAX_TOKENS = 1500

# --- Memory Consolidation ---

CONSOLIDATION_MAX_BACKOFF_MULTIPLIER = 16
USER_ENTITY_NAME = "User"

OBSERVATION_DUPLICATE_SIMILARITY_THRESHOLD = 0.90

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

# Builtin automations
BUILTIN_CHAT_EXTRACTION_ID = "builtin:chat-extraction"
BUILTIN_CONSOLIDATION_ID = "builtin:consolidation"
BUILTIN_MEMORY_MAINTENANCE_ID = "builtin:memory-maintenance"
BUILTIN_MEMORY_HEALTH_ID = "builtin:memory-health"
DEFAULT_EXTRACTION_IDLE_MINUTES = 5
DEFAULT_CONSOLIDATION_IDLE_MINUTES = 5
DEFAULT_CONSOLIDATION_COOLDOWN_MINUTES = 30
DEFAULT_MEMORY_MAINTENANCE_COOLDOWN_MINUTES = 24 * 60
DEFAULT_MEMORY_HEALTH_COOLDOWN_MINUTES = 24 * 60

# --- Monitor ---

MONITOR_POLL_INTERVAL = 300  # 5 minutes
MONITOR_EVENT_APPROACHING_HORIZON_MINUTES = 5 * 60  # 5 hours
AUTOMATION_EVENT_APPROACHING_DEFAULT_LEAD_MINUTES = 60
MONITOR_CALENDAR_DAYS = 1
MONITOR_CALENDAR_LIMIT = 50

assert AUTOMATION_EVENT_APPROACHING_DEFAULT_LEAD_MINUTES <= MONITOR_EVENT_APPROACHING_HORIZON_MINUTES, (
    f"{AUTOMATION_EVENT_APPROACHING_DEFAULT_LEAD_MINUTES=} must be <= {MONITOR_EVENT_APPROACHING_HORIZON_MINUTES=}"
)
