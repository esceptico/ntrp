# ntrp server

Backend package for ntrp.

It provides:

- `ntrp-server` CLI entrypoint
- FastAPI HTTP/SSE server
- agent runtime and multi-agent tooling
- integrations and deferred tool loading
- persistent memory records, search, graph/lens APIs, and desktop admin surfaces
- builtin skills and user-tool loading
- sandboxed `render_html` widget tool support for interactive desktop clients

Run from source:

```bash
uv sync --extra dev
uv run ntrp-server serve
```

Run tests:

```bash
uv run pytest
```

Repository and full documentation: https://github.com/esceptico/ntrp
