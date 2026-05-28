# ntrp memory redesign — spec

Status: draft v1, ready to argue with.
Owner: tim + ntrp
Started: 2026-05-27

Companion doc: `docs/internal/ntrp-memory-redesign-scratchpad.md` (working/decisions log). This spec is the consolidated picture.

---

## 0. TL;DR

ntrp memory becomes **one table** (`memory_items`) of typed rows linked by a **role-typed parent DAG** (`memory_item_parents`). Six kinds: `episode`, `observation`, `claim`, `skill`, `proposal`, `artifact_ref`. Raw atomic turns/tool-calls are **not** memory; they live in their source-of-truth store and are referenced via `source_refs[]`. Per-source connectors emit `kind=episode` items on a hybrid boundary trigger. Four background automations turn episodes into observations, observations into claims, contradictions into supersessions, and recurring claims into skill proposals. Skills land as files in `~/.ntrp/skills/` with a thin DB pointer + usage. UX = Today / Graph / Skills / Search. Migration: backup the DB once, drop every old table, start fresh.

---

## 1. Goals, non-goals, principles

### Goals
- Replace the current type-zoo (5 active + 5 deprecated `object_type`s + parallel `observations`/`facts`/`memory_events` tables) with **one primitive shape**.
- Multi-source from day one: chat, files, gmail, slack, calendar, dex run logs, browser events.
- Continual learning without fine-tuning: the system gets better through consolidation and skill induction over the same primitive.
- Provenance you can walk: every memory item points back to its sources.
- UX that reflects what the user actually wants (what changed, what affects me, what does ntrp know about X), not "here are 4187 facts".

### Non-goals
- Fine-tuning. ntrp is app-level memory, not weight-level learning.
- Replacing skills infra (`~/.ntrp/skills/` stays).
- A general knowledge-graph product. Entity resolution is out of scope; reintroduce later if needed.
- Backward compatibility with current schema. We back up the DB once and burn the rest.

### Principles
1. **One primitive, attributes do the typing**. `kind` is informational; the schema doesn't branch.
2. **Provenance is mandatory.** Every non-`user_authored` item has `source_refs[]`; every derived item has `parents[]`.
3. **No deletes at runtime.** Contradictions invalidate via `status=superseded` + `invalid_at`. Never erase.
4. **Background work runs as automations.** No new scheduler/queue infra.
5. **No LLM-asked numbers.** Confidence is derived from non-LLM signals only.
6. **Simplicity beats completeness.** Add complexity only after a real use case forces it.

---

## 2. Data model

### 2.1 `memory_item`

```python
class MemoryItem:
    id: str
    kind: Literal["episode", "observation", "claim", "skill", "proposal", "artifact_ref"]
    content: str                          # actual text/payload (or short caption for artifact_ref)
    provenance: Literal["recorded", "inferred", "user_authored", "external"]
    source_refs: list[SourceRef]          # required for recorded/inferred/external; may be empty for user_authored
    confidence: float                     # 0..1, DERIVED from non-LLM signals only.
                                          # LLMs never write floats. If an LLM ever produces a
                                          # confidence-shaped input, it returns low|med|high and
                                          # we map to a band midpoint. UI displays as low|med|high
                                          # buckets; the float exists for ranking math. See §2.8.
    status: Literal["active", "superseded", "archived"]
    valid_from: datetime
    invalid_at: datetime | None
    scope: Scope                          # "user" | "project:<id>" | "session:<id>"
    tags: list[str]
    artifact_ref: str | None              # path/uri for kind in {skill, artifact_ref}
    usage: UsageRollup                    # counters: activated/helped/hurt/ignored
    feedback: FeedbackRollup              # explicit user thumbs / corrections
    created_at: datetime
    updated_at: datetime
```

### 2.2 `memory_item_parents` (edge table)

```python
class MemoryItemParent:
    child_id: str
    parent_id: str
    role: Literal["step", "evidence", "contradicts", "supersedes", "similar_to"]
    order: int | None      # only for role=step (ordered workflow chains)
```

Indexed on `(child_id)` and `(parent_id)` so DAG walks both directions are cheap (recursive CTE).

### 2.3 `SourceRef`

```python
class SourceRef:
    kind: Literal[
        "chat_msg", "tool_call", "automation_run", "file", "url", "user_input",
        "email", "slack_msg", "calendar_event", "dex_run", "browser_event",
    ]
    ref: str               # opaque pointer (session_id:msg_id, gmail message id, etc.)
    captured_at: datetime
```

### 2.4 Indexes

- FTS on `content`
- Vector on `content` (re-embedded on content change, cached otherwise)
- B-tree on `(status, scope, kind)` — primary hot path for retrieval
- B-tree on `(valid_from)` and `(invalid_at)` — temporal queries

### 2.5 The kinds — why each exists

For each kind: **why we need it**, **how it's used**, **why we can't drop it**, **prior art**, **alternatives**, **our pick**.

---

#### `episode`

- **Why**: long-running activity (a chat, a dex run, a gmail thread) needs to be chunked into bounded, citable slices. Without it, the pattern finder has nothing to cluster other than raw 10000-turn streams.
- **How (concrete chunking mechanism)**:
  1. **Buffer**: per `(scope, source_kind)`, a small `episode_buffers` row tracks the open chunk: `started_at`, `last_activity_at`, `turn_count`, `tokens`, `content_so_far`, `source_refs_so_far`, `running_centroid_vec`. Not a `memory_item` — transient.
  2. **Close trigger** fires on the first of: turn/token budget hit, idle gap exceeded, topic-shift cosine drop > 0.3 vs running centroid, or explicit close (chat ends, run ends, `/wrap`).
  3. **Finalize**: connector calls an LLM once to summarize `content_so_far` into a short episode body, then writes one `kind=episode` row with `provenance=inferred` and `source_refs[]` = all turn ids accumulated. Buffer is reset.
  4. **Overlap**: when the buffer resets, the last ~5 turns (or ~10% of budget) are copied into the next buffer as carry-forward. Those turns end up referenced by two episodes' `source_refs`. Standard sliding-window-with-overlap pattern from RAG chunking — fixes mid-conversation boundary loss.
