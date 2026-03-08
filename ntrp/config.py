import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path
from typing import Literal

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

NTRP_DIR = Path.home() / ".ntrp"
SETTINGS_PATH = NTRP_DIR / "settings.json"

_logger = get_logger(__name__)


SETTINGS_BACKUP_PATH = NTRP_DIR / "settings.json.bak"


def set_ntrp_dir(path: str | Path) -> None:
    global NTRP_DIR, SETTINGS_PATH, SETTINGS_BACKUP_PATH
    NTRP_DIR = Path(path)
    SETTINGS_PATH = NTRP_DIR / "settings.json"
    SETTINGS_BACKUP_PATH = NTRP_DIR / "settings.json.bak"


# Provider → (chat_model, memory_model, embedding_model)
PROVIDER_KEY_FIELDS = {
    "anthropic": "anthropic_api_key",
    "openai": "openai_api_key",
    "google": "gemini_api_key",
    "openrouter": "openrouter_api_key",
}

SERVICE_KEY_FIELDS = {
    "exa": "exa_api_key",
    "telegram": "telegram_bot_token",
}

# Provider → (chat_model, memory_model, embedding_model)
MODEL_DEFAULTS = {
    "ANTHROPIC_API_KEY": ("claude-sonnet-4-6", "claude-sonnet-4-6", None),
    "OPENAI_API_KEY": ("gpt-5.2", "gpt-5.2", "text-embedding-3-small"),
    "GEMINI_API_KEY": ("gemini-3.1-pro-preview", "gemini-3-flash-preview", "gemini-embedding-001"),
}


def mask_api_key(key: str | None) -> str | None:
    if not key or len(key) < 8:
        return "****" if key else None
    return key[:4] + "..." + key[-4:]


