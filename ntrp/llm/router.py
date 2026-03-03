import hashlib

from ntrp.llm.anthropic import AnthropicClient
from ntrp.llm.base import CompletionClient, EmbeddingClient
from ntrp.llm.gemini import GeminiClient
from ntrp.llm.models import Provider, get_embedding_model, get_embedding_models, get_model, get_models
from ntrp.llm.openai import OpenAIClient

_completion_clients: dict[str, CompletionClient] = {}
_embedding_clients: dict[str, EmbeddingClient] = {}
_api_keys: dict[Provider | str, str | None] = {}
_last_oauth_fingerprint: str | None = None
_stale_clients: list[CompletionClient] = []


def init(config) -> None:
    _completion_clients.clear()
    _embedding_clients.clear()
    _api_keys[Provider.ANTHROPIC] = config.anthropic_api_key
    _api_keys[Provider.OPENAI] = config.openai_api_key
    _api_keys[Provider.GOOGLE] = config.gemini_api_key

    # Load stored custom model keys (direct API keys from onboarding)
    from ntrp.config import load_user_settings

    settings = load_user_settings()
    custom_keys = settings.get("custom_model_keys", {})
    for model_id, key in custom_keys.items():
        _api_keys[model_id] = key

    # Fallback: env var lookup via api_key_env (legacy / power-user)
    for model in get_models().values():
        if model.provider == Provider.CUSTOM and model.api_key_env and model.id not in _api_keys:
            _api_keys[model.id] = config.model_extra.get(model.api_key_env.lower())
    for model in get_embedding_models().values():
        if model.provider == Provider.CUSTOM and model.api_key_env and model.id not in _api_keys:
            _api_keys[model.id] = config.model_extra.get(model.api_key_env.lower())


def _token_fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()[:16]


def _get_anthropic_client() -> AnthropicClient:
    global _last_oauth_fingerprint

    from ntrp.llm.claude_oauth import get_access_token

    token = get_access_token()
    if token:
        fp = _token_fingerprint(token)
        if fp == _last_oauth_fingerprint and "anthropic" in _completion_clients:
            return _completion_clients["anthropic"]  # type: ignore[return-value]
        _last_oauth_fingerprint = fp
        client = AnthropicClient(auth_token=token)
    else:
        _last_oauth_fingerprint = None
        client = AnthropicClient(api_key=_api_keys.get(Provider.ANTHROPIC))

    if old := _completion_clients.get("anthropic"):
        _stale_clients.append(old)
    _completion_clients["anthropic"] = client
    return client


def get_completion_client(model_id: str) -> CompletionClient:
    model = get_model(model_id)
    if model.provider == Provider.ANTHROPIC:
        return _get_anthropic_client()

    cache_key = model.id if model.provider == Provider.CUSTOM else (model.base_url or model.provider.value)
    if cache_key not in _completion_clients:
        key = _api_keys.get(model.provider)
        match model.provider:
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
    cache_key = model.id if model.provider == Provider.CUSTOM else model.provider.value
    if cache_key not in _embedding_clients:
        key = _api_keys.get(model.provider)
        match model.provider:
            case Provider.OPENAI:
                _embedding_clients[cache_key] = OpenAIClient(api_key=key)
            case Provider.GOOGLE:
                _embedding_clients[cache_key] = GeminiClient(api_key=key)
            case Provider.CUSTOM:
                _embedding_clients[cache_key] = OpenAIClient(base_url=model.base_url, api_key=_api_keys.get(model.id))
            case _:
                raise ValueError(f"Provider {model.provider} does not support embeddings")
    return _embedding_clients[cache_key]


async def close() -> None:
    for client in _stale_clients:
        await client.close()
    _stale_clients.clear()
    for client in _completion_clients.values():
        await client.close()
    for client in _embedding_clients.values():
        await client.close()
    _completion_clients.clear()
    _embedding_clients.clear()
