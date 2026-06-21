# Tool Harness Audit

Audit an MCP / agent tool harness for **agent ergonomics**: whether an LLM agent can discover, choose, call, chain, and recover from tools correctly without wasting context or guessing.

---

## Core invariants

| # | Invariant | What good looks like |
|---|-----------|----------------------|
| 1 | **Agent-readable output, not raw API dumps** | Prefer compact Markdown-style output for humans/agents. Do not dump raw backend JSON. If structured fields are needed for chaining, present stable refs/fields clearly. |
| 2 | **Clear ownership, low overlap** | One obvious tool owns each read/write path. Avoid duplicate aliases and overlapping tools that force the agent to guess. |
| 3 | **Semantic handles over opaque IDs** | Prefer slugs, names, emails, handles, or response-scoped refs. Backend UUIDs may exist internally, but should not be the primary agent-facing selector. |
| 4 | **Stable refs for follow-up actions** | If another tool must act on a result, return a stable `ref`/slug. Index refs are only safe inside the same response or with a response token. |
| 5 | **High-signal returns** | Return fields that help the next action. Drop low-level noise like raw UUIDs, etags, mime internals, giant metadata blobs, and irrelevant relations. |
| 6 | **Bounded output by default** | Paginate, truncate, filter, or summarize large results. Include `limit`/cursor and tell the agent how to continue or narrow the query. |
| 7 | **Concise default, optional detail** | Defaults cover the common case. Add `detail_level`, `include_*`, or `response_format` only when evals show it improves task success/token use. |
| 8 | **Right-sized tools** | Split genuinely separate decisions/ownership boundaries; consolidate mechanical read chains. Do not hide important user decisions inside a mega-tool. |
| 9 | **Read-before-write / preview-before-risk** | Every mutation has an observable read path. Risky writes support preview/dry-run, confirmation, or `expected_version` / `if_match`. |
| 10 | **Idempotency where possible** | Safe retries via idempotency keys, natural no-ops, or conflict detection. |
| 11 | **Return what changed** | Mutations return the changed fields/new state/diff, not only “success”. |
| 12 | **Helpful errors** | Errors explain the next action: missing field, invalid ref, call-this-first, narrow-query, retry-later, permission-needed. |
| 13 | **Consistent naming and params** | Same concept = same name. Prefer unambiguous params like `customer_ref`, `user_email`, `issue_slug`, `time_window`. |
| 14 | **Self-describing tool names** | Names describe user intent, not backend internals: `search_issues`, `archive_contact`, `propose_event_slots`, not `exec_proc_42`. |
| 15 | **Stable ordering** | Deterministic sorting in outputs and accepted input lists. If order matters, document it. |
| 16 | **Absolute timestamps with timezone** | Canonical time is ISO-8601 with timezone. Relative display (`2h ago`) is optional, never the only timestamp. |
| 17 | **Provenance for derived results** | Aggregates/summaries include source names, query/window, and how the result was derived. |
| 18 | **Concrete workflow examples** | Skills/docs show realistic chains, including search → inspect → preview → mutate → verify. Avoid toy one-liners. |
| 19 | **Fast cheap reads before deep tools** | Provide cheap discovery tools before expensive/broad tools. Tool descriptions should steer the agent to start cheap. |
| 20 | **Tool descriptions are onboarding docs** | Describe when to use it, when not to use it, required prerequisites, related tools, result shape, and failure modes. |
| 21 | **Destructive/openness annotations** | Mark destructive, open-world, networked, or high-risk tools with MCP annotations or equivalent metadata. |
| 22 | **Eval-driven ergonomics** | Validate with real agentic eval tasks. Track tool-call count, errors, token use, wrong-tool calls, truncation, and recovery behavior. |

---

## Audit report template

### Tool harness audit — `<repo / service name>`

| # | Workflow / Tool | Invariant | Severity | Finding | Fix |
|---|-----------------|-----------|----------|---------|-----|
| 1 | `search_issues` / `find_issues` | #2 ownership | High | Two tools cover the same read path, so agents choose inconsistently. | Keep `search_issues`; remove or alias `find_issues` internally. |
| 2 | `set_config` | #9 read-before-write | High | Overwrites current state without checking a version/safety token. | Add `get_config`; require `expected_version` on write. |
| 3 | `list_logs` | #6 bounded output | Medium | Returns unbounded logs and unrelated context. | Replace with `search_logs(query, limit, cursor)` and truncation guidance. |
| 4 | `get_file` | #3/#5 handles + signal | Medium | Returns opaque storage IDs and internal metadata but no semantic file name/ref. | Return `file_ref`, title, type, canonical timestamp, and source path. |
| 5 | `update_issue` | #11 changed state | Low | Reports only “success”. | Return updated issue summary and field-level diff. |

