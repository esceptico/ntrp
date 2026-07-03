---
name: add-feed
description: Use this skill when the user wants a memory feed — a scheduled automation that fetches targeted data from their integrations (gmail/calendar/slack/web) and keeps ONE memory page current, updated in place. Examples; "track my PR queue", "keep an invoices page", "week-ahead brief".
---

# Add Feed

A **feed** is a scheduled automation that owns one memory page under `feeds/` and rewrites it in place every run. The page is the current state of one question ("what's in my PR queue?"), not a log. This replaces raw per-integration ingest with targeted, user-shaped briefings.

Your job: clarify the target if needed, then call `create_automation` once. The user reviews the prompt + schedule in the approval card.

## Shape of a feed

- **One question per feed.** "Open PRs waiting on me", "invoices/acts pending", "next 7 days of commitments". If the user asks for a grab-bag, split it or ask which one matters.
- **One page per feed.** `feeds/<slug>.md`, slug from the question ("pr-queue", "invoices", "week-ahead").
- **Update-in-place.** Each run rewrites the whole page via `memory_write`. Never append, never keep history — the automation run log is the history.

## What to call

Call `create_automation` once:

- **`name`**: short, the question — e.g. `"PR queue feed"`.
- **`trigger_type` / schedule**: match the data's cadence — a PR queue is `every: "2h"` on weekdays; a week-ahead brief is `at: "07:30", days: "daily"`. Don't over-poll slow data.
- **`auto_approve`**: true — a feed must run unattended (memory_write is approval-gated otherwise).
- **`description`** (the prompt the feed runs on): use this template, filled in:

```
You maintain the memory page `feeds/<slug>.md` — a briefing that answers: <the question>.

1. Read the current page first, then fetch only what's needed to answer the
   question, using <specific integration tools / sources>.
2. If nothing MEANINGFUL changed versus the current page, STOP — no rewrite, no
   timestamp bump. Your run is logged either way; the page's stamp means "last
   meaningful change", and the automation's run history means "last checked".
   Be ruthless about this: a feed that rewrites cosmetic diffs is noise and cost.
3. Otherwise rewrite the page with `memory_write` (full page, update-in-place):
   - `# <Title>` then a one-line answer/summary.
   - Compact sections or a table for the items (tabular data belongs in a table).
   - Lead with what needs action; drop resolved items entirely.
   - End with `_Changed <date/time>._`
   - Keep it under ~40 lines. Stale content is worse than missing content.
4. If a run surfaces a DURABLE fact (a decision, a person, a standing change),
   call `remember` for it — the page is transient state, records are memory.
```

## Presets

When the user's ask matches one of these, start from it (adjust sources/cadence to
their setup) instead of inventing a shape. Focused feeds beat a generic "email feed".

| Preset | Question the page answers | Cadence |
|---|---|---|
| `pr-queue` | Which PRs wait on me (review, CI red, unresolved threads)? | every 2h, weekdays |
| `work-blockers` | What is blocked and on whom — mine and what I block for others? | every 4h, weekdays |
| `job-applications` | Where does each active application/interview process stand? | daily 09:00 |
| `billing-security` | Unusual charges, quota/limit warnings, security alerts needing action? | daily 08:00 |
| `week-ahead` | Commitments, deadlines, and travel in the next 7 days? | daily 07:30 |
| `invoices` | Which invoices/acts are unsent, unsigned, or unpaid? | weekly mon 10:00 |

## Rules

- The description must stand alone — the feed agent has no memory of this conversation. Name the exact tools/sources to check.
- Never point a feed at a record-backed page (me.md, topics/…) — `memory_write` will refuse; feeds live under `feeds/`.
- One `create_automation` call. Before it, 2-3 sentences: what feed, why this schedule.
