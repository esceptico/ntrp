# ntrp memory redesign — scratchpad

Status: draft / thinking out loud. Not a final spec. Living doc.
Owner: tim + ntrp
Started: 2026-05-27
Last edit: 2026-05-27 (naming converged to event/summary/fact/skill)

---

## 0. Why this exists

Current memory is a taxonomy hell. We have 5 active + 5 deprecated object types, a parallel cached workflow-cluster layer, marker objects on the side, a 4-tab Review UI, and the user (tim) keeps hitting weirdness because the model doesn't match how he thinks about memory.

Concrete state of the live DB as of 2026-05-27:

| object_type | status | count |
|---|---|---|
| fact | active | 4187 |
| fact | superseded | 84 |
| lesson | active | 70 |
| lesson | superseded | 16 |
| artifact | active | 93 |
| memory_episode | active | 236 |
| memory_episode | archived | 78 |
| action_candidate | draft | 87 |
| action_candidate | archived | 1 |
| procedure_candidate | archived | 6 |
| run_provenance | archived | 160 |

Plus separate `observations` (10458), `facts` (5675, legacy), `entities` (6580), `memory_events` (14643), `memory_access_events` (724). Two parallel storage layers (legacy facts/observations + new knowledge_objects) with overlapping responsibilities.

The user has explicitly said: **burn it and start over.**

---

## 1. What we already consolidated on (chat history)

1. **One primitive, not a zoo of types.** A `memory_item`. `kind` is an informational tag, not a schema branch.
2. **DAG of items via parents**, not a level integer. Abstraction is emergent from graph depth.
3. **Role-typed parent links**: `step | evidence | contradicts | supersedes | similar_to`. Order optional for `step`.
4. **Provenance is first-class and non-negotiable.** `recorded | inferred | user_authored | external` + structured `source_refs[]`.
5. **Temporal validity (Graphiti-style).** Items are never deleted at runtime. `status ∈ {active, superseded, archived}` + `valid_from`, `invalid_at`.
6. **Skills leave the DB.** They live as files in `~/.ntrp/skills/`. The DB only holds a `kind=skill` item with `artifact_ref` + usage + lifecycle.
7. **Consolidators are background automations.** We already have automations. Each consolidator: read items → group → emit a new item with typed parents.
8. **UX is not type-tabs.** It's `Today / Graph / Skills / Search`. No more "Library with 4156 facts" page.
9. **Confidence is a real number, derived from non-LLM signals only.** Never written by an LLM.
10. **Migration is burn-the-db.** One backup, then drop every old table. No backfill plan.

---

## 2. Prior art check — are we reinventing something?

Short answer: no, but we're synthesizing three established shoulders. We're not first, but the combination is fresh.

| Idea | Closest prior art | What we keep, what differs |
|---|---|---|
| One free-form primitive | Mem0 flat strings, A-MEM atomic notes | Keep. We add stricter provenance and richer parent links. |
| Temporal validity (`valid_from / invalid_at`, contradiction → invalidation not deletion) | Zep / Graphiti bitemporal model | Keep, directly stolen. |
| Recorded vs inferred split | Hindsight (vectorize) — world/experience (recorded) vs observation/opinion (inferred) | Keep the *distinction*, drop the 4-network architecture. Collapsed to a single `provenance` enum. |
| DAG via parents, not levels | A-MEM (atomic notes + inferred links, Zettelkasten-style) | A-MEM uses `related_to` only. We add role-typed links. |
| Role-typed edges (`supersedes`, `contradicts`, `evidence`) | RDF/OWL, generic KG; not common in agent memory. Graphiti has implicit invalidation but not explicit edge roles. | Net-new in agent-memory space as far as I can find. |
| Sleep-time / background consolidator | Mem0 async extraction, Graphiti background ingest, Letta sleeptime (arXiv:2503.18931, noted only for the pattern, not the primitives) | Keep. Ours = ntrp automations. |
| Skills as files, memory holds pointer + usage | Dex's direction; Anthropic Claude memory tool (file-backed) | Keep. |
| Workflow induction from traces | Voyager descendants; Third Layer "browser trajectory → SOP" project (per `#tim-x-thirdlayer`) | Keep as a *consolidator*, not a primitive. `is_toolable` gate lives here. |

