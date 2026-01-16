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
        console.print("  NTRP_VAULT_PATH - path to your Obsidian vault")
        console.print("  OPENAI_API_KEY - your OpenAI API key")
        raise SystemExit(1)

    config = ctx.obj["config"]

    console.print("[bold]ntrp status[/bold]")
    console.print()
    console.print(f"Vault path: [cyan]{config.vault_path}[/cyan]")
    console.print(f"Database: [cyan]{config.db_path}[/cyan]")
    console.print(f"Embedding model: {config.embedding_model}")
    console.print(f"Chat model: {config.chat_model}")
    console.print(f"Database exists: {'[green]yes[/green]' if config.db_path.exists() else '[yellow]no[/yellow]'}")


@main.command()
@click.option("--host", default="127.0.0.1", help="Host to bind to")
@click.option("--port", "-p", default=8000, help="Port to bind to")
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


if __name__ == "__main__":
    main()
