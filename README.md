# NTRP

Personal AI assistant with persistent memory, scheduling, and multi-source knowledge integration.

## How to Run

```bash
# Install
git clone https://github.com/your-username/ntrp.git
cd ntrp
uv sync
cd ntrp-ui && bun install && cd ..

# Configure
cp .env.example .env
# Edit .env and set OPENAI_API_KEY

# Start
uv run ntrp serve              # backend
cd ntrp-ui && bun run src/index.tsx  # UI
```

**Headless mode**:
```bash
uv run ntrp run -p "your prompt here"
```

**Docker**:
```bash
cp .env.example .env  # Edit: set OPENAI_API_KEY
docker-compose up -d
```

## Features

- **Memory** - Remembers facts and patterns across conversations
- **Scheduling** - Run tasks at specified times with email notifications
- **Sources** - Obsidian notes, browser history, Gmail, Calendar, web search

## License

MIT
