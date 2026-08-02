from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from a_exp_v2 import core
from a_exp_v2.cli import app
from a_exp_v2.runner import CodexRunResult
from a_exp_v2.validators import validate_run_record, validate_status_json


runner = CliRunner()


def commit_all(root: Path, message: str) -> None:
    env = core.git_commit_env()
    subprocess.run(["git", "-C", str(root), "add", "--all"], check=True, env=env)
    subprocess.run(["git", "-C", str(root), "commit", "-m", message], check=True, env=env)


def write_study(root: Path, name: str, state: str) -> None:
    path = root / "projects" / name
    path.mkdir(parents=True)
    (path / "README.md").write_text(f"# {name}\n", encoding="utf-8")
    (path / "GOAL.md").write_text(
        "# Goal\n\nObjective, evidence criteria, autonomy envelope, stop conditions.\n",
        encoding="utf-8",
    )
    core.write_study_state(
        path / "STATE.yaml",
        core.StudyState(
            state=state,
            ready_after=None,
            summary="Ready to explore" if state == "ready" else "Still shaping",
            next_direction=None,
            open_questions=[],
            requires=[],
            last_run_id=None,
            consecutive_failures=0,
        ),
    )
    commit_all(root, f"Create {name}")


def closeout(next_state: str = "completed") -> dict[str, Any]:
    return {
        "outcome": "completed" if next_state == "completed" else "progress",
        "next_state": next_state,
        "summary": "Finished the study",
        "experiments": ["exp-1"],
        "verification": [{"command": "pytest", "result": "passed"}],
        "files_changed": [],
        "artifacts": [],
        "next_direction": None,
        "open_questions": [],
        "budget_used": {"wall_seconds": 1, "experiments": 1},
    }


def fake_result(value: dict[str, Any] | None, returncode: int = 0) -> CodexRunResult:
    return CodexRunResult(
        command=["codex"],
        returncode=returncode,
        stdout="",
        stderr="",
        thread_id="thread-cli",
        turn_started=True,
        closeout=value,
        closeout_error=None if value else "missing final response",
    )


def test_cli_init_status_enable_disable_and_kanban(tmp_path: Path) -> None:
    with runner.isolated_filesystem(temp_dir=tmp_path) as isolated:
        root = Path(isolated)
        result = runner.invoke(app, ["init", str(root)])
        assert result.exit_code == 0
        assert (root / ".a-exp" / "config.yaml").exists()
        write_study(root, "demo", "ready")

        status_result = runner.invoke(app, ["status", "--json"])
        data = json.loads(status_result.stdout)
        assert validate_status_json(data) == []
        assert data["work"]["runnable"] == 1

        assert runner.invoke(app, ["disable", "demo"]).exit_code == 0
        assert json.loads(runner.invoke(app, ["status", "--json"]).stdout)["work"]["runnable"] == 0
        assert runner.invoke(app, ["enable", "demo"]).exit_code == 0

        kanban = runner.invoke(app, ["kanban", "demo"])
        assert kanban.exit_code == 0
        assert (root / "reports" / "kanban" / "demo.md").exists()
        assert subprocess.run(
            ["git", "-C", str(root), "status", "--short"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout == ""


def test_cli_run_once_success(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(core, "run_codex", lambda **_: fake_result(closeout()))
    with runner.isolated_filesystem(temp_dir=tmp_path) as isolated:
        root = Path(isolated)
        core.init_workspace(root)
        write_study(root, "demo", "ready")
        result = runner.invoke(app, ["run-once"])
        assert result.exit_code == 0
        assert result.stdout.startswith("ok ")
        record = json.loads(next((root / ".a-exp" / "runs").glob("*.json")).read_text())
        assert validate_run_record(record) == []


def test_cli_no_work_and_active_run_messages(tmp_path: Path) -> None:
    with runner.isolated_filesystem(temp_dir=tmp_path) as isolated:
        root = Path(isolated)
        core.init_workspace(root)
        write_study(root, "demo", "shaping")
        no_work = runner.invoke(app, ["run-once"])
        assert no_work.exit_code == 0
        assert no_work.stdout == "No runnable work.\n"

        state = core.load_study_state(root / "projects" / "demo" / "STATE.yaml")
        core.write_study_state(root / "projects" / "demo" / "STATE.yaml", core.replace(state, state="ready"))
        commit_all(root, "Ready demo")
        (root / ".a-exp" / "running" / "active.json").write_text(
            json.dumps({"run_id": "active", "project": "demo", "pid": os.getpid()}),
            encoding="utf-8",
        )
        active = runner.invoke(app, ["run-once"])
        assert active.exit_code == 0
        assert active.stdout == "Run already active.\n"


def test_cli_invalid_study_and_failed_closeout(monkeypatch, tmp_path: Path) -> None:
    with runner.isolated_filesystem(temp_dir=tmp_path) as isolated:
        root = Path(isolated)
        core.init_workspace(root)
        missing = runner.invoke(app, ["enable", "missing"])
        assert missing.exit_code == 2
        assert "not a valid study" in missing.stderr

        write_study(root, "demo", "ready")
        monkeypatch.setattr(core, "run_codex", lambda **_: fake_result(None, returncode=1))
        failed = runner.invoke(app, ["run-once"])
        assert failed.exit_code == 1
        assert "Agent run failed" in failed.stderr


def test_cli_invalid_config_exits_two(tmp_path: Path) -> None:
    with runner.isolated_filesystem(temp_dir=tmp_path) as isolated:
        root = Path(isolated)
        core.init_workspace(root)
        (root / ".a-exp" / "config.yaml").write_text(
            "layout_version: 1\n",
            encoding="utf-8",
        )

        result = runner.invoke(app, ["status", "--json"])

        assert result.exit_code == 2
        assert "layout_version must be 2" in result.stderr
