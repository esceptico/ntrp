# v1.0 Hardening Tracker

## Must fix (security/stability)

- [x] **Path traversal in notes tools** — `Path(vault) / user_input` doesn't prevent `../../`. Need `resolve()` + check under vault. Same in Gmail token deletion route.
- [x] **Pagination validation** — list endpoints accept unbounded `limit`/`offset`. Cap and validate.
- [x] **Skill installation safety** — no hash verification, no file size limit, no directory depth limit on GitHub downloads.
- [x] **Streaming endpoint error handling** — `svc.prepare()` failure in `/chat/stream` has no clean error response.

## Should fix (robustness)

- [x] **Scheduler missed runs** — silently skipped on restart. Make configurable (skip vs catch-up) or at minimum log clearly.
- [x] **DST handling in schedules** — spring-forward skips runs, fall-back double-runs.
- [x] **Config corruption recovery** — corrupted `settings.json` silently returns `{}`. No backup/recovery.
- [x] **Notifier retries** — transient network errors permanently fail. No retry for Telegram/email.
- [x] **Consolidation LLM failures** — silently returns empty, no backoff, fact gets stuck.

## Nice-to-haves

- [ ] **Test coverage** — only memory has tests. Zero for server routes, automations, notifiers.
- [ ] **Rate limiting** on API endpoints.
- [ ] **Backup/restore API** — no way to export memory or migrate instances.
- [x] **Logger in obsidian.py** — uses `print()` instead of logger.
- [ ] **Pagination metadata** — list endpoints don't return total counts consistently.
