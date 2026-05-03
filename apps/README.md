# apps

Top-level runnable surfaces live here:

- `server` - self-contained uv project with backend package, tests, API server source, and builtin skills.
- `tui` - self-contained Bun/OpenTUI terminal client.
- `desktop` - self-contained Bun/Electron desktop client.

The Python package name stays `ntrp`, so imports and the `ntrp-server` entrypoint do not change.

There is intentionally no root Python or Bun workspace yet. Each app owns its own project config and lockfile until there is real shared code worth extracting.
