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
**Status:** TODO — design agreed:
- Collapse "explicit"/"source" into "chat" (both come from conversation)
- `source_ref` becomes a meaningful locator (not opaque session UUID)
- `recall()` gets `provenance: bool` flag — includes source data when on
- Don't pre-format provenance — pass raw source to LLM, let it decide presentation
- UI toggle in settings to enable/disable provenance in recall results
- Touches: extraction, remember tool, recall tool, formatting, settings, UI

## 11. No persistent chat history
Sessions are ephemeral — raw messages lost after session rotation. Can't search past conversations or trace facts to original messages.
**Status:** TODO — design:
- `chat_messages` table: id, session_id, role, content, timestamp
- FTS index on content (no vector — too expensive per message)
- `session_search()` tool for raw conversation search ("what did we discuss about X?")
- Facts link to message IDs for provenance (solves #10 naturally)
- Retention limits needed for hosted scenario

## 12. No memory archival
Facts/observations accumulate forever. sqlite-vec does linear scans — more embeddings = slower recall().
**Status:** TODO — design:
- Archive consolidated facts from vec index (knowledge already in observations)
- Archive stale observations (low access, not touched in months)
- `archived_at` timestamp on facts/observations — keep rows, remove from vec/FTS
- Run as final step of consolidation loop
- Provenance links stay intact since base rows are preserved
