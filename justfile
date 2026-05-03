set dotenv-load := true
set shell := ["bash", "-uc"]

# List recipes.
default:
    @just --list

# Install dependencies for all apps.
install:
    cd apps/server && uv sync --extra dev
    cd apps/tui && bun install
    cd apps/desktop && bun install

# Run the backend server.
server:
    cd apps/server && uv run ntrp-server serve

# Run the terminal UI.
tui:
    cd apps/tui && bun run dev

# Run the desktop client.
desktop:
    cd apps/desktop && bun run dev

# Run checks.
check:
    cd apps/server && uv run ruff check .
    cd apps/server && uv run ruff format --check .
    cd apps/server && uv run pytest tests
    cd apps/tui && bun run typecheck
    cd apps/desktop && bun run typecheck

# Build distributable artifacts.
build:
    cd apps/server && uv build
    cd apps/tui && bun run build
    cd apps/desktop && bun run build

# Start Docker Compose services.
up:
    docker compose up -d

# Stop Docker Compose services.
down:
    docker compose down
