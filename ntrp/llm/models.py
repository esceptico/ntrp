import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from ntrp.logging import get_logger

_logger = get_logger(__name__)

MODELS_PATH = Path.home() / ".ntrp" / "models.json"


class Provider(Enum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GOOGLE = "google"
    CUSTOM = "custom"


@dataclass(frozen=True)
class Model:
    id: str
    provider: Provider
    max_context_tokens: int
    max_output_tokens: int = 8192
    price_in: float = 0
    price_out: float = 0
    price_cache_read: float = 0
    price_cache_write: float = 0
    base_url: str | None = None
    api_key_env: str | None = None


# Prices are per million tokens.
DEFAULTS = [
    Model(
        "claude-opus-4-6",
        provider=Provider.ANTHROPIC,
        max_context_tokens=200_000,
        max_output_tokens=16384,
        price_in=5,
        price_out=25,
        price_cache_read=0.50,
        price_cache_write=6.25,
    ),
    Model(
        "claude-sonnet-4-6",
        provider=Provider.ANTHROPIC,
        max_context_tokens=200_000,
        max_output_tokens=8192,
        price_in=3,
        price_out=15,
        price_cache_read=0.30,
        price_cache_write=3.75,
    ),
    Model(
        "gpt-5.2",
        provider=Provider.OPENAI,
        max_context_tokens=128_000,
        max_output_tokens=16384,
        price_in=2,
        price_out=8,
    ),
    Model(
        "gemini-3-pro-preview",
        provider=Provider.GOOGLE,
        max_context_tokens=128_000,
        max_output_tokens=65536,
        price_in=1.25,
        price_out=10,
    ),
    Model(
        "gemini-3-flash-preview",
        provider=Provider.GOOGLE,
        max_context_tokens=128_000,
        max_output_tokens=65536,
        price_in=0.15,
        price_out=0.60,
    ),
]


@dataclass(frozen=True)
class EmbeddingModel:
    id: str
    provider: Provider
    dim: int
    base_url: str | None = None
    api_key_env: str | None = None


EMBEDDING_DEFAULTS = [
    EmbeddingModel("text-embedding-3-small", Provider.OPENAI, 1536),
    EmbeddingModel("text-embedding-3-large", Provider.OPENAI, 3072),
    EmbeddingModel("text-embedding-ada-002", Provider.OPENAI, 1536),
    EmbeddingModel("gemini-embedding-001", Provider.GOOGLE, 3072),
]


_models: dict[str, Model] = {m.id: m for m in DEFAULTS}
_embedding_models: dict[str, EmbeddingModel] = {m.id: m for m in EMBEDDING_DEFAULTS}
_custom_loaded = False


def load_custom_models() -> None:
    global _custom_loaded
    if _custom_loaded:
        return
    _custom_loaded = True

    if not MODELS_PATH.exists():
        return

    try:
        raw = json.loads(MODELS_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        _logger.warning("Failed to read %s", MODELS_PATH, exc_info=True)
        return

    if not isinstance(raw, dict):
        _logger.warning("%s: expected a JSON object, got %s", MODELS_PATH, type(raw).__name__)
        return

    embedding_raw = {}
    for model_id, entry in raw.items():
        if model_id == "embedding":
            if isinstance(entry, dict):
                embedding_raw = entry
            continue

        if not isinstance(entry, dict):
            _logger.warning("Skipping custom model %s: expected object", model_id)
            continue
        if "base_url" not in entry:
            _logger.warning("Skipping custom model %s: missing base_url", model_id)
            continue
        if "context_window" not in entry:
            _logger.warning("Skipping custom model %s: missing context_window", model_id)
            continue

        model = Model(
            id=model_id,
            provider=Provider.CUSTOM,
            max_context_tokens=int(entry["context_window"]),
            max_output_tokens=int(entry.get("max_output_tokens", 8192)),
            price_in=float(entry.get("price_in", 0)),
            price_out=float(entry.get("price_out", 0)),
            base_url=entry["base_url"],
            api_key_env=entry.get("api_key_env"),
        )
        _models[model_id] = model
        _logger.info("Registered custom model: %s (base_url=%s)", model_id, model.base_url)

    for model_id, entry in embedding_raw.items():
        if not isinstance(entry, dict):
            _logger.warning("Skipping custom embedding model %s: expected object", model_id)
            continue
        if "base_url" not in entry:
            _logger.warning("Skipping custom embedding model %s: missing base_url", model_id)
            continue
        if "dim" not in entry:
            _logger.warning("Skipping custom embedding model %s: missing dim", model_id)
            continue

        emb = EmbeddingModel(
            id=model_id,
            provider=Provider.CUSTOM,
            dim=int(entry["dim"]),
            base_url=entry["base_url"],
            api_key_env=entry.get("api_key_env"),
        )
        _embedding_models[model_id] = emb
        _logger.info("Registered custom embedding model: %s (base_url=%s)", model_id, emb.base_url)


def get_model(model_id: str) -> Model:
    if model_id not in _models:
        raise ValueError(f"Unknown model: {model_id}. Available: {', '.join(_models)}")
    return _models[model_id]


def get_embedding_model(model_id: str) -> EmbeddingModel:
    if model_id not in _embedding_models:
        raise ValueError(f"Unknown embedding model: {model_id}. Available: {', '.join(_embedding_models)}")
    return _embedding_models[model_id]


def list_models() -> list[str]:
    return list(_models)


def get_models() -> dict[str, Model]:
    return _models


def list_embedding_models() -> list[str]:
    return list(_embedding_models)


def get_embedding_models() -> dict[str, EmbeddingModel]:
    return _embedding_models
