from __future__ import annotations

import json
from pathlib import Path

import typer

from . import __version__
from .core import (
    AExpError,
    find_workspace,
    format_status,
    init_workspace,
    run_once,
    set_project_enabled,
    status_json,
)
from .kanban import generate as generate_kanban


app = typer.Typer(no_args_is_help=True, invoke_without_command=True)


@app.callback()
def callback(
    version: bool = typer.Option(False, "--version", help="Print version and exit."),
) -> None:
    if version:
        typer.echo(__version__)
        raise typer.Exit()


@app.command()
def init(
    path: Path = typer.Argument(Path("."), help="Workspace path to initialize."),
) -> None:
    """Initialize an a-exp-v2 workspace."""
    created = init_workspace(path.resolve())
    for item in created:
        typer.echo(item)


@app.command()
def status(
    json_output: bool = typer.Option(False, "--json", help="Print scheduler-readable JSON."),
) -> None:
    """Show repo runnable-work status."""
    root = find_workspace()
    data = status_json(root)
    if json_output:
        typer.echo(json.dumps(data, indent=2))
    else:
        typer.echo(format_status(data))


@app.command("run-once")
def run_once_command() -> None:
    """Run one runnable project work lane."""
    root = find_workspace()
    record = run_once(root)
    if record is None:
        data = status_json(root)
        if data["sessions"]["active"] > 0:
            typer.echo("Run already active.")
        else:
            typer.echo("No runnable work.")
        return
    typer.echo(f"ok {record['run_id']}")


@app.command()
def enable(project: str) -> None:
    """Enable a project work lane."""
    root = find_workspace()
    set_project_enabled(root, project, True)
    typer.echo(f"Enabled {project}")


@app.command()
def disable(project: str) -> None:
    """Disable a project work lane."""
    root = find_workspace()
    set_project_enabled(root, project, False)
    typer.echo(f"Disabled {project}")


@app.command()
def kanban(
    project: str | None = typer.Argument(None, help="Optional project name."),
    output_dir: Path | None = typer.Option(None, "--output-dir", help="Output directory."),
) -> None:
    """Generate deterministic Markdown kanban summaries."""
    root = find_workspace()
    if output_dir is not None and not output_dir.is_absolute():
        output_dir = root / output_dir
    paths = generate_kanban(root, project=project, output_dir=output_dir)
    for path in paths:
        typer.echo(path)


def main() -> None:
    try:
        app()
    except AExpError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(exc.exit_code)


if __name__ == "__main__":
    main()
