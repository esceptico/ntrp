# ntrp

**ntrp** is entropy — the measure of disorder in a system. Your calendar, emails, apartment hunt, health goals, half-remembered conversations, and recurring chores all accumulate. This project exists to reduce it.

ntrp is a local-first personal assistant: a Python backend and an Electron desktop app. It isn't a coding agent — it's a place to keep the moving parts of your life in one system that remembers, watches, and compresses each domain down to what actually needs you.

![ntrp Home — the focus set and life slices](docs/images/main.png)

## Slices — the home surface

A **slice** is a domain of your life — apartment hunt, health, a side project, finances. Each slice is backed by a memory topic page and watched by a **standing agent** that runs on a schedule, keeps the page current, and raises **at most one ask** when something genuinely needs your judgment. **Home** is the entrypoint: a composer, the focus set (every slice's one ask, in one list), and the slices strip.

- **Focus, not a feed** — the agent's whole job is to decide the single highest-leverage thing per slice, or stay silent. A quiet slice is the deliverable, not a gap.
- **Derived from memory** — you don't hand-register slices. A daily suggester reads your unpromoted topic pages, spots the ones that are real life domains, and offers them as one-click ghost chips on Home.
- **Slice rooms** — open a slice to see its open loops, the agent's last run, the ask with a Discuss button, related slices, and a scoped composer. Chats you start here carry the slice's page as context.

<table>
<tr>
<td width="50%"><img src="docs/images/slice-room.png" alt="A slice room"/></td>
<td width="50%"><img src="docs/images/memory-patterns.png" alt="Memory topic pages"/></td>
</tr>
<tr>
<td align="center"><em>A slice room — one ask, open loops, agent status</em></td>
<td align="center"><em>Memory: the topic pages slices are built on</em></td>
</tr>
</table>

## What else it does

- **Persistent memory**: durable, source-backed records that consolidate into readable topic pages; provenance stays visible, recall is hybrid (keyword + semantic).
- **Automations**: scheduled tasks, background agents, channel automations, and multi-agent workflows. Slice agents are ordinary automations you can edit, pause, or reschedule.
- **Structured output**: pass a schema and an agent run returns a validated object, not just prose — the mechanism behind a slice agent's one-ask nomination.
- **Per-automation tool scoping**: an allowlist of tool-name patterns bounds what any given automation's runs may touch.
- **Connected sources**: Gmail, Google Calendar, Slack, web search, MCP servers, local files, shell commands, and notifications.
- **Rich desktop UI**: streaming traces, tool approvals, memory inspection, integration setup assistants, MCP config, and sandboxed HTML widgets.
- **Any LLM**: Claude, GPT, Gemini, OpenRouter, Ollama, vLLM, LM Studio, custom OpenAI-compatible endpoints, or OpenAI account sign-in through the Codex provider.

![Automations — slice agents are ordinary, editable automations](docs/images/automations.png)

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

- `apps/server` — FastAPI backend, agent runtime, memory system, slices, tools, integrations, builtin skills, tests, and Python package metadata.
- `apps/desktop` — Electron desktop client: Home + slice rooms, chat, traces, memory UI, approvals, settings, integration assistants, MCP management, and HTML widget rendering.
- `docs` — Mintlify docs plus internal design/research notes.
- `tasks` / `notes` — working plans, lessons, and project notes.

## Core concepts

- **Slices** map life domains to memory topic pages, each watched by a standing agent that compresses the domain into at most one ask.
- **Memory** stores durable records and synthesizes them into readable topic pages, instead of shoving everything into the prompt.
- **Agents** run a tool loop that can return validated structured output; per-run tool scoping bounds what each may touch.
- **Tools** are policy-aware. Mutating operations require approval; large integration groups are deferred until the agent loads them.
- **Streaming** uses per-session SSE with ordered events, resumable cursors, tool lifecycle events, and run/background status.
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
