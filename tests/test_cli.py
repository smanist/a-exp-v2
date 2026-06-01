from __future__ import annotations

import json
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from a_exp_v2 import core
from a_exp_v2.cli import app
from a_exp_v2.validators import validate_run_record, validate_status_json


runner = CliRunner()


def write_project(root: Path, name: str, tasks: str) -> None:
    project = root / "projects" / name
    project.mkdir(parents=True, exist_ok=True)
    (project / "README.md").write_text(f"# {name}\n\n## Log\n", encoding="utf-8")
    (project / "TASKS.md").write_text(tasks, encoding="utf-8")


def test_cli_init_status_enable_disable_and_kanban(tmp_path: Path) -> None:
    result = runner.invoke(app, ["init", str(tmp_path)])
    assert result.exit_code == 0
    assert (tmp_path / ".a-exp" / "config.yaml").exists()
    assert (tmp_path / ".agents" / "skills" / "workflow" / "SKILL.md").exists()

    write_project(tmp_path, "demo", "- [ ] Ready\n")

    with runner.isolated_filesystem(temp_dir=tmp_path) as iso:
        # Typer's isolated filesystem changes cwd to a child dir; initialize there
        # so command-level workspace discovery is exercised from cwd.
        cwd = Path(iso)
        core.init_workspace(cwd)
        write_project(cwd, "demo", "- [ ] Ready\n")

        status_result = runner.invoke(app, ["status", "--json"])
        assert status_result.exit_code == 0
        data = json.loads(status_result.stdout)
        assert validate_status_json(data) == []
        assert data["jobs"]["runnable"] == 1

        disable_result = runner.invoke(app, ["disable", "demo"])
        assert disable_result.exit_code == 0
        assert "Disabled demo" in disable_result.stdout
        assert json.loads(runner.invoke(app, ["status", "--json"]).stdout)["jobs"]["runnable"] == 0

        enable_result = runner.invoke(app, ["enable", "demo"])
        assert enable_result.exit_code == 0
        assert "Enabled demo" in enable_result.stdout

        kanban_result = runner.invoke(app, ["kanban"])
        assert kanban_result.exit_code == 0
        assert (cwd / "reports" / "kanban" / "demo.md").exists()
        assert (
            subprocess.run(
                ["git", "-C", str(cwd), "log", "-1", "--format=%s"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            == "Generate a-exp-v2 kanban"
        )
        assert (
            subprocess.run(
                ["git", "-C", str(cwd), "status", "--short"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            == ""
        )


def test_cli_run_once_success_and_run_record_schema(
    tmp_path: Path, monkeypatch
) -> None:
    def fake_agent(root: Path, prompt: str, lane: core.Lane, log_path: Path) -> subprocess.CompletedProcess[str]:
        readme = root / "projects" / lane.project / "README.md"
        readme.write_text(
            readme.read_text(encoding="utf-8")
            + "\n## Task closeout\n\n"
            + "Task: Ready\n"
            + "Mode: conventional\n"
            + "Status: completed\n"
            + "Summary: done\n"
            + "Verification:\n"
            + "- Command: pytest\n"
            + "- Result: passed\n",
            encoding="utf-8",
        )
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("fake log\n", encoding="utf-8")
        return subprocess.CompletedProcess(["codex"], 0, "ok", "")

    monkeypatch.setattr(core, "launch_agent", fake_agent)
    with runner.isolated_filesystem(temp_dir=tmp_path) as iso:
        cwd = Path(iso)
        core.init_workspace(cwd)
        write_project(cwd, "demo", "- [ ] Ready\n")
        monkeypatch.setattr(core, "launch_agent", fake_agent)

        result = runner.invoke(app, ["run-once"])
        assert result.exit_code == 0
        assert result.stdout.startswith("ok ")
        run_record = json.loads(next((cwd / ".a-exp" / "runs").glob("*.json")).read_text())
        assert validate_run_record(run_record) == []


def test_cli_enable_unknown_project_exits_with_workspace_error(tmp_path: Path) -> None:
    with runner.isolated_filesystem(temp_dir=tmp_path):
        core.init_workspace(Path.cwd())
        result = runner.invoke(app, ["enable", "missing"])
        assert result.exit_code == 2
        assert "Project has no TASKS.md" in result.stderr


def test_cli_run_once_no_work_exits_zero_without_run_record(tmp_path: Path) -> None:
    with runner.isolated_filesystem(temp_dir=tmp_path) as iso:
        cwd = Path(iso)
        core.init_workspace(cwd)
        write_project(cwd, "demo", "- [x] Done\n")

        result = runner.invoke(app, ["run-once"])

        assert result.exit_code == 0
        assert "No runnable work." in result.stdout
        assert list((cwd / ".a-exp" / "runs").glob("*.json")) == []


def test_cli_run_once_failed_closeout_exits_one(tmp_path: Path, monkeypatch) -> None:
    def fake_agent(root: Path, prompt: str, lane: core.Lane, log_path: Path) -> subprocess.CompletedProcess[str]:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("fake log\n", encoding="utf-8")
        return subprocess.CompletedProcess(["codex"], 0, "ok", "")

    monkeypatch.setattr(core, "launch_agent", fake_agent)
    with runner.isolated_filesystem(temp_dir=tmp_path) as iso:
        cwd = Path(iso)
        core.init_workspace(cwd)
        write_project(cwd, "demo", "- [ ] Ready\n")

        result = runner.invoke(app, ["run-once"])

        assert result.exit_code == 1
        assert "closeout validation failed" in result.stderr
        run_record = json.loads(next((cwd / ".a-exp" / "runs").glob("*.json")).read_text())
        assert run_record["status"] == "failed"
        assert validate_run_record(run_record) == []
