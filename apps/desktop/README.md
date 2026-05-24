# ntrp desktop

Small Electron client for the local ntrp server.

```bash
bun install
bun run dev
```

Use Node `^20.19.0` or `>=22.12.0` for Vite 7. The checked-in `.node-version` pins `22.12.0` for local version managers.

The app connects to `http://localhost:6877` by default. Server URL and API key are stored in Electron's app data directory; the API key is encrypted with Electron `safeStorage` when the OS supports it.
