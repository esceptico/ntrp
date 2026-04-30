import os
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from ntrp.embedder import EmbeddingConfig
from ntrp.llm.models import (
    Provider,
    get_embedding_model,
    get_embedding_models,
    get_models,
    get_models_by_provider,
    load_custom_models,
)
from ntrp.logging import get_logger
from ntrp.settings import NTRP_DIR, load_user_settings

_logger = get_logger(__name__)


# --- Provider / service mappings ---

PROVIDER_KEY_FIELDS = {
    "anthropic": "anthropic_api_key",
    "openai": "openai_api_key",
    "google": "gemini_api_key",
    "openrouter": "openrouter_api_key",
}

# provider_field → (default_chat, default_memory, default_embedding)
MODEL_DEFAULTS = {
    "anthropic_api_key": ("claude-sonnet-4-6", "claude-sonnet-4-6", None),
    "openai_api_key": ("gpt-5.2", "gpt-5.2", "text-embedding-3-small"),
    "gemini_api_key": ("gemini-3.1-pro-preview", "gemini-3-flash-preview", "gemini-embedding-001"),
}

PERSIST_KEYS = frozenset(
    {
        "chat_model",
        "research_model",
        "memory_model",
        "embedding_model",
        "memory",
        "dreams",
        "consolidation_interval",
        "google",
        "gmail_days",
        "max_depth",
        "reasoning_effort",
        "compression_threshold",
        "max_messages",
        "compression_keep_ratio",
        "summary_max_tokens",
        "mcp_servers",
        "web_search",
    }
)


