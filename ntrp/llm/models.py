import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from ntrp.logging import get_logger
from ntrp.usage import Pricing

_logger = get_logger(__name__)


def _models_path() -> Path:
    from ntrp.config import NTRP_DIR

    return NTRP_DIR / "models.json"


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
    pricing: Pricing = field(default_factory=Pricing)
    base_url: str | None = None
    api_key_env: str | None = None


# Prices are per million tokens.
DEFAULTS = [
    Model(
        "claude-opus-4-6",
        provider=Provider.ANTHROPIC,
        max_context_tokens=200_000,
        max_output_tokens=16384,
        pricing=Pricing(price_in=5, price_out=25, price_cache_read=0.50, price_cache_write=6.25),
    ),
    Model(
        "claude-sonnet-4-6",
        provider=Provider.ANTHROPIC,
        max_context_tokens=200_000,
        max_output_tokens=8192,
        pricing=Pricing(price_in=3, price_out=15, price_cache_read=0.30, price_cache_write=3.75),
    ),
    Model(
        "gpt-5.2",
        provider=Provider.OPENAI,
        max_context_tokens=128_000,
        max_output_tokens=16384,
        pricing=Pricing(price_in=2, price_out=8),
    ),
    Model(
        "gemini-3-pro-preview",
        provider=Provider.GOOGLE,
        max_context_tokens=128_000,
        max_output_tokens=65536,
        pricing=Pricing(price_in=1.25, price_out=10),
    ),
    Model(
        "gemini-3-flash-preview",
        provider=Provider.GOOGLE,
        max_context_tokens=128_000,
        max_output_tokens=65536,
        pricing=Pricing(price_in=0.15, price_out=0.60),
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

    if not _models_path().exists():
        return

    try:
        raw = json.loads(_models_path().read_text())
    except (json.JSONDecodeError, OSError):
        _logger.warning("Failed to read %s", _models_path(), exc_info=True)
        return

    if not isinstance(raw, dict):
        _logger.warning("%s: expected a JSON object, got %s", _models_path(), type(raw).__name__)
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
            pricing=Pricing(
                price_in=float(entry.get("price_in", 0)),
                price_out=float(entry.get("price_out", 0)),
            ),
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


def get_models_by_provider(provider: Provider) -> dict[str, Model]:
    return {mid: m for mid, m in _models.items() if m.provider == provider}


def list_embedding_models() -> list[str]:
    return list(_embedding_models)


def get_embedding_models() -> dict[str, EmbeddingModel]:
    return _embedding_models


def get_embedding_models_by_provider(provider: Provider) -> dict[str, EmbeddingModel]:
    return {mid: m for mid, m in _embedding_models.items() if m.provider == provider}


def add_custom_model(
    model_id: str,
    base_url: str,
    context_window: int,
    max_output_tokens: int = 8192,
    api_key_env: str | None = None,
) -> Model:
    raw = {}
    if _models_path().exists():
        try:
            raw = json.loads(_models_path().read_text())
        except (json.JSONDecodeError, OSError):
            raw = {}

    entry: dict = {"base_url": base_url, "context_window": context_window}
    if max_output_tokens != 8192:
        entry["max_output_tokens"] = max_output_tokens
    if api_key_env:
        entry["api_key_env"] = api_key_env

    raw[model_id] = entry
    _models_path().parent.mkdir(exist_ok=True)
    _models_path().write_text(json.dumps(raw, indent=2))

    model = Model(
        id=model_id,
        provider=Provider.CUSTOM,
        max_context_tokens=context_window,
        max_output_tokens=max_output_tokens,
        base_url=base_url,
        api_key_env=api_key_env,
    )
    _models[model_id] = model
    return model


def remove_custom_model(model_id: str) -> None:
    if model_id not in _models or _models[model_id].provider != Provider.CUSTOM:
        raise ValueError(f"Not a custom model: {model_id}")

    del _models[model_id]

    if _models_path().exists():
        try:
            raw = json.loads(_models_path().read_text())
        except (json.JSONDecodeError, OSError):
            return
        raw.pop(model_id, None)
        _models_path().write_text(json.dumps(raw, indent=2))

