import os

from ntrp.llm.anthropic import AnthropicClient
from ntrp.llm.base import CompletionClient, EmbeddingClient
from ntrp.llm.gemini import GeminiClient
from ntrp.llm.models import Provider, get_embedding_model, get_model, get_models
from ntrp.llm.openai import OpenAIClient

_completion_clients: dict[str, CompletionClient] = {}
_embedding_clients: dict[str, EmbeddingClient] = {}
_api_keys: dict[Provider | str, str | None] = {}


def init(config) -> None:
    _completion_clients.clear()
    _embedding_clients.clear()
    _api_keys[Provider.ANTHROPIC] = config.anthropic_api_key
    _api_keys[Provider.OPENAI] = config.openai_api_key
    _api_keys[Provider.GOOGLE] = config.gemini_api_key
    for model in get_models().values():
        if model.provider == Provider.CUSTOM and model.api_key_env:
            _api_keys[model.id] = os.environ.get(model.api_key_env)


def get_completion_client(model_id: str) -> CompletionClient:
    model = get_model(model_id)
    cache_key = model.id if model.provider == Provider.CUSTOM else (model.base_url or model.provider.value)
    if cache_key not in _completion_clients:
        key = _api_keys.get(model.provider)
        match model.provider:
            case Provider.ANTHROPIC:
                _completion_clients[cache_key] = AnthropicClient(api_key=key)
            case Provider.OPENAI:
                _completion_clients[cache_key] = OpenAIClient(api_key=key)
            case Provider.GOOGLE:
                _completion_clients[cache_key] = GeminiClient(api_key=key)
            case Provider.CUSTOM:
                _completion_clients[cache_key] = OpenAIClient(base_url=model.base_url, api_key=_api_keys.get(model.id))
            case _:
                raise ValueError(f"Unknown provider: {model.provider}")
    return _completion_clients[cache_key]


def get_embedding_client(model_id: str) -> EmbeddingClient:
    model = get_embedding_model(model_id)
    cache_key = model.provider.value
    if cache_key not in _embedding_clients:
        key = _api_keys.get(model.provider)
        match model.provider:
            case Provider.OPENAI:
                _embedding_clients[cache_key] = OpenAIClient(api_key=key)
            case Provider.GOOGLE:
                _embedding_clients[cache_key] = GeminiClient(api_key=key)
            case _:
                raise ValueError(f"Provider {model.provider} does not support embeddings")
    return _embedding_clients[cache_key]


async def close() -> None:
    for client in _completion_clients.values():
        await client.close()
    for client in _embedding_clients.values():
        await client.close()
    _completion_clients.clear()
    _embedding_clients.clear()
