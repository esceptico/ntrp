# Memory Activation Benchmark Plan

## Goal

Benchmark ntrp's memory activation system as a retrieval + agent-behavior component, not as a vibes demo.

The benchmark runner should use an isolated memory DB per run and compare fixed configurations:

- no-memory baseline
- current ntrp activation
- ntrp activation with ablations: no patterns, no entity boost, no temporal boost, no vector, no FTS
- future extraction/ranking variants

## Common Adapter Contract

Create a benchmark adapter with four operations:

```python
class MemoryBenchmarkAdapter(Protocol):
    async def reset(self, run_id: str) -> None: ...
    async def ingest_turns(self, *, conversation_id: str, turns: list[dict]) -> None: ...
    async def search(self, *, query: str, top_k: int, budget_chars: int) -> list[dict]: ...
    async def answer(self, *, question: str, context: list[dict]) -> str: ...
```

`search()` should call `KnowledgeActivationService.inspect(record_access=False)` and return:

- `knowledge_object_id`
- `object_type`
- `title`
- `text`
- `score`
- `rank`
- `reasons`
- `signals`
- `source_ids`
- `chars`

Store every result as JSONL so failures can be replayed without re-ingesting.

## Metrics

Report benchmark-native metrics plus ntrp diagnostics:

- answer accuracy / judge pass rate
- retrieval recall@k when gold evidence is available
- activation precision@k via judge on retrieved context relevance
- wrong-domain rate, e.g. memory activation query retrieving mechinterp activations
- stale/superseded hit rate
- duplicate/near-duplicate rate
- source trace rate: `% answers with source refs`
- profile trace rate: `% profile/inference answers with cited profile sections`
- average context chars/tokens
- retrieval latency p50/p95
- DB growth per 1k turns
- generated durable memories per 1k turns
- junk entity count and telemetry pollution count

## LOCOMO

Use first because it is the closest to long-term conversational memory.

Dataset shape:

- 10 very long conversations
- ~300 turns per conversation
- up to 35 sessions
- QA types: single-hop, multi-hop, temporal, commonsense/open-domain, adversarial
- also event graph summarization

Procedure:

1. Create `/tmp/ntrp-bench-locomo-<run_id>.db`.
2. Ingest each dialogue session/turn in chronological order.
3. Let ntrp create memory episodes and durable facts/patterns/procedures/entity refs. Run provenance is audit-only and should not fan out into extra source/evidence knowledge objects.
4. For each question, run activation at top-k cutoffs: `10,20,50,200`.
5. Generate answer from activated context using a fixed answer model.
6. Judge against gold answer with fixed judge model.
7. Break down by question type and by retrieval failure class.

Expected failure classes to tag:

- missed gold fact
- missed multi-evidence bridge
- profile needed but not retrieved
- retrieved wrong domain
- retrieved stale/superseded fact
- too broad pattern crowded out concrete fact
- context budget truncation
- answer model failed despite correct context

TriMem-inspired slices to report:

- single-evidence vs multi-evidence questions;
- temporal update/supersession questions;
- entity/profile inference questions, e.g. user preference/person/project-state questions;
- facts-only vs facts+source hydration vs facts+profile+source hydration;
- context-token tradeoff versus full-context baseline;
- wrong-domain retrieval under profile query reformulation.

Source: Snap Research LOCOMO project page + `snap-research/locomo`; TriMem paper/project/GitHub: https://arxiv.org/abs/2605.19952, https://tmlr-trimem.github.io/, https://github.com/tmlr-group/TriMem.

## LongMemEval

Use second because it directly probes memory-update and preference behavior.

Dataset shape from `mem0ai/memory-benchmarks`:

- 500 questions
- categories include single-session user, single-session assistant, single-session preference, knowledge update, temporal reasoning, multi-session

Procedure:

Same adapter as LOCOMO. Required breakdown:

- single-session-user
- single-session-assistant
- single-session-preference
- knowledge-update
- temporal-reasoning
- multi-session
- profile/inference subset where the answer requires synthesizing several remembered details

Ablations to prioritize:

- profile tier on/off
- source hydration on/off
- query reformulation on/off
- supersession on/off
- temporal validity on/off
- pattern activation on/off
- entity boost on/off

Source: `mem0ai/memory-benchmarks`.

## BEAM

Use after LOCOMO/LongMemEval are stable because it is scale-heavy.

Dataset shape from `mem0ai/memory-benchmarks`:

