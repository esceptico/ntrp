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
3. Let ntrp create run provenance, memory episodes, durable facts/patterns/procedures, and entity refs.
4. For each question, run activation at top-k cutoffs: `10,20,50,200`.
5. Generate answer from activated context using a fixed answer model.
6. Judge against gold answer with fixed judge model.
7. Break down by question type and by retrieval failure class.

Expected failure classes to tag:

- missed gold fact
- retrieved wrong domain
- retrieved stale/superseded fact
- too broad pattern crowded out concrete fact
- context budget truncation
- answer model failed despite correct context

Source: Snap Research LOCOMO project page + `snap-research/locomo`.

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

Ablations to prioritize:

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

## Recommended Implementation Order

1. Add local `ntrp-bench` runner with isolated DB + JSONL outputs.
2. Implement LOCOMO ingest/search/evaluate smoke test with 10 questions.
3. Run full LOCOMO.
4. Add LongMemEval adapter.
5. Add ablation config matrix.
6. Add BEAM small scale.
7. Add STATE-Bench agent adapter.

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

If this table cannot explain failures, the benchmark harness is not done.
