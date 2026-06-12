# ntrp desktop

Electron client for the local ntrp server.

It provides:

- chat over the server's SSE stream
- tool approval cards and activity traces
- memory browsing/editing views for profile entries, facts, patterns, graph/lenses, cleanup, and learning proposals
- sandboxed HTML widgets rendered from the agent's `render_html` tool
- local server URL/API key storage; API keys use Electron `safeStorage` when supported by the OS

## Development

```bash
bun install
bun run dev
```

Use Node `^20.19.0` or `>=22.12.0` for Vite 7. The checked-in `.node-version` pins `22.12.0` for local version managers.

The app connects to `http://localhost:6877` by default.

## Checks

```bash
bun run typecheck
bun test
```

## Builds

```bash
bun run dist          # current platform
bun run dist:mac      # macOS dmg/zip
bun run dist:win      # Windows NSIS
bun run dist:linux    # Linux AppImage
```
