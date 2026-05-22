from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from ntrp.knowledge.models import ActivationBundle, ActivationRequest


class ActivationInspector(Protocol):
    async def inspect(self, request: ActivationRequest) -> ActivationBundle: ...


@dataclass(frozen=True)
class MemoryEvalCase:
    name: str
    query: str
    expected_object_ids: set[str] = field(default_factory=set)
    forbidden_object_ids: set[str] = field(default_factory=set)
    scope: str | None = None
    min_expected_hits: int | None = None
    tags: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class MemoryEvalCaseResult:
    name: str
    passed: bool
    retrieved_object_ids: list[str]
    missing_expected_ids: set[str]
    forbidden_hits: set[str]
    expected_hits: set[str]
    precision: float
    recall: float
    tags: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class MemoryEvalResult:
    passed: bool
    cases: list[MemoryEvalCaseResult]

    @property
    def failed(self) -> list[MemoryEvalCaseResult]:
        return [case for case in self.cases if not case.passed]


@dataclass(frozen=True)
class MemoryEvalSuite:
    name: str
    cases: list[MemoryEvalCase]
    description: str = ""


@dataclass(frozen=True)
class MemoryEvalBenchmarkResult:
    suite_name: str
    passed: bool
    case_count: int
    pass_count: int
    precision: float
    recall: float
    cases: list[MemoryEvalCaseResult]

    @property
    def failed(self) -> list[MemoryEvalCaseResult]:
        return [case for case in self.cases if not case.passed]


def _case_metrics(expected: set[str], retrieved: set[str]) -> tuple[set[str], float, float]:
    if not expected:
        return set(), 1.0, 1.0
    hits = expected & retrieved
    precision = len(hits) / len(retrieved) if retrieved else 0.0
    recall = len(hits) / len(expected)
    return hits, precision, recall


async def run_memory_eval_cases(
    inspector: ActivationInspector,
    cases: list[MemoryEvalCase],
    *,
    budget_chars: int = 2_000,
    limit: int = 10,
) -> MemoryEvalResult:
    """Run deterministic memory-retrieval eval cases against activation.

    This intentionally avoids LLM judging. It catches stale/poisoned regressions by
    checking exact retrieved object IDs: expected IDs must appear, forbidden IDs
    must not appear.
    """
    results: list[MemoryEvalCaseResult] = []
    for case in cases:
        bundle = await inspector.inspect(
            ActivationRequest(
                query=case.query,
                scope=case.scope,
                budget_chars=budget_chars,
                limit=limit,
                include_actions=False,
                record_access=False,
            )
        )
        retrieved = [candidate.object_id for candidate in bundle.candidates]
        retrieved_set = set(retrieved)
        hits, precision, recall = _case_metrics(case.expected_object_ids, retrieved_set)
        missing = case.expected_object_ids - retrieved_set
        forbidden = case.forbidden_object_ids & retrieved_set
        min_ok = True if case.min_expected_hits is None else len(hits) >= case.min_expected_hits
        passed = not missing and not forbidden and min_ok
        results.append(
            MemoryEvalCaseResult(
                name=case.name,
                passed=passed,
                retrieved_object_ids=retrieved,
                missing_expected_ids=missing,
                forbidden_hits=forbidden,
                expected_hits=hits,
                precision=precision,
                recall=recall,
                tags=case.tags,
            )
        )
    return MemoryEvalResult(passed=all(case.passed for case in results), cases=results)


async def run_memory_eval_suite(
    inspector: ActivationInspector,
    suite: MemoryEvalSuite,
    *,
    budget_chars: int = 2_000,
    limit: int = 10,
) -> MemoryEvalBenchmarkResult:
    result = await run_memory_eval_cases(inspector, suite.cases, budget_chars=budget_chars, limit=limit)
    precision = sum(case.precision for case in result.cases) / len(result.cases) if result.cases else 1.0
    recall = sum(case.recall for case in result.cases) / len(result.cases) if result.cases else 1.0
    pass_count = sum(1 for case in result.cases if case.passed)
    return MemoryEvalBenchmarkResult(
        suite_name=suite.name,
        passed=result.passed,
        case_count=len(result.cases),
        pass_count=pass_count,
        precision=precision,
        recall=recall,
        cases=result.cases,
    )


