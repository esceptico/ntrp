## Task 3 Report

Implemented dirty-aware artifact publish.

- Added `KnowledgeRuntime.publish_artifacts_if_dirty()` returning `ArtifactPublishReport`.
- Kept `KnowledgeRuntime.rebuild_artifacts()` forced/manual and returning `int`.
- Fingerprint covers active records from `RecordStore.list(limit=None)` plus typed labels from `labels_for(..., include_kind=True)`.
- Checkpoint is stored in memory DB `meta` after successful export.
- `memory_publish` now reports refreshed vs skipped no-op.
- Added focused tests for unchanged no-op, label changes, record changes, and handler wording.

Verification:

```bash
cd apps/server
uv run pytest tests/test_memory_publish_dirty.py tests/automation/test_memory_maintenance_handler.py
```

Result: 14 passed.
