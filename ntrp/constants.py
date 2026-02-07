from typing import Any

# --- Content Truncation Limits ---

CONTENT_PREVIEW_LIMIT = 500
CONTENT_READ_LIMIT = 10000
EMBEDDING_TEXT_LIMIT = 8000
BASH_OUTPUT_LIMIT = 5000
DIFF_PREVIEW_LINES = 20


# --- Default Pagination ---

DEFAULT_READ_LINES = 500
DEFAULT_LIST_LIMIT = 50


# --- Supported Models ---
# LiteLLM format: provider/model -> {tokens, request_kwargs?}
# Single source of truth for UI selection, context compression, and provider routing
# "request_kwargs" are merged into litellm completion calls as-is

SUPPORTED_MODELS: dict[str, dict[str, Any]] = {
    "anthropic/claude-sonnet-4-5-20250929": {"tokens": 200000},
    "openai/gpt-5.2": {"tokens": 200000},
    "gemini/gemini-3-pro-preview": {"tokens": 900000},
    "gemini/gemini-3-flash-preview": {"tokens": 900000},
    "openrouter/moonshotai/kimi-k2.5": {
        "tokens": 200000,
        "request_kwargs": {
            "extra_body": {"provider": {"order": ["moonshotai"], "allow_fallbacks": False}},
        },
    },
    "openrouter/arcee-ai/trinity-large-preview:free": {"tokens": 200000},
}

# Embedding models (OpenAI): model -> dimension
EMBEDDING_MODELS: dict[str, int] = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}


# --- Agent Limits ---

AGENT_MAX_DEPTH = 8
AGENT_MAX_ITERATIONS = 50

EXPLORE_TIMEOUT = 180
SUBAGENT_DEFAULT_TIMEOUT = 180


# --- Text Processing ---

WEB_SEARCH_MAX_RESULTS = 20


# --- Conversation ---

CONVERSATION_GAP_THRESHOLD = 1800  # seconds (30 min) - show time gap note if exceeded


# --- Session ---

SESSION_EXPIRY_HOURS = 24
CONSOLIDATION_INTERVAL = 30.0  # seconds between consolidation batches
CHARS_PER_TOKEN = 4  # rough char-to-token ratio for estimation


# --- Context Compaction ---

COMPRESSION_THRESHOLD = 0.75  # % of model limit to trigger compaction
TAIL_TOKEN_BUDGET = 8000  # tokens kept verbatim during compaction
MASK_THRESHOLD = 300  # chars — tool results below this are left as-is
MASK_PREVIEW_CHARS = 200  # chars kept when masking old tool results

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
ENTITY_RESOLUTION_AUTO_MERGE = 0.85  # score threshold for auto-merging entities
ENTITY_RESOLUTION_NAME_SIM_THRESHOLD = 0.5  # minimum name similarity to consider candidate
ENTITY_TEMPORAL_SIGMA_HOURS = 168  # 1 week for temporal proximity scoring
ENTITY_TEMPORAL_NEUTRAL = 0.5  # neutral score when temporal info unknown
ENTITY_SCORE_COOCCURRENCE_WEIGHT = 0.5
ENTITY_SCORE_NAME_WEIGHT = 0.3
ENTITY_SCORE_TEMPORAL_WEIGHT = 0.2
ENTITY_CANDIDATES_LIMIT = 50  # max candidates to consider during resolution

# LLM temperatures
EXTRACTION_TEMPERATURE = 0.0  # deterministic extraction
CONSOLIDATION_TEMPERATURE = 0.1  # very deterministic for consolidation decisions

# Forget operation
FORGET_SIMILARITY_THRESHOLD = 0.8
FORGET_SEARCH_LIMIT = 10

# Recall: search and expand graph context
RECALL_SEARCH_LIMIT = 5  # seed nodes from search
RECALL_OBSERVATION_LIMIT = 5  # max observations in context

# V2 Fact Linking
LINK_TEMPORAL_SIGMA_HOURS = 12  # Exponential decay: weight = exp(-Δt / σ), half-life ~8h
LINK_TEMPORAL_MIN_WEIGHT = 0.01  # Floor to avoid tiny weights
LINK_SEMANTIC_THRESHOLD = 0.7
LINK_SEMANTIC_SEARCH_LIMIT = 20

# V2 Scored BFS
BFS_DECAY_FACTOR = 0.8
BFS_SCORE_THRESHOLD = 1e-6
BFS_MAX_FACTS = 50

# V2 Retrieval Recency
RECENCY_SIGMA_HOURS = 72  # Exponential boost: recency = exp(-hours_since_event / σ)
