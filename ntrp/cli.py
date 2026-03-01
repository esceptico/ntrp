import asyncio
import secrets
import socket

import click
import uvicorn
from rich.console import Console

from ntrp.config import get_config
from ntrp.core.agent import Agent
from ntrp.core.prompts import build_system_prompt
from ntrp.core.spawner import create_spawn_fn
from ntrp.events.internal import RunCompleted, RunStarted
from ntrp.logging import UVICORN_LOG_CONFIG
from ntrp.server.runtime import Runtime
from ntrp.tools.core.context import IOBridge, RunContext, ToolContext

console = Console()


@click.group()
def main():
    """ntrp - personal entropy reduction system"""


@main.command()
def status():
    """Show current status of ntrp."""
    config = get_config()
    console.print("[bold]ntrp status[/bold]")
    console.print()
    console.print(f"Database dir: [cyan]{config.db_dir}[/cyan]")
    console.print(f"Embedding model: {config.embedding_model}")
    console.print(f"Chat model: {config.chat_model}")


@main.command()
@click.option("--host", default=None, help="Host to bind to (or NTRP_HOST)")
@click.option("--port", default=None, type=int, help="Port to bind to (or NTRP_PORT)")
@click.option("--reload", is_flag=True, help="Enable auto-reload for development")
def serve(host: str | None, port: int | None, reload: bool):
    config = get_config()
    host = host or config.host
    port = port or config.port

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
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
    )


@main.command()
@click.option("-p", "--prompt", required=True, help="The prompt to execute")
def run(prompt: str):
    """Run agent once with a prompt (headless, non-interactive mode)."""
    asyncio.run(_run_headless(prompt))


async def _run_headless(prompt: str):
    runtime = Runtime()
    await runtime.connect()

    try:
        system_prompt = build_system_prompt(
            source_details=runtime.source_mgr.get_details(),
            last_activity=None,
            memory_context=None,
        )

        run_id = secrets.token_hex(4)
        session_state = runtime.session_service.create()

        tool_ctx = ToolContext(
            session_state=session_state,
            registry=runtime.executor.registry,
            run=RunContext(
                run_id=run_id,
                max_depth=runtime.config.max_depth,
                explore_model=runtime.config.explore_model,
            ),
            io=IOBridge(),
            services=runtime.tool_services,
            channel=runtime.channel,
        )

        tool_ctx.spawn_fn = create_spawn_fn(
            executor=runtime.executor,
            model=runtime.config.chat_model,
            max_depth=runtime.config.max_depth,
            current_depth=0,
        )

        agent = Agent(
            tools=runtime.executor.get_tools(),
            tool_executor=runtime.executor,
            model=runtime.config.chat_model,
            system_prompt=system_prompt,
            ctx=tool_ctx,
            max_depth=runtime.config.max_depth,
            current_depth=0,
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
                    session_id=session_state.session_id,
                    messages=tuple(agent.messages),
                    usage=agent.usage,
                    result=result,
                )
            )
    finally:
        await runtime.close()


if __name__ == "__main__":
    main()