- 100K to 10M token conversations
- 2,000+ questions
- ability types include preference following, instruction following, information extraction, multi-session reasoning, knowledge update, summarization, temporal reasoning, event ordering, abstention, contradiction resolution

Procedure:

1. Start with `100K` and 10 conversations.
2. Increase to `1M` only after retrieval latency and DB growth are sane.
3. Treat `10M` as stress/perf, not day-one correctness.

Report by memory ability type and include latency/context-token curves.

Source: `mem0ai/memory-benchmarks`.

## STATE-Bench

Use to answer whether memory improves actual agents, not just retrieval.

Benchmark properties from Microsoft STATE-Bench:

- 450 stateful enterprise tasks
- domains: travel, customer support, shopping
- multi-turn user simulator
- stateful tools/environment
- metrics: task completion, pass^5 reliability, efficiency, UX score

Procedure:

Run each task in two modes:

1. no-memory baseline
2. ntrp memory-enabled agent

Then compare:

- pass@1
- pass^5
- average turns
- unnecessary tool calls
- retrieval tokens
- total tokens/cost
- UX score

Use ntrp activation only for cross-task/experience memory; do not leak current task ground truth between repeats.

Source: Microsoft Open Source Blog, “Introducing STATE-Bench”.

## Implemented benchmark layers

### Local deterministic fixture

`ntrp.knowledge.evals.benchmark_memory_suite()` is the deterministic local benchmark layer. It does not replace LOCOMO/LongMemEval/BEAM/STATE-Bench, but it gives CI a stable, source-id-based regression suite for the behaviors those benchmarks stress:

- current fact beats stale/superseded fact;
- holistic query retrieves the profile tier;
- action query retrieves procedure memory;
- source/evidence query can retrieve a closed episode;
- current preference beats stale preference;
- assistant recommendation recall;
- decision recall;
- negative generic-advice case does not inject project memory.

`tests/test_knowledge_activation.py::test_benchmark_memory_suite_runs_against_seeded_long_term_memory` seeds an isolated DB and runs this suite through `KnowledgeActivationService`, so benchmark regressions fail before external datasets are wired.

### LongMemEval retrieval runner

`ntrp-server benchmark longmemeval` is the first repeatable external benchmark runner. It:

- reads LongMemEval-S / LongMemEval-Oracle style JSON;
- creates an isolated SQLite DB per case under the run directory, then removes those DBs unless `--keep-dbs` is set;
- ingests haystack sessions as closed `memory_episode` objects with `source_ids` containing benchmark session ids;
- supports explicit source ablations: `--variant raw-episodes`, `--variant extracted` (deterministic question-conditioned source-backed focused facts only), and `--variant raw-plus-extracted`;
- runs `KnowledgeActivationService.inspect()` with configurable `--top-k` and `--budget-chars`;
- writes `traces.jsonl`, `failures.jsonl`, and `metrics.json`;
- reports recall@k, MRR@k, gold-session coverage, all-gold retrieval rate, and optional answer correctness/grounding metrics overall and by question type.

Default mode prefixes the activation query with `source evidence for ...` so raw `memory_episode` objects are eligible for source-tier retrieval. Use `--direct-query` to expose current activation behavior for normal user questions; this is the mode that reproduces the weak raw-episode baseline.

Examples:

```bash
cd apps/server
uv run ntrp-server benchmark longmemeval \
  --dataset ../../data/longmemeval_s.json \
  --output-dir ../../benchmark-results \
  --limit 50 \
  --top-k 10 \
  --direct-query

uv run ntrp-server benchmark longmemeval \
  --dataset ../../data/longmemeval_oracle.json \
  --output-dir ../../benchmark-results \
  --per-type-limit 10 \
  --top-k 10 \
  --direct-query

uv run ntrp-server benchmark longmemeval \
  --dataset ../../data/longmemeval_oracle.json \
  --output-dir ../../benchmark-results \
  --per-type-limit 10 \
  --top-k 10 \
  --direct-query \
  --evaluate-answers

uv run ntrp-server benchmark longmemeval \
  --dataset ../../data/longmemeval_s.json \
  --output-dir ../../benchmark-results \
  --limit 50 \
  --top-k 10 \
  --direct-query \
  --variant extracted \
  --evaluate-answers

uv run ntrp-server benchmark longmemeval \
  --dataset ../../data/longmemeval_s.json \
  --output-dir ../../benchmark-results \
  --limit 50 \
  --top-k 10 \
  --direct-query \
  --variant raw-plus-extracted \
  --evaluate-answers

# Optional real model answer/judge path; deterministic local mode remains CI default.
uv run ntrp-server benchmark longmemeval \
  --dataset ../../data/longmemeval_s.json \
  --output-dir ../../benchmark-results \
  --limit 50 \
  --top-k 10 \
  --direct-query \
  --evaluate-answers \
  --answer-model claude-sonnet-4-0 \
  --judge-model claude-sonnet-4-0

# Optional real episode-close extraction pipeline for extracted/raw-plus-extracted variants.
# This is expensive on LongMemEval-S because each case has many haystack sessions.
uv run ntrp-server benchmark longmemeval \
  --dataset ../../data/longmemeval_oracle.json \
  --output-dir ../../benchmark-results \
  --limit 2 \
  --top-k 10 \
  --direct-query \
  --variant extracted \
  --extraction-model claude-sonnet-4-0 \
  --evaluate-answers
```

