# Task 2 Report

## Files changed

- `apps/server/ntrp/constants.py`
- `apps/server/ntrp/automation/builtins.py`
- `apps/server/ntrp/automation/scheduler.py`
- `apps/server/ntrp/server/runtime/automation.py`
- `apps/server/tests/automation/test_memory_maintenance_handler.py`
- `apps/server/tests/automation/test_scheduler_catchup.py`

## Tests run

Command:

```bash
./.venv/bin/python -m pytest -q tests/automation/test_memory_maintenance_handler.py tests/automation/test_scheduler_catchup.py
```

Summary:

- `17 passed in 1.65s`

## Self-review

- Kept `memory_consolidate` reconcile-only; it no longer calls `knowledge.rebuild_artifacts()`.
- Added separate builtin wiring for `memory_publish`, with its own constant, schedule, seeded builtin, runtime handler, and catch-up eligibility.
- `memory_consolidate` summary still reports all mutating fields from the Task 1 contract, including `reclassified` and `pruned`.
- `memory_publish` reports refreshed artifact count and returns unavailable when knowledge is absent or memory is not ready.
- Touched only the requested server/runtime/test files.

## Concerns

- I set `MEMORY_PUBLISH_AT` to `03:30` so publish runs after the `03:00` reconcile pass. The brief required a separate builtin but did not specify the exact time.

## Fix: review sequencing issue

### Files changed

- `apps/server/ntrp/automation/scheduler.py`
- `apps/server/tests/automation/test_scheduler_catchup.py`
- `.superpowers/sdd/task-2-report.md`

### Tests run

Command:

```bash
cd /Users/escept1co/src/ntrp/apps/server && ./.venv/bin/python -m pytest -q tests/automation/test_scheduler_catchup.py tests/automation/test_memory_maintenance_handler.py
```

### Output summary

- `17 passed in 2.54s`

### Self-review

- Removed `memory_publish` from missed-run catch-up eligibility so a boot-time catch-up cannot race ahead of `integration_sync` or `memory_consolidate`.
- Kept the nominal `03:30` publish schedule unchanged; normal nightly ordering still stays `integration_sync` -> `memory_consolidate` -> `memory_publish`.
- Did not add dirty/no-op publish gating from Task 3.

## Fix: ordered catch-up sequencing

### Files changed

- `apps/server/ntrp/automation/scheduler.py`
- `apps/server/tests/automation/test_scheduler_catchup.py`
- `.superpowers/sdd/task-2-report.md`

### Tests run

Command:

```bash
cd /Users/escept1co/src/ntrp/apps/server && ./.venv/bin/python -m pytest -q tests/automation/test_scheduler_catchup.py tests/automation/test_memory_maintenance_handler.py
```

### Output summary

- `18 passed in 2.08s`

### Self-review

- Superseded the earlier workaround that removed `memory_publish` from catch-up.
- Restored `memory_publish` catch-up eligibility so a missed overnight reconcile still publishes on the same boot.
- Added ordered catch-up sequencing for overdue builtins: `integration_sync` runs first, `memory_consolidate` waits for it, and `memory_publish` waits for both.
- Woke the scheduler when one catch-up phase finishes so the next overdue phase starts immediately instead of waiting for the next 60s poll.
- Kept Task 3 dirty/no-op publish gating out of scope.
