# Episode dedup redesign — recall → LLM adjudication

Date: 2026-05-29
Status: IN PROGRESS
Touches: `memory/connectors/episode_close.py`, `_constants.py`, `connectors/base.py`,
`connectors/chat.py`, `server/runtime/knowledge.py`, `items_store.py` (reuse only)

## 0. The bug that triggered this

Live DB had two `episode` rows about the same fact (scope `user`, same day, ~13h apart):

- **04:02 (rich):** track + deadline + form URL + linked Obsidian files + the
  `wisteria-monkey` automation task id. 5 bullets.
- **17:27 (poor):** track + deadline + form URL. A **strict subset** of the first —
  adds nothing.

Their cosine was **0.85**, below the dedup gate of **0.93**, so the second was
inserted. Root cause: **cosine is symmetric and dilutes under length mismatch.**
A short episode fully *contained* in a long one scores low cosine, because the
long one's extra material drags the similarity down. A single global cosine
threshold is therefore simultaneously **too high** (misses subset-duplicates) and
**unsafe to lower** (would suppress genuinely distinct episodes).

## 1. Why inline, not async

Dedup is an **upstream integrity gate**; consolidation (pattern finder, lens pass,
claim promotion) is a **downstream consumer**. If duplicates exist transiently,
every derivation job in between ingests them and *amplifies* the noise — two MATS
episodes become two evidence edges, inflated recurrence counts, a polluted
directory. You cannot cleanly un-pollute that after fan-out. So dedup runs
**inline at finalize**, before insert, exactly where it does today.

Cost is bounded because the LLM call is **gated by recall**: the cosine net only
surfaces a candidate when something genuinely similar already exists. Most episode
closes have zero candidates → zero LLM calls → same cost as today. We pay the
adjudication call only when there is a real duplicate decision to make.

## 2. Prior art (validated by research)

- **mem0**: cosine is *only* a top-k recall net (OSS default threshold **0.7**);
  an LLM picks **ADD / UPDATE / DELETE / NOOP**. No hard cosine gate on the decision.
- **Zep/Graphiti**: hybrid recall, LLM resolves, **never drops** — bi-temporal
  invalidation (keep both, mark obsolete).
- Classic **entity resolution**: *blocking* (cheap candidate gen) → *matching*
  (expensive pairwise decision). Blocking bounds match cost.
- **Asymmetric containment** is the named fix for our exact miss: Jaccard
  *containment* `|A∩B|/|A|` (not similarity) is ~1.0 when A ⊂ B regardless of B's
  extra length; NLI entailment is the stronger version.

Conclusion: replace the single 0.93 gate with **loose-cosine recall + an explicit
containment signal + LLM adjudication that merges/supersedes rather than dropping.**

## 3. Design

### 3.1 Candidate recall (cheap, no LLM)
- Scan recent episodes: `list_recent_items(kind="episode", window=7d, limit=50, scope)`
  (unchanged).
- Keep candidates with cosine ≥ **`DEDUP_RECALL_SIMILARITY = 0.80`** (down from 0.93).
- Cap to top **`DEDUP_ADJUDICATE_LIMIT = 5`** by cosine.
- If **no candidates** → KEEP, insert immediately. (Common path, zero LLM.)

### 3.2 Containment signal (cheap, no LLM)
- Pure function `_containment(new, cand) = |tok(new) ∩ tok(cand)| / |tok(new)|`,
  asymmetric, token-set based. ~1.0 means "new is subsumed by cand."
- Computed per candidate and fed into the adjudication prompt alongside cosine, so
  the LLM can distinguish "short & fully contained → drop" from "short but adds a
  deadline → merge."

### 3.3 LLM adjudication (only when candidates exist)
One structured call. Prompt includes the new summary + each candidate (`id`,
cosine, containment, content). Model returns JSON:

```json
{"action": "keep|drop|supersede|merge",
 "target_id": "<candidate id or null>",
 "merged_content": "<string or null>",
 "reason": "<short>"}
```

Parsing is defensive: strip code fences, `json.loads`; on any failure → **KEEP**
(fail open — never silently lose a new episode).

### 3.4 Apply the decision
- **keep** → insert the new episode (today's behavior).
- **drop** → skip insert. (MATS 17:27 lands here — contained, adds nothing.)
- **supersede** → insert new; `insert_parent_edge(new_id, target_id, "supersedes")`;
  set target `status='superseded'`, `invalid_at=now`. Follows the existing
  `contradictions.py` convention exactly (child = winner, parent = loser).
- **merge** → update the target in place: `content = merged_content`, re-embed,
  keep it active; do **not** insert the new row. Combines unique info from both into
  the canonical record. No info loss.

### 3.5 Fallback
`finalize_buffer` gains `dedup_client: DedupAdjudicator | None = None`. When absent
(unit tests that don't wire it), the recalled-candidate path collapses to the
**legacy high-threshold gate**: any candidate with cosine ≥ `DEDUP_SIMILARITY`
(0.93) → drop, else keep. Keeps existing tests green; real wiring supplies the
adjudicator.

## 4. Constants (`_constants.py`)
```
DEDUP_RECALL_SIMILARITY = 0.80   # recall net (blocking stage)
DEDUP_ADJUDICATE_LIMIT  = 5      # max candidates sent to the LLM
DEDUP_SIMILARITY        = 0.93   # legacy fallback gate (no adjudicator)
DEDUP_WINDOW_DAYS       = 7      # unchanged
DEDUP_SCAN_LIMIT        = 50     # unchanged
```

## 5. Wiring
`DedupAdjudicator` protocol + `CompletionDedupClient(model)` live beside
`SummaryClient`/`CompletionSummaryClient` in `episode_close.py`. Threaded through
`BufferingConnector.__init__` → `finalize_buffer(...)`, `ChatConnector.__init__`,
and constructed in `server/runtime/knowledge.py` (alongside the existing
`CompletionSummaryClient(self.config.memory_model)`), including the hot-reload path.

## 6. Tests (TDD)
1. `_containment` pure unit: subset → 1.0; disjoint → 0.0; partial.
2. recall returns candidates ordered by cosine, capped at limit, filtered at 0.80.
3. adjudicate **drop**: new contained, fake client returns drop → no insert.
4. adjudicate **supersede**: fake returns supersede → new inserted, edge created,
   old `superseded`.
5. adjudicate **merge**: fake returns merge+merged_content → target content updated
   & re-embedded, no new row.
6. **keep**: no candidates → insert, zero LLM calls (assert client not called).
7. parse failure → KEEP (fail open).
8. legacy fallback (no dedup_client): existing
   `test_finalize_skips_near_duplicate_episode` still passes unchanged.
9. **MATS regression**: seed rich 04:02 episode; finalize poor 17:27 with a real-ish
   fake adjudicator → dropped.

## 7. Out of scope (noted, not built)
- **Manual curation as training signal**: when the user manually supersedes/archives,
  the system should capture that as labeled dedup ground truth. Separate thread
  ("human-in-the-loop feedback into memory") — touches supersede, lens edits, manual
  archives broadly.
- NLI/entailment containment (stronger than Jaccard). Add only if Jaccard proves
  too blunt on real data.
- Dedup for non-episode kinds (claims already have `contradictions.py`).