The role-typed edges are the one piece worth defending as novel.

---

## 3. The data model

### Naming convention

Final pick after multiple rounds with tim: `episode → observation → claim → proposal → skill` (+ `artifact_ref`).

| kind | meaning | typical provenance |
|---|---|---|
| `episode` | session/multi-turn rollup — "what happened in this slice of activity" | `inferred` |
| `observation` | mid-level instance/witnessed pattern, still context-bound | `inferred` |
| `claim` | decontextualized assertion, holds across situations | `inferred` or `user_authored` |
| `skill` | procedural — has `artifact_ref` to a file in `~/.ntrp/skills/` | `inferred` (promoted) or `user_authored` |
| `proposal` | pending review — becomes `skill` or `claim` on approval | `inferred` |
| `artifact_ref` | pointer to a large external artifact (file, doc, URL) | any |

Pipeline: `episode → observation → claim → proposal → skill`.

**Raw atomic entries are not a `kind`.** They live in their original source (session store, filesystem, gmail, slack, dex runs, etc.). Episodes reference slices of them via `source_refs[]`. This matches the dominant pattern across Mem0, Graphiti, A-MEM, LangMem, MemoryOS — only Claude's memory tool treats raw turns as first-class, and it's the outlier.

`episode` here matches the semantics of the current `memory_episode` type in the live DB: a closed multi-turn slice waiting to be abstracted. `observation` is the mid-level witnessed pattern from one or more episodes. `claim` is the time-decontextualized assertion (what the current schema calls `fact`/`lesson`).

### `memory_item`

```python
class MemoryItem:
    id: str
    kind: Literal["episode", "observation", "claim", "skill", "proposal", "artifact_ref"]
    content: str                          # the actual text/payload
    provenance: Literal["recorded", "inferred", "user_authored", "external"]
    source_refs: list[SourceRef]          # always populated; empty list invalid for non-user_authored
    confidence: float                     # 0..1, DERIVED. Never written by an LLM.
                                          # Computed from evidence/contradictions/recency/usage. See §8.
    status: Literal["active", "superseded", "archived"]
    valid_from: datetime
    invalid_at: datetime | None
    scope: Scope                          # user | project:<id> | session:<id>
    tags: list[str]
    artifact_ref: str | None              # path/uri for kind=skill or kind=artifact_ref
    usage: UsageRollup                    # counters, maintained by recorders
    feedback: FeedbackRollup              # ratings, maintained by recorders
    created_at: datetime
    updated_at: datetime
    # parents live in a separate edge table (memory_item_parents) — see below.
```

### `memory_item_parents` (edge table)

```python
class MemoryItemParent:
    child_id: str
    parent_id: str
    role: Literal["step", "evidence", "contradicts", "supersedes", "similar_to"]
    order: int | None     # only meaningful for role=step
```

### `SourceRef`

```python
class SourceRef:
    kind: Literal["chat_msg", "file", "url", "tool_call", "automation_run", "user_input"]
    ref: str              # opaque id/uri
    captured_at: datetime
```

### `Scope`

String: `"user"` or `"project:<id>"` or `"session:<id>"`. Defaults to `user`. No bubble-up infra.

### What's *not* a separate table

- No `workflow_clusters`, no `skill_promotions`, no `action_candidate` table.
- A workflow cluster is a `kind=claim` (or `kind=observation` if not yet abstracted) with N `role=step` parents.
- A skill promotion is a `kind=proposal` with parents pointing to its evidence.
- A consolidation candidate is just a `kind=claim` with low confidence — surfaces in Today automatically.

### Indexes

