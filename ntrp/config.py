import json
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from ntrp.logging import get_logger

NTRP_DIR = Path.home() / ".ntrp"
SETTINGS_PATH = NTRP_DIR / "settings.json"

logger = get_logger(__name__)


def load_user_settings() -> dict:
    if not SETTINGS_PATH.exists():
        return {}
    try:
        return json.loads(SETTINGS_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        logger.warning("Failed to load user settings", exc_info=True)
        return {}


def save_user_settings(settings: dict) -> None:
    NTRP_DIR.mkdir(exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(settings, indent=2))


class Config(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="NTRP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Required
    vault_path: Path = Field(description="Path to Obsidian vault")

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

    # Browser history (optional)
    browser: str | None = None  # "chrome", "arc", "safari", or None to disable
    browser_days: int = 30

    # Gmail (optional)
    gmail: bool = False
    gmail_days: int = 30

    # Calendar (optional)
    calendar: bool = False

    # Exa.ai for web search (optional) - no prefix, standard env var
    exa_api_key: str | None = Field(default=None, alias="EXA_API_KEY")

    # Scheduling
    schedule_email: str | None = None

    @property
    def db_dir(self) -> Path:
        db_dir = Path.home() / ".ntrp"
        db_dir.mkdir(exist_ok=True)
        return db_dir

    @property
    def sessions_db_path(self) -> Path:
        return self.db_dir / "sessions.db"

    @property
    def search_db_path(self) -> Path:
        return self.db_dir / "search.db"

    @property
    def memory_db_path(self) -> Path:
        return self.db_dir / "memory.db"

    @field_validator("vault_path", mode="before")
    @classmethod
    def expand_vault_path(cls, v: str | Path) -> Path:
        """Expand ~ in vault path."""
        return Path(v).expanduser()


@lru_cache
def get_config() -> Config:
    """Get cached config instance with user settings overlay."""
    config = Config()  # type: ignore - pydantic handles validation
    settings = load_user_settings()
    if "chat_model" in settings:
        config.chat_model = settings["chat_model"]
    if "memory_model" in settings:
        config.memory_model = settings["memory_model"]
    return config