def load_user_settings() -> dict:
    if not SETTINGS_PATH.exists():
        return {}
    try:
        return json.loads(SETTINGS_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        _logger.warning("Failed to load user settings, trying backup", exc_info=True)
        if SETTINGS_BACKUP_PATH.exists():
            try:
                data = json.loads(SETTINGS_BACKUP_PATH.read_text())
                _logger.info("Restored settings from backup")
                return data
            except (json.JSONDecodeError, OSError):
                _logger.warning("Backup settings also corrupted")
        return {}


def save_user_settings(settings: dict) -> None:
    NTRP_DIR.mkdir(exist_ok=True)
    if SETTINGS_PATH.exists():
        try:
            SETTINGS_PATH.replace(SETTINGS_BACKUP_PATH)
        except OSError:
            pass
    SETTINGS_PATH.write_text(json.dumps(settings, indent=2))
    SETTINGS_PATH.chmod(0o600)


# --- API key hashing ---


def _hash_key(key: str, salt: bytes) -> str:
    return hashlib.sha256(salt + key.encode()).hexdigest()


def hash_api_key(key: str) -> str:
    salt = secrets.token_bytes(16)
    h = _hash_key(key, salt)
    return f"{salt.hex()}:{h}"


def verify_api_key(key: str, stored_hash: str) -> bool:
    try:
        salt_hex, h = stored_hash.split(":", 1)
        salt = bytes.fromhex(salt_hex)
        return hmac.compare_digest(_hash_key(key, salt), h)
    except (ValueError, IndexError):
        return False


def generate_api_key() -> tuple[str, str]:
    """Returns (plaintext_key, salted_hash)."""
    key = secrets.token_urlsafe(32)
    return key, hash_api_key(key)


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="NTRP_",
        env_file=(NTRP_DIR / ".env", ".env"),
        env_file_encoding="utf-8",
        extra="allow",
        validate_assignment=True,
        populate_by_name=True,
    )

    # API keys — read from standard env vars via aliases
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    openrouter_api_key: str | None = Field(default=None, alias="OPENROUTER_API_KEY")

    # Model IDs (must match entries in llm/models.py DEFAULTS or user config)
    chat_model: str | None = None
    explore_model: str | None = None
    memory_model: str | None = None
    embedding_model: str | None = None

    # Memory (graph-based knowledge store)
    memory: bool = True

    # Google (Gmail + Calendar)
    google: bool = False
    gmail_days: int = 30

    # Exa.ai for web search (optional) - no prefix, standard env var
    exa_api_key: str | None = Field(default=None, alias="EXA_API_KEY")
    # Web search provider selection (auto, exa, ddgs, none)
    web_search: Literal["auto", "exa", "ddgs", "none"] = Field(default="auto", alias="WEB_SEARCH")

    # Telegram bot token (optional) - no prefix, standard env var
    telegram_bot_token: str | None = Field(default=None, alias="TELEGRAM_BOT_TOKEN")

    # Obsidian vault
    vault_path: Path | None = None

    # Browser history (optional)
    browser: str | None = None
    browser_days: int = 30

    # MCP servers
    mcp_servers: dict[str, dict] | None = None

    # Agent depth limit
    max_depth: int = 8

    # Server
    host: str = "127.0.0.1"
    port: int = 6877

    # API authentication (salted hash, not plaintext)
    api_key_hash: str | None = None

    @model_validator(mode="after")
    def _resolve_model_defaults(self) -> "Config":
        if not self.chat_model:
            for env_var, (chat, memory, _) in MODEL_DEFAULTS.items():
                if os.environ.get(env_var) or getattr(self, env_var.lower(), None):
                    self.chat_model = chat
                    if not self.memory_model:
                        self.memory_model = memory
                    break
        if not self.explore_model and self.chat_model:
            self.explore_model = self.chat_model
        if not self.embedding_model:
            for env_var, (_, _, embedding) in MODEL_DEFAULTS.items():
                if embedding and (os.environ.get(env_var) or getattr(self, env_var.lower(), None)):
                    self.embedding_model = embedding
                    break
        return self

    @field_validator("chat_model", "explore_model", "memory_model")
    @classmethod
    def _validate_model(cls, v: str | None) -> str | None:
        if v is None:
            return v
        from ntrp.llm.models import strip_oauth_prefix

        raw = strip_oauth_prefix(v)
        models = get_models()
        if raw not in models:
            _logger.warning("Unknown model '%s' in settings, falling back to default", v)
            return None
        return v

    @field_validator("embedding_model")
    @classmethod
    def _validate_embedding_model(cls, v: str | None) -> str | None:
        if v is None:
            return v
        models = get_embedding_models()
        if v not in models:
            _logger.warning("Unknown embedding model '%s' in settings, falling back to default", v)
            return None
        return v

    @field_validator("browser", mode="before")
    @classmethod
    def _normalize_browser(cls, v: str | None) -> str | None:
        if v in ("", "none"):
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

    @field_validator("browser_days")
    @classmethod
    def _validate_browser_days(cls, v: int) -> int:
        if not 1 <= v <= 365:
            raise ValueError(f"browser_days must be 1-365, got {v}")
        return v

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
        return EmbeddingConfig(
            model=model.id,
            dim=model.dim,
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
        "google",
        "gmail_days",
        "max_depth",
        "mcp_servers",
        "web_search",
    }
)


def get_config() -> Config:
    load_custom_models()
    settings = load_user_settings()

    # Flatten legacy sources nesting
    if "sources" in settings:
        for key in ("gmail", "calendar", "google", "memory"):
            if key in settings["sources"]:
                settings.setdefault(key, settings["sources"][key])

    # Migrate legacy gmail/calendar → google
    if "gmail" in settings or "calendar" in settings:
        settings.setdefault("google", settings.pop("gmail", False) or settings.pop("calendar", False))

    # Build config: init args (settings.json) > env vars > defaults
    overrides = {k: settings[k] for k in PERSIST_KEYS if k in settings}

    # Restore api_key_hash from settings
    if "api_key_hash" in settings:
        overrides["api_key_hash"] = settings["api_key_hash"]

    # Load stored provider keys (env vars still take priority)
    provider_keys = settings.get("provider_keys", {})
    for provider_id, field in PROVIDER_KEY_FIELDS.items():
        alias = field.upper()
        if provider_id in provider_keys and not os.environ.get(alias):
            overrides[field] = provider_keys[provider_id]

    # Load stored service keys (env vars still take priority)
    service_keys = settings.get("service_keys", {})
    for service_id, field in SERVICE_KEY_FIELDS.items():
        alias = field.upper()
        if service_id in service_keys and not os.environ.get(alias):
            overrides[field] = service_keys[service_id]

    config = Config(_env_file=(NTRP_DIR / ".env", ".env"), **overrides)  # type: ignore - pydantic handles validation
    return config
