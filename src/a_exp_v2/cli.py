from __future__ import annotations

import json
from pathlib import Path

import typer

from . import __version__
from .core import (
    AExpError,
    WorkspaceError,
    commit_workspace_changes,
    find_workspace,
    format_status,
    init_workspace,
    run_once,
    set_project_enabled,
    status_json,
)
from .kanban import generate as generate_kanban


app = typer.Typer(no_args_is_help=True, invoke_without_command=True)


def exit_with_error(exc: AExpError) -> None:
    typer.echo(str(exc), err=True)
    raise typer.Exit(exc.exit_code)


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
    try:
        created = init_workspace(path.resolve())
    except AExpError as exc:
        exit_with_error(exc)
    for item in created:
        typer.echo(item)


@app.command()
def status(
    json_output: bool = typer.Option(False, "--json", help="Print scheduler-readable JSON."),
) -> None:
    """Show study lifecycle and runnable-session status."""
    try:
        root = find_workspace()
        data = status_json(root)
    except AExpError as exc:
        exit_with_error(exc)
    if json_output:
        typer.echo(json.dumps(data, indent=2))
    else:
        typer.echo(format_status(data))


@app.command("run-once")
def run_once_command() -> None:
    """Run or resume one ready study session."""
    try:
        root = find_workspace()
        record = run_once(root)
    except AExpError as exc:
        exit_with_error(exc)
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
    """Enable a study for scheduling."""
    try:
        root = find_workspace()
        set_project_enabled(root, project, True)
    except AExpError as exc:
        exit_with_error(exc)
    typer.echo(f"Enabled {project}")


@app.command()
def disable(project: str) -> None:
    """Disable a study for scheduling."""
    try:
        root = find_workspace()
        set_project_enabled(root, project, False)
    except AExpError as exc:
        exit_with_error(exc)
    typer.echo(f"Disabled {project}")


@app.command()
def kanban(
    project: str | None = typer.Argument(None, help="Optional project name."),
    output_dir: Path | None = typer.Option(None, "--output-dir", help="Output directory."),
) -> None:
    """Generate deterministic Markdown kanban summaries."""
    try:
        root = find_workspace()
    except AExpError as exc:
        exit_with_error(exc)
    if output_dir is not None and not output_dir.is_absolute():
        output_dir = root / output_dir
    try:
        paths = generate_kanban(root, project=project, output_dir=output_dir)
        relative_paths = [path.relative_to(root) for path in paths if path.is_relative_to(root)]
        commit_workspace_changes(root, "Generate a-exp-v2 kanban", relative_paths)
    except FileNotFoundError as exc:
        exit_with_error(WorkspaceError(str(exc)))
    except AExpError as exc:
        exit_with_error(exc)
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
