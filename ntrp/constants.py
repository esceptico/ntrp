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

EXPLORE_TIMEOUT = 300
EXPLORE_MODEL_DEFAULT = "gemini-3-flash-preview"
SUBAGENT_DEFAULT_TIMEOUT = 300


# --- Text Processing ---

WEB_SEARCH_MAX_RESULTS = 20


# --- Conversation ---

CONVERSATION_GAP_THRESHOLD = 1800  # seconds (30 min) - show time gap note if exceeded


# --- Session ---

SESSION_EXPIRY_HOURS = 24
HISTORY_MESSAGE_LIMIT = 50  # max user/assistant messages returned for UI history
CONSOLIDATION_INTERVAL = 30.0  # seconds between consolidation batches


# --- Context Compaction ---

COMPRESSION_THRESHOLD = 0.80  # % of model token limit to trigger compaction
MAX_MESSAGES = 80  # message count ceiling — compress regardless of tokens
COMPRESSION_KEEP_RATIO = 0.50  # keep most recent 50% of messages, compress the rest

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

# Forget operation
FORGET_SIMILARITY_THRESHOLD = 0.8
FORGET_SEARCH_LIMIT = 10

# Recall: search and expand graph context
RECALL_SEARCH_LIMIT = 5  # seed nodes from search
RECALL_OBSERVATION_LIMIT = 5  # max observations in context


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

# --- Dream Mode ---

DREAM_MIN_FACTS = 20
DREAM_CLUSTER_FACTOR = 3
DREAM_TEMPERATURE = 0.7
DREAM_EVAL_TEMPERATURE = 0.3

# --- Observation Merge ---

OBSERVATION_MERGE_SIMILARITY_THRESHOLD = 0.90
OBSERVATION_MERGE_TEMPERATURE = 0.1

# --- Schedule ---

FRIDAY_WEEKDAY = 4

# --- Indexing ---

INDEXABLE_SOURCES = {"notes", "memory"}
