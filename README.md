# ntrp

**ntrp** is entropy — the measure of disorder in a system. Your calendar, emails, memory, half-remembered conversations, and recurring chores all accumulate. This project exists to reduce it.

![ntrp desktop UI](docs/images/main.png)

## What it does

- **Persistent memory**: stores source-backed records, builds scoped records and lenses, and keeps provenance visible.
- **Autonomous work**: scheduled automations, background agents, research agents, and multi-agent workflows.
- **Connected sources**: Gmail, Google Calendar, Slack, web search, MCP servers, local files, shell commands, and notifications.
- **Rich desktop UI**: streaming traces, tool approvals, memory inspection, integration setup assistants, MCP config, and rendered HTML widgets.
- **Lean tool context**: deferred tool schemas keep the model prompt small until a capability is needed.
- **Any LLM**: Claude, GPT, Gemini, OpenRouter, Ollama, vLLM, LM Studio, custom OpenAI-compatible endpoints, or OpenAI account sign-in through the Codex provider.

## Install

### Backend package

```bash
uv tool install ntrp    # or: pip install ntrp
ntrp-server serve       # starts backend, prints a one-time API key
```

The backend package does **not** include the desktop source tree. Use a source checkout for the Electron app.

### Desktop from source

```bash
git clone https://github.com/esceptico/ntrp.git
cd ntrp
just install
just server      # terminal 1
just desktop     # terminal 2
```

Or run the desktop directly:

```bash
cd apps/desktop
bun install
bun run dev
```

Paste the server API key on first launch. If no model provider is configured, the desktop onboarding flow lets you connect one.

Full setup guide, integrations, and API reference live in `docs/` and at **[docs.ntrp.io](https://docs.ntrp.io)**.

## Common commands

This repo uses [`just`](https://github.com/casey/just) as a thin task router:

```bash
just              # list recipes
just install      # install server and desktop deps
just server       # run backend from apps/server
just desktop      # run desktop client
just check        # run backend tests and desktop typecheck
```

Useful focused checks:

```bash
cd apps/server && uv sync --extra dev && uv run pytest
cd apps/desktop && bun run typecheck && bun test
```

## Repo layout

- `apps/server` — FastAPI backend, agent runtime, memory system, tools, integrations, builtin skills, tests, and Python package metadata.
- `apps/desktop` — Electron desktop client with chat, traces, memory UI, approvals, settings, integration assistants, MCP management, and HTML widget rendering.
- `docs` — Mintlify docs plus internal design/research notes.
- `tasks` / `notes` — working plans, lessons, and project notes.

## Core concepts

- **Memory** stores durable records and exposes lens/graph views instead of shoving everything into the prompt.
- **Tools** are policy-aware. Mutating operations require approval; large integration groups are deferred until the agent calls `load_tools`.
- **Streaming** uses per-session SSE with ordered events, resumable cursors, tool lifecycle events, and run/background task status.
- **Setup assistants** guide painful integration onboarding for Google, Slack, and MCP without requiring managed auth vendors.
- **HTML widgets** let the agent render sandboxed charts, forms, tables, and other rich cards in the desktop chat.

## Releasing

```bash
./release patch    # 0.5.2 → 0.5.3
./release minor    # 0.5.2 → 0.6.0
./release major    # 0.5.2 → 1.0.0
./release rc minor # 0.5.2 → 0.6.0-rc.1
./release rc       # 0.6.0-rc.1 → 0.6.0-rc.2
./release final    # 0.6.0-rc.2 → 0.6.0
```

Bumps version, creates a PR, merges, tags, and publishes a GitHub release. PyPI packages are published automatically via CI. Release candidates are GitHub prereleases.

## Inspired by

- [letta](https://github.com/letta-ai/letta) — persistent memory and personalized agents
- [hindsight](https://github.com/vectorize-io/hindsight) — graph memory structure

## License

MIT
