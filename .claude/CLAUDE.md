# NTRP

Personal entropy reduction system — Python backend (FastAPI) + TypeScript/React frontend (OpenTUI).

## Project Structure

- `ntrp/` — Python backend
  - `core/` — agent loop, spawning, tool execution @ntrp/core/agent.py
  - `memory/` — fact-centric memory system @ntrp/memory/facts.py
  - `tools/` — available tools (bash, files, web, memory, search, email, calendar)
  - `search/` — vector search & retrieval
  - `context/` — context compression
  - `server/` — FastAPI server @ntrp/server/app.py
  - `sources/` — data sources (obsidian, browser, exa)
- `ntrp-ui/` — React/TypeScript frontend with OpenTUI (Bun)
- `tests/` — pytest suite
- `.context/` — reference docs (not committed)

## Commands

```bash
uv run ntrp serve          # start server
uv run pytest tests/       # run tests
uv run python -m ntrp.cli  # cli entry, we're not using it usually
```

## Environment

- Python 3.13+ with uv
- Run scripts: `uv run ...`
- Config: `.env` (vault path, API keys)

## Style

- No defaults unless unavoidable
- Imports at top (exception: circular imports)
- Simple dataclasses over complex inheritance
- No sloppy comments — code speaks for itself
- Keep it simple, split into atomic pieces
- Minimal docstrings — skip if function is self-explanatory
- Separation of concerns — each module owns its domain

## Rules

- Check existing code before writing new
- Cleanup after refactoring, remove dead code
- No fallbacks or backward compatibility hacks
- Ask if uncertain

## Key Patterns

- Tools: `async execute(execution: ToolExecution, **kwargs) -> ToolResult`
- Memory: facts → links → observations (consolidation)
- Retrieval: vector + FTS → RRF → BFS expansion
- All constants in @ntrp/constants.py