- FTS on `content`
- Vector on `content` (re-embedded on `content` change; cached otherwise)
- B-tree on `(status, scope, kind)` — speeds up the hot "list active items in scope X of kind Y" query that retrieval and UI run constantly. Without it, sqlite scans the full table.
- B-tree on `(valid_from)` and `(invalid_at)` — for point-in-time queries and the active-window filter.
- Edge table indexes on `(child_id)` and `(parent_id)` for both directions of DAG walks via recursive CTE.

---

## 4. The pipeline (the "how")

Same primitive, four operations. Each is a background automation.

```
  INGEST              CONSOLIDATE                ABSTRACT                  PROMOTE
source connector →  close current episode →  group N episodes/obs    →  gate by is_toolable
emit kind=episode   when boundary fires      emit kind=observation       emit kind=proposal
parents=[]          (already kind=episode)   role=evidence parents       parents=[claims]
source_refs=[…]                              then group obs/claims        user approves →
                                             emit kind=claim              kind=skill +
                                             role=evidence parents        artifact_ref to file
```

### The four consolidators (all automations)

1. **Episode closer** — watches an active episode buffer; closes it into a final `kind=episode` item when a boundary trigger fires (see §4.1). Cheap. The episode item gets `source_refs[]` pointing at the raw turns/events in the source-of-truth store.
2. **Pattern finder** — runs daily. Two passes:
   - **episodes → observations**: clusters episodes by semantic + tag similarity, emits `kind=observation` with `role=evidence` parents.
   - **observations + claims → claims**: clusters observations and existing claims, emits `kind=claim`. Can consume other claims (patterns of patterns).
3. **Contradiction watcher** — for any new `kind=claim`, finds existing active claims with opposite content → emits edge `role=contradicts`. **Auto-flips** the older one to `status=superseded` with `invalid_at=now` by default; surfaces the action in Today with one-click undo. User can also manually flip status from the UI at any time.
4. **Skill inducer** — for claims that pass `is_toolable` (see §5) → emits `kind=proposal` with a draft skill file. User approves → flip to `kind=skill, status=active`.

### 4.1 Episode boundaries — when do we close one and start the next

Long sessions (1000+ turns) can't be one episode. We need a trigger.

**The trigger is hybrid** — any of these fires a close (whichever comes first):

| Trigger | Default threshold | Rationale |
|---|---|---|
| **Turn / token budget** | 50 turns OR ~8k content tokens | bounds episode size so summaries stay useful |
| **Idle gap** | 10 min of inactivity | natural conversation breaks; tim confirmed this works in practice |
| **Topic shift** | embedding cosine drop > 0.3 across recent N turns | semantic boundary detection |
| **Session close** | explicit | for sources that have an end (a closed chat, a finished dex run) |

Each connector configures its own thresholds. Chat episodes might fire on idle gap. Dex run episodes fire on run end. Email episodes fire on thread completion. Etc.

Defaults are tunable, not load-bearing. Start with the values above, move them based on telemetry.

