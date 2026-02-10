import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from evals.judge import JudgeVerdict
from evals.metrics import RetrievalMetrics


@dataclass
class SampleResult:
    question_id: str
    question_type: str
    question: str
    expected_answer: str
    generated_answer: str
    verdict: JudgeVerdict
    metrics: RetrievalMetrics
    facts: list[str]
    observations: list[str]


def print_summary(results: list[SampleResult], config_info: dict) -> None:
    print(f"\n{'=' * 70}")
    print("LongMemEval Results")
    print(f"{'=' * 70}")
    print(f"Model: {config_info.get('model', '?')}")
    print(f"Questions: {len(results)}")
    print(
        f"Consolidation: {'on' if config_info.get('consolidate') else 'off'}"
    )
    print(f"Recall limit: {config_info.get('recall_limit', '?')}")

    by_type: dict[str, list[SampleResult]] = defaultdict(list)
    for r in results:
        by_type[r.question_type].append(r)

    header = (
        f"{'Type':<30} | {'N':>3} | {'Acc':>6} "
        f"| {'FP':>5} | {'Sel%':>5}"
    )
    sep = "-" * len(header)

    print(f"\n{header}")
    print(sep)

    type_accs = []
    all_total = 0
    all_correct = 0

    for qtype in sorted(by_type):
        items = by_type[qtype]
        n = len(items)
        correct = sum(1 for r in items if r.verdict.correct)
        acc = correct / n * 100 if n else 0
        avg_fp = sum(r.metrics.fact_precision for r in items) / n
        avg_sel = sum(r.metrics.selectivity * 100 for r in items) / n

        print(
            f"{qtype:<30} | {n:>3} | {acc:>5.1f}% "
            f"| {avg_fp:>.3f} | {avg_sel:>4.1f}%"
        )

        type_accs.append(acc)
        all_correct += correct
        all_total += n

    print(sep)
    overall_acc = all_correct / all_total * 100 if all_total else 0
    task_avg_acc = sum(type_accs) / len(type_accs) if type_accs else 0
    avg_fp = sum(r.metrics.fact_precision for r in results) / len(results)
    avg_sel = sum(r.metrics.selectivity * 100 for r in results) / len(results)

    print(
        f"{'OVERALL':<30} | {all_total:>3} | {overall_acc:>5.1f}% "
        f"| {avg_fp:>.3f} | {avg_sel:>4.1f}%"
    )
    print(f"{'TASK-AVERAGED':<30} |     | {task_avg_acc:>5.1f}% |")
    print()


def save_results(
    results: list[SampleResult], config_info: dict, output_dir: Path
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    path = output_dir / f"eval_{timestamp}.json"

    type_groups: dict[str, list[SampleResult]] = defaultdict(list)
    for r in results:
        type_groups[r.question_type].append(r)

    type_accs = {}
    for qtype, items in type_groups.items():
        type_accs[qtype] = (
            sum(1 for r in items if r.verdict.correct) / len(items)
            if items
            else 0
        )

    data = {
        "config": config_info,
        "summary": {
            "total": len(results),
            "correct": sum(1 for r in results if r.verdict.correct),
            "overall_accuracy": (
                sum(1 for r in results if r.verdict.correct) / len(results)
                if results
                else 0
            ),
            "task_averaged_accuracy": (
                sum(type_accs.values()) / len(type_accs) if type_accs else 0
            ),
            "avg_fact_precision": (
                sum(r.metrics.fact_precision for r in results) / len(results)
                if results
                else 0
            ),
            "avg_selectivity": (
                sum(r.metrics.selectivity for r in results) / len(results)
                if results
                else 0
            ),
            "per_type": type_accs,
        },
        "questions": [
            {
                "question_id": r.question_id,
                "question_type": r.question_type,
                "question": r.question,
                "expected_answer": r.expected_answer,
                "generated_answer": r.generated_answer,
                "correct": r.verdict.correct,
                "reasoning": r.verdict.reasoning,
                "retrieval": {
                    "fact_precision": r.metrics.fact_precision,
                    "facts_from_gold": r.metrics.facts_from_gold,
                    "facts_retrieved": r.metrics.facts_retrieved,
                    "total_facts": r.metrics.total_facts,
                    "selectivity": r.metrics.selectivity,
                    "recall_all": r.metrics.recall_all,
                    "session_recall": r.metrics.session_recall,
                },
                "facts_retrieved": r.facts,
                "observations_retrieved": r.observations,
            }
            for r in results
        ],
    }

    path.write_text(json.dumps(data, indent=2))
    print(f"Results saved to {path}")
    return path
