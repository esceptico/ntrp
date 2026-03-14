# --- Content Truncation Limits ---

CONTENT_PREVIEW_LIMIT = 500
CONTENT_READ_LIMIT = 10000
EMBEDDING_TEXT_LIMIT = 8000
BASH_OUTPUT_LIMIT = 5000
DIFF_PREVIEW_LINES = 20


# --- Default Pagination ---

DEFAULT_READ_LINES = 500
DEFAULT_LIST_LIMIT = 50


# --- Agent Limits ---

AGENT_MAX_DEPTH = 8
AGENT_MAX_ITERATIONS = None

BASH_TIMEOUT = 120

EXPLORE_TIMEOUT = 300
SUBAGENT_DEFAULT_TIMEOUT = 300


# --- Text Processing ---

WEB_SEARCH_MAX_RESULTS = 20


# --- Conversation ---

CONVERSATION_GAP_THRESHOLD = 1800  # seconds (30 min) - show time gap note if exceeded


# --- Channel ---

CHANNEL_DISPATCH_WORKERS = 32


# --- Session ---

HISTORY_MESSAGE_LIMIT = 50  # max user/assistant messages returned for UI history
CONSOLIDATION_INTERVAL = 1800.0  # seconds between consolidation batches (30 min)


# --- Context Compaction ---

COMPRESSION_THRESHOLD = 0.8  # % of model token limit to trigger compaction
MAX_MESSAGES = 120  # message count ceiling — compress regardless of tokens
COMPRESSION_KEEP_RATIO = 0.2  # the most recent % of messages to keep uncompressed

# Tool result offloading: large results stored externally, compact reference in context
# Manus pattern: full representation → file, compact representation → context
OFFLOAD_THRESHOLD = 30000  # chars — results above this are offloaded to temp files (matches Claude Code)
OFFLOAD_PREVIEW_CHARS = 300  # chars kept in compact reference


# --- Display Truncation ---

BROWSER_TITLE_TRUNCATE = 50
EMAIL_SUBJECT_TRUNCATE = 40
EMAIL_FROM_TRUNCATE = 30
SNIPPET_TRUNCATE = 120
URL_TRUNCATE = 60


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
SYSTEM_PROMPT_OBSERVATION_LIMIT = 5  # max observations in system prompt memory context
OBSERVATION_HISTORY_LIMIT = 10  # max history entries kept per observation


# V2 Retrieval Recency
RECENCY_SIGMA_HOURS = 72  # Exponential boost: recency = exp(-hours_since_event / σ)


# --- Archival ---

ARCHIVE_DECAY_THRESHOLD = 0.1  # decay_score below this = eligible for archival
ARCHIVE_FACT_MIN_AGE_DAYS = 30  # minimum age before a fact can be archived
ARCHIVE_OBSERVATION_MIN_AGE_DAYS = 90  # observations need longer before archival
ARCHIVE_OBSERVATION_STALENESS_DAYS = 30  # no updates within this period = stale


# --- Search & Retrieval ---

RRF_K = 60
RRF_OVERFETCH_FACTOR = 2

# --- Context Compression (Summarizer) ---

SUMMARY_MAX_TOKENS = 1500

# --- Memory Consolidation ---

CONSOLIDATION_MAX_BACKOFF_MULTIPLIER = 16
USER_ENTITY_NAME = "User"

# --- Dream Mode ---

DREAM_MIN_FACTS = 20
DREAM_CLUSTER_FACTOR = 3
DREAM_MAX_PAIRS = 6  # max cluster pairs to cross-pollinate (caps LLM calls)
DREAM_DEDUP_THRESHOLD = 0.85  # cosine similarity — skip dreams too similar to recent ones
DREAM_TEMPERATURE = 0.7
DREAM_EVAL_TEMPERATURE = 0.3

# --- Observation Merge ---

OBSERVATION_MERGE_SIMILARITY_THRESHOLD = 0.90
OBSERVATION_MERGE_TEMPERATURE = 0.1

# --- Fact Merge ---

FACT_MERGE_SIMILARITY_THRESHOLD = 0.90  # lower than dedup (0.95) — LLM makes final call
FACT_MERGE_TEMPERATURE = 0.1

# --- Automation ---

FRIDAY_WEEKDAY = 4
DAYS_IN_WEEK = 7
SCHEDULER_POLL_INTERVAL = 60
SCHEDULER_STOP_TIMEOUT = 5
SCHEDULER_DEDUP_TTL = 86400  # 24 hours
SCHEDULER_EVENT_MAX_RETRIES = 5
SCHEDULER_EVENT_RETRY_BASE_SECONDS = 30
SCHEDULER_EVENT_RETRY_MAX_SECONDS = 1800

# --- Monitor ---

MONITOR_POLL_INTERVAL = 300  # 5 minutes
MONITOR_EVENT_APPROACHING_HORIZON_MINUTES = 5 * 60  # 5 hours
AUTOMATION_EVENT_APPROACHING_DEFAULT_LEAD_MINUTES = 60
MONITOR_CALENDAR_DAYS = 1
MONITOR_CALENDAR_LIMIT = 50

assert AUTOMATION_EVENT_APPROACHING_DEFAULT_LEAD_MINUTES <= MONITOR_EVENT_APPROACHING_HORIZON_MINUTES, (
    f"{AUTOMATION_EVENT_APPROACHING_DEFAULT_LEAD_MINUTES=} must be <= {MONITOR_EVENT_APPROACHING_HORIZON_MINUTES=}"
)
