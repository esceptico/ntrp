# ntrp desktop

Small Electron client for the local ntrp server.

```bash
bun install
bun run dev
```

The app connects to `http://localhost:6877` by default. Server URL and API key are stored in Electron's app data directory; the API key is encrypted with Electron `safeStorage` when the OS supports it.