**Prior art for this exact pattern**:
- MemoryOS (arXiv:2506.06326) — fixed buffer + promote-on-overflow. Buffer fullness is the trigger.
- Letta sleeptime agents (arXiv:2503.18931) — idle time is the trigger.
- Generative Agents (arXiv:2304.03442) — accumulated importance threshold fires reflection.
- Graphiti (https://help.getzep.com/graphiti) — every turn is its own episode node; no bundling. We're chunkier than Graphiti on purpose.
- Event Segmentation Theory (Zacks 2007, https://psycnet.apa.org/record/2007-04149-002) — cog-sci basis: humans segment continuous experience at prediction-error boundaries (≈ our topic-shift trigger).

We're not implementing the wheel. Hybrid (budget OR idle OR topic-shift OR explicit) is the standard pattern across 2024–2026 systems.

### 4.2 Multi-source ingest (gmail / slack / dex / calendar / browser / chat)

ntrp memory is not chat-only. Any source can feed it via a **connector**.

```
gmail connector       ─┐
slack connector       ─┤
calendar connector    ─┼─►  normalize  ─►  emit episode  ─►  pattern finder ...
dex run connector     ─┤
browser connector     ─┤
chat hook (existing)  ─┘
```

Each connector is an automation that:
- pulls or receives from its source (poll or webhook),
- dedupes against a last-seen marker,
- emits one or more `kind=episode` items (the pipeline takes over from there),
- populates `source_refs[]` with a source-specific ref so we can always walk back.

`SourceRef.kind` enum extends to cover every source:

```python
class SourceRef:
    kind: Literal[
        "chat_msg", "file", "url", "tool_call", "automation_run", "user_input",
        "email", "slack_msg", "calendar_event", "dex_run", "browser_event",
    ]
    ref: str
    captured_at: datetime
```

#### Do all sources become episodes?

Default: **yes, every source emits `kind=episode`**, pipeline handles it uniformly.

But connectors can short-circuit when the source is already structured enough:
- A calendar event → emit `kind=claim` directly ("meeting with X on date Y", `provenance=external`). No episode needed.
- A dex skill-execution log → emit `kind=observation` directly (it's already a witnessed instance).
- A signup confirmation email → `kind=claim` ("user signed up for service X on date Y").

Episode is the default; short-circuiting is a per-connector choice.

#### Provenance / confidence base by source

| Source | provenance | confidence base |
|---|---|---|
| chat (user) | `recorded` | high |
| chat (assistant) | `recorded` | medium |
| file/fs activity | `recorded` | high |
| gmail | `external` | medium |
| slack | `external` | medium |
| calendar | `external` | high (structured) |
| dex run logs | `external` | high (structured) |
| browser events | `external` | low (noisy) |
| user-typed item in UI | `user_authored` | very high |

Confidence is still derived (§8.2), but each source has a different base.

#### Cross-source dedup

If the same thing shows up in gmail and slack ("Tim accepted meeting"), pattern finder sees two episodes with overlapping content and emits **one** `kind=claim` with both as `role=evidence` parents. No new dedup infra; existing consolidator does it.

### What lives outside consolidators

- **Connectors** (ingest from any source) — automations on a schedule or webhook trigger. Emit memory_items, don't consume them.
- **Retrieval** — query layer over `memory_items` filtered by `status=active`, scope, and validity window (`valid_from <= now AND (invalid_at IS NULL OR invalid_at > now)`).

### Why this is simpler than current

Current: ingest → write to facts/observations → run reflector → write knowledge_objects → run workflow miner → write workflow_clusters cache → run skill_promotions → write action_candidates → user approves → write skill files. Five storage shapes, three sync points, two cache layers, chat-only.

New: connector emits episode → consolidators read/write items → skill files. One shape. Provenance is the only structural distinction. Any source plugs in by adding a connector.

---

## 5. Continual learning — how it actually works here

CL for an agent that doesn't fine-tune = three loops, all expressed as consolidators on the same primitive:

### Loop A: Reflection (Reflexion lineage)
- During a task, raw turns/tool-calls stay in their source-of-truth store (chat session, run logs, etc.). The chat connector emits a `kind=episode` item when the boundary trigger fires (idle gap, turn budget, topic shift, or explicit close).
- Pattern finder consolidates episodes into `kind=observation` and then into `kind=claim`.

### Loop B: Skill induction (Voyager + Third Layer "browser trajectory → SOP")
- Pattern finder identifies repeated workflows (a fact with `role=step` parents = ordered event chain seen >= N times).
- Skill inducer applies the `is_toolable` gate:
  1. **Repetition** — count of independent instances above baseline.
  2. **Determinism** — low variance in steps across instances.
  3. **Trigger** — first step / precondition identifiable from input context.
  4. **Success signal** — outcome can be checked (explicit metadata, or absence of correction within N turns).
- Pass → `kind=proposal` with a draft skill file. User approves → becomes `kind=skill`.
- Critically: skill file lives in `~/.ntrp/skills/`. The memory_item is the *pointer* + usage + lifecycle.

### Loop C: Contradiction resolution (Graphiti pattern)
- When the user corrects ntrp ("no, I use Adidas now"), the chat connector emits an episode covering that turn. Pattern finder emits a new claim ("user has Adidas"). Contradiction watcher sees it conflicts with the active "user has Nike" claim and auto-flips Nike to `superseded` with `invalid_at=now`. The action surfaces in Today with one-click undo. The Nike claim is never deleted. Query-at-time still returns Nike for `t < now`.

### Why "we apply CL to it" works
The system is one homogeneous substrate. Every CL technique in the literature (Reflexion, Voyager, AriGraph, A-MEM links, Graphiti invalidation) maps to "another consolidator". We don't need a new schema per technique. We add an automation.

---

## 6. UX — what the user actually sees

### Today (default view)
- New skills since last open
- New contradictions detected and auto-resolved (with undo)
- Items the consolidator flagged as low-confidence and wants confirmation
- Recent supersessions
- Lightweight feed of cards. ~20 items max. Not a stream you scroll forever.

**Not on Today**: the thousands of active claims. Those are infrastructure, not UX.

### Graph
- Pick any item → see parents (where it came from) and children (what was derived from it).
- Walk up: skill → fact → summary → event → original chat message.
- This *is* provenance. No separate "audit" view.

### Skills
- The only place where memory affects *future* behavior in a big way.
- List of `kind=skill` items, with usage stats and "last helped" / "last hurt" counters.
- Click a skill → see source claims (parents).

### Search
- One search box. Full-text + vector + filters (kind, scope, status, tags).
- Default filter: `status=active, scope ∈ {user, current_project}`.
- Power-user can change filters to dig into archived/superseded for forensics.

### What's gone
- "Library" tab with 4187 facts → Search.
- "Review" tab with draft/active/superseded/archived per type → Today + Search filters.
- "Activation" tab with model-visible vs observed-used → folded into Skills (usage stats) and Search (a filter).

---

## 7. Burn list — every old table goes

**All tables below are dropped.** Backup is taken once at `~/.ntrp/memory.db.bak.2026-05-27`. Nothing is migrated. Old shape and old data both die together.

| Current table / type | Fate |
|---|---|
| `knowledge_objects` (+ FTS/vec satellites) | dropped |
| `facts` (legacy + FTS/vec) | dropped |
| `observations` (legacy + FTS/vec) | dropped |
| `entities`, `entity_aliases`, `entity_*`, `knowledge_entity_refs`, `obs_entity_refs` | dropped. If we ever need entity resolution again, re-introduce as a separate layer. |
| `memory_events`, `memory_access_events` | dropped. Telemetry, not memory. Move to a separate analytics table or a flat log if we still want usage stats. |
| `temporal_checkpoints` | dropped |
| `action_candidate`, `procedure_candidate`, `run_provenance`, `pattern`, `entity_profile`, `profile_tier`, `memory_episode` (legacy types) | dropped — these were `object_type` rows inside `knowledge_objects` and die with the table |
| `workflow_clusters` cache and marker objects | dropped — clusters are first-class `kind=claim` items in the new schema |
| `skill_promotions` flow | dropped — replaced by `kind=proposal` → user approve → `kind=skill` |
| Review UI (4 tabs) | replaced by Today + Search |
| Activation UI | replaced by Skills usage + Search filter |

**What the new schema starts with**: `memory_items` + `memory_item_parents` + FTS/vec satellites for `memory_items.content`. That's it.

---

## 8. Resolved decisions (was open questions)

1. **Edge table vs JSON parents** → edge table `memory_item_parents(child_id, parent_id, role, order)`. JSON is a footgun for graph walks. (tim, 2026-05-27)
2. **Confidence scoring** → keep `confidence: float` on the item, but **always derived from non-LLM signals**. No LLM ever writes to it. Inputs:
   - `provenance` (recorded > inferred > external)
   - count and confidence-weighted sum of independent `evidence` parents (better evidence > more evidence)
   - count of unresolved `contradicts` edges against this item
   - recency of last supporting `source_ref` or `evidence` parent
   - usage feedback rollup (helped / hurt counters)
   Recomputed by the consolidator/watcher whenever a relevant edge or feedback event fires. UI may bucket for display, the underlying number is real and queryable. Rationale: LLMs are miscalibrated number-estimators; serious systems (Graphiti, A-MEM) don't store an LLM-asked float. Mem0 does and is widely seen as noisy. (tim, 2026-05-27)
3. **Auto-supersede vs ask** → auto-flip by default; surface in Today feed with one-click undo. UI also exposes manual status changes for any item. No threshold-asking. (tim, 2026-05-27)
4. **Embedding strategy** → re-embed on `content` change, cache aggressively otherwise. (tim, 2026-05-27)
5. **Migration plan** → burn it. One backup at `~/.ntrp/memory.db.bak.2026-05-27`, then drop every old table. No parallel writes, no backfill, no read-from-old fallback. If we lose something later, we restore from backup manually. (tim, 2026-05-27)
6. **is_toolable thresholds** → start with baselines (~3 repetitions, similarity ~0.7) but **don't lock numbers**; tune from telemetry. (tim, 2026-05-27)
7. **`similar_to` edges** → compute live via vector search initially. Add a `// TODO: materialize if hot` comment in retrieval code. (tim, 2026-05-27)
8. **Today needs feed or counts** → lightweight feed of cards for awareness. Not a stream. ~20 items max. (tim, 2026-05-27)
9. **Scope inheritance** → explicit only. Pass project id on write, filter on read. No bubble-up infra. (tim, 2026-05-27)
10. **Empty `parents`** → fine. Empty + `recorded` = raw event; empty + `user_authored` = manually typed fact. (tim, 2026-05-27)

## 8.5. Remaining open questions

- **Confidence formula.** §8.2 sketches the inputs. Need concrete arithmetic before coding. Sketch:
  ```
  base = {recorded: 0.9, inferred: 0.5, user_authored: 0.85, external: 0.6}[provenance]
  evidence_bonus  = min(0.3, 0.05 * sum(parent.confidence for parent in evidence_parents))
  contradict_pen  = 0.15 * count(unresolved contradicts edges)
  recency_decay   = max(0, 0.05 * months_since_last_support)
  usage_adj       = 0.05 * tanh(helped - hurt)
  confidence = clamp(base + evidence_bonus - contradict_pen - recency_decay + usage_adj, 0, 1)
  ```
  Tune from real data once we have any.
- **Summary boundary heuristic.** What groups events into one summary? Session boundary is obvious; topic clustering inside a long session is fuzzier. Start with: same session AND same top-level chat thread.
- **Are we sure `artifact_ref` and `skill` need to be separate kinds?** Both have `artifact_ref` pointing at a file. The difference is intent — skill is procedural, artifact_ref is just "a file we care about". Maybe keep both, maybe collapse. Decide when writing the spec.

---

## 9. What I'd build first (rough order)

Don't take this as a plan yet — just a sequence to argue with.

1. **Backup + burn.** Copy `~/.ntrp/memory.db` to `~/.ntrp/memory.db.bak.2026-05-27`, drop every table from §7, ship the new `memory_items` + `memory_item_parents` schema with FTS/vec satellites.
2. **Ingest path.** Chat/tool/file connector emits `kind=episode` items on the configured boundary trigger (idle gap / turn budget / topic shift / explicit close), with proper `source_refs[]`. Additional connectors (gmail, slack, calendar, dex, browser) ship behind their own automations, same shape.
3. **Retrieval.** New query layer over `memory_items` filtered by `status=active`, scope, validity window. Used by chat injection, operator, background, research.
4. **Episode closer + pattern finder** consolidators (automations). Watch what they produce.
5. **Pattern finder** consolidator.
6. **Contradiction watcher.**
7. **Skill inducer + is_toolable gate.**
8. **UX.** New Today + Search + Graph + Skills views. Old Memory tab gone.

After (1)–(3) the assistant has a working simpler memory and nothing of the old shape remains. After (4)–(7) we have continual learning. After (8) the UX is honest about what's in the DB.

---

## 10. The one-paragraph version

ntrp memory becomes one table of `memory_item` rows. Each row has a `kind` tag (`episode`, `observation`, `claim`, `skill`, `proposal`, `artifact_ref`), a `provenance` (`recorded`, `inferred`, `user_authored`, `external`), a `confidence` float that is always derived from non-LLM signals (evidence parents, contradictions, recency, usage), temporal validity (`valid_from`, `invalid_at`, `status`), and a list of role-typed parent links forming a DAG (`step`, `evidence`, `contradicts`, `supersedes`, `similar_to`) stored in `memory_item_parents`. Raw atomic turns/tool-calls stay in their source-of-truth store (chat session, run logs, gmail, slack, dex, calendar, browser) and are referenced via `source_refs[]`. Skills live as files in `~/.ntrp/skills/`; the DB stores the pointer + usage. Per-source connectors emit `kind=episode` items on a hybrid boundary trigger (turn budget OR idle gap OR topic shift OR explicit close), and four background automations — episode closer, pattern finder, contradiction watcher, skill inducer — read items, group them, emit new items with parents. That's the entire continual-learning loop. The UI is Today / Graph / Skills / Search, not type-tabs. Nothing is deleted at runtime; contradictions invalidate, they don't erase. Provenance is non-optional. Migration plan: backup the current DB once, drop every old table, start fresh on the new schema.

---

## 11. References / shoulders we're standing on

- **Zep / Graphiti**: bitemporal knowledge graph. Source for: `valid_from / invalid_at`, contradiction-by-invalidation, "summary" naming.
- **Mem0**: flat NL strings + dedupe pipeline. Source for: simplicity bias, async extraction, "fact" naming.
- **A-MEM**: atomic Zettelkasten notes with inferred links. Source for: DAG over uniform primitives.
- **Hindsight (vectorize)**: recorded vs inferred split. Source for: `provenance` as first-class.
- **Squire 1992 / ACT-R**: episodic / semantic / procedural taxonomy. Source for: naming legitimacy.
- **AriGraph (2024)**: episodic edge / event terminology. Source for: "event" as the raw-layer name.
- **Reflexion** lineage: reflection → memory updates. Source for: pattern finder + episode closer pattern.
- **MemoryOS** (arXiv:2506.06326). Source for: buffer + promote-on-overflow trigger.
- **Letta sleeptime agents** (arXiv:2503.18931). Source for: idle-time trigger (only — we're not adopting Letta primitives).
- **Generative Agents** (arXiv:2304.03442). Source for: accumulated-importance trigger (only — we're not adopting Park primitives).
- **Event Segmentation Theory, Zacks 2007** (https://psycnet.apa.org/record/2007-04149-002). Source for: cog-sci basis for topic-shift trigger.
- **Voyager** descendants and Third Layer "browser trajectory → SOP" project (`#tim-x-thirdlayer`): skill induction from trajectories. Source for: `is_toolable` gate.
- Internal: tim's Dex work moving toward file-based skills + recordings. Source for: skills-as-files.

---

## 12. Status

- §3 data model: tim signed off with edits — naming converged to `event / summary / fact / skill / proposal / artifact_ref`, `content_schema` dropped, `confidence` kept as a derived float (never written by LLM).
- §4 pipeline: tim signed off; episode closer emits `kind=episode` on hybrid boundary trigger (turn budget, idle gap, topic shift, explicit close), pattern finder runs two passes (episode→observation, observation→claim), contradiction watcher auto-flips by default. Multi-source ingest pattern (gmail/slack/calendar/dex/browser/chat) documented in §4.2.
- §8: all 10 questions resolved. Three smaller questions in §8.5 to resolve while building.
- Next step: write the real spec at `docs/internal/ntrp-memory-redesign-spec.md` with schema DDL, consolidator interfaces, migration script, and a phased build plan.