### Summary
- **N findings**: X high, Y medium, Z low
- **Highest-impact fixes**: ownership boundaries (#2), mutation safety (#9–#11), output bounds (#6), error guidance (#12)
- **Eval gap**: if no agentic eval harness exists, ergonomics are unverified

---

## Examples: bad → good

Examples intentionally use Markdown-style tool outputs, not raw backend JSON.

### #2 — Ownership / overlap

```text
Bad tools:
- search_issues(query)
- find_issues(text)
- query_issues(filter)

Problem: three tools own the same read path.

Good tool:
- search_issues(query, status?, assignee_ref?, limit?, cursor?)

Why: one obvious issue-search path; filters are parameters, not extra tools.
```

### #3/#4 — Semantic handles and stable refs

```md
Bad result:
- id: a3f2-9c71-44e0-bad-opaque-id
- mime_type: image/png
- etag: 88aa7f...

Good result:
1. Q3 deck
   - file_ref: files/q3-deck
   - type: image
   - updated_at: 2026-06-19T14:32:00-04:00
   - source: Google Drive / Sales folder

Why: the agent can refer to `files/q3-deck` without copying a raw UUID.
```

### #6 — Pagination + truncation

```md
Bad result:
40k tokens of raw log lines...

Good result:
Search logs: "payment timeout"
Showing: 50 of 2,300 matches
Cursor: logs/payment-timeout:page2

Top matches:
1. 2026-06-19T14:20:11Z — checkout-api — timeout contacting Stripe
2. 2026-06-19T14:21:03Z — worker-payments — retry succeeded

Next steps:
- Pass cursor `logs/payment-timeout:page2` for more.
- Narrow with `service:checkout-api` to reduce noise.
```

### #7 — Optional detail level

```text
Good call:
get_customer_context(customer_ref="acme-corp", detail_level="concise")

Concise result includes:
- customer name
- plan/status
- open tickets
- recommended next action

Detailed result may add:
- ticket history
- billing events
- notes and provenance
```

### #8/#9 — Right-sized tools without hiding risky decisions

```text
Bad chain:
list_users() → list_events() → create_event()
Problem: too much mechanical context and too many chances to pick the wrong thing.

Also bad:
schedule_event(attendee, window)
Problem: silently chooses and books a slot; hides a user decision.

Good chain:
1. propose_event_slots(attendee_email, time_window)
2. create_event(slot_ref, expected_calendar_version)
3. get_event(event_ref)

Why: read chain is consolidated into slot proposal, but the risky write stays explicit and verifiable.
```

### #9/#10 — Read-before-write + idempotency

```md
Bad write:
set_config(key="retention_days", value="30")
Result: success

Good flow:
1. get_config(key="retention_days")
   - current_value: 14
   - version: config-v12

2. set_config(
     key="retention_days",
     value="30",
     expected_version="config-v12",
     idempotency_key="retention-days-30-2026-06-19"
   )

Good result:
Updated config: retention_days
Changed:
- value: 14 → 30
- version: config-v12 → config-v13
```

### #11 — Return what changed

```md
Bad result:
Success.

Good result:
Updated issue: billing-timeout-regression
Changed:
- status: open → closed
- assignee: unassigned → maya@example.com
- updated_at: 2026-06-19T14:32:00-04:00
```

### #12 — Helpful errors

```md
Bad error:
400 BadRequest

Good error:
Cannot update config: missing `expected_version`.
Next step:
1. Call `get_config(key="retention_days")`.
2. Retry `set_config` with the returned version.
```

### #13/#14 — Names and params

```text
Bad:
exec_kv_batch_upsert(user, payload)
pg_run_proc_42(id)
save_contact(contact)

Good:
update_customer_profile(customer_ref, fields, expected_version)
archive_contact(contact_email, reason)
upsert_contact(contact_email, fields, idempotency_key)
```

### #16 — Timestamps

```md
Bad:
created: 2026-06-19 14:32:00
updated: 2h ago

Good:
created_at: 2026-06-19T14:32:00-04:00
updated_at: 2026-06-19T16:10:00-04:00
updated_relative: 2h ago
```

### #17 — Provenance

```md
Bad summary:
Revenue is down 12%.

Good summary:
Revenue change: -12%
Window: 2026-06-01 → 2026-06-19
Compared to: previous 19 days
Sources:
- Stripe balance transactions
- Internal subscriptions table
Derivation: gross revenue excluding refunds, grouped by transaction created_at
```

---

## How to run the audit

1. Inventory every tool: name, description, params, output, side effects, example call/result.
2. Map common workflows end-to-end: search → inspect → preview → mutate → verify.
3. Score each tool/workflow against invariants #1–22.
4. Severity:
   - **High**: causes wrong tool selection, unsafe writes, data loss, or unrecoverable agent failure.
   - **Medium**: wastes context, encourages ambiguous calls, or makes recovery harder.
   - **Low**: polish, consistency, naming, or documentation cleanup.
5. Prioritize fixes in this order:
   1. Ownership boundaries and tool selection.
   2. Mutation safety and read-before-write.
   3. Output bounds and stable refs.
   4. Helpful errors and workflow examples.
   5. Eval harness and regression tasks.
6. If no eval harness exists, say so directly: **ergonomics are unverified** until real agent transcripts prove the tools work.