# --- Config ---


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="NTRP_",
        env_file_encoding="utf-8",
        extra="allow",
        validate_assignment=True,
        populate_by_name=True,
    )

    ntrp_dir: Path = Field(default=NTRP_DIR, alias="NTRP_DIR")

    # API keys — read from standard env vars via aliases
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    openrouter_api_key: str | None = Field(default=None, alias="OPENROUTER_API_KEY")

    # Model IDs
    chat_model: str | None = None
    research_model: str | None = None
    memory_model: str | None = None
    embedding_model: str | None = None

    # Memory
    memory: bool = True
    dreams: bool = False
    consolidation_interval: int = 30

    # Google (Gmail + Calendar)
    google: bool = False
    gmail_days: int = 30

    # Exa web search
    exa_api_key: str | None = Field(default=None, alias="EXA_API_KEY")
    web_search: Literal["auto", "exa", "ddgs", "none"] = Field(default="auto", alias="WEB_SEARCH")

    # Telegram
    telegram_bot_token: str | None = Field(default=None, alias="TELEGRAM_BOT_TOKEN")

    # Slack
    slack_bot_token: str | None = Field(default=None, alias="SLACK_BOT_TOKEN")
    slack_user_token: str | None = Field(default=None, alias="SLACK_USER_TOKEN")

    # MCP servers
    mcp_servers: dict[str, dict] | None = None

    # Agent
    max_depth: int = 8
    reasoning_effort: str | None = None

    # Context compaction
    compression_threshold: float = 0.8
    max_messages: int = 120
    compression_keep_ratio: float = 0.2
    summary_max_tokens: int = 1500

    # Server
    host: str = "127.0.0.1"
    port: int = 6877

    # API authentication
    api_key_hash: str | None = None

    # --- Validators ---

    @model_validator(mode="after")
    def _resolve_model_defaults(self) -> Self:
        self._migrate_deprecated_env()
        self._resolve_chat_model()
        self._fill_model_fallbacks()
        self._resolve_embedding_model()
        return self

    def _migrate_deprecated_env(self) -> None:
        if not self.research_model and (legacy := os.environ.get("NTRP_EXPLORE_MODEL")):
            _logger.warning("NTRP_EXPLORE_MODEL is deprecated, use NTRP_RESEARCH_MODEL")
            self.research_model = legacy

    def _resolve_chat_model(self) -> None:
        if self.chat_model:
            return
        for field, (chat, memory, _) in MODEL_DEFAULTS.items():
            if getattr(self, field, None):
                self.chat_model = chat
                if not self.memory_model:
                    self.memory_model = memory
                return

    def _fill_model_fallbacks(self) -> None:
        if not self.memory_model and self.chat_model:
            self.memory_model = self.chat_model
        if not self.research_model and self.chat_model:
            self.research_model = self.chat_model

    def _resolve_embedding_model(self) -> None:
        if self.embedding_model:
            return
        for field, (_, _, embedding) in MODEL_DEFAULTS.items():
            if embedding and getattr(self, field, None):
                self.embedding_model = embedding
                return

    @field_validator("chat_model", "research_model", "memory_model")
    @classmethod
    def _validate_model(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v not in get_models():
            _logger.warning("Unknown model '%s' in settings, falling back to default", v)
            return None
        return v

    @field_validator("embedding_model")
    @classmethod
    def _validate_embedding_model(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v not in get_embedding_models():
            _logger.warning("Unknown embedding model '%s' in settings, falling back to default", v)
            return None
        return v

    @field_validator("web_search", mode="before")
    @classmethod
    def _normalize_web_search(cls, v: str | None) -> str:
        if v is None:
            return "auto"
        normalized = str(v).strip().lower()
        if normalized in ("", "auto"):
            return "auto"
        if normalized in ("exa", "ddgs", "none"):
            return normalized
        raise ValueError("web_search must be one of: auto, exa, ddgs, none")

    # --- Derived properties ---

    @property
    def has_providers(self) -> bool:
        return bool(self.anthropic_api_key or self.openai_api_key or self.gemini_api_key or self.openrouter_api_key)

    @property
    def has_any_model(self) -> bool:
        return self.has_providers or bool(get_models_by_provider(Provider.CUSTOM))

    @property
    def embedding(self) -> EmbeddingConfig | None:
        if not self.embedding_model:
            return None
        model = get_embedding_model(self.embedding_model)
        return EmbeddingConfig(model=model.id, dim=model.dim)

    @property
    def db_dir(self) -> Path:
        return self.ntrp_dir

    @property
    def sessions_db_path(self) -> Path:
        return self.db_dir / "sessions.db"

    @property
    def search_db_path(self) -> Path:
        return self.db_dir / "search.db"

    @property
    def memory_db_path(self) -> Path:
        return self.db_dir / "memory.db"


# --- Config loading ---


def _migrate_legacy_settings(settings: dict) -> None:
    if "sources" in settings:
        for key in ("gmail", "calendar", "google", "memory"):
            if key in settings["sources"]:
                settings.setdefault(key, settings["sources"][key])
    if "gmail" in settings or "calendar" in settings:
        settings.setdefault("google", settings.pop("gmail", False) or settings.pop("calendar", False))
    if "explore_model" in settings:
        settings.setdefault("research_model", settings.pop("explore_model"))


def get_config() -> Config:
    load_custom_models(NTRP_DIR)
    settings = load_user_settings()
    _migrate_legacy_settings(settings)

    overrides = {k: settings[k] for k in PERSIST_KEYS if k in settings}
    if "api_key_hash" in settings:
        overrides["api_key_hash"] = settings["api_key_hash"]

    config = Config(
        _env_file=(NTRP_DIR / ".env", ".env"),
        **overrides,
    )  # type: ignore

    # Fill stored API keys where env / .env didn't provide one
    for provider_id, field in PROVIDER_KEY_FIELDS.items():
        if getattr(config, field) is None and provider_id in settings.get("provider_keys", {}):
            setattr(config, field, settings["provider_keys"][provider_id])

    # service_keys are keyed by Config attr name (e.g. "slack_bot_token").
    # Legacy keys ("slack", "slack-user", "telegram", "exa") are migrated to
    # their Config attr names on read.
    _LEGACY_SERVICE_ID_MAP = {
        "slack": "slack_bot_token",
        "slack-user": "slack_user_token",
        "telegram": "telegram_bot_token",
        "exa": "exa_api_key",
    }
    stored_keys = settings.get("service_keys", {})
    for stored_id, api_key in stored_keys.items():
        attr = _LEGACY_SERVICE_ID_MAP.get(stored_id, stored_id)
        if hasattr(config, attr) and getattr(config, attr) is None:
            setattr(config, attr, api_key)

    return config
