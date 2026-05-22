import asyncio
import json
import socket
from pathlib import Path

import click
import uvicorn
from coolname import generate_slug
from rich.console import Console

from ntrp.agent import Role
from ntrp.benchmarks.longmemeval import LongMemEvalRunnerConfig, run_longmemeval_sync
from ntrp.config import get_config
from ntrp.core.factory import AgentConfig, create_agent
from ntrp.core.prompts import build_system_prompt
from ntrp.events.internal import RunCompleted
from ntrp.logging import UVICORN_LOG_CONFIG
from ntrp.server.runtime import Runtime
from ntrp.settings import generate_api_key, load_user_settings, save_user_settings
from ntrp.tools.core.context import IOBridge
from ntrp.tools.deferred import build_deferred_tools_prompt_for_schemas

console = Console()


def _require_chat_model(config) -> None:
    if not config.chat_model:
        console.print("[red]Error:[/red] No chat model configured.")
        console.print()
        console.print("Set a provider API key:")
        console.print("  ANTHROPIC_API_KEY")
        console.print("  OPENAI_API_KEY")
        console.print("  GEMINI_API_KEY")
        console.print()
        console.print("Or specify a model directly: NTRP_CHAT_MODEL=<model>")
        raise SystemExit(1)


@click.group()
@click.version_option(package_name="ntrp")
def main():
    """ntrp - personal entropy reduction system"""


@main.command()
def status():
    """Show current status of ntrp."""
    config = get_config()
    console.print("[bold]ntrp status[/bold]")
    console.print()
    console.print(f"Database dir: [cyan]{config.db_dir}[/cyan]")
    console.print(f"Chat model: {config.chat_model or '[dim]not set[/dim]'}")
    console.print(f"Memory model: {config.memory_model or '[dim]not set[/dim]'}")
    console.print(f"Embedding model: {config.embedding_model or '[dim]not set[/dim]'}")


@main.command()
@click.option("--host", default=None, help="Host to bind to (or NTRP_HOST)")
@click.option("--port", default=None, type=int, help="Port to bind to (or NTRP_PORT)")
@click.option("--reload", is_flag=True, help="Enable auto-reload for development")
@click.option("--reset-key", is_flag=True, help="Generate a new API key")
def serve(host: str | None, port: int | None, reload: bool, reset_key: bool):
    """Start the ntrp API server."""
    config = get_config()

    if reset_key or not config.api_key_hash:
        settings = load_user_settings()
        plaintext, hashed = generate_api_key()
        settings["api_key_hash"] = hashed
        save_user_settings(settings)
        config.api_key_hash = hashed
        label = "New API key" if reset_key else "Your API key"
        console.print(f"[bold]{label}:[/bold] [cyan]{plaintext}[/cyan]")
        console.print("[dim]Enter this in the TUI to connect. It won't be shown again.[/dim]")
        console.print()

    host = host or config.host
    port = port or config.port

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, port))
        except OSError:
            console.print(f"[red]Error:[/red] Port {port} is already in use")
            console.print("[dim]Kill the existing process or use --port to pick another[/dim]")
            raise SystemExit(1)

    console.print(f"[bold]ntrp server[/bold] starting on http://{host}:{port}")
    console.print("[dim]Press Ctrl+C to stop[/dim]")
    console.print()

    uvicorn.run(
        "ntrp.server.app:app",
        host=host,
        port=port,
        reload=reload,
        log_config=UVICORN_LOG_CONFIG,
        timeout_graceful_shutdown=3,
    )




@main.group()
def benchmark():
    """Run repeatable memory benchmarks."""