- **Can't drop because**: clustering directly over raw turns is prohibitively expensive and noisy; every serious system that bypasses this layer (Mem0, A-MEM) does aggressive per-turn LLM extraction at ingest, which is the same cost paid in a different place. We pay it once per episode close.
- **Prior art**:
  - Zep/Graphiti `Episode` node — but Graphiti treats one turn = one episode. We bundle.
  - Current ntrp `memory_episode` — matches our semantics already.
  - MemoryOS "short-term memory" buffer — same idea, different name.
- **Alternatives considered**:
  - **No episode layer** (Mem0, A-MEM): every turn triggers extraction. Pros: simpler. Cons: huge LLM cost on every message; no natural session-level audit unit; mismatched with multi-source (a gmail thread isn't a turn).
  - **Per-turn episode** (Graphiti): every message turn is its own episode. Pros: simplest write path. Cons: 10000+ episodes per active week per source; the pattern finder still has to bundle them anyway.
- **Pick**: bundled episode with hybrid boundary trigger + 5-turn sliding overlap. Best fit for multi-source ingest with bounded LLM cost.

---

#### `observation`

- **Why**: gap between "what happened in session X" (episode) and "user prefers X across all situations" (claim) needs a stepping stone. Single-instance witnessed patterns ("tim corrected me twice this session for hallucinating sources") are real and useful, but they're not yet decontextualized claims.
- **How**: emitted by the **pattern finder**, first pass. Consumes episodes (and other observations) grouped by semantic+tag similarity. `role=evidence` parents point to source episodes. Consumed by the second pass of pattern finder to become claims.
- **Can't drop because**: jumping straight from episode → claim collapses two different abstraction operations into one and produces worse claims. Real evidence: Mem0's flat-strings approach produces noisy, redundant memories that need a separate dedupe pass; Graphiti needs a separate "communities" feature to recover this middle layer.
- **Prior art**:
  - Reflexion (arXiv:2303.11366) "verbal reinforcement" — per-task reflection, same role.
  - Graphiti "community" summaries — clusters of facts; same purpose.
  - Generative Agents (arXiv:2304.03442) "reflection" output before higher reflection (pattern reference only).
- **Alternatives considered**:
  - **Drop the middle layer**: see "can't drop because" above. Loses the natural audit unit and forces pattern finder to do both jobs.
  - **Make it just a low-confidence claim**: works mechanically but loses semantic clarity. We'd be using `confidence` to mean two different things (uncertainty about truth vs. abstraction level).
- **Pick**: keep as its own kind. The boundary is: observation is still context-bound ("during session X"); claim is decontextualized ("user prefers X").

---

#### `claim`

- **Why**: this is the layer that actually affects future behavior. When retrieval injects memory into a prompt, it almost always injects claims (and skills). Without claims, you have a journal, not a memory.
- **How**: emitted by pattern finder's second pass, by user (typed directly in UI), or by external connectors short-circuiting (calendar events become claims directly). Consumed by retrieval, by skill inducer, by contradiction watcher.
- **Can't drop because**: there's no system in the literature that works without a semantic/decontextualized layer. Even Mem0's "flat strings" are claims in this sense — they just don't have anything underneath them.
- **Prior art**: Mem0 "memories", Graphiti entities/edges, A-MEM atomic notes (claim-shaped), LangMem "managed memories", current ntrp `fact`/`lesson`.
- **Alternatives**: none viable; this layer is universal across every serious system.
- **Pick**: keep.

---

#### `skill`

- **Why**: skills change *future* behavior in a way claims don't. A claim says "user prefers casual tone"; a skill says "when responding to user, do X then Y then Z". Skills are executable knowledge.
- **How**: induced by the skill inducer from repeated claim/observation patterns that pass `is_toolable` gate; created via `proposal` → user approval. The DB row holds the pointer + lifecycle + usage; the actual instructions live in `~/.ntrp/skills/<name>/SKILL.md`.
- **Can't drop because**: skills are how ntrp gets meaningfully better over time without fine-tuning. Without this, the system can only accumulate facts, not new behaviors.
- **Prior art**:
  - Voyager (arXiv:2305.16291) — skill library induced from trajectories.
  - Anthropic Skills (2025) — markdown files describing capabilities.
  - Cursor rules, Continue/Cline rules — user-curated skill-shaped files.
  - Internal: tim's Dex work moving toward file-based skills + recordings.
- **Alternatives**:
  - **Skill stored as content in DB** (no file): cons — skill body becomes hard to edit, version, share, or invoke from outside ntrp. Files win.
  - **Skill stored ONLY as file, no DB row**: cons — lose usage tracking, lifecycle, scope, provenance back to source claims.
- **Pick**: DB row + file. Standard pattern for procedural memory in 2025–2026.

---

#### `proposal`

- **Why**: human-in-the-loop. Skill inducer emits skill proposals; pattern finder may emit low-confidence claims that need confirmation. Both should be visible and approvable, not auto-promoted blindly.
- **How**: kind=proposal items appear in Today + a Review-style queue. User approves → kind flips to `skill` or `claim`, file (if any) moves to `~/.ntrp/skills/`. Reject → status=archived (kept for provenance).
- **Can we drop it?**: honest answer — possibly. The simpler alternative (a `pending_review` flag or `status=draft` on the target kind) works mechanically. Keeping `proposal` as its own kind costs one extra enum value but separates two genuinely different uncertainties: "I'm not sure this is true" (low confidence) vs "I'm not sure user wants this active" (pending review). We pick "keep as a kind" for clarity, but this is the most legitimate collapse candidate. See §2.5.5.
- **Prior art**: LangMem approval flow, Mem0 "review" mode (optional), Anthropic Projects "approve memory" flow, current ntrp `action_candidate`.
- **Alternatives**:
  - **Status=draft on the target kind** (no separate kind): mechanically works. Cons — `give me all claims` query needs to remember to exclude drafts; conflates the two uncertainties above.
  - **Drop entirely, auto-promote everything**: real systems either have human-in-the-loop or accept being noisy. We picked human-in-the-loop.
- **Pick**: separate kind, with a note that this is the cheapest kind to collapse later if it doesn't earn its weight.

---

#### `artifact_ref`

- **Why**: some things are too big to inline (a long doc, an external URL we care about), but memory should still know about them and be able to walk to them.
- **How**: pointer + caption. `artifact_ref` field is the path/URL; `content` is a short human caption. Created by user or by connectors (e.g. dex deliverable, gmail attachment). Treated as a memory item but content is in the external file.
- **Can't drop because**: without it, we either inline 100KB blobs into `content` (kills FTS/vector usefulness) or lose the pointer entirely.
- **Prior art**: Anthropic Skills bundle approach, Notion AI doc references, Cursor `@file` mentions, current ntrp `artifact` type.
- **Alternatives**:
  - **Just use tags + URL in content**: works but loses typed querying ("show me all artifact_refs in scope X"). Marginal saving.
  - **Drop**: feasible but inconvenient. Better to keep.
- **Pick**: keep. Cheapest kind in the schema; high leverage.

### 2.6 The roles (parent edge types)

| role | meaning | example |
|---|---|---|
| `step` | parent is one ordered step of a sequence (workflow / playbook). `order` field is required. | skill steps; reconstructable workflows |
| `evidence` | parent supports/justifies the child | observation → episodes that witnessed it |
| `contradicts` | parent is a contradicting item; resolution is by `supersedes` or by user | new "Adidas" claim contradicts existing "Nike" claim |
| `supersedes` | parent is the older version of this assertion (now `status=superseded`) | the "Adidas" claim supersedes the "Nike" claim |
| `similar_to` | semantic neighbor; not load-bearing for invalidation | mostly computed live via vector search |

### 2.7 What is NOT in the schema

- No raw-event table as a memory primitive. Telemetry/event logs may exist but feed connectors; they aren't `memory_items`.
- No separate workflow_cluster / skill_promotion / action_candidate tables.
- No entity_profile / pattern / procedure_candidate as `kind`s.
- No `confidence` written by an LLM (it's a derived float).

### 2.8 Honest simplifications — status after first review

1. **Collapse `proposal` into `status=draft` + a `pending_review` flag.** **Still open.** Saves one kind. Costs query clarity (every `give me claims` query needs to remember to exclude drafts). Reassess after a few slices of real proposal-queue usage.
2. **Collapse `skill` into `artifact_ref` + `tags=["skill"]`.** **REJECTED.** Reason: skill activation is hot-path (chat prompt injection runs per turn). Filtering by `kind=skill` is one cheap index hit; filtering by `kind=artifact_ref AND tags @> ["skill"]` adds noise to every retrieval call site without simplifying the schema. Keep both kinds.
3. **Replace `confidence: float` with `trust: Literal["low","med","high"]`.** **REJECTED — partial agreement.** We keep the float, but with strict rules:
   - The stored value is always a float (`0..1`).
   - It is **never** written by an LLM.
   - Source-truthfulness base values live in a config map (`recorded=0.9, external=0.6, ...`) — human-set, not LLM-set.
   - Derivation combines these floats with non-LLM signals (evidence-parent count and their floats, unresolved contradictions, recency, usage feedback rollup).
   - UI **displays** the result as a `low | med | high` bucket. The float exists for ranking math; the bucket exists for humans.
   - If we ever do need an LLM-mediated estimate (avoided where possible), the LLM returns one of `low | med | high` — never a number — and we map to a band-midpoint float.
   - This way the LLM is never asked to estimate a real number; humans/UI never have to interpret one either.

---

## 3. Pipeline / stages

For each stage: **why**, **how**, **can't-do-without**, **prior art**, **alternatives**, **pick**.

### 3.1 Ingest connectors

- **Why**: ntrp must consume from many sources, not just chat. The connector is the universal entry point.
- **How**: per-source automation (poll or webhook). Dedupe against last-seen marker. Normalize. Emit `kind=episode` items (or short-circuit to `observation`/`claim` for structured sources like calendar). Populate `source_refs[]` with source-specific refs.
- **Can't drop because**: without connectors, memory is chat-only. Multi-source is a hard requirement.
- **Prior art**: Mem0 source connectors, LangChain document loaders, Letta data sources, Cognee data ingestion pipelines.
- **Alternatives**:
  - **One mega-connector**: cons — fragile; each source has different rate limits, auth, dedup keys, schemas.
  - **No connectors, pull on-demand from chat tools**: cons — no continuous awareness; misses async-arriving info (gmail thread that progresses while ntrp isn't running).
- **Pick**: per-source connector automations, each emitting into the same pipeline.

### 3.2 Episode close trigger

- **Why**: episodes must be bounded so summarization stays useful. Long sessions / always-on streams need automatic chunking.
- **How**: connector watches the source, closes the current episode on the first of:
  - turn / token budget (default ~50 turns / ~8k tokens)
  - idle gap (default ~10 min)
  - topic shift (embedding cosine drop > ~0.3)
  - explicit close (chat ends, run ends, thread completes)
- **Can't drop because**: without a trigger, episodes either never close (memory rots in an open buffer) or close on a fixed schedule that ignores activity (wastes LLM calls or produces stub episodes).
- **Prior art**:
  - MemoryOS (arXiv:2506.06326) — buffer + promote-on-overflow.
  - Letta sleeptime (arXiv:2503.18931) — idle-time trigger (pattern reference only).
  - Generative Agents (arXiv:2304.03442) — accumulated importance (pattern reference only).
  - Event Segmentation Theory (Zacks 2007) — cog-sci basis for topic-shift trigger.
  - Graphiti — no trigger (per-turn), included as the negative case.
- **Alternatives**:
  - **Per-turn episodes** (Graphiti): cons — too many episodes; doesn't solve summarization cost.
  - **Time-only** (every N minutes): cons — closes mid-conversation; produces useless slices.
  - **Manual close only**: cons — user is the bottleneck.
- **Pick**: hybrid trigger, per-connector defaults, all tunable.

### 3.3 Pattern finder (consolidator)

- **Why**: turns episodes into observations and observations into claims. This is where abstraction happens.
- **How**: scheduled automation, runs daily by default. Two passes:
  - **episode → observation**: cluster episodes by content similarity + shared tags + temporal proximity. For each cluster, emit one observation with `role=evidence` parents.
  - **observation/claim → claim**: cluster observations (and existing claims) by similarity, emit a new claim with `role=evidence` parents. Can consume claims (patterns of patterns).
- **Can't drop because**: without it, episodes pile up and nothing ever becomes durable memory. Retrieval would have to consume episodes directly, which is noisy and breaks decontextualization.
- **Prior art**: Reflexion, A-MEM linking pass, Graphiti entity extraction, Mem0 dedupe + extract LLM, MemoryOS "long-term" promotion.
- **Alternatives**:
  - **Online extraction at every turn** (Mem0): cons — LLM cost on every message; same total cost paid in worse shape.
  - **No abstraction layer, only retrieval-time clustering**: cons — every read pays for clustering; results inconsistent across reads.
- **Pick**: scheduled background consolidator, two passes, off the hot path.

### 3.4 Contradiction watcher

- **Why**: knowledge changes. "User has Nike" → "user has Adidas". Without explicit handling, contradictions either accumulate (the system "believes" both) or silently delete (loses history).
- **How**: triggered by new claim creation. Look for active claims with semantically opposed content (vector + entity-shared filter). For each conflict, emit `role=contradicts` edge. By default, **auto-flip** the older claim to `status=superseded`, set `invalid_at=now`, emit `role=supersedes` edge. Surface the action in Today with one-click undo. User can also manually flip status from the UI.
- **Cross-scope rule (scoped override, both stay active)**: a contradiction across scopes (e.g. `user`-scoped "tim writes commits in present tense" vs `project:ntrp`-scoped "tim writes commits in past tense") does **not** auto-supersede. Both stay `status=active`. The retrieval layer, when injecting into prompt context, surfaces this to the LLM as a structured note: *"general: <user-claim>. In current project: <project-claim>."* The LLM gets to see both and pick the right one for the situation. Pattern: scoped override (like env vars, gitconfig). Detection is the same vector+entity-shared filter; the difference is the action (annotate, not invalidate).
- **Can't drop because**: a personal-assistant memory will see facts change constantly. Without this, retrieval starts returning stale claims as if they were current.
- **Prior art**: Graphiti bi-temporal invalidation (the canonical pattern), Zep contradiction handling. Mem0 has only soft deduplication. Scoped-override pattern: env-var / config systems, not specific to memory literature.
- **Alternatives**:
  - **Hard delete contradictions**: cons — loses ability to query history ("what did we think before X happened").
  - **Manual review only**: cons — user is the bottleneck; backlog grows.
  - **Always auto-supersede across scopes too**: cons — loses general knowledge that's still true outside the project.
- **Pick**: Graphiti-style invalidation + auto-flip *within scope*; scoped-override annotation *across scopes*. Surface-and-undo for the within-scope case.

### 3.5 Skill inducer + `is_toolable` gate

- **Why**: turn recurring claim patterns into executable skills. This is the CL payoff.
- **How**: scheduled automation. Look at claims with `role=step` parents (ordered workflow chains) or claims with high evidence count. Apply the gate:
  1. Repetition: ≥ N independent supporting episodes.
  2. Determinism: low variance in steps across instances (e.g. step content Jaccard > 0.7).
  3. Trigger: first step / precondition identifiable from input context.
  4. Success signal: outcome can be checked (explicit success metadata or absence of correction within window).
  Pass → emit `kind=proposal` with a draft skill file in `/tmp/ntrp/proposed-skills/`. User approves → `kind=skill`, file moves to `~/.ntrp/skills/`.
- **Can't drop because**: without skill induction, ntrp accumulates knowledge but doesn't change behavior. That's the difference between memory-only and continual-learning agents.
- **Prior art**: Voyager skill library, AgentGen, trace-to-SOP work, Third Layer's browser-trajectory project (`#tim-x-thirdlayer`).
- **Alternatives**:
  - **User-only skill authoring**: cons — high friction; user has to notice patterns and write them up.
  - **Auto-promote without approval**: cons — skill files affect future behavior; an auto-promoted bad skill silently degrades quality.
- **Pick**: induce + propose + user approves. Approval gate is non-negotiable.

### 3.6 Retrieval

- **Why**: chat/operator/background/research all need to query memory at request time.
- **How**: query layer over `memory_items` with:
  - `status=active`
  - scope filter (`user`, current project, current session)
  - validity window (`valid_from <= now AND (invalid_at IS NULL OR invalid_at > now)`)
  - hybrid score: FTS + vector + recency + usage feedback weighting
  - kind filter (often "claims and skills only" for prompt injection)
- **Can't drop because**: writing memory you can't read is pointless.
- **Prior art**: BM25 + dense retrieval is universal; HippoRAG-2 graph walks; Graphiti's hybrid search; Mem0 vector + filter.
- **Alternatives**:
  - **Pure vector**: cons — keyword precision matters for entity-grounded queries.
  - **Pure BM25**: cons — misses semantic neighbors.
  - **Full graph walk on every query**: cons — expensive; use only for explicit provenance walks.
- **Pick**: hybrid retrieval with kind/scope/validity filters; graph walks only on user-initiated provenance views.

### 3.7 Confidence — derivation

Confidence is a derived `[0, 1]` float, never LLM-written, displayed as `low | med | high` buckets. The math is grounded in cognitive-science prior art (Ebbinghaus, ACT-R, SM-2). We do not invent.

#### 3.7.1 Prior art (each piece is derived from a real equation)

| Source | Equation | Used for | URL |
|---|---|---|---|
| Ebbinghaus (1885); Murre & Dros (2015) refit | `R(t) = exp(-t/S)` | Age-decay term | https://doi.org/10.1371/journal.pone.0120644 |
| ACT-R Base-Level Learning (Anderson 2004) | `B_i = ln(Σ_j t_j^{-d})`, `d ≈ 0.5` | Recency-of-use term + power-law decay | https://act-r.psy.cmu.edu/publications/pubinfo.php?id=628 |
| SuperMemo SM-2 (Wozniak 1987) | `EF' = EF + (0.1 - (5-q)(0.08 + 0.02(5-q)))`, `EF ∈ [1.3, 2.5]` | Usage-driven adjustment + bounded ease | https://supermemo.guru/wiki/Algorithm_SM-2 |
| Leitner (1972) | Box promotion/demotion | Provenance base as starting "box" | https://en.wikipedia.org/wiki/Leitner_system |
| MemoryOS (Li et al. 2024) | `heat(t) = heat_0 × exp(-λt)` + tier floors | Floor constants per component | https://arxiv.org/abs/2409.12524 |

#### 3.7.2 The formula

Four multiplicative components, each in `(0, 1]`, each with a floor so nothing collapses entire confidence to zero:

```
confidence = provenance × evidence × decay × usage
```

**Provenance** (Leitner-style starting prior + soft contradiction penalty):
```
provenance = provenance_base × (1 - 0.15 × tanh(contradiction_count))
```
- `provenance_base` from per-source config (e.g. `recorded=0.9`, `user_authored=0.95`, `inferred=0.75`, `external=0.6`)
- `tanh` is SM-2's bounded-penalty pattern: one contradiction barely dents (~0.12); five saturate at ~0.15 — matches human memory's robustness to single conflicting events

**Evidence** (ACT-R fan-in with diminishing returns):
```
w_evidence  = mean(parent_confidences) if N > 0 else 1
evidence    = 0.5 + 0.5 × (1 - exp(-k × N × w_evidence))
```
- `k = 0.4` — diminishing-returns rate; 3 strong parents reach ~0.95
- Floor of 0.5: an item without evidence parents (e.g. directly user-authored) is not penalised
- Quality-weighted by mean parent confidence: a claim supported by 3 weak observations is worth less than 3 strong ones

**Decay** (ACT-R recency + Ebbinghaus age, weighted blend):
```
decay = clamp(
    0.7 × (1 + last_used_days) ** (-0.5)
  + 0.3 × exp(-age_days / 100),
    lo = 0.05, hi = 1.0
)
```
- `d = 0.5` from ACT-R BLL fit
- `S = 100` days from Ebbinghaus refits (~3-month half-life for declarative facts)
- Recency dominates (0.7) — matches ACT-R; age is the smaller secondary term
- Floor 0.05 from MemoryOS tier-floor pattern — no silent erasure; explicit archive only

**Usage** (SM-2 ease-factor analog with helped/hurt/ignored):
```
net_usage  = helped - hurt - 0.3 × ignored
ratio      = net_usage / max(1, helped + hurt + ignored)
usage      = clamp(0.85 + 0.15 × tanh(ratio), lo = 0.5, hi = 1.0)
```
- Centered at 0.85 — never being used costs little; being mostly helpful pushes toward 1.0; being mostly hurtful pulls down
- `tanh` keeps it bounded — one bad activation does not wreck a heavily-used skill (SM-2 bounded-EF pattern)
- `ignored` (activated but not used downstream) weighted at 0.3 — soft negative signal, not as strong as `hurt`
- Floor 0.5 — a consistently-hurtful item is still surfaced as "low" rather than disappearing; user decides to archive

#### 3.7.3 Worked example

Inputs: `provenance_base=0.9, N=3, parent_confidences=[0.7, 0.8, 0.6], contradiction_count=0, age_days=30, last_used_days=2, helped=5, hurt=1, ignored=2`.

```
provenance = 0.9 × (1 - 0.15 × tanh(0)) = 0.9 × 1.0    = 0.900
w_evidence = mean([0.7, 0.8, 0.6])                     = 0.700
evidence   = 0.5 + 0.5 × (1 - exp(-0.4 × 3 × 0.7))
           = 0.5 + 0.5 × (1 - exp(-0.84))
           = 0.5 + 0.5 × 0.568                         = 0.784
decay      = 0.7 × (1 + 2)^(-0.5) + 0.3 × exp(-30/100)
           = 0.7 × 0.577 + 0.3 × 0.741
           = 0.404 + 0.222                             = 0.626
net_usage  = 5 - 1 - 0.3 × 2                           = 3.4
ratio      = 3.4 / 8                                   = 0.425
usage      = 0.85 + 0.15 × tanh(0.425)
           = 0.85 + 0.15 × 0.401                       = 0.910

confidence = 0.900 × 0.784 × 0.626 × 0.910             ≈ 0.402
```
Bucket: `med` (mapping: `<0.4=low, 0.4..0.7=med, >0.7=high`).

#### 3.7.4 Sanity checks

| Scenario | Expected | Computed |
|---|---|---|
| Brand-new user-authored claim, no usage, no evidence | high (user wrote it) | `0.95 × 0.5 × 1.0 × 0.85 = 0.404` — med. Acceptable; LLM still sees it but as medium-confidence. After first reuse it rises. |
| Same claim, 1 year of no retrieval | low / forgotten | decay term clamps near floor (~0.05), confidence drops to ~`0.02`. Effectively forgotten. |
| 1 contradiction on otherwise strong claim | small dip | provenance factor drops from 0.9 to ~0.79, ~12% reduction. Robust. |
| Heavy positive usage (`helped=20, hurt=0, ignored=0`) | high | usage ≈ 0.85 + 0.15 × tanh(1.0) ≈ 0.964. Combined with strong provenance + recent use: ~0.85+. |

#### 3.7.5 Pitfalls (and why this formula avoids them)

- **Pitfall: pure multiplicative → everything decays to zero.** Avoided: per-component floors (0.5 on evidence and usage, 0.05 on decay) plus tanh-bounded penalties.
- **Pitfall: linear additive → no real decay.** Avoided: decay term is genuinely exponential/power-law.
- **Pitfall: LLM-written numbers.** Avoided: every input is an integer count, a config float, or a timestamp.
- **Pitfall: knife-edge contradiction handling.** Avoided: tanh-saturated penalty; you need many contradictions, not one, to crater provenance. Hard supersession is the *status* mechanism (§3.4), separate from the *confidence* mechanism.

#### 3.7.6 Reference implementation (~30 lines)

```python
import math

PROVENANCE_BASE = {"recorded": 0.9, "user_authored": 0.95, "inferred": 0.75, "external": 0.6}

def compute_confidence(
    provenance: str,
    parent_confidences: list[float],
    contradiction_count: int,
    age_days: float,
    last_used_days: float,
    helped: int, hurt: int, ignored: int,
) -> float:
    base = PROVENANCE_BASE[provenance]
    prov = base * (1.0 - 0.15 * math.tanh(contradiction_count))

    n = len(parent_confidences)
    w  = sum(parent_confidences) / n if n else 1.0
    ev = 0.5 + 0.5 * (1.0 - math.exp(-0.4 * n * w)) if n else 0.5

    dec = max(0.05, min(1.0,
        0.7 * (1.0 + last_used_days) ** -0.5
      + 0.3 * math.exp(-age_days / 100.0)
    ))

    total = helped + hurt + ignored
    if total == 0:
        usage = 0.85
    else:
        net   = helped - hurt - 0.3 * ignored
        ratio = net / total
        usage = max(0.5, min(1.0, 0.85 + 0.15 * math.tanh(ratio)))

    return round(prov * ev * dec * usage, 4)


def confidence_bucket(conf: float) -> str:
    if conf < 0.4:  return "low"
    if conf < 0.7:  return "med"
    return "high"
```

Recompute schedule: on item create, on parent change, on contradiction add/remove, on usage feedback, on retrieval (cheap — no I/O). Plus a nightly sweep over items where `last_used_days` matters (otherwise the cached float is stale).

---

## 4. Abstract data flow

### 4.1 Diagram (text)

```
┌─────────────────────────────────────────────────────────────────────┐
│                       SOURCES OF TRUTH                              │
│  chat session store   filesystem   gmail   slack   calendar   dex   │
│  browser events       run logs                                      │
└──────┬────────┬────────┬───────┬──────────┬─────────┬─────────┬─────┘
       │        │        │       │          │         │         │
       ▼        ▼        ▼       ▼          ▼         ▼         ▼
   ┌──────────────────────────────────────────────────────────────┐
   │                       CONNECTORS                             │
   │ (per-source automations: poll/webhook, dedupe, normalize)    │
   │ each watches its source for boundary triggers (§3.2)         │
   └──────────────────────────────┬───────────────────────────────┘
                                  │ emit kind=episode
                                  ▼
   ┌──────────────────────────────────────────────────────────────┐
   │                     memory_items table                       │
   │ kind=episode rows, each with source_refs[] back to source    │
   └──────────────────────────────┬───────────────────────────────┘
                                  │ pattern finder (scheduled)
                                  │ pass 1: cluster episodes
                                  ▼
   ┌──────────────────────────────────────────────────────────────┐
   │   kind=observation rows, role=evidence parents → episodes    │
   └──────────────────────────────┬───────────────────────────────┘
                                  │ pattern finder pass 2
                                  ▼
   ┌──────────────────────────────────────────────────────────────┐
   │   kind=claim rows, role=evidence parents → observations      │
   │   contradiction watcher tags conflicts, supersedes older     │
   └──────────────────────────────┬───────────────────────────────┘
                                  │ skill inducer + is_toolable
                                  ▼
   ┌──────────────────────────────────────────────────────────────┐
   │   kind=proposal rows (draft skill file in /tmp)              │
   │   user approves → kind=skill, file moves to ~/.ntrp/skills/  │
   └──────────────────────────────────────────────────────────────┘

   Read path (retrieval): chat / operator / background / research
   → query memory_items WHERE status=active AND scope match AND validity
   → hybrid score (FTS + vector + usage)
   → inject claims + skills into context
```

### 4.2 Worked example (end-to-end)

**Day 1**, user works with ntrp on a refactor session. Chat connector emits:
- 3 episodes (idle gaps closed them), each summarizing ~30 turns. `source_refs[]` → chat msgs 1–30, 31–60, 61–90. `provenance=inferred`.

**Day 2**, pattern finder runs.
- Pass 1 clusters the 3 episodes (similar tags, same project scope) into 1 observation: "user spent the session refactoring the memory module and corrected me twice about naming". `role=evidence` parents → the 3 episodes.
- Pass 2 finds an earlier similar observation from last week ("user corrected me about naming during another redesign session"). Emits a claim: "user wants explicit naming options before I commit to a decision". `role=evidence` parents → both observations.

**Day 3**, user has another session, ntrp again jumps to a naming decision without asking. User corrects.
- New episode + observation + claim ("user wants naming options first") gets emitted.
- Contradiction watcher: the new claim is semantically aligned (not opposed) — no supersession needed.
- After 3 similar claims accumulate, **skill inducer** fires `is_toolable`:
  - Repetition: 3+ supporting episodes ✓
  - Determinism: steps are stable (ask → list options → wait) ✓
  - Trigger: "about to make a naming/structure decision" ✓
  - Success signal: absence of correction within next 5 turns ✓
- Emits `kind=proposal`: a draft skill file `propose-naming-options.md`. Surfaces in Today.

**Day 4**, user opens Today, sees the proposal, clicks Approve.
- kind flips to `skill`. File moves to `~/.ntrp/skills/propose-naming-options/SKILL.md`. Skill becomes available for activation in future chat turns.

**Later**, ntrp activates the skill. Usage rollup increments. If user thumbs-down, `feedback` records it; if hurt count grows, confidence drops (derived); skill may stop activating.

If user later changes their mind ("actually, just decide and tell me"), a new claim contradicts the old one. Auto-supersede flips the old claim to `status=superseded` with `invalid_at=now`. The skill, which depends on the now-superseded claim, gets flagged in Today: "supporting claim invalidated — review this skill?".

---

## 5. External sources + CL — the full picture

### 5.1 External sources

Each is an independent connector automation. Same shape: pull/receive → dedupe → normalize → emit memory_items.

| Source | Connector triggers on | Typically emits | Provenance |
|---|---|---|---|
| chat | turn budget / idle / topic shift | `episode` | `recorded` |
| files (workspace) | file mtime change + idle | `episode` (per session of edits) | `recorded` |
| gmail | new thread / thread close / poll | `episode` (per thread); structured msgs short-circuit to `claim` | `external` |
| slack | mention / DM / channel poll | `episode` per active window | `external` |
| calendar | event create/update | `claim` (short-circuit, structured) | `external` |
| dex run logs | run end | `observation` (already structured) | `external` |
| browser events | tab close / idle | `episode` | `external` |
| user-typed (in UI) | submit | `claim` or `skill` directly | `user_authored` |

Confidence base per source: see scratchpad §8.2 inputs. Adjusted by `usage.feedback` and contradiction count.

### 5.2 The continual-learning loop

Three intersecting cycles, all using the same primitive:

1. **Knowledge cycle**: episode → observation → claim → (skill).
2. **Correction cycle**: new evidence creates a claim → contradiction watcher → older claim superseded → dependent skills flagged.
3. **Skill cycle**: claims pass `is_toolable` → proposal → user approves → skill activates → usage feedback → confidence updates → skill stays or fades.

```
                    NEW EVIDENCE
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
   ┌──────────────────┐   ┌──────────────────┐
   │ new claim emitted │  │ usage feedback    │
   └────┬─────────┬───┘   │ (helped/hurt)     │
        │         │       └────────┬─────────┘
        │         │                │
        │         ▼                ▼
        │  ┌──────────────┐  ┌─────────────────┐
        │  │ contradiction │  │ confidence      │
        │  │ → supersede   │  │ recomputed      │
        │  └──────┬───────┘  └─────────────────┘
        │         │
        ▼         ▼
   ┌─────────────────────────────┐
   │  skill inducer (is_toolable) │
   └──────────────┬──────────────┘
                  │ proposal
                  ▼
            user approves
                  │
                  ▼
              new skill
```

The point: every learning operation is one of (a) emit an item, (b) link items with a role-typed edge, (c) flip a status. There are no other primitives. CL is what emerges when these run on a schedule over real activity.

---

## 6. UX / UI

Replace 4 type-tabs with 4 task-oriented views.

### 6.1 Today (default)

Lightweight feed (~20 cards max, "show more" for the tail). Each card is one thing the user might want to act on or be aware of:

- **New skills since last open** — single tap to activate/disable
- **New contradictions auto-resolved** — with one-click undo for the supersession
- **Low-confidence claims wanting confirmation** — approve / reject / edit
- **Pending proposals** — skill or claim drafts awaiting approval
- **Recent corrections** — what changed in the last day

No giant list of facts. No raw counts. The feed is "what changed that I might care about".

### 6.2 Graph

Provenance walker. Pick any item → see parents (where it came from) and children (what was derived from it).

- Skill → claims that motivated it → observations → episodes → source refs (jump to original gmail / slack / chat msg).
- This *is* the audit view. No separate "where did this come from" surface needed.

**Rendering: real graph visualization**, not a collapsible tree. Force-directed or similar — nodes colored by `kind`, edges labeled by `role`. The DAG shape is the point; flattening it to a tree hides the parents-shared-across-children topology that makes provenance interesting. Concrete implementation deferred to slice 9; tech options include react-flow, cytoscape, vis-network.

### 6.3 Skills

- List of `kind=skill` items with: name, last-activated, helped/hurt counts, confidence, source claim count.
- Click → SKILL.md preview + parents.
- Disable/enable toggle per skill.
- This is the only place the user "manages" memory in the sense of changing future behavior; everything else is observation/audit.

### 6.4 Search

One search box. Hybrid retrieval. Default filters: `status=active`, `scope ∈ {user, current_project}`. Power-user filters: kind, scope override, status (include superseded/archived for forensics), date range, source kind.

### 6.5 What's gone

- "Library with 4187 facts" — replaced by Search.
- "Review with draft/active/superseded/archived per type" — folded into Today (proposals + low-confidence) and Search (forensics).
- "Activation" — replaced by Skills usage + Search filter.

### 6.6 UX research grounding (directional)

These are pattern matches from the UX research pass, not URL-cited inline. Tighten before any external publication.

- "Today / changes feed" pattern: matches Rewind, Granola, Limitless "what happened" surfaces.
- Graph walk for provenance: matches Cursor `@`-mentions for files + Anthropic Projects citations.
- Skills-as-files: matches Cursor rules, Continue rules, Anthropic Skills.
- One unified search with filters: matches Notion AI, Mem0 dashboard, Zep dashboard.

Failures we're avoiding (from publicly discussed criticism):
- ChatGPT memory page (2024–2025): flat list, no provenance, no temporal sense. Users could not find what mattered or why something was remembered.
- Mem0 dashboard: type-zoo-ish; required understanding internal categories.
- Current ntrp Memory tab: type-tabs with raw counts; the failure we're explicitly replacing.

---

## 7. Build order

Slices in the order I'd ship them. Each is small enough to land in one PR with tests + thermo review.

1. **Backup + burn.** Copy `~/.ntrp/memory.db` to `~/.ntrp/memory.db.bak.2026-05-27`. Drop all current memory tables (see scratchpad §7). Create `memory_items` + `memory_item_parents` + FTS/vec satellites. Write schema tests.
2. **Chat connector + episode close.** Emit `kind=episode` from chat session activity with hybrid boundary triggers. Backfill nothing.
3. **Retrieval layer.** New query API used by chat injection, operator, background, research. Hybrid scoring. Activate against the new table.
4. **Pattern finder, pass 1 (episode → observation).** Scheduled automation. Validate output by sampling.
5. **Pattern finder, pass 2 (observation/claim → claim).**
6. **Contradiction watcher.** With auto-supersede + Today surface.
7. **Skill inducer + `is_toolable` gate.** Emit proposals.
8. **UX: Today + Search.** Behind a flag while old Memory tab is still up.
9. **UX: Graph + Skills views.** Old Memory tab removed.
10. **Future: additional connectors.** Gmail, calendar, slack, dex run logs — one at a time, each behind its own flag, each with its own dedupe/marker logic. **Out of scope for v1**; chat-only for slices 1–9. The connector interface is designed so adding sources later is mechanical: implement `(poll/webhook) → dedupe → normalize → emit memory_item`.

After (1)–(3): a working simpler memory with nothing of the old shape, chat-only. After (4)–(7): continual learning on chat. After (8)–(9): honest UX. After (10), much later: multi-source.

---

## 8. Open questions

### Resolved
- **Topic shift threshold.** Hard limit: 0.3 cosine drop vs running centroid. Tune later if needed.
- **Episode boundary defaults per source.** Chat: 50 turns / 10 min idle / 5-turn sliding overlap. Gmail: per thread. Calendar: per event. Files: per save-burst (~5 min idle). Idle gap is the dominant trigger in practice.
- **Skill confidence decay.** No auto-deactivate. If a skill hasn't helped in N activations, surface in Today with a "review this skill" card.
- **`artifact_ref` vs `skill` separation.** Keep both. Skill = procedural intent (hot-path activated), artifact_ref = passive bookmark. Collapse rejected (see §2.8 item 2).
- **Cross-scope contradiction.** Scoped override, both stay active. Retrieval surfaces both to the LLM as "general: X. In this project: Y." See §3.4 cross-scope rule.

### Still open
- **`proposal` as separate kind vs `status=draft` flag.** Defer; reassess after a few weeks of real proposal queue usage.
- **Confidence-formula constants** (`d=0.5`, `S=100`, `k=0.4`, the floors, the bucket thresholds) — locked from prior art but will likely need empirical tuning once we have real activity. Built-in as config values, not code constants, so they can be adjusted without a migration.

---

## 9. References

- Scratchpad: `docs/internal/ntrp-memory-redesign-scratchpad.md`
- Zep / Graphiti — bi-temporal model, episodes. https://help.getzep.com/graphiti
- Mem0 — flat memory strings, dedupe pipeline. https://docs.mem0.ai/
- A-MEM (Xu et al. 2024) — atomic notes + inferred links.
- MemoryOS — arXiv:2506.06326 (buffer + promote-on-overflow).
- Letta sleeptime — arXiv:2503.18931 (idle-time consolidation, pattern reference only).
- Generative Agents — arXiv:2304.03442 (reflection cycle, pattern reference only).
- Reflexion — arXiv:2303.11366 (verbal reinforcement).
- Voyager — arXiv:2305.16291 (skill library induction).
- Event Segmentation Theory — Zacks 2007, https://psycnet.apa.org/record/2007-04149-002.
- Ebbinghaus forgetting curve refit — Murre & Dros 2015, https://doi.org/10.1371/journal.pone.0120644.
- ACT-R Base-Level Learning — Anderson et al. 2004, https://act-r.psy.cmu.edu/publications/pubinfo.php?id=628.
- SuperMemo SM-2 — Wozniak 1987, https://supermemo.guru/wiki/Algorithm_SM-2.
- Leitner system — https://en.wikipedia.org/wiki/Leitner_system.
- Anthropic Skills — https://www.anthropic.com/news/agent-skills (skills-as-files).
- Third Layer browser-trajectory → SOP project — Slack `#tim-x-thirdlayer`.
- Internal: tim's Dex work — file-based skills + recordings direction.

---

## 10. Status

- §1 principles: locked.
- §2 data model: locked. `episode / observation / claim / skill / proposal / artifact_ref`. Edge table with five roles. §2.8 lists three honest collapse candidates to revisit after first slices ship.
- §3 stages: locked. Six stages, each with grounded justification. §3.7 confidence formula now concrete with worked example, sanity checks, and 30-line reference implementation.
- §4 data flow: locked. Worked example covers happy path + correction path + skill induction path.
- §5 external sources + CL: locked. Per-source connector pattern + three-cycle CL diagram.
- §6 UX: locked direction. Concrete cards/views described; UX claims labeled directional, not URL-cited.
- §7 build order: 10 slices.
- §8 open questions: 6 small items to resolve during build.

### Self-audit notes
- **Weakest justification**: `proposal` as its own kind. Real collapse candidate. Spec flags this.
- **Real redundancy**: `skill` and `artifact_ref` both carry `artifact_ref`. Acknowledged in §2.8.
- **Complexity worth challenging**: `confidence: float` vs a `trust` enum. Acknowledged in §2.8.
- **Citation rigor**: §6 UX is directional, not inline-cited. Tighten if used externally.

**This spec is ready to start cutting code against.** Begin at slice 1 when given the go-ahead.
