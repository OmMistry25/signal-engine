"""signal-engine CLI."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import typer

app = typer.Typer(help="Real-time intent signal capture and scoring.")


@app.command()
def version() -> None:
    """Print the package version."""
    typer.echo("signal-engine 0.1.0")


@app.command()
def poll(
    source: str,
    seed: Path = typer.Option(
        Path("seeds/greenhouse_companies.yaml"),
        "--seed",
        help="Path to source seed file (used by greenhouse).",
    ),
) -> None:
    """Run one poll cycle for a named source (currently: 'greenhouse')."""
    if source == "greenhouse":
        result = asyncio.run(_poll_greenhouse(seed))
        typer.echo(json.dumps(result, indent=2, default=str))
        return
    typer.echo(f"unknown source: {source}", err=True)
    raise typer.Exit(1)


async def _poll_greenhouse(seed_path: Path) -> dict[str, Any]:
    # Lazy imports so `signal-engine version` doesn't pull in db / httpx.
    from signal_engine.db.session import session_scope
    from signal_engine.sources.greenhouse import GreenhouseWorker, load_companies

    companies = load_companies(seed_path)
    worker = GreenhouseWorker(companies)
    async with session_scope() as session:
        result = await worker.run(session)
    return result.model_dump()


def main() -> None:
    app()


if __name__ == "__main__":
    main()