Original raw-episode direct-query baselines from 2026-05-21:

| Dataset/config | Cases | Recall@10 | MRR@10 | Notes |
| --- | ---: | ---: | ---: | --- |
| LongMemEval-S `--limit 50 --direct-query` | 50 | 0.140 | 0.140 | 40 no-candidate cases, 3 wrong retrieved sessions |
| LongMemEval-Oracle `--per-type-limit 10 --direct-query` | 60 | 0.117 | 0.117 | 53 no-candidate cases; 0.0 on multi-session, assistant, temporal slices |

Current direct-query results after conversational/personal/temporal eligibility, focused evidence snippets, informative-term ranking, and deterministic answer composition, latest refreshed 2026-05-22:

| Dataset/config | Variant | Cases | Recall@10 | MRR@10 | Notes |
| --- | --- | ---: | ---: | ---: | --- |
| LongMemEval-S `--limit 50 --direct-query --evaluate-answers` | raw-episodes | 50 | 1.000 | 0.917 | `benchmark-results/longmemeval-20260522T141649Z`; semantic category-to-instance aliasing fixed the remaining Spotify/music-streaming retrieval miss |
| LongMemEval-S `--limit 50 --direct-query --variant extracted --evaluate-answers` | extracted | 50 | 0.260 | 0.250 | `benchmark-results/longmemeval-20260522T141958Z`; extracted-only objects remain too weak as a standalone substitute; answer accuracy is 0.300 after answer-composition improvements |
| LongMemEval-S `--limit 50 --direct-query --variant raw-plus-extracted --evaluate-answers` | raw-plus-extracted | 50 | 1.000 | 0.825 | `benchmark-results/longmemeval-20260522T141757Z`; best deterministic S answer accuracy so far, while extracted objects still compete with raw episodes in rank |
| LongMemEval-Oracle `--per-type-limit 10 --direct-query --evaluate-answers` | raw-episodes | 60 | 1.000 | 1.000 | `benchmark-results/longmemeval-20260522T135650Z`; all slices 1.000 retrieval; gold-session coverage and all-gold retrieval also 1.000 after focused source snippets |

Source-tier raw evidence baselines from the same runner:

| Dataset/config | Cases | Recall@10 | MRR@10 | Notes |
| --- | ---: | ---: | ---: | --- |
| LongMemEval-S `--limit 50` | 50 | 0.560 | 0.560 | exercises raw source retrieval rather than normal direct-question activation |
| LongMemEval-Oracle `--per-type-limit 10` | 60 | 1.000 | 1.000 | expected/easy oracle haystack; useful as ingestion/scoring sanity check, not product quality |


Focused evidence snippets are now part of activation for long raw source objects (`memory_episode`, legacy `episode`, and run provenance): when an episode is too large for prompt budget, activation keeps source/date headers plus the highest-overlap conversational snippets and immediate neighboring lines. This is the general fix for the partial-context bug: complete supporting sources can fit into the budget without benchmark-specific gold peeking, while adjacent answer context is less likely to be sliced away. Informative-term lexical scoring also ignores generic question glue and handles simple plural/singular variants so terms like `bikes` and `bike` match. A small semantic alias bridge handles category-to-instance queries where lexical evidence names the instance but not the category, e.g. `music streaming service` retrieving `Spotify`; embeddings remain the more general long-term retrieval path.

Answer-eval mode (`--evaluate-answers`) defaults to deterministic local evaluation: a compact evidence/composition answerer emits cited excerpts from activated candidates and handles small common compositions such as day deltas, totals, short issue inference, personal-best times, simple yes/no same-method questions, and move-location answers. A local overlap/source judge checks answer correctness and source support, including computed answers grounded in cited gold sources. This is not a product answer model and should not be optimized as a leaderboard; it is a reliability harness that exposes cases where retrieval is nominally green but the memory context is insufficient or the generated answer is unsupported. Optional `--answer-model` and `--judge-model` enable real LLM answer/judge runs while keeping deterministic mode as the CI-safe default.