def benchmark_memory_suite(object_ids: dict[str, str]) -> MemoryEvalSuite:
    """Top-tier-inspired deterministic memory benchmark suite.

    The suite mirrors the failure modes covered by LOCOMO/LongMemEval/BEAM/
    STATE-Bench-style evaluations without requiring external datasets: temporal
    updates, profile-vs-fact routing, procedural recall, source/evidence lookup,
    contradiction suppression, and stale-memory guards.
    """

    def oid(name: str) -> str:
        if name not in object_ids:
            raise KeyError(f"missing benchmark object id: {name}")
        return object_ids[name]

    return MemoryEvalSuite(
        name="ntrp-memory-benchmark-v1",
        description=(
            "Deterministic benchmark for long-term-memory retrieval: LoCoMo-style profile continuity, "
            "LongMemEval-style temporal updates/abstention guards, and STATE-Bench-style procedure recall."
        ),
        cases=[
            MemoryEvalCase(
                name="current-fact-beats-stale-fact",
                query="canary smoke checks deploy channel policy",
                expected_object_ids={oid("current_policy")},
                forbidden_object_ids={oid("stale_policy")},
                tags={"longmemeval", "temporal_update", "stale_guard"},
            ),
            MemoryEvalCase(
                name="profile-used-for-holistic-state-query",
                query="what do we know about Dex",
                expected_object_ids={oid("dex_profile")},
                tags={"locomo", "profile", "holistic"},
            ),
            MemoryEvalCase(
                name="procedure-retrieved-for-action-query",
                query="how should Prime pod cleanup be done",
                expected_object_ids={oid("prime_procedure")},
                tags={"state_bench", "procedure", "action"},
            ),
            MemoryEvalCase(
                name="source-evidence-query-can-retrieve-episode",
                query="source evidence for Dex profile continuity",
                expected_object_ids={oid("dex_episode")},
                tags={"source_grounding", "evidence", "beam"},
            ),
            MemoryEvalCase(
                name="current-preference-beats-stale-preference",
                query="what editor do I currently prefer",
                expected_object_ids={oid("current_preference")},
                forbidden_object_ids={oid("stale_preference")},
                tags={"preference", "temporal_update", "stale_guard"},
            ),
            MemoryEvalCase(
                name="assistant-recommendation-recall",
                query="what did you recommend for Trigger deploy checks",
                expected_object_ids={oid("assistant_recommendation")},
                tags={"assistant_recommendation", "conversational_recall"},
            ),
            MemoryEvalCase(
                name="decision-recall",
                query="what did we decide about Dex Slack sync",
                expected_object_ids={oid("dex_slack_decision")},
                tags={"decision", "conversational_recall", "multi_session"},
            ),
            MemoryEvalCase(
                name="generic-advice-does-not-inject-project-memory",
                query="how do I cook pasta",
                forbidden_object_ids={
                    oid("current_policy"),
                    oid("dex_profile"),
                    oid("prime_procedure"),
                    oid("assistant_recommendation"),
                    oid("dex_slack_decision"),
                },
                tags={"negative", "memory_abstention"},
            ),
        ],
    )



def default_memory_retrieval_suite() -> MemoryEvalSuite:
    """Reusable smoke benchmark for retrieval regressions.

    Object IDs are placeholders by design: callers can copy this suite and replace
    IDs with fixture/runtime IDs. The tags define the behavior each case is meant
    to protect.
    """
    return MemoryEvalSuite(
        name="default-memory-retrieval-regressions",
        description="FTS/vector/entity/time/stale/contradiction retrieval smoke cases.",
        cases=[
            MemoryEvalCase(
                name="lexical-current-fact",
                query="current project preference",
                expected_object_ids={"CURRENT_FACT_ID"},
                forbidden_object_ids={"STALE_FACT_ID"},
                tags={"fts", "stale_guard"},
            ),
            MemoryEvalCase(
                name="entity-specific-procedure",
                query="Prime Intellect pod procedure",
                expected_object_ids={"ENTITY_PROCEDURE_ID"},
                tags={"entity"},
            ),
            MemoryEvalCase(
                name="recent-memory",
                query="latest memory policy",
                expected_object_ids={"RECENT_FACT_ID"},
                tags={"temporal"},
            ),
            MemoryEvalCase(
                name="semantic-contradiction-suppression",
                query="deploy release channel",
                expected_object_ids={"CURRENT_POLICY_ID"},
                forbidden_object_ids={"CONTRADICTED_POLICY_ID"},
                tags={"contradiction", "stale_guard"},
            ),
        ],
    )
