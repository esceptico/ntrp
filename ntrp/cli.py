import asyncio
import socket

import click
import uvicorn
from coolname import generate_slug
from rich.console import Console

from ntrp.agent import Role
from ntrp.config import get_config
from ntrp.core.factory import AgentConfig, create_agent
from ntrp.core.prompts import build_system_prompt
from ntrp.events.internal import RunCompleted
from ntrp.logging import UVICORN_LOG_CONFIG
from ntrp.memory.learning_context import get_approved_learning_context
from ntrp.server.runtime import Runtime
from ntrp.settings import generate_api_key, load_user_settings, save_user_settings
from ntrp.tools.core.context import IOBridge

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
        system_prompt = build_system_prompt(
            source_details={},
            memory_context=None,
            learning_context=await get_approved_learning_context(runtime.memory) if runtime.memory else None,
        )

        run_id = generate_slug(2)
        session_state = runtime.session_service.create()

        config = AgentConfig.from_config(runtime.config)

        agent = create_agent(
            executor=runtime.executor,
            config=config,
            tools=runtime.executor.get_tools(),
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
