import json
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from ntrp.constants import SUPPORTED_MODELS
from ntrp.embedder import EmbeddingConfig
from ntrp.logging import get_logger

NTRP_DIR = Path.home() / ".ntrp"
SETTINGS_PATH = NTRP_DIR / "settings.json"

_logger = get_logger(__name__)


def load_user_settings() -> dict:
    if not SETTINGS_PATH.exists():
        return {}
    try:
        return json.loads(SETTINGS_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        _logger.warning("Failed to load user settings", exc_info=True)
        return {}


def save_user_settings(settings: dict) -> None:
    NTRP_DIR.mkdir(exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(settings, indent=2))


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="NTRP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        validate_assignment=True,
        populate_by_name=True,
    )

    # OpenAI (optional, for embeddings/models)
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")

    # LiteLLM model format: provider/model
    # Examples: anthropic/claude-sonnet-4, gemini/gemini-2.0-flash, openai/gpt-4o
    # LiteLLM reads API keys from standard env vars:
    #   ANTHROPIC_API_KEY, GEMINI_API_KEY (or GOOGLE_API_KEY), OPENAI_API_KEY
    chat_model: str
    memory_model: str
    embedding_model: str
    embedding_dim: int = 1536
    embedding_prefix: bool = False

    # Memory (graph-based knowledge store)
    memory: bool = True

    # Gmail (optional)
    gmail: bool = False
    gmail_days: int = 30

    # Calendar (optional)
    calendar: bool = False

    # Exa.ai for web search (optional) - no prefix, standard env var
    exa_api_key: str | None = Field(default=None, alias="EXA_API_KEY")

    # Telegram bot token (optional) - no prefix, standard env var
    telegram_bot_token: str | None = Field(default=None, alias="TELEGRAM_BOT_TOKEN")

    # Obsidian vault
    vault_path: Path | None = None

    # Browser history (optional)
    browser: str | None = None
    browser_days: int = 30

    # API authentication (optional — required when exposed to network)
    api_key: str | None = None

    @field_validator("chat_model")
    @classmethod
    def _validate_chat_model(cls, v: str) -> str:
        if v not in SUPPORTED_MODELS:
            raise ValueError(f"Unsupported model: {v}. Must be one of: {', '.join(SUPPORTED_MODELS)}")
        return v

    @field_validator("browser_days")
    @classmethod
    def _validate_browser_days(cls, v: int) -> int:
        if not 1 <= v <= 365:
            raise ValueError(f"browser_days must be 1-365, got {v}")
        return v

    @property
    def embedding(self) -> EmbeddingConfig:
        return EmbeddingConfig(
            model=self.embedding_model,
            dim=self.embedding_dim,
            prefix=self.embedding_prefix,
        )

    @property
    def db_dir(self) -> Path:
        return NTRP_DIR

    @property
    def sessions_db_path(self) -> Path:
        return self.db_dir / "sessions.db"

    @property
    def search_db_path(self) -> Path:
        return self.db_dir / "search.db"

    @property
    def memory_db_path(self) -> Path:
        return self.db_dir / "memory.db"


PERSIST_KEYS = frozenset({
    "chat_model", "memory_model", "embedding_model", "embedding_dim",
    "embedding_prefix", "browser", "browser_days", "vault_path",
    "memory", "gmail", "gmail_days", "calendar",
})


def get_config() -> Config:
    settings = load_user_settings()

    # Flatten legacy sources nesting
    if "sources" in settings:
        for key in ("gmail", "calendar", "memory"):
            if key in settings["sources"]:
                settings.setdefault(key, settings["sources"][key])

    # Build config: init args (settings.json) > env vars > defaults
    overrides = {k: settings[k] for k in PERSIST_KEYS if k in settings}
    config = Config(**overrides)  # type: ignore - pydantic handles validation

    # Persist resolved config back so it survives restarts
    resolved = config.model_dump(include=PERSIST_KEYS)
    if resolved.get("vault_path") is not None:
        resolved["vault_path"] = str(resolved["vault_path"])
    if any(settings.get(k) != v for k, v in resolved.items()):
        settings.update(resolved)
        save_user_settings(settings)

    return config
