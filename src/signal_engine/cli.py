"""signal-engine CLI."""
import typer

app = typer.Typer(help="Real-time intent signal capture and scoring.")


@app.command()
def version() -> None:
    """Print the package version."""
    typer.echo("signal-engine 0.1.0")


@app.command()
def poll(source: str) -> None:
    """Run one poll cycle for a named source (e.g. 'greenhouse')."""
    typer.echo(f"poll({source}) — worker not implemented yet")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
