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
    skip_pipeline: bool = typer.Option(
        False,
        "--skip-pipeline",
        help="Just persist signal_events; don't run the matcher/scorer/publisher.",
    ),
) -> None:
    """Run one poll cycle for a named source (currently: 'greenhouse')."""
    if source == "greenhouse":
        result = asyncio.run(_poll_greenhouse(seed, skip_pipeline=skip_pipeline))
        typer.echo(json.dumps(result, indent=2, default=str))
        return
    typer.echo(f"unknown source: {source}", err=True)
    raise typer.Exit(1)


@app.command()
def process() -> None:
    """Run the matcher → scorer → publisher pipeline over unprocessed events."""
    result = asyncio.run(_process_only())
    typer.echo(json.dumps(result, indent=2, default=str))


async def _poll_greenhouse(seed_path: Path, *, skip_pipeline: bool) -> dict[str, Any]:
    from signal_engine.db.session import session_scope
    from signal_engine.pipeline import process_new_events
    from signal_engine.sources.greenhouse import GreenhouseWorker, load_companies

    companies = load_companies(seed_path)
    worker = GreenhouseWorker(companies)
    async with session_scope() as session:
        poll_result = await worker.run(session)
        output: dict[str, Any] = {"poll": poll_result.model_dump()}
        if not skip_pipeline:
            output["pipeline"] = await process_new_events(session)
        return output


async def _process_only() -> dict[str, Any]:
    from signal_engine.db.session import session_scope
    from signal_engine.pipeline import process_new_events

    async with session_scope() as session:
        return await process_new_events(session)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
