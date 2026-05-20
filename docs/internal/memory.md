# Current Knowledge System

ntrp no longer has a separate fact-extraction / consolidation memory pipeline. The current system is the knowledge layer described in:

- `docs/internal/knowledge-system-architecture.md`
- `docs/internal/knowledge-pipeline.md`
- `docs/internal/knowledge-system-implementation-notes.md`

## Runtime Shape

Chat/tool/runtime events create `knowledge_objects` with explicit provenance. Reflection automations promote active episodes into durable lessons, procedures, actions, and artifacts. Recall reads from the same knowledge source instead of a separate legacy memory store.

## Built-In Automations

The only current system knowledge automations are:

- `builtin:knowledge-reflection` using `knowledge_reflection`
- `builtin:knowledge-reflection-sweep` using `knowledge_reflection`
- `builtin:knowledge-retention` using `knowledge_retention`
- `builtin:knowledge-health` using `knowledge_health`

Any old built-in rows from the deleted memory pipeline are pruned during built-in seeding.

## Code Map

```text
apps/server/ntrp/knowledge/
apps/server/ntrp/server/routers/knowledge.py
apps/server/ntrp/server/runtime/knowledge.py
apps/server/ntrp/memory/search_source.py
apps/server/ntrp/tools/memory.py
apps/desktop/src/components/memory/KnowledgeHomePane.tsx
apps/tui/src/components/viewers/memory/MemoryViewer.tsx
```
