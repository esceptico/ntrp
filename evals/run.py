import argparse
import asyncio
import sys
import time
from pathlib import Path

from ntrp.config import get_config
from ntrp.logging import get_logger

from evals.data import load_questions, sample_questions
from evals.judge import judge
from evals.metrics import compute_retrieval_metrics
from evals.pipeline import EvalConfig, run_question
from evals.report import SampleResult, print_summary, save_results

_logger = get_logger(__name__)


async def _run_one(
    question,
    config: EvalConfig,
    sem: asyncio.Semaphore,
    idx: int,
    total: int,
) -> SampleResult | None:
    async with sem:
        label = f"[{idx + 1}/{total}] {question.question_type}"
        print(f"{label}: {question.question[:60]}...", flush=True)

        try:
            result = await run_question(question, config)

            verdict = await judge(
                question.question,
                question.answer,
                result.generated_answer,
                config.judge_model,
            )

            metrics = compute_retrieval_metrics(
                result.fact_session_ids,
                question.answer_session_ids,
                result.total_facts,
                len(result.facts),
            )

            status = "PASS" if verdict.correct else "FAIL"
            print(
                f"  {status} | facts={len(result.facts)}/{result.total_facts} "
                f"[sel={metrics.selectivity:.0%}] | "
                f"FP={metrics.fact_precision:.2f} ({metrics.facts_from_gold}/{len(result.facts)} from gold)",
                flush=True,
            )

            return SampleResult(
                question_id=question.question_id,
                question_type=question.question_type,
                question=question.question,
                expected_answer=question.answer,
                generated_answer=result.generated_answer,
                verdict=verdict,
                metrics=metrics,
                facts=result.facts,
                observations=result.observations,
            )
        except Exception:
            _logger.exception("Question %s failed", question.question_id)
            print(f"  ERROR: {question.question_id}", flush=True)
            return None


async def main() -> None:
    parser = argparse.ArgumentParser(description="LongMemEval benchmark")
    parser.add_argument(
        "--data",
        type=str,
        default="data/longmemeval_oracle.json",
        help="Path to LongMemEval JSON",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=10,
        help="Questions per type (default: 10)",
    )
    parser.add_argument(
        "--full", action="store_true", help="Run all questions"
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Model for extraction + generation + judge",
    )
    parser.add_argument(
        "--judge-model", type=str, default=None, help="Judge model override"
    )
    parser.add_argument(
        "--consolidate",
        action="store_true",
        help="Run consolidation (default: off)",
    )
    parser.add_argument(
        "--recall-limit",
        type=int,
        default=5,
        help="Recall limit (default: 5)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=5,
        help="Concurrent questions (default: 5)",
    )
    parser.add_argument(
        "--seed", type=int, default=42, help="Random seed for sampling"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="evals/results",
        help="Output directory",
    )
    parser.add_argument(
        "--embedding-model",
        type=str,
        default=None,
        help="Override embedding model (e.g. gemini/gemini-embedding-001)",
    )
    args = parser.parse_args()

    # Bump LLM retry for eval workload
    import ntrp.llm as llm_module

    llm_module.MAX_RETRIES = 5
    llm_module.MAX_DELAY = 30.0

    config = get_config()
    data_path = Path(args.data)
    if not data_path.exists():
        print(f"Data not found: {data_path}", file=sys.stderr)
        sys.exit(1)

    extraction_model = args.model or config.memory_model
    judge_model = args.judge_model or args.model or config.memory_model

    if args.embedding_model:
        from ntrp.embedder import EmbeddingConfig
        # Auto-detect dim for known models
        embedding = EmbeddingConfig(model=args.embedding_model, dim=3072)
    else:
        embedding = config.embedding

    eval_config = EvalConfig(
        embedding=embedding,
        extraction_model=extraction_model,
        judge_model=judge_model,
        consolidate=args.consolidate,
        recall_limit=args.recall_limit,
    )

    questions = load_questions(data_path)
    if not args.full:
        questions = sample_questions(
            questions, n_per_type=args.sample, seed=args.seed
        )

    print(f"LongMemEval eval: {len(questions)} questions")
    print(f"Model: {extraction_model} | Judge: {judge_model}")
    print(
        f"Consolidation: {'on' if args.consolidate else 'off'} "
        f"| Recall limit: {args.recall_limit}"
    )
    print(f"Concurrency: {args.concurrency}")
    print()

    sem = asyncio.Semaphore(args.concurrency)
    t0 = time.monotonic()

    tasks = [
        _run_one(q, eval_config, sem, i, len(questions))
        for i, q in enumerate(questions)
    ]
    raw_results = await asyncio.gather(*tasks)
    results = [r for r in raw_results if r is not None]

    elapsed = time.monotonic() - t0
    print(f"\nCompleted {len(results)}/{len(questions)} in {elapsed:.1f}s")

    if results:
        config_info = {
            "model": extraction_model,
            "judge_model": judge_model,
            "consolidate": args.consolidate,
            "recall_limit": args.recall_limit,
            "concurrency": args.concurrency,
            "data": str(data_path),
            "sample_per_type": args.sample if not args.full else "full",
            "seed": args.seed,
        }
        print_summary(results, config_info)
        save_results(results, config_info, Path(args.output))


if __name__ == "__main__":
    asyncio.run(main())