@benchmark.command("longmemeval")
@click.option("--dataset", "dataset_path", type=click.Path(exists=True, dir_okay=False, path_type=Path), required=True)
@click.option("--output-dir", type=click.Path(file_okay=False, path_type=Path), default=Path("benchmark-results"), show_default=True)
@click.option("--limit", type=int, default=None, help="Maximum number of cases to run.")
@click.option("--per-type-limit", type=int, default=None, help="Maximum cases per question type, useful for stratified smokes.")
@click.option("--top-k", type=click.IntRange(1, 50), default=10, show_default=True)
@click.option("--budget-chars", type=click.IntRange(200, 20_000), default=20_000, show_default=True)
@click.option("--keep-dbs", is_flag=True, help="Keep per-case isolated SQLite DBs for debugging.")
@click.option("--direct-query", is_flag=True, help="Use the benchmark question directly instead of prefixing it for raw evidence retrieval.")
@click.option("--variant", type=click.Choice(["raw-episodes", "extracted", "raw-plus-extracted"]), default="raw-episodes", show_default=True)
@click.option("--evaluate-answers", is_flag=True, help="Generate cited answers and judge correctness/grounding.")
@click.option("--answer-model", type=str, default=None, help="Optional LLM model for answer generation. Deterministic local answerer is used by default.")
@click.option("--judge-model", type=str, default=None, help="Optional LLM model for answer judging. Deterministic local judge is used by default.")
@click.option("--extraction-model", type=str, default=None, help="Optional model for real episode-close extraction in extracted/raw-plus-extracted variants.")
def benchmark_longmemeval(
    dataset_path: Path,
    output_dir: Path,
    limit: int | None,
    per_type_limit: int | None,
    top_k: int,
    budget_chars: int,
    keep_dbs: bool,
    direct_query: bool,
    variant: str,
    evaluate_answers: bool,
    answer_model: str | None,
    judge_model: str | None,
    extraction_model: str | None,
):
    """Run LongMemEval retrieval benchmark with JSONL traces."""
    result = run_longmemeval_sync(
        LongMemEvalRunnerConfig(
            dataset_path=dataset_path,
            output_dir=output_dir,
            limit=limit,
            per_type_limit=per_type_limit,
            top_k=top_k,
            budget_chars=budget_chars,
            keep_dbs=keep_dbs,
            raw_evidence_query=not direct_query,
            variant=variant,
            evaluate_answers=evaluate_answers,
            answer_model=answer_model,
            judge_model=judge_model,
            extraction_model=extraction_model,
        )
    )
    metrics = result["metrics"]
    console.print("[bold]LongMemEval retrieval benchmark[/bold]")
    console.print(f"cases: {metrics['cases']}  recall@{metrics['top_k']}: {metrics['recall_at_k']:.3f}  mrr@{metrics['top_k']}: {metrics['mrr_at_k']:.3f}")
    for question_type, row in metrics["by_question_type"].items():
        line = (
            f"  {question_type}: n={row['cases']} recall@{metrics['top_k']}={row['recall_at_k']:.3f} "
            f"mrr@{metrics['top_k']}={row['mrr_at_k']:.3f} "
            f"gold_cov={row.get('gold_session_coverage_at_k', 0.0):.3f} "
            f"all_gold={row.get('all_gold_retrieved_rate', 0.0):.3f}"
        )
        if "answer_accuracy" in row:
            line += f" answer_acc={row['answer_accuracy']:.3f} grounded_correct={row['grounded_correct_rate']:.3f}"
        console.print(line)
    if "gold_session_coverage_at_k" in metrics:
        console.print(
            f"gold coverage: avg={metrics['gold_session_coverage_at_k']:.3f} "
            f"all_gold={metrics['all_gold_retrieved_rate']:.3f}"
        )
    if metrics.get("answer_eval"):
        answer_eval = metrics["answer_eval"]
        console.print(
            f"answers: acc={answer_eval['answer_accuracy']:.3f} "
            f"grounding={answer_eval['source_grounding_rate']:.3f} "
            f"grounded_correct={answer_eval['grounded_correct_rate']:.3f}"
        )
    console.print(f"metrics: [cyan]{result['paths']['metrics_json']}[/cyan]")
    console.print(f"traces:  [cyan]{result['paths']['traces_jsonl']}[/cyan]")
    console.print(f"failures:[cyan]{result['paths']['failures_jsonl']}[/cyan]")
    if keep_dbs and result["paths"].get("db_dir"):
        console.print(f"dbs:     [cyan]{result['paths']['db_dir']}[/cyan]")
    console.print_json(json.dumps(metrics))


@main.command()
@click.option("-p", "--prompt", required=True, help="The prompt to execute")
def run(prompt: str):
    """Run agent once with a prompt (headless, non-interactive mode)."""
    config = get_config()
    _require_chat_model(config)
    asyncio.run(_run_headless(prompt))


async def _run_headless(prompt: str):
    runtime = Runtime()
    await runtime.connect()

    try:
        config = AgentConfig.from_config(runtime.config)
        tools = runtime.executor.get_tools()
        deferred_tools_context = (
            build_deferred_tools_prompt_for_schemas(
                runtime.executor.registry, frozenset(runtime.executor.tool_services), tools
            )
            if config.deferred_tools
            else None
        )
        system_prompt = build_system_prompt(
            source_details={},
            memory_context=None,
            deferred_tools_context=deferred_tools_context,
        )

        run_id = generate_slug(2)
        session_state = runtime.session_service.create()

        agent = create_agent(
            executor=runtime.executor,
            config=config,
            tools=tools,
            session_state=session_state,
            run_id=run_id,
            io=IOBridge(),
        )

        messages = [
            {"role": Role.SYSTEM, "content": system_prompt},
            {"role": Role.USER, "content": prompt},
        ]

        console.print(f"[dim]Running: {prompt}[/dim]\n")
        run_result = await agent.run(messages)
        console.print(run_result.text)
        await runtime.stores.outbox.enqueue_run_completed(
            RunCompleted(
                run_id=run_id,
                session_id=session_state.session_id,
                messages=tuple(messages),
                usage=run_result.usage,
                result=run_result.text,
            )
        )
    finally:
        await runtime.close()


if __name__ == "__main__":
    main()
