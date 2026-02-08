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
    )

    # OpenAI (for embeddings) - no prefix, standard env var
    openai_api_key: str = Field(alias="OPENAI_API_KEY")

    # LiteLLM model format: provider/model
    # Examples: anthropic/claude-sonnet-4, gemini/gemini-2.0-flash, openai/gpt-4o
    # LiteLLM reads API keys from standard env vars:
    #   ANTHROPIC_API_KEY, GEMINI_API_KEY (or GOOGLE_API_KEY), OPENAI_API_KEY
    chat_model: str = "gemini/gemini-3-flash-preview"
    memory_model: str = "gemini/gemini-2.0-flash"
    embedding_model: str = "text-embedding-3-small"
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

    # Obsidian vault
    vault_path: Path | None = None

    # Browser history (optional)
    browser: str | None = None
    browser_days: int = 30

    # Scheduling
    schedule_email: str | None = None

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


_config: Config | None = None


def get_config() -> Config:
    global _config
    if _config is not None:
        return _config
    config = Config()  # type: ignore - pydantic handles validation
    settings = load_user_settings()
    for key in ("chat_model", "memory_model", "embedding_model", "embedding_dim", "browser", "browser_days"):
        if key in settings:
            try:
                setattr(config, key, settings[key])
            except Exception:
                _logger.warning("Ignoring invalid saved setting %s=%r", key, settings[key])
    if "vault_path" in settings:
        config.vault_path = Path(settings["vault_path"])
    if "sources" in settings:
        src = settings["sources"]
        for key in ("gmail", "calendar", "memory"):
            if key in src:
                setattr(config, key, src[key])
    _config = config
    return _config