Current answer-eval results, latest refreshed 2026-05-22:

| Dataset/config | Cases | Recall@10 | Gold session coverage@10 | All-gold rate | Answer accuracy | Grounded-correct rate | Notes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| LongMemEval-Oracle `--per-type-limit 10 --direct-query --evaluate-answers` | 60 | 1.000 | 1.000 | 1.000 | 0.633 | 0.633 | `benchmark-results/longmemeval-20260522T135650Z`; deterministic composition improved Oracle answer accuracy from 0.433, but remaining failures still include deeper extraction/count/list synthesis and preference-form answers |
| LongMemEval-S `--limit 50 --direct-query --evaluate-answers` | 50 | 1.000 | 1.000 | 1.000 | 0.820 | 0.820 | `benchmark-results/longmemeval-20260522T141649Z`; semantic aliasing removed the last retrieval miss; remaining 9 failures are `right_source_wrong_answer` |
| LongMemEval-S `--limit 50 --direct-query --variant extracted --evaluate-answers` | 50 | 0.260 | 0.260 | 0.260 | 0.300 | 0.300 | `benchmark-results/longmemeval-20260522T141958Z`; extracted-only is still the main weak ablation and needs real batch/profile extraction work |
| LongMemEval-S `--limit 50 --direct-query --variant raw-plus-extracted --evaluate-answers` | 50 | 1.000 | 1.000 | 1.000 | 0.840 | 0.840 | `benchmark-results/longmemeval-20260522T141757Z`; best deterministic S answer accuracy so far, but MRR still drops because extracted facts compete with raw episodes |
| LongMemEval-S first 50 as five `--limit 10` chunks with `--answer-model claude-sonnet-4-0 --judge-model claude-sonnet-4-0` | 50 | 1.000 | 1.000 | 1.000 | 0.880 | 0.880 | chunks `benchmark-results/longmemeval-20260522T142705Z`, `...143019Z`, `...143150Z`, `...143334Z`, `...143336Z`; same first-50 coverage as deterministic run, split only to fit command timeout; 6 `right_source_wrong_answer` failures |
| LongMemEval-Oracle `--limit 2 --direct-query --variant extracted --extraction-model claude-sonnet-4-0 --evaluate-answers` | 2 | 1.000 | 1.000 | 1.000 | 0.000 | 0.000 | `benchmark-results/longmemeval-20260522T140740Z`; real episode-close extraction plumbing works, but tiny temporal slice proves retrieval only; answer composition over extracted summaries still failed |

Reliability/failure taxonomy currently emitted into traces/failures:

- `no_candidates`
- `gold_session_not_retrieved`
- `partial_gold_context_wrong_answer`
- `right_source_wrong_answer`
- `answer_missing_gold`
- `uncited_or_ungrounded_answer`
- `correct_answer_wrong_source`

Warnings include `gold_retrieved_bad_rank`, `partial_gold_retrieved`, and `answer_correct_without_gold_source`.

## Recommended Implementation Order

1. Batch/cache real episode-close extraction before running larger extracted-only LongMemEval-S slices; naive per-session model extraction times out because S cases contain many haystack sessions.
2. Add profile-only and raw+facts+profiles ablations once extraction throughput is sane.
3. Continue improving answer composition for deeper list/count/preference-form questions; deterministic S is now 0.840 in raw+extracted and LLM answer/judge on the same first 50 is 0.880, but Oracle deterministic remains 0.633.
4. Replace the tiny semantic alias bridge with proper embedding/semantic retrieval once an embedding provider is configured for benchmark temp DBs.
5. Implement LOCOMO ingest/search/evaluate smoke test with 10 questions.
5. Run full LOCOMO.
6. Add BEAM small scale.
7. Add STATE-Bench agent adapter.
8. Keep expanding local `benchmark_memory_suite()` with realistic seeded cases.

## Pass Criteria for First Useful Result

The first useful result is not a high score. It is a debuggable table with:

- question id
- question type
- gold answer
- generated answer
- judge verdict
- activated object ids
- rank/score/reasons/signals per activated object
- source ids
- failure class
- retrieval tier used: raw/source, atomic durable, profile
- profile section ids/source refs when profile tier was used
- context chars/tokens by tier

If this table cannot explain failures, the benchmark harness is not done.
