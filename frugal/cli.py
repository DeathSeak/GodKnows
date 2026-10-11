"""Command-line interface for Frugal."""

from __future__ import annotations

import sys
from pathlib import Path
import click

from frugal import config, metrics, server, state, storage


@click.group()
@click.version_option(version="2.0.0", prog_name="frugal")
def main() -> None:
    """Frugal — A Token Firewall for AI Coding Agents."""
    pass


@main.command()
def init() -> None:
    """Initialize the .frugal directory, config.toml, and SQLite database."""
    try:
        storage.ensure_directories()
        config.load_or_create_config()
        state.initialize_db()
        base_dir = storage.get_base_dir()
        click.echo("[FRUGAL INIT] Initialization complete:")
        click.echo(f"  - Storage directory: {base_dir}")
        click.echo(f"  - Logs directory:    {base_dir / 'logs'}")
        click.echo(f"  - Visuals directory: {base_dir / 'visual'}")
        click.echo(f"  - Config file:       {config.get_default_config_path()}")
        click.echo(f"  - State database:    {state.get_default_db_path()}")
    except Exception as e:
        click.echo(f"[FRUGAL ERROR] Initialization failed: {e}", err=True)
        sys.exit(1)



@main.command()
@click.option("--format", "output_format", type=click.Choice(["md", "json"]), default="md", help="Output format")
def bench(output_format: str) -> None:
    """Run the empirical benchmark suite and display token reduction results."""
    try:
        workspace_dir = Path.cwd()
        if str(workspace_dir) not in sys.path:
            sys.path.insert(0, str(workspace_dir))
        from benchmark.run_benchmark import run_benchmarks
        click.echo("[FRUGAL BENCH] Executing benchmark suite across all scenarios...")
        report = run_benchmarks(output_format=output_format)
        click.echo(report)
    except Exception as e:
        click.echo(f"[FRUGAL ERROR] Benchmark execution failed: {e}", err=True)
        sys.exit(1)



@main.command()
def serve() -> None:
    """Start the Frugal FastMCP server."""
    click.echo("[FRUGAL] Starting FastMCP server...", err=True)
    server.mcp.run()


@main.command()
@click.option("--session-id", default=None, help="Filter stats by specific session ID")
def stats(session_id: str | None) -> None:
    """Display token accounting statistics."""
    report = server.frugal_stats(session_id=session_id)
    click.echo(report)


if __name__ == "__main__":
    main()
