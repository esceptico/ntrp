# Memory System Bugs

## 1. No foreign key enforcement
`database.py` never sets `PRAGMA foreign_keys = ON`. All `REFERENCES` in schema are decorative.
**Status:** FIXED — added PRAGMA, migration v1 recreates entity_refs with ON DELETE CASCADE/SET NULL

## 2. `source_fact_ids` as JSON — LIKE scan on deletion
`remove_source_facts()` does full table scan with `LIKE '%{fact_id}%'`, false-matches substrings.
**Status:** FIXED — single pass over non-empty observations, set-based filtering, no LIKE

## 3. `history` grows unbounded
Every observation update appends a HistoryEntry. No cap or pruning.
**Status:** FIXED — capped at OBSERVATION_HISTORY_LIMIT (10), keeps most recent entries

## 4. Decay math — access_count is noise
`access_boost = 1 + log1p(access_count) * 0.1` — time dominates completely, access barely matters.
**Status:** FIXED — multiplier changed from 0.1 to 0.5, frequently accessed facts now meaningfully resist decay

## 5. `evidence_count` is denormalized and redundant
Stored as column but always computed as `len(source_fact_ids)`. Never queried independently.
**Status:** FIXED — removed column (migration v2), replaced with computed property on model

## 6. `deserialize_embedding` L2-normalizes on every read
Wasted computation if embeddings are already normalized at write time.
**Status:** FIXED — normalize in serialize_embedding (write), deserialize is now a plain copy

## 7. No `ON DELETE CASCADE` on `entity_refs`
FK enforcement is off, and manual cleanup only happens in `FactRepository.delete()`.
**Status:** FIXED — covered by bug #1 (FK enforcement + migration v1 with CASCADE)

## 8. Entity lookup by surface name instead of resolved entity_id
`get_facts_for_entity()` queries `WHERE er.name = ?` — misses facts tagged with variant names that resolved to the same entity.
**Status:** FIXED — now resolves to entity_id via subquery, uses COLLATE NOCASE

## 9. Consolidated facts returned in retrieval
`retrieve_facts()` returns facts that are already consolidated into observations, causing duplicate context.
**Status:** FIXED — filter `consolidated_at IS NOT NULL` after batch fetch

## 10. Source provenance is too thin
`source_type` ("chat"/"explicit") + `source_ref` (session ID) can't trace back to a specific message or source.
**Status:** FIXED — collapsed "explicit"/"source" into "chat", source_ref now includes message range (session_id:start-end)
- Remaining: recall() integration to surface original conversation context (Task 1.6, future)

## 11. No persistent chat history
Sessions are ephemeral — raw messages lost after session rotation. Can't trace facts to original messages.
**Status:** FIXED — chat_messages table in sessions.db, incremental sync on save, backfill existing sessions, slice lookup for provenance
- Remaining: recall() integration to surface original conversation context (Task 1.6, future)

## 12. No memory archival
Facts/observations accumulate forever. sqlite-vec does linear scans — more embeddings = slower recall().
**Status:** FIXED — archived_at column (migration v3), excluded from search, archive/unarchive methods, archival pass in consolidation loop, stats in API

## 13. API delete doesn't clean observation source_fact_ids
`FactService.delete()` doesn't call `remove_source_facts()` — only `forget()` does. Facts deleted via API leave dangling IDs in observation `source_fact_ids`.
**Status:** FIXED — added remove_source_facts + cleanup_orphaned_entities to FactService.delete()

## 14. N+1 queries in entity_expand
`entity_expand()` in retrieval.py runs 2 queries per entity (count + fetch). 100 entities = 200 queries.
**Status:** FIXED — batch count query (count_entity_facts_batch), halves the query count

## 15. `obs_entity_refs` missing ON DELETE for entity_id
No cascade when entity is deleted — orphaned `obs_entity_refs` rows remain.
**Status:** FIXED — migration v4 recreates table with ON DELETE CASCADE

## 16. Sessions SCHEMA missing `archived_at`
`archived_at` not in CREATE TABLE — relies on ALTER in init_schema. Works but fragile.
**Status:** FIXED — added to SCHEMA CREATE TABLE

## 17. Missing index on `sessions.archived_at`
Multiple queries filter on `archived_at` but no index exists.
**Status:** FIXED — added to SCHEMA

## 18. VACUUM not followed by explicit commit
After migrations, `VACUUM` is not committed explicitly.
**Status:** FIXED — added commit after VACUUM
