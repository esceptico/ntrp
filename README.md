# ntrp

**ntrp** is entropy – the measure of disorder in a system. Your calendar, emails, notes, browser tabs, half-remembered conversations – it all accumulates. This project exists to reduce it.

I built this for myself. ADHD and scattered attention meant I kept losing track of things (e.g. what I said, what I planned, what I was supposed to follow up on). So I made an assistant that hooks into my stuff and actually remembers.

![](docs/images/screen1.png)
![](docs/images/screen2.png)

## What it does

- **Persistent memory**: learns facts and patterns across conversations, consolidates them over time
- **Scheduled tasks**: morning briefings, daily reviews, health tracking – runs autonomously on a schedule
- **Connected sources**: Obsidian vault, Gmail, Google Calendar, browser history, web search (so far)
- **Shell access**: runs commands, manages files, sends emails
- **Any LLM**: Claude, GPT, Gemini built-in; OpenRouter, Ollama, vLLM, or any OpenAI-compatible endpoint via custom models

<details>
<summary>Memory</summary>

![](docs/images/memory.png)
</details>

<details>
<summary>Schedules</summary>

![](docs/images/schedules.png)
</details>

<details>
<summary>Connections</summary>

![](docs/images/sources.png)
</details>

## Install

```bash
uv tool install ntrp    # backend (or: pip install ntrp)
bun install -g ntrp-cli # terminal UI (or: npx ntrp-cli)
```

## Quick start

Create `~/.ntrp/.env` with at least one LLM provider key and model variables (see [.env.example](.env.example)):

```bash
mkdir -p ~/.ntrp
cat > ~/.ntrp/.env << 'EOF'
ANTHROPIC_API_KEY=sk-ant-...
NTRP_CHAT_MODEL=claude-sonnet-4-6
NTRP_MEMORY_MODEL=claude-sonnet-4-6
NTRP_EMBEDDING_MODEL=text-embedding-3-small
EOF
```

```bash
ntrp serve   # starts backend, prints a one-time API key
ntrp         # terminal UI (separate terminal) – paste the key on first launch
```

The server generates an API key on first run and prints it once. Enter it in the UI setup screen — it's saved to your system keychain. Use `ntrp serve --reset-key` to regenerate.

See [docs/setup.md](docs/setup.md) for Google OAuth, Telegram, Obsidian, custom models, Docker, and other integrations.

## Requirements

- Python 3.13+, [uv](https://docs.astral.sh/uv/)
- [Bun](https://bun.sh/) (terminal UI)
- At least one LLM provider API key

## Inspired by

- [opencode](https://github.com/nicepkg/opencode) – terminal UI
- [letta](https://github.com/letta-ai/letta) – persistent memory and personalized approach
- [hindsight](https://github.com/vectorize-io/hindsight) – graph memory structure

## Versioning

Pre-1.0: `0.minor.patch`. Minor bumps for new features (may be breaking), patch bumps for fixes. All changes go through PRs, except docs and minor non-code updates.

## License

MIT
