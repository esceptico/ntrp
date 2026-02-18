# Setup Guide

## Requirements

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)
- [Bun](https://bun.sh/) (for the terminal UI)

## Quick Start

```bash
git clone https://github.com/esceptico/ntrp.git
cd ntrp
uv sync
cd ntrp-ui && bun install && cd ..
cp .env.example .env
```

Edit `.env` — you need at least one LLM provider key and the three model variables. See `.env.example` for all options.

```bash
uv run ntrp serve              # backend
cd ntrp-ui && bun run src/index.tsx  # UI (separate terminal)
```

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

## Exa.ai Web Search

- Sign up at [exa.ai](https://exa.ai)
- Get your API key from the dashboard
- Add to `.env`:

```
EXA_API_KEY=your-key
```

## Obsidian

Point ntrp at your vault directory:

```
NTRP_VAULT_PATH=/path/to/your/vault
```

Ntrp indexes `.md` files from the vault for retrieval during conversations.

## Browser History

Reads local browser history for context. macOS only.

```
NTRP_BROWSER=chrome    # or: safari, arc
NTRP_BROWSER_DAYS=30   # how far back to look
```

## Docker

```bash
cp .env.example .env   # configure your keys
docker-compose up -d
```

Data is persisted in a Docker volume. The server is available at `http://localhost:8000` (or `NTRP_PORT`).

## API Authentication

When exposing the server beyond localhost, set a bearer token:

```
NTRP_API_KEY=your-secret-key
```

All API requests must then include `Authorization: Bearer your-secret-key`.
