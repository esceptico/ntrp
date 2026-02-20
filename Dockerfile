FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS build

ENV UV_LINK_MODE=copy

RUN apt-get update && apt-get install -y gcc g++ build-essential && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

COPY ntrp ./ntrp

FROM python:3.13-slim

WORKDIR /app

RUN groupadd --gid 1000 ntrp \
    && useradd --uid 1000 --gid ntrp --create-home ntrp \
    && mkdir -p /app/data /home/ntrp/.ntrp \
    && chown -R ntrp:ntrp /app /home/ntrp/.ntrp

COPY --from=build --chown=ntrp:ntrp /app/.venv /app/.venv

COPY --chown=ntrp:ntrp ntrp ./ntrp
COPY --chown=ntrp:ntrp skills ./skills

USER ntrp

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "ntrp.server.app:app", "--host", "0.0.0.0", "--port", "8000"]
