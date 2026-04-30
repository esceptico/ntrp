# Setup Guide

## Requirements

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) or pip
- [Bun](https://bun.sh/) (for the terminal UI)

## Install

```bash
uv tool install ntrp    # or: pip install ntrp
bun install -g ntrp-cli # or: npx ntrp-cli
```

## Quick Start

Create `~/.ntrp/.env` with at least one LLM provider key and the model variables. See [.env.example](../.env.example) for all options.

```bash
mkdir -p ~/.ntrp
cp .env.example ~/.ntrp/.env   # if developing from source
# or create ~/.ntrp/.env manually with your keys
```

```bash
ntrp-server serve   # starts backend, prints a one-time API key
ntrp                # terminal UI (separate terminal) – paste the key on first launch
```

Config priority: environment variables > CWD `.env` > `~/.ntrp/.env` > defaults.

## Custom Models

You can use any OpenAI-compatible model (OpenRouter, Ollama, vLLM, LM Studio, etc.) by defining it in `~/.ntrp/models.json`:

```json
{
  "deepseek/deepseek-r1": {
    "base_url": "https://openrouter.ai/api/v1",
    "api_key_env": "OPENROUTER_API_KEY",
    "context_window": 128000,
    "max_output_tokens": 8192
  },
  "ollama/llama3": {
    "base_url": "http://localhost:11434/v1",
    "context_window": 8192
  }
}
```

Each model needs:
- `base_url` — the OpenAI-compatible API endpoint
- `context_window` — max input tokens (used for context compression thresholds)
- `api_key_env` (optional) — name of the environment variable holding the API key
- `max_output_tokens` (optional, default 8192)
- `price_in`, `price_out` (optional) — cost per million tokens, for usage tracking

Then use the model ID in your `.env`:

```
NTRP_CHAT_MODEL=deepseek/deepseek-r1
```

Custom models appear in the settings UI alongside built-in models.

## Google Gmail & Calendar

Requires a Google Cloud project with OAuth credentials.

### 1. Create a Google Cloud project

- Go to [Google Cloud Console](https://console.cloud.google.com/)
- Create a new project (or use an existing one)

### 2. Enable APIs

In **APIs & Services > Library**, enable:
- **Gmail API**
- **Google Calendar API**

### 3. Configure OAuth consent screen

- Go to **APIs & Services > OAuth consent screen**
- Choose **External** user type
- Fill in app name and your email
- Add scopes: `gmail.readonly`, `gmail.send`, `calendar`
- Add your Google account as a test user (required while app is in "Testing" status)

### 4. Create credentials

- Go to **APIs & Services > Credentials**
- Click **Create Credentials > OAuth client ID**
- Application type: **Desktop app**
- Download the JSON file
- Save it as `~/.ntrp/gmail_credentials.json`

### 5. Enable in ntrp

In your `.env`:

```
NTRP_GMAIL=true
NTRP_CALENDAR=true
```

On first use, a browser window opens for OAuth consent. The token is saved to `~/.ntrp/gmail_token.json` and refreshes automatically.

## Telegram Notifications

Used for scheduled task notifications.

### 1. Create a bot

- Message [@BotFather](https://t.me/BotFather) on Telegram
- Send `/newbot` and follow the prompts
- Copy the bot token

### 2. Get your user ID

- Message [@userinfobot](https://t.me/userinfobot) on Telegram
- It replies with your user ID

### 3. Configure

In your `.env`:

```
TELEGRAM_BOT_TOKEN=your-bot-token
```

When creating a scheduled task with notifications, select Telegram as the channel and provide your user ID.

## Web Search

Web search is available out of the box via DuckDuckGo (DDGS). For higher-quality results, configure Exa:

- Sign up at [exa.ai](https://exa.ai)
- Get your API key from the dashboard
- Add to `.env`:

```
EXA_API_KEY=your-key
```

Control the provider with `WEB_SEARCH` (`auto` | `exa` | `ddgs` | `none`). Default `auto` prefers Exa when `EXA_API_KEY` is set, otherwise falls back to DDGS.

## Browser History

Reads local browser history for context. macOS only.

```
NTRP_BROWSER=chrome    # or: safari, arc
NTRP_BROWSER_DAYS=30   # how far back to look
```

## Context Compaction

Controls when and how conversation context is compressed to stay within model limits. Adjustable in **Settings > Limits** or via `PATCH /config`.

| Setting | Key | Default | Range |
|---|---|---|---|
| Compact trigger | `compression_threshold` | `0.8` | 0.5–1.0 (fraction of model context window) |
| Max messages | `max_messages` | `120` | 20–500 |
| Keep ratio | `compression_keep_ratio` | `0.2` | 0.1–0.8 (fraction of recent messages kept) |
| Summary tokens | `summary_max_tokens` | `1500` | 500–4000 |
| Consolidation interval | `consolidation_interval` | `30` | Minutes between memory consolidation runs |

Compaction triggers when either the message count exceeds `max_messages` or actual input tokens exceed `compression_threshold` × model context limit. The most recent `compression_keep_ratio` fraction of messages is preserved, and older messages are replaced with an LLM-generated summary capped at `summary_max_tokens`.

## Docker

```bash
cp .env.example .env   # configure your keys
docker compose up -d
```

Data (sessions, memory, search index) is persisted in the `ntrp-data` volume, mapped to `~/.ntrp` inside the container. The server runs as a non-root user and is available at `http://localhost:6877` (or `NTRP_PORT`).

Gmail and Calendar tokens are stored in `~/.ntrp/` (covered by the data volume). Browser history is not available in Docker.

## API Authentication

The server generates and stores a hashed API key on first run. The plaintext key is printed once — enter it in the terminal UI setup screen or pass it via `--token`:

```bash
ntrp --token <key>             # or set NTRP_API_KEY env var
```

To regenerate the key:

```bash
ntrp-server serve --reset-key
```

All API requests require `Authorization: Bearer <key>`.
