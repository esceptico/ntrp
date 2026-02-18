import json
from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from ntrp.embedder import EmbeddingConfig
from ntrp.llm.models import DEFAULTS, EMBEDDING_DEFAULTS
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

    # API keys — read from standard env vars via aliases
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    openrouter_api_key: str | None = Field(default=None, alias="OPENROUTER_API_KEY")

    # Model IDs (must match entries in llm/models.py DEFAULTS or user config)
    chat_model: str
    explore_model: str | None = None
    memory_model: str
    embedding_model: str

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

    @model_validator(mode="after")
    def _default_explore_model(self) -> "Config":
        if not self.explore_model:
            self.explore_model = self.chat_model
            _logger.info("explore_model not set, defaulting to chat_model: %s", self.chat_model)
        return self

    @field_validator("chat_model", "explore_model")
    @classmethod
    def _validate_chat_model(cls, v: str | None) -> str | None:
        if v is None:
            return v
        valid = {m.id for m in DEFAULTS}
        if v not in valid:
            raise ValueError(f"Unsupported model: {v}. Must be one of: {', '.join(valid)}")
        return v

    @field_validator("embedding_model")
    @classmethod
    def _validate_embedding_model(cls, v: str) -> str:
        valid = {m.id for m in EMBEDDING_DEFAULTS}
        if v not in valid:
            raise ValueError(f"Unsupported embedding model: {v}. Must be one of: {', '.join(valid)}")
        return v

    @field_validator("browser", mode="before")
    @classmethod
    def _normalize_browser(cls, v: str | None) -> str | None:
        if v in ("", "none"):
            return None
        return v

    @field_validator("browser_days")
    @classmethod
    def _validate_browser_days(cls, v: int) -> int:
        if not 1 <= v <= 365:
            raise ValueError(f"browser_days must be 1-365, got {v}")
        return v

    @property
    def embedding(self) -> EmbeddingConfig:
        dims = {m.id: m.dim for m in EMBEDDING_DEFAULTS}
        return EmbeddingConfig(
            model=self.embedding_model,
            dim=dims[self.embedding_model],
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


PERSIST_KEYS = frozenset(
    {
        "chat_model",
        "explore_model",
        "memory_model",
        "embedding_model",
        "browser",
        "browser_days",
        "vault_path",
        "memory",
        "gmail",
        "gmail_days",
        "calendar",
    }
)


def get_config() -> Config:
    settings = load_user_settings()

    # Flatten legacy sources nesting
    if "sources" in settings:
        for key in ("gmail", "calendar", "memory"):
            if key in settings["sources"]:
                settings.setdefault(key, settings["sources"][key])

    # Build config: init args (settings.json) > env vars > defaults
    overrides = {k: settings[k] for k in PERSIST_KEYS if k in settings}
    return Config(**overrides)  # type: ignore - pydantic handles validation
