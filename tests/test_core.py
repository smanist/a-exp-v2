from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from a_exp_v2 import core
from a_exp_v2.config import load_config
from a_exp_v2.kanban import generate as generate_kanban


def write_project(root: Path, name: str, tasks: str) -> None:
    project = root / "projects" / name
    project.mkdir(parents=True, exist_ok=True)
    (project / "README.md").write_text(f"# {name}\n\n## Log\n", encoding="utf-8")
    (project / "TASKS.md").write_text(tasks, encoding="utf-8")


def test_init_does_not_create_self_project(tmp_path: Path) -> None:
    created = core.init_workspace(tmp_path)

    assert tmp_path / ".git" in created
    assert (tmp_path / ".git").exists()
    assert tmp_path / ".a-exp" / "config.yaml" in created
    assert tmp_path / ".gitignore" in created
    assert (tmp_path / ".gitignore").read_text(encoding="utf-8") == core.default_gitignore_text()
    assert (tmp_path / "projects").is_dir()
    assert not (tmp_path / "projects" / "a-exp").exists()
    assert (tmp_path / "APPROVAL_QUEUE.md").exists()
    agents_text = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert "## Fast Orientation" in agents_text
    assert "`projects/<project>/TASKS.md`: the project work lane" in agents_text
    assert "## Git Rule" in agents_text
    assert (tmp_path / ".agents" / "skills" / "workflow" / "SKILL.md").exists()
    assert "## Git Closeout" in (
        tmp_path / ".agents" / "skills" / "workflow" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert (tmp_path / "docs" / "schemas" / "status-json.md").exists()
    assert (
        subprocess.run(
            ["git", "-C", str(tmp_path), "log", "-1", "--format=%s"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        == "Initialize a-exp-v2 workspace"
    )
    assert (
        subprocess.run(
            ["git", "-C", str(tmp_path), "status", "--short"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        == ""
    )
    artifact_dir = tmp_path / "modules" / "demo" / "artifacts" / "example"
    artifact_dir.mkdir(parents=True)
    for name in ["archive.zip", "array.npz", "table.parquet"]:
        (artifact_dir / name).write_text("data\n", encoding="utf-8")
    assert (
        subprocess.run(
            [
                "git",
                "-C",
                str(tmp_path),
                "check-ignore",
                "modules/demo/artifacts/example/archive.zip",
                "modules/demo/artifacts/example/array.npz",
                "modules/demo/artifacts/example/table.parquet",
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        == [
            "modules/demo/artifacts/example/archive.zip",
            "modules/demo/artifacts/example/array.npz",
            "modules/demo/artifacts/example/table.parquet",
        ]
    )


def test_init_creates_workspace_git_root_inside_parent_repo(tmp_path: Path) -> None:
    subprocess.run(["git", "-C", str(tmp_path), "init"], check=True, capture_output=True, text=True)
    workspace = tmp_path / "workspace"

    created = core.init_workspace(workspace)

    assert workspace / ".git" in created
    assert (workspace / ".git").exists()
    assert (workspace / ".a-exp" / "config.yaml").exists()
    assert (
        subprocess.run(
            ["git", "-C", str(workspace), "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        == str(workspace)
    )


def test_status_uses_runnable_work_not_due_time(tmp_path: Path) -> None:
    core.init_workspace(tmp_path)
    write_project(
        tmp_path,
        "demo",
        "\n".join(
            [
                "# demo",
                "",
                "- [ ] Ready task",
                "  Why: test",
                "  Done when: done",
                "- [ ] Blocked task [blocked-by: data]",
                "- [ ] Approval task [approval-needed: budget]",
                "- [x] Done task",
            ]
        ),
    )

    data = core.status_json(tmp_path)

    assert data["health"] == "ok"
    assert data["jobs"]["runnable"] == 1
    item = data["jobs"]["items"][0]
    assert item["project"] == "demo"
    assert item["state"] == "runnable"
    assert item["open_tasks"] == 3
    assert item["blocked_tasks"] == 2
    assert item["runnable_tasks"] == 1
    assert "due" not in item
    assert "next_run_at" not in item


def test_enable_disable_requires_existing_project(tmp_path: Path) -> None:
    core.init_workspace(tmp_path)
    write_project(tmp_path, "demo", "- [ ] Ready\n")

    core.set_project_enabled(tmp_path, "demo", False)
    assert core.status_json(tmp_path)["jobs"]["items"][0]["state"] == "disabled"
    assert (
        subprocess.run(
            ["git", "-C", str(tmp_path), "log", "-1", "--format=%s"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        == "Disable a-exp-v2 project demo"
    )

    core.set_project_enabled(tmp_path, "demo", True)
    assert core.status_json(tmp_path)["jobs"]["items"][0]["state"] == "runnable"
    assert (
        subprocess.run(
            ["git", "-C", str(tmp_path), "log", "-1", "--format=%s"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        == "Enable a-exp-v2 project demo"
    )
    assert (
        subprocess.run(
            ["git", "-C", str(tmp_path), "status", "--short"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        == ""
    )

    with pytest.raises(core.WorkspaceError, match="Project has no TASKS.md"):
        core.set_project_enabled(tmp_path, "missing", True)

    config = load_config(tmp_path / ".a-exp" / "config.yaml")
    assert config.projects["demo"].enabled is True


def test_select_lane_uses_priority_then_project_name(tmp_path: Path) -> None:
    core.init_workspace(tmp_path)
    write_project(tmp_path, "zeta", "- [ ] Z task\n")
    write_project(tmp_path, "alpha", "- [ ] A task\n")

    config = load_config(tmp_path / ".a-exp" / "config.yaml")
    config.projects["zeta"] = core.ProjectLaneConfig(enabled=True, priority=5)
    config.projects["alpha"] = core.ProjectLaneConfig(enabled=True, priority=5)
    core.dump_config(config, tmp_path / ".a-exp" / "config.yaml")

    assert core.select_lane(tmp_path).project == "alpha"

    config.projects["zeta"].priority = 1
    core.dump_config(config, tmp_path / ".a-exp" / "config.yaml")
    assert core.select_lane(tmp_path).project == "zeta"


def test_run_once_records_success_when_project_memory_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    core.init_workspace(tmp_path)
    write_project(tmp_path, "demo", "- [ ] Ready\n")

    def fake_agent(root: Path, prompt: str, lane: core.Lane, log_path: Path) -> subprocess.CompletedProcess[str]:
        readme = root / "projects" / lane.project / "README.md"
        readme.write_text(
            readme.read_text(encoding="utf-8")
            + "\n## Task closeout\n\n"
            + "Task: Ready\n"
            + "Status: completed\n"
            + "Verification:\n"
            + "- Command: pytest\n"
            + "- Result: passed\n",
            encoding="utf-8",
        )
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("fake log\n", encoding="utf-8")
        return subprocess.CompletedProcess(["codex"], 0, "ok", "")

    monkeypatch.setattr(core, "launch_agent", fake_agent)
    record = core.run_once(tmp_path)

    assert record is not None
    assert record["status"] == "completed"
    assert record["project"] == "demo"
    assert record["task"] == "Ready"
    assert record["closeout_validation"]["ok"] is True
    assert record["closeout_validation"]["checks"] == {
        "durable_memory_changed": True,
        "task_mentioned": True,
        "outcome_recorded": True,
        "verification_recorded": True,
    }
    run_files = list((tmp_path / ".a-exp" / "runs").glob("*.json"))
    assert len(run_files) == 1
    assert (
        subprocess.run(
            ["git", "-C", str(tmp_path), "log", "-1", "--format=%s"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        == "Run a-exp-v2 task for demo"
    )
    assert (
        subprocess.run(
            ["git", "-C", str(tmp_path), "status", "--short"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        == ""
    )


def test_run_once_fails_closeout_when_project_memory_does_not_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    core.init_workspace(tmp_path)
    write_project(tmp_path, "demo", "- [ ] Ready\n")

    def fake_agent(root: Path, prompt: str, lane: core.Lane, log_path: Path) -> subprocess.CompletedProcess[str]:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("fake log\n", encoding="utf-8")
        return subprocess.CompletedProcess(["codex"], 0, "ok", "")

    monkeypatch.setattr(core, "launch_agent", fake_agent)
    with pytest.raises(core.AgentRunFailed):
        core.run_once(tmp_path)

    run_data = json.loads(next((tmp_path / ".a-exp" / "runs").glob("*.json")).read_text())
    assert run_data["status"] == "failed"
    assert run_data["closeout_validation"]["ok"] is False


def test_launch_agent_streams_log_while_process_runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    codex = bin_dir / "codex"
    codex.write_text(
        "\n".join(
            [
                "#!/bin/sh",
                "printf 'ready\\n'",
                "i=0",
                "while [ $i -lt 40 ]; do",
                "  if grep -q '\\[stdout\\] ready' .a-exp/logs/live.log; then",
                "    printf 'observed\\n' >&2",
                "    exit 0",
                "  fi",
                "  i=$((i + 1))",
                "  sleep 0.05",
                "done",
                "printf 'not streamed\\n' >&2",
                "exit 2",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    codex.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    lane = core.Lane(
        project="demo",
        enabled=True,
        priority=100,
        model="test",
        max_duration_ms=5000,
        tasks=[],
    )

    result = core.launch_agent(tmp_path, "prompt", lane, tmp_path / ".a-exp" / "logs" / "live.log")

    log_text = (tmp_path / ".a-exp" / "logs" / "live.log").read_text(encoding="utf-8")
    assert result.returncode == 0
    assert result.stdout == "ready\n"
    assert result.stderr == "observed\n"
    assert "[stdout] ready" in log_text
    assert "[stderr] observed" in log_text
    assert "## summary" in log_text
    assert (tmp_path / ".a-exp" / "logs" / "live.brief.log").exists()


def test_launch_agent_writes_brief_log_with_folded_tool_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    codex = bin_dir / "codex"
    codex.write_text(
        "\n".join(
            [
                "#!/bin/sh",
                "printf 'codex\\n' >&2",
                "printf 'I am orienting on the project.\\n' >&2",
                "printf 'exec\\n' >&2",
                "printf 'python inspect_project.py in /tmp/demo\\n' >&2",
                "printf ' succeeded in 0ms:\\n' >&2",
                "printf '# README\\n' >&2",
                "printf 'lengthy file content\\n' >&2",
                "printf 'more lengthy file content\\n' >&2",
                "printf 'codex\\n' >&2",
                "printf 'I finished reading the project files.\\n' >&2",
                "printf 'tokens used\\n' >&2",
                "printf '1,234\\n' >&2",
                "printf 'Done.\\n'",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    codex.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    lane = core.Lane(
        project="demo",
        enabled=True,
        priority=100,
        model="test",
        max_duration_ms=5000,
        tasks=[],
    )

    result = core.launch_agent(tmp_path, "prompt", lane, tmp_path / ".a-exp" / "logs" / "brief-demo.log")

    full_log = (tmp_path / ".a-exp" / "logs" / "brief-demo.log").read_text(encoding="utf-8")
    brief_log = (tmp_path / ".a-exp" / "logs" / "brief-demo.brief.log").read_text(encoding="utf-8")
    assert result.returncode == 0
    assert "lengthy file content" in full_log
    assert "I am orienting on the project." in brief_log
    assert "Command:" in brief_log
    assert "Result: succeeded in 0ms:" in brief_log
    assert "Folded output lines: 3" in brief_log
    assert "lengthy file content" not in brief_log
    assert "Tokens used: 1,234" in brief_log
    assert "Done." in brief_log


def test_no_work_and_active_run_do_not_write_run_records(tmp_path: Path) -> None:
    core.init_workspace(tmp_path)
    write_project(tmp_path, "done", "- [x] Finished\n")

    assert core.run_once(tmp_path) is None
    assert list((tmp_path / ".a-exp" / "runs").glob("*.json")) == []


def test_running_marker_blocks_when_pid_is_alive(tmp_path: Path) -> None:
    core.init_workspace(tmp_path)
    write_project(tmp_path, "demo", "- [ ] Ready\n")
    marker = tmp_path / ".a-exp" / "running" / "active.json"
    marker.write_text(
        json.dumps({"run_id": "active", "project": "demo", "pid": os.getpid(), "started_at": "now"}),
        encoding="utf-8",
    )

    assert core.status_json(tmp_path)["sessions"]["active"] == 1
    assert core.run_once(tmp_path) is None
    assert list((tmp_path / ".a-exp" / "runs").glob("*.json")) == []


def test_approval_and_experiment_counts(tmp_path: Path) -> None:
    core.init_workspace(tmp_path)
    write_project(tmp_path, "demo", "- [ ] Ready\n")
    (tmp_path / "APPROVAL_QUEUE.md").write_text(
        "# Approval Queue\n\n## Pending\n\n- [ ] approve budget\n\n## Completed\n",
        encoding="utf-8",
    )
    exp_dir = tmp_path / "projects" / "demo" / "experiments" / "exp1"
    exp_dir.mkdir(parents=True)
    (exp_dir / "progress.json").write_text('{"status": "running"}\n', encoding="utf-8")

    data = core.status_json(tmp_path)
    assert data["approvals"]["pending"] == 1
    assert data["experiments"]["running"] == 1


def test_kanban_overwrites_project_file_and_reads_runs(tmp_path: Path) -> None:
    core.init_workspace(tmp_path)
    write_project(tmp_path, "demo", "- [x] Finished\n")
    run_dir = tmp_path / ".a-exp" / "runs"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "run_id": "run",
                "project": "demo",
                "task": "Finished",
                "status": "completed",
                "ended_at": "2026-05-31T00:00:00Z",
                "log_file": ".a-exp/logs/demo.log",
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "reports" / "kanban" / "demo.md"
    output.write_text("old\n", encoding="utf-8")

    written = generate_kanban(tmp_path)

    assert written == [output]
    text = output.read_text(encoding="utf-8")
    assert "## demo-Tasks" in text
    assert "**Runs**" in text
    assert "Finished: completed" in text
