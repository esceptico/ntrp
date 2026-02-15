from dataclasses import dataclass
from enum import Enum


class Provider(Enum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GOOGLE = "google"
    CUSTOM = "custom"


@dataclass(frozen=True)
class Model:
    id: str
    provider: Provider
    context_window: int
    max_output_tokens: int = 8192
    price_in: float = 0
    price_out: float = 0
    price_cache_read: float = 0
    price_cache_write: float = 0
    base_url: str | None = None


# Prices are per million tokens.
DEFAULTS = [
    Model("claude-opus-4-6", Provider.ANTHROPIC, 200_000,
          max_output_tokens=16384, price_in=5, price_out=25, price_cache_read=0.50, price_cache_write=6.25),
    Model("claude-sonnet-4-5-20250929", Provider.ANTHROPIC, 200_000,
          max_output_tokens=8192, price_in=3, price_out=15, price_cache_read=0.30, price_cache_write=3.75),
    Model("gpt-5.2", Provider.OPENAI, 128_000,
          max_output_tokens=16384, price_in=2, price_out=8),
    Model("gemini-3-pro-preview", Provider.GOOGLE, 128_000,
          max_output_tokens=65536, price_in=1.25, price_out=10),
    Model("gemini-3-flash-preview", Provider.GOOGLE, 128_000,
          max_output_tokens=65536, price_in=0.15, price_out=0.60),
]


@dataclass(frozen=True)
class EmbeddingModel:
    id: str
    provider: Provider
    dim: int


EMBEDDING_DEFAULTS = [
    EmbeddingModel("text-embedding-3-small", Provider.OPENAI, 1536),
    EmbeddingModel("text-embedding-3-large", Provider.OPENAI, 3072),
    EmbeddingModel("text-embedding-ada-002", Provider.OPENAI, 1536),
    EmbeddingModel("gemini-embedding-001", Provider.GOOGLE, 3072),
]


_models: dict[str, Model] = {m.id: m for m in DEFAULTS}
_embedding_models: dict[str, EmbeddingModel] = {m.id: m for m in EMBEDDING_DEFAULTS}


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
