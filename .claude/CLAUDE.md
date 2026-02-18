# NTRP

Personal entropy reduction system – Python backend (FastAPI) + TypeScript/React frontend (OpenTUI).

## Project Structure

- `ntrp/` – Python backend
  - `core/` – agent loop, spawning, tool execution @ntrp/core/agent.py
  - `memory/` – fact-centric memory system @ntrp/memory/facts.py
  - `llm/` – model registry, provider routing, custom models @ntrp/llm/models.py
  - `tools/` – available tools (bash, files, web, memory, search, email, calendar)
  - `skills/` – skill registry, installer, service
  - `services/` – chat, config, and other service layers
  - `schedule/` – scheduled task execution
  - `notifiers/` – notification channels (telegram, email)
  - `search/` – vector search & retrieval
  - `context/` – context compression
  - `server/` – FastAPI server @ntrp/server/app.py
  - `sources/` – data sources (obsidian, browser, exa)
  - `events/` – internal event system
- `ntrp-ui/` – React/TypeScript frontend with OpenTUI (Bun)
- `skills/` – builtin skills (add-model, etc.)
- `tests/` – pytest suite
- `docs/` – setup guide, memory docs
- `.context/` – reference docs (not committed)

## Commands

```bash
uv run ntrp serve          # start server
uv run pytest tests/       # run tests
uv run python -m ntrp.cli  # cli entry, we're not using it usually
```

## Environment

- Python 3.13+ with uv
- Run scripts: `uv run ...`
- Config: `.env` (vault path, API keys, model selection)
- Custom models: `~/.ntrp/models.json` (OpenRouter, Ollama, vLLM, etc.)
- User settings: `~/.ntrp/settings.json`

## Style

- No defaults unless unavoidable
- Imports at top (exception: circular imports)
- Simple dataclasses over complex inheritance
- No sloppy comments – code speaks for itself
- Keep it simple, split into atomic pieces
- Minimal docstrings – skip if function is self-explanatory
- Separation of concerns – each module owns its domain

## Rules

- Check existing code before writing new
- Cleanup after refactoring, remove dead code
- No fallbacks or backward compatibility hacks
- Ask if uncertain

## Key Patterns

- Tools: `async execute(execution: ToolExecution, **kwargs) -> ToolResult`
- Memory: facts → entities → observations (consolidation), dreams (cross-domain)
- Retrieval: observations (hybrid search) first, then facts (vector + FTS → RRF → entity expansion)
- Models: `_models` dict in `llm/models.py`, `Provider.CUSTOM` for user-defined models
- Skills: scanned from `skills/` (builtin), `.skills/` (project), `~/.ntrp/skills/` (global)
- All constants in @ntrp/constants.py
