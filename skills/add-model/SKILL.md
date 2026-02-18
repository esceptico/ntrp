---
name: add-model
description: Add a custom OpenAI-compatible model (OpenRouter, Ollama, vLLM, LM Studio, etc.) to ~/.ntrp/models.json
---

# Add Custom Model

Help the user register a custom model in `~/.ntrp/models.json`.

## Information to collect

Ask the user for the following (one question at a time is fine):

1. **Model ID** — a name they'll use to reference it (e.g. `openrouter/deepseek-r1`, `ollama/llama3`)
2. **Base URL** — the OpenAI-compatible API endpoint (e.g. `https://openrouter.ai/api/v1`, `http://localhost:11434/v1`)
3. **API key env var** (optional) — the environment variable holding the API key (e.g. `OPENROUTER_API_KEY`). Not needed for local models like Ollama.
4. **Context window** — max input tokens (e.g. `128000`). If the user doesn't know, suggest checking the model's docs.
5. **Max output tokens** (optional, default 8192)

## Common presets

If the user mentions a known provider, pre-fill what you can:

- **OpenRouter**: `base_url: "https://openrouter.ai/api/v1"`, `api_key_env: "OPENROUTER_API_KEY"`
- **Ollama**: `base_url: "http://localhost:11434/v1"`, no api_key_env needed
- **vLLM**: `base_url: "http://localhost:8000/v1"`, no api_key_env needed
- **LM Studio**: `base_url: "http://localhost:1234/v1"`, no api_key_env needed
- **Together.ai**: `base_url: "https://api.together.xyz/v1"`, `api_key_env: "TOGETHER_API_KEY"`

## How to write the config

1. Read `~/.ntrp/models.json` if it exists (it may not — create it as `{}` if missing)
2. Add the new model entry
3. Write the file back with proper JSON formatting

The file format is:

```json
{
  "model-id": {
    "base_url": "https://...",
    "api_key_env": "ENV_VAR_NAME",
    "context_window": 128000,
    "max_output_tokens": 8192
  }
}
```

Only include `api_key_env` if the user provided one. Only include `max_output_tokens` if it differs from the default (8192).

## After adding

Tell the user:
- The model is now available as `model-id`
- They can set it in `.env` as `NTRP_CHAT_MODEL=model-id` (or `NTRP_MEMORY_MODEL`, `NTRP_EXPLORE_MODEL`)
- If they specified an `api_key_env`, remind them to set that environment variable
- The server needs a restart to pick up the new model
