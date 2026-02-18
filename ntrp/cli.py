import asyncio

import click
from rich.console import Console

from ntrp.config import Config
from ntrp.logging import UVICORN_LOG_CONFIG

console = Console()


@click.group(invoke_without_command=True)
@click.pass_context
def main(ctx):
    """ntrp - personal entropy reduction system"""
    try:
        ctx.ensure_object(dict)
        ctx.obj["config"] = Config()
    except ValueError as e:
        # Only fail if we're running a command that needs config
        ctx.obj["config_error"] = str(e)

    # If no subcommand, show help
    if ctx.invoked_subcommand is None:
        console.print("[bold]ntrp[/bold] - personal entropy reduction system\n")
        console.print("Run [cyan]ntrp serve[/cyan] to start the server.")
        console.print("\nUse [cyan]ntrp --help[/cyan] for all commands.")


@main.command()
@click.pass_context
def status(ctx):
    """Show current status of ntrp."""
    if "config_error" in ctx.obj:
        console.print(f"[red]Error:[/red] {ctx.obj['config_error']}")
        console.print()
        console.print("[bold]Required environment variables:[/bold]")
        console.print("  OPENAI_API_KEY - your OpenAI API key")
        console.print()
        console.print("[bold]Optional environment variables:[/bold]")
        console.print("  ANTHROPIC_API_KEY, GEMINI_API_KEY - LLM provider keys")
        console.print("  EXA_API_KEY - for web search")
        raise SystemExit(1)

    config = ctx.obj["config"]

    console.print("[bold]ntrp status[/bold]")
    console.print()
    console.print(f"Database dir: [cyan]{config.db_dir}[/cyan]")
    console.print(f"Embedding model: {config.embedding_model}")
    console.print(f"Chat model: {config.chat_model}")


@main.command()
@click.option("--host", default="127.0.0.1", help="Host to bind to")
@click.option("--port", default=8000, help="Port to bind to")
@click.option("--reload", is_flag=True, help="Enable auto-reload for development")
@click.pass_context
def serve(ctx, host: str, port: int, reload: bool):
    """Start the ntrp API server."""
    if "config_error" in ctx.obj:
        console.print(f"[red]Error:[/red] {ctx.obj['config_error']}")
        raise SystemExit(1)

    import uvicorn

    console.print(f"[bold]ntrp server[/bold] starting on http://{host}:{port}")
    console.print("[dim]Press Ctrl+C to stop[/dim]")
    console.print()

    uvicorn.run(
        "ntrp.server.app:app",
        host=host,
        port=port,
        reload=reload,
        log_config=UVICORN_LOG_CONFIG,
    )


@main.command()
@click.option("-p", "--prompt", required=True, help="The prompt to execute")
@click.pass_context
def run(ctx, prompt: str):
    """Run agent once with a prompt (headless, non-interactive mode)."""
    if "config_error" in ctx.obj:
        console.print(f"[red]Error:[/red] {ctx.obj['config_error']}")
        raise SystemExit(1)

    asyncio.run(_run_headless(prompt))


async def _run_headless(prompt: str):
    from uuid import uuid4

    from ntrp.core.agent import Agent
    from ntrp.core.prompts import build_system_prompt
    from ntrp.core.spawner import create_spawn_fn
    from ntrp.events import RunCompleted, RunStarted
    from ntrp.server.runtime import Runtime
    from ntrp.tools.core.context import IOBridge, RunContext, ToolContext

    runtime = Runtime()
    await runtime.connect()

    try:
        system_prompt = build_system_prompt(
            source_details=runtime.get_source_details(),
            last_activity=None,
            memory_context=None,
        )

        run_id = str(uuid4())[:8]
        session_state = runtime.create_session()

        tool_ctx = ToolContext(
            session_state=session_state,
            registry=runtime.executor.registry,
            run=RunContext(
                run_id=run_id,
                max_depth=runtime.max_depth,
                explore_model=runtime.config.explore_model,
            ),
            io=IOBridge(),
            memory=runtime.memory,
            channel=runtime.channel,
        )

        tool_ctx.spawn_fn = create_spawn_fn(
            executor=runtime.executor,
            model=runtime.config.chat_model,
            max_depth=runtime.max_depth,
            current_depth=0,
            cancel_check=None,
        )

        agent = Agent(
            tools=runtime.tools,
            tool_executor=runtime.executor,
            model=runtime.config.chat_model,
            system_prompt=system_prompt,
            ctx=tool_ctx,
            max_depth=runtime.max_depth,
            current_depth=0,
            cancel_check=None,
        )

        console.print(f"[dim]Running: {prompt}[/dim]\n")
        runtime.channel.publish(RunStarted(run_id=run_id, session_id=session_state.session_id))
        result: str | None = None
        try:
            result = await agent.run(task=prompt, history=None)
            console.print(result)
        finally:
            runtime.channel.publish(
                RunCompleted(
                    run_id=run_id,
                    prompt_tokens=agent.total_input_tokens,
                    completion_tokens=agent.total_output_tokens,
                    cache_read_tokens=agent.total_cache_read_tokens,
                    cache_write_tokens=agent.total_cache_write_tokens,
                    result=result,
                )
            )
    finally:
        await runtime.close()


if __name__ == "__main__":
    main()
