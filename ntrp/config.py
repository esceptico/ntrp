import json
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from ntrp.embedder import EmbeddingConfig
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
    model_config = SettingsConfigDict(
        env_prefix="NTRP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
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


@lru_cache
def get_config() -> Config:
    config = Config()  # type: ignore - pydantic handles validation
    settings = load_user_settings()
    if "chat_model" in settings:
        config.chat_model = settings["chat_model"]
    if "memory_model" in settings:
        config.memory_model = settings["memory_model"]
    if "embedding_model" in settings:
        config.embedding_model = settings["embedding_model"]
    if "embedding_dim" in settings:
        config.embedding_dim = settings["embedding_dim"]
    if "vault_path" in settings:
        config.vault_path = Path(settings["vault_path"])
    if "browser" in settings:
        config.browser = settings["browser"]
    if "browser_days" in settings:
        config.browser_days = settings["browser_days"]
    if "sources" in settings:
        src = settings["sources"]
        if "gmail" in src:
            config.gmail = src["gmail"]
        if "calendar" in src:
            config.calendar = src["calendar"]
        if "memory" in src:
            config.memory = src["memory"]
    return config
