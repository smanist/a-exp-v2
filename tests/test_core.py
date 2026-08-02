from __future__ import annotations

import json
import multiprocessing
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
import yaml

from a_exp_v2 import core
from a_exp_v2.config import ProjectConfig, dump_config, load_config
from a_exp_v2.kanban import generate as generate_kanban
from a_exp_v2.runner import CodexRunResult
from a_exp_v2.validators import validate_run_record, validate_status_json


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
        env=core.git_commit_env(),
    )
    return result.stdout.strip()


def commit_all(root: Path, message: str = "Shape study") -> None:
    git(root, "add", "--all")
    git(root, "commit", "-m", message)


def write_initial_context(root: Path, path: Path) -> None:
    (path / "handoffs").mkdir(exist_ok=True)
    handoff_id = "r0001-initial"
    handoff = {
        "schema_version": 1,
        "handoff_id": handoff_id,
        "study": path.name,
        "created_at": "2026-08-02T12:00:00Z",
        "context_revision": 1,
        "previous_handoff": None,
        "source_commit": "0" * 40,
        "based_on_run_id": None,
        "change_class": "initial",
        "thread_policy": "resume",
        "goal_sha256": core.content_hash(path / "GOAL.md"),
        "steering_sha256": None,
        "summary": "Initial interactive handoff",
        "decisions": [],
        "constraints": [],
        "retained_evidence": [],
        "superseded_assumptions": [],
        "rejected_alternatives": [],
        "next_direction": "Continue",
        "open_questions": [],
        "relevant_paths": [],
        "interactive_experiments": [],
        "interactive_commits": [],
        "artifacts": [],
        "source_thread_id": None,
    }
    (path / "handoffs" / f"{handoff_id}.yaml").write_text(
        yaml.safe_dump(handoff, sort_keys=False), encoding="utf-8"
    )
    core.write_study_context(
        path / "CONTEXT.yaml",
        core.StudyContext(revision=1, latest_handoff=handoff_id),
    )


def write_study(
    root: Path,
    name: str,
    *,
    state: str = "ready",
    ready_after: str | None = None,
    requires: list[str] | None = None,
    failures: int = 0,
    commit: bool = True,
) -> Path:
    path = root / "projects" / name
    path.mkdir(parents=True, exist_ok=True)
    (path / "README.md").write_text(f"# {name}\n\nEnvironment orientation.\n", encoding="utf-8")
    (path / "GOAL.md").write_text(
        "# Goal\n\n## Objective\nAdvance evidence.\n\n"
        "## Evidence Criteria\nVerified output.\n\n"
        "## Autonomy Envelope\nRun local experiments.\n\n"
        "## Stop Conditions\nStop when supported.\n",
        encoding="utf-8",
    )
    core.write_study_state(
        path / "STATE.yaml",
        core.StudyState(
            state=state,
            ready_after=ready_after,
            summary=f"{name} summary",
            next_direction="Continue",
            open_questions=[],
            requires=requires or [],
            last_run_id=None,
            consecutive_failures=failures,
        ),
    )
    (path / "handoffs").mkdir(exist_ok=True)
    if state == "shaping":
        core.write_study_context(
            path / "CONTEXT.yaml", core.StudyContext(revision=0, latest_handoff=None)
        )
    else:
        write_initial_context(root, path)
    if commit:
        commit_all(root, f"Shape {name}")
    return path


def successful_closeout(
    *,
    next_state: str = "ready",
    files: list[str] | None = None,
    experiments: list[str] | None = None,
) -> dict[str, Any]:
    outcome = {
        "ready": "progress",
        "needs_human": "needs_human",
        "paused": "paused",
        "blocked": "blocked",
        "completed": "completed",
    }[next_state]
    return {
        "outcome": outcome,
        "next_state": next_state,
        "summary": "Made measurable progress",
        "experiments": experiments or ["exp-a", "exp-b"],
        "verification": [{"command": "pytest -q", "result": "passed"}],
        "files_changed": files or [],
        "artifacts": ["projects/demo/artifacts/result.json"],
        "next_direction": "Run the next comparison" if next_state == "ready" else None,
        "open_questions": ["Choose a threshold"] if next_state == "needs_human" else [],
        "budget_used": {"wall_seconds": 12, "experiments": 2},
    }


def result(
    closeout: dict[str, Any] | None,
    *,
    returncode: int = 0,
    thread_id: str | None = "thread-1",
    turn_started: bool = True,
) -> CodexRunResult:
    return CodexRunResult(
        command=["codex"],
        returncode=returncode,
        stdout="",
        stderr="",
        thread_id=thread_id,
        turn_started=turn_started,
        duration_seconds=12,
        closeout=closeout,
        closeout_error=None if closeout is not None else "missing final response",
    )


def completed_session_data(
    study: str,
    run_id: str,
    *,
    next_state: str = "ready",
    summary: str = "Completed test session",
    artifacts: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "run_id": run_id,
        "study": study,
        "status": "completed",
        "outcome": "progress" if next_state == "ready" else next_state,
        "previous_state": "ready",
        "next_state": next_state,
        "started_at": "2026-08-01T00:00:00Z",
        "ended_at": "2026-08-01T00:01:00Z",
        "codex_thread_id": f"thread-{study}",
        "replaced_thread_id": None,
        "context_revision": 1,
        "handoff_id": "r0001-initial",
        "requested_thread_policy": "resume",
        "applied_thread_action": "new",
        "context_consumed": True,
        "summary": summary,
        "experiments": [],
        "verification": [{"command": "pytest", "result": "passed"}],
        "files_changed": [],
        "artifacts": artifacts or [],
        "budget_used": {"wall_seconds": 1, "experiments": 0},
        "commits": [],
        "next_direction": None,
        "open_questions": [],
    }


def append_handoff(
    root: Path,
    path: Path,
    *,
    change_class: str,
    thread_policy: str,
    superseded_assumptions: list[str] | None = None,
    interactive_experiments: list[str] | None = None,
    artifacts: list[str] | None = None,
) -> str:
    context = core.load_study_context(path / "CONTEXT.yaml")
    assert context.latest_handoff is not None
    revision = context.revision + 1
    handoff_id = f"r{revision:04d}-test"
    data = {
        "schema_version": 1,
        "handoff_id": handoff_id,
        "study": path.name,
        "created_at": f"2026-08-{revision + 2:02d}T12:00:00Z",
        "context_revision": revision,
        "previous_handoff": context.latest_handoff,
        "source_commit": "1" * 40,
        "based_on_run_id": None,
        "change_class": change_class,
        "thread_policy": thread_policy,
        "goal_sha256": core.content_hash(path / "GOAL.md"),
        "steering_sha256": (
            core.content_hash(path / "STEERING.md")
            if (path / "STEERING.md").exists()
            else None
        ),
        "summary": f"Revision {revision}",
        "decisions": [],
        "constraints": [],
        "retained_evidence": [],
        "superseded_assumptions": superseded_assumptions or [],
        "rejected_alternatives": [],
        "next_direction": "Continue",
        "open_questions": [],
        "relevant_paths": [],
        "interactive_experiments": interactive_experiments or [],
        "interactive_commits": [],
        "artifacts": artifacts or [],
        "source_thread_id": None,
    }
    (path / "handoffs" / f"{handoff_id}.yaml").write_text(
        yaml.safe_dump(data, sort_keys=False), encoding="utf-8"
    )
    core.write_study_context(
        path / "CONTEXT.yaml",
        core.StudyContext(revision=revision, latest_handoff=handoff_id),
    )
    return handoff_id


def test_init_creates_taskless_workspace_and_commits(tmp_path: Path) -> None:
    created = core.init_workspace(tmp_path)

    assert tmp_path / ".git" in created
    assert (tmp_path / "projects").is_dir()
    assert list((tmp_path / "projects").iterdir()) == []
    assert (tmp_path / "docs" / "schemas" / "study.md").exists()
    assert (tmp_path / "docs" / "schemas" / "context-handoff.md").exists()
    assert (tmp_path / ".agents" / "skills" / "workflow" / "SKILL.md").exists()
    assert load_config(tmp_path / ".a-exp" / "config.yaml").layout_version == 3
    assert yaml.safe_load((tmp_path / ".a-exp" / "kit.lock.yaml").read_text())["version"] == "0.3.0"
    assert "STATE.yaml" in (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert git(tmp_path, "log", "-1", "--format=%s") == "Initialize a-exp-v2 workspace"
    assert git(tmp_path, "status", "--short") == ""


def test_init_creates_nested_git_root(tmp_path: Path) -> None:
    git(tmp_path, "init")
    workspace = tmp_path / "workspace"
    core.init_workspace(workspace)
    assert Path(git(workspace, "rev-parse", "--show-toplevel")) == workspace


def test_init_rejects_external_runtime_root_before_writing(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside-runtime-root"
    outside.mkdir()
    (tmp_path / ".a-exp").symlink_to(outside, target_is_directory=True)

    with pytest.raises(core.WorkspaceError, match="runtime directory escapes workspace"):
        core.init_workspace(tmp_path)

    assert list(outside.iterdir()) == []


def test_package_tree_symlink_requires_source_inside_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "installed-package" / "skills"
    outside.mkdir(parents=True)
    monkeypatch.setattr(core, "package_resource_path", lambda _: outside)

    assert core.symlink_package_tree(workspace, "skills", ".agents/skills") is None
    assert not (workspace / ".agents" / "skills").exists()


def test_state_validation_and_invalid_discovery(tmp_path: Path) -> None:
    core.init_workspace(tmp_path)
    path = write_study(tmp_path, "bad", commit=False)
    (path / "STATE.yaml").write_text("schema_version: 1\nstate: running\n", encoding="utf-8")
    commit_all(tmp_path)

    studies, issues = core.discover_studies(tmp_path)
    assert studies[0].effective_state == "invalid"
    assert any("Invalid projects/bad" in issue for issue in issues)
    data = core.status_json(tmp_path)
    assert data["health"] == "degraded"
    assert data["studies"]["invalid"] == 1


def test_unquoted_yaml_timestamp_is_normalized(tmp_path: Path) -> None:
    path = tmp_path / "STATE.yaml"
    path.write_text(
        "schema_version: 1\n"
        "state: ready\n"
        "ready_after: 2026-08-02T12:00:00Z\n"
        "summary: Ready later\n"
        "next_direction: null\n"
        "open_questions: []\n"
        "requires: []\n"
        "last_run_id: null\n"
        "consecutive_failures: 0\n",
        encoding="utf-8",
    )

    state = core.load_study_state(path)

    assert state.ready_after == "2026-08-02T12:00:00Z"


def test_status_contract_and_lifecycle_counts(tmp_path: Path) -> None:
    core.init_workspace(tmp_path)
    write_study(tmp_path, "ready")
    write_study(tmp_path, "human", state="needs_human")
    write_study(tmp_path, "shape", state="shaping")

    data = core.status_json(tmp_path)
    assert validate_status_json(data) == []
    assert data["health"] == "ok"
    assert data["work"]["runnable"] == 1
    assert data["studies"]["ready"] == 1
    assert data["studies"]["needs_human"] == 1
    assert next(item for item in data["studies"]["items"] if item["id"] == "shape")[
        "state"
    ] == "shaping"
    item = next(item for item in data["studies"]["items"] if item["id"] == "ready")
    assert item["configured_state"] == "ready"
    assert item["eligible"] is True
    assert item["run_count"] == 0


def test_dirty_idle_workspace_degrades_health_and_blocks_claim(tmp_path: Path) -> None:
    core.init_workspace(tmp_path)
    write_study(tmp_path, "demo")
    (tmp_path / "scratch.txt").write_text("uncommitted\n", encoding="utf-8")

    assert core.status_json(tmp_path)["health"] == "degraded"
    with pytest.raises(core.WorkspaceError, match="uncommitted changes"):
        core.run_once(tmp_path)


def test_scoped_commit_refuses_unrelated_staged_paths(tmp_path: Path) -> None:
    core.init_workspace(tmp_path)
    (tmp_path / "unrelated.txt").write_text("user work\n", encoding="utf-8")
    git(tmp_path, "add", "unrelated.txt")
    report = tmp_path / "reports" / "kanban" / "summary.md"
    report.write_text("generated\n", encoding="utf-8")

    with pytest.raises(core.WorkspaceError, match="unrelated staged"):
        core.commit_workspace_changes(
            tmp_path,
            "Generate summary",
            ["reports/kanban/summary.md"],
        )

    assert core.git_staged_paths(tmp_path) == ["unrelated.txt"]
    assert "reports/kanban/summary.md" in core.git_status_paths(tmp_path)


def test_enable_disable_requires_valid_study_and_commits(tmp_path: Path) -> None:
    core.init_workspace(tmp_path)
    write_study(tmp_path, "demo")

    core.set_project_enabled(tmp_path, "demo", False)
    assert core.status_json(tmp_path)["studies"]["items"][0]["state"] == "disabled"
    assert git(tmp_path, "log", "-1", "--format=%s") == "Disable a-exp-v2 study demo"
    core.set_project_enabled(tmp_path, "demo", True)
    assert core.status_json(tmp_path)["work"]["runnable"] == 1
    with pytest.raises(core.WorkspaceError, match="not a valid study"):
        core.set_project_enabled(tmp_path, "missing", True)
    with pytest.raises(core.WorkspaceError, match="Invalid study ID"):
        core.set_project_enabled(tmp_path, "../outside", True)


def test_capability_eligibility_and_host_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    core.init_workspace(tmp_path)
    write_study(tmp_path, "gpu", requires=["cuda", "cpu"])
    host = tmp_path / ".a-exp" / "host.yaml"
    host.write_text("capabilities: []\n", encoding="utf-8")
    monkeypatch.setenv("A_EXP_HOST_CONFIG", str(host))

    data = core.status_json(tmp_path)
    item = data["studies"]["items"][0]
    assert data["health"] == "ok"
    assert item["state"] == "ineligible"
    assert "cuda" in item["ineligible_reason"]
    assert data["work"]["runnable"] == 0

    host.write_text("capabilities: [cuda]\n", encoding="utf-8")
    assert core.status_json(tmp_path)["work"]["runnable"] == 1
    assert "cpu" in core.load_host_capabilities()
    assert {"linux", "macos"} & core.load_host_capabilities()


def test_config_is_strict_and_danger_requires_project_override(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("layout_version: 3\ndefaults:\n  mystery: 1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unknown"):
        load_config(path)
    path.write_text(
        "layout_version: 3\ndefaults:\n  sandbox: danger-full-access\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="explicit project override"):
        load_config(path)

    path.write_text(
        "layout_version: 3\nprojects:\n  /tmp/outside-study:\n    enabled: true\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="study ID"):
        load_config(path)


def test_discovery_rejects_study_symlink_that_escapes_workspace(tmp_path: Path) -> None:
    core.init_workspace(tmp_path)
    outside = tmp_path.parent / f"{tmp_path.name}-outside-study"
    outside.mkdir()
    (outside / "README.md").write_text("# Outside\n", encoding="utf-8")
    (outside / "GOAL.md").write_text("# Goal\n", encoding="utf-8")
    core.write_study_state(outside / "STATE.yaml", core.default_invalid_state())
    (tmp_path / "projects" / "escape").symlink_to(outside, target_is_directory=True)

    data = core.status_json(tmp_path)

    assert data["health"] == "degraded"
    assert data["studies"]["invalid"] == 1
    assert data["work"]["runnable"] == 0
    assert any("escapes workspace" in warning for warning in data["warnings"])
    with pytest.raises(core.WorkspaceError, match="Invalid study ID"):
        core.thread_record_path(tmp_path, "../outside")

    threads = tmp_path / ".a-exp" / "threads"
    threads.rmdir()
    outside_threads = tmp_path.parent / f"{tmp_path.name}-outside-threads"
    outside_threads.mkdir()
    threads.symlink_to(outside_threads, target_is_directory=True)
    with pytest.raises(core.WorkspaceError, match="escapes workspace"):
        core.thread_record_path(tmp_path, "demo")


def test_discovery_rejects_external_sessions_directory(tmp_path: Path) -> None:
    core.init_workspace(tmp_path)
    study = write_study(tmp_path, "demo")
    outside = tmp_path.parent / f"{tmp_path.name}-outside-sessions"
    outside.mkdir()
    (study / "sessions").symlink_to(outside, target_is_directory=True)
    commit_all(tmp_path, "Add invalid sessions link")

    data = core.status_json(tmp_path)

    assert data["health"] == "degraded"
    assert data["studies"]["invalid"] == 1
    assert data["work"]["runnable"] == 0
    assert any("sessions" in warning and "escapes workspace" in warning for warning in data["warnings"])
    with pytest.raises(core.WorkspaceError, match="degraded"):
        core.run_once(tmp_path)
    assert list(outside.iterdir()) == []


def test_runtime_directory_symlink_degrades_before_claim(tmp_path: Path) -> None:
    core.init_workspace(tmp_path)
    write_study(tmp_path, "demo")
    runs = tmp_path / ".a-exp" / "runs"
    runs.rmdir()
    outside = tmp_path.parent / f"{tmp_path.name}-outside-runs"
    outside.mkdir()
    runs.symlink_to(outside, target_is_directory=True)

    data = core.status_json(tmp_path)

    assert data["health"] == "degraded"
    assert data["work"]["runnable"] == 0
    assert any(".a-exp/runs" in warning for warning in data["warnings"])
    with pytest.raises(core.WorkspaceError, match="degraded"):
        core.run_once(tmp_path)
    assert list(outside.iterdir()) == []


def test_selection_ready_after_priority_last_run_and_id(tmp_path: Path) -> None:
    core.init_workspace(tmp_path)
    write_study(tmp_path, "zeta")
    write_study(tmp_path, "alpha")
    config = load_config(tmp_path / ".a-exp" / "config.yaml")
    config.projects["zeta"] = ProjectConfig(priority=10)
    config.projects["alpha"] = ProjectConfig(priority=10)
    dump_config(config, tmp_path / ".a-exp" / "config.yaml")
    commit_all(tmp_path, "Configure priorities")

    studies, _ = core.discover_studies(tmp_path)
    assert core.select_study(studies).project == "alpha"

    session = tmp_path / "projects" / "alpha" / "sessions" / "old.yaml"
    session.parent.mkdir(parents=True)
    old_session = completed_session_data("alpha", "old")
    old_session["started_at"] = "2026-01-01T00:00:00Z"
    session.write_text(yaml.safe_dump(old_session, sort_keys=False), encoding="utf-8")
    commit_all(tmp_path, "Record alpha history")
    studies, _ = core.discover_studies(tmp_path)
    assert core.select_study(studies).project == "zeta"

    config = load_config(tmp_path / ".a-exp" / "config.yaml")
    config.projects["alpha"].priority = 1
    dump_config(config, tmp_path / ".a-exp" / "config.yaml")
    commit_all(tmp_path, "Prefer alpha")
    studies, _ = core.discover_studies(tmp_path)
    assert core.select_study(studies).project == "alpha"


def test_future_cooldown_is_not_runnable(tmp_path: Path) -> None:
    core.init_workspace(tmp_path)
    write_study(tmp_path, "demo", ready_after="2999-01-01T00:00:00Z")
    assert core.status_json(tmp_path)["studies"]["ready"] == 1
    assert core.status_json(tmp_path)["work"]["runnable"] == 0


def test_live_and_stale_markers_derive_running(tmp_path: Path) -> None:
    core.init_workspace(tmp_path)
    write_study(tmp_path, "demo")
    marker = tmp_path / ".a-exp" / "running" / "active.json"
    marker.write_text(
        json.dumps({"run_id": "active", "project": "demo", "pid": os.getpid()}),
        encoding="utf-8",
    )
    data = core.status_json(tmp_path)
    assert data["sessions"]["active"] == 1
    assert data["studies"]["items"][0]["state"] == "running"
    (tmp_path / "projects" / "demo" / "WORKING.md").write_text("in progress\n")
    assert core.run_once(tmp_path) is None
    (tmp_path / "projects" / "demo" / "WORKING.md").unlink()

    marker.write_text(
        json.dumps({"run_id": "stale", "project": "demo", "pid": 999_999_999}),
        encoding="utf-8",
    )
    data = core.status_json(tmp_path)
    assert data["sessions"]["active"] == 0
    assert not marker.exists()


def test_invalid_live_marker_degrades_workspace(tmp_path: Path) -> None:
    core.init_workspace(tmp_path)
    write_study(tmp_path, "demo")
    marker = tmp_path / ".a-exp" / "running" / "active.json"
    marker.write_text(
        json.dumps({"run_id": "active", "project": "../outside", "pid": os.getpid()}),
        encoding="utf-8",
    )

    data = core.status_json(tmp_path)

    assert data["health"] == "degraded"
    assert data["sessions"]["active"] == 0
    assert data["work"]["runnable"] == 0
    assert any("Invalid running marker study ID" in warning for warning in data["warnings"])


def _claim_and_hold(root: str, queue: Any, release: Any) -> None:
    try:
        claim = core.claim_next_study(Path(root))
        queue.put(None if claim is None else claim[1])
        release.wait(10)
    except Exception as exc:  # pragma: no cover - diagnostic transport
        queue.put(f"error:{exc}")


def test_atomic_claim_allows_only_one_process(tmp_path: Path) -> None:
    core.init_workspace(tmp_path)
    write_study(tmp_path, "demo")
    context = multiprocessing.get_context("fork")
    queue = context.Queue()
    release = context.Event()
    processes = [
        context.Process(target=_claim_and_hold, args=(str(tmp_path), queue, release))
        for _ in range(2)
    ]
    for process in processes:
        process.start()
    values = [queue.get(timeout=10), queue.get(timeout=10)]
    release.set()
    for process in processes:
        process.join(timeout=10)
    assert sum(value is not None for value in values) == 1
    assert not any(isinstance(value, str) and value.startswith("error:") for value in values)


@pytest.mark.parametrize(
    "next_state", ["ready", "needs_human", "paused", "blocked", "completed"]
)
def test_successful_run_applies_each_valid_next_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    next_state: str,
) -> None:
    core.init_workspace(tmp_path)
    write_study(tmp_path, "demo")

    def fake_run_codex(**_: Any) -> CodexRunResult:
        return result(successful_closeout(next_state=next_state))

    monkeypatch.setattr(core, "run_codex", fake_run_codex)
    record = core.run_once(tmp_path)
    assert record is not None
    assert record["next_state"] == next_state
    assert record["experiments"] == ["exp-a", "exp-b"]
    assert record["context_revision"] == 1
    assert record["handoff_id"] == "r0001-initial"
    assert record["requested_thread_policy"] == "resume"
    assert record["applied_thread_action"] == "new"
    assert record["context_consumed"] is True
    assert validate_run_record(record) == []
    state = core.load_study_state(tmp_path / "projects" / "demo" / "STATE.yaml")
    assert state.state == next_state
    assert state.ready_after is not None if next_state == "ready" else state.ready_after is None
    assert state.consecutive_failures == 0
    assert len(list((tmp_path / "projects" / "demo" / "sessions").glob("*.yaml"))) == 1
    assert git(tmp_path, "status", "--short") == ""


def test_success_closeout_stages_declared_paths_and_records_checkpoint_commits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    core.init_workspace(tmp_path)
    write_study(tmp_path, "demo")

    def fake_run_codex(**_: Any) -> CodexRunResult:
        result_path = tmp_path / "projects" / "demo" / "RESULT.md"
        result_path.write_text("evidence\n", encoding="utf-8")
        git(tmp_path, "add", "projects/demo/RESULT.md")
        git(tmp_path, "commit", "-m", "Record experiment checkpoint")
        return result(successful_closeout(files=["projects/demo/RESULT.md"]))

    monkeypatch.setattr(core, "run_codex", fake_run_codex)
    record = core.run_once(tmp_path)
    session = yaml.safe_load(
        next((tmp_path / "projects" / "demo" / "sessions").glob("*.yaml")).read_text()
    )
    assert "projects/demo/RESULT.md" in record["files_changed"]
    assert len(session["commits"]) == 1
    assert git(tmp_path, "show", "--format=%s", "--no-patch", session["commits"][0]) == (
        "Record experiment checkpoint"
    )
    assert git(tmp_path, "status", "--short") == ""


def test_resume_failure_before_turn_replaces_thread(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    core.init_workspace(tmp_path)
    write_study(tmp_path, "demo")
    core.write_thread_record(tmp_path, "demo", "missing-thread", "old-run", 1)
    calls: list[str | None] = []

    def fake_run_codex(**kwargs: Any) -> CodexRunResult:
        calls.append(kwargs["thread_id"])
        if len(calls) == 1:
            return result(None, returncode=1, thread_id=None, turn_started=False)
        return result(successful_closeout(next_state="completed"), thread_id="replacement")

    monkeypatch.setattr(core, "run_codex", fake_run_codex)
    record = core.run_once(tmp_path)
    assert calls == ["missing-thread", None]
    assert record["codex_thread_id"] == "replacement"
    assert record["replaced_thread_id"] == "missing-thread"
    assert record["requested_thread_policy"] == "resume"
    assert record["applied_thread_action"] == "resume_fallback"
    assert core.read_thread_id(tmp_path, "demo") == "replacement"


def test_clean_infrastructure_failure_retries_then_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    core.init_workspace(tmp_path)
    write_study(tmp_path, "demo")
    monkeypatch.setattr(
        core,
        "run_codex",
        lambda **_: result(None, returncode=2, thread_id=None, turn_started=False),
    )

    with pytest.raises(core.AgentRunFailed):
        core.run_once(tmp_path)
    state_path = tmp_path / "projects" / "demo" / "STATE.yaml"
    first = core.load_study_state(state_path)
    assert first.state == "ready"
    assert first.consecutive_failures == 1
    assert first.ready_after is not None
    core.write_study_state(state_path, replace(first, ready_after=None))
    commit_all(tmp_path, "Make retry due")

    with pytest.raises(core.AgentRunFailed):
        core.run_once(tmp_path)
    second = core.load_study_state(state_path)
    assert second.state == "failed"
    assert second.consecutive_failures == 2
    assert len(list((tmp_path / "projects" / "demo" / "sessions").glob("*.yaml"))) == 2
    assert git(tmp_path, "status", "--short") == ""


def test_runner_exception_becomes_clean_retry_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    core.init_workspace(tmp_path)
    write_study(tmp_path, "demo")

    def explode(**_: Any) -> CodexRunResult:
        raise OSError("process launch broke")

    monkeypatch.setattr(core, "run_codex", explode)
    with pytest.raises(core.AgentRunFailed, match="runner exception"):
        core.run_once(tmp_path)
    state = core.load_study_state(tmp_path / "projects" / "demo" / "STATE.yaml")
    assert state.state == "ready"
    assert state.consecutive_failures == 1
    runtime = json.loads(next((tmp_path / ".a-exp" / "runs").glob("*.json")).read_text())
    assert any("process launch broke" in error for error in runtime["closeout_validation"]["errors"])
    assert git(tmp_path, "status", "--short") == ""


def test_undeclared_dirty_file_preserves_recovery_and_degrades_health(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    core.init_workspace(tmp_path)
    write_study(tmp_path, "demo")

    def fake_run_codex(**_: Any) -> CodexRunResult:
        (tmp_path / "unexpected.txt").write_text("preserve me\n", encoding="utf-8")
        return result(successful_closeout(files=[]))

    monkeypatch.setattr(core, "run_codex", fake_run_codex)
    with pytest.raises(core.AgentRunFailed, match="undeclared"):
        core.run_once(tmp_path)
    assert (tmp_path / "unexpected.txt").exists()
    assert list((tmp_path / ".a-exp" / "recovery").glob("*.json"))
    assert core.status_json(tmp_path)["health"] == "degraded"
    assert core.load_study_state(tmp_path / "projects" / "demo" / "STATE.yaml").state == "ready"


def test_agent_state_edit_is_unsafe_recovery(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    core.init_workspace(tmp_path)
    study = write_study(tmp_path, "demo")

    def fake_run_codex(**_: Any) -> CodexRunResult:
        (study / "STATE.yaml").write_text("agent-owned: false\n", encoding="utf-8")
        return result(successful_closeout(files=["projects/demo/STATE.yaml"]))

    monkeypatch.setattr(core, "run_codex", fake_run_codex)
    with pytest.raises(core.AgentRunFailed, match="STATE.yaml"):
        core.run_once(tmp_path)
    assert list((tmp_path / ".a-exp" / "recovery").glob("*.json"))


def test_agent_config_commit_is_detected_as_scheduler_owned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    core.init_workspace(tmp_path)
    write_study(tmp_path, "demo")

    def fake_run_codex(**_: Any) -> CodexRunResult:
        config_path = tmp_path / ".a-exp" / "config.yaml"
        config = load_config(config_path)
        config.projects["demo"] = ProjectConfig(sandbox="danger-full-access")
        dump_config(config, config_path)
        git(tmp_path, "add", ".a-exp/config.yaml")
        git(tmp_path, "commit", "-m", "Change scheduler policy")
        return result(successful_closeout(files=[]))

    monkeypatch.setattr(core, "run_codex", fake_run_codex)

    with pytest.raises(core.AgentRunFailed, match="scheduler-owned"):
        core.run_once(tmp_path)
    recovery = json.loads(next((tmp_path / ".a-exp" / "recovery").glob("*.json")).read_text())
    assert any(".a-exp/config.yaml" in error for error in recovery["errors"])
    assert core.status_json(tmp_path)["health"] == "degraded"


def test_closeout_oserror_creates_recovery_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    core.init_workspace(tmp_path)
    write_study(tmp_path, "demo")
    monkeypatch.setattr(
        core,
        "run_codex",
        lambda **_: result(successful_closeout(next_state="completed")),
    )
    original_atomic_write = core.atomic_write_text

    def fail_session_write(path: Path, content: str) -> None:
        if path.parent.name == "sessions":
            raise OSError("session storage unavailable")
        original_atomic_write(path, content)

    monkeypatch.setattr(core, "atomic_write_text", fail_session_write)

    with pytest.raises(core.AgentRunFailed, match="OSError"):
        core.run_once(tmp_path)
    recovery = json.loads(next((tmp_path / ".a-exp" / "recovery").glob("*.json")).read_text())
    assert any("session storage unavailable" in error for error in recovery["errors"])
    assert not list((tmp_path / ".a-exp" / "running").glob("*.json"))


def test_failure_closeout_oserror_falls_back_to_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    core.init_workspace(tmp_path)
    write_study(tmp_path, "demo")
    monkeypatch.setattr(
        core,
        "run_codex",
        lambda **_: result(None, returncode=2, thread_id=None, turn_started=False),
    )
    original_atomic_write = core.atomic_write_text

    def fail_failure_session(path: Path, content: str) -> None:
        if path.parent.name == "sessions":
            raise OSError("failure session storage unavailable")
        original_atomic_write(path, content)

    monkeypatch.setattr(core, "atomic_write_text", fail_failure_session)

    with pytest.raises(core.AgentRunFailed, match="failure closeout failed"):
        core.run_once(tmp_path)
    state = core.load_study_state(tmp_path / "projects" / "demo" / "STATE.yaml")
    assert state.state == "ready"
    assert state.consecutive_failures == 0
    recovery = json.loads(next((tmp_path / ".a-exp" / "recovery").glob("*.json")).read_text())
    assert any("failure session storage unavailable" in error for error in recovery["errors"])
    runtime = json.loads(next((tmp_path / ".a-exp" / "runs").glob("*.json")).read_text())
    assert runtime["next_state"] == "recovery_required"
    assert core.status_json(tmp_path)["health"] == "degraded"


def test_real_codex_smoke_refuses_nonempty_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "existing"
    workspace.mkdir()
    sentinel = workspace / "AGENTS.md"
    sentinel.write_text("preserve me\n", encoding="utf-8")
    script = Path(__file__).resolve().parents[1] / "scripts" / "smoke_real_codex.py"

    completed = subprocess.run(
        [sys.executable, str(script), "--workspace", str(workspace)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    assert "nonexistent or empty" in completed.stderr
    assert sentinel.read_text(encoding="utf-8") == "preserve me\n"
    assert not (workspace / ".git").exists()


def test_approvals_experiments_and_kanban(tmp_path: Path) -> None:
    core.init_workspace(tmp_path)
    study = write_study(tmp_path, "demo", state="needs_human")
    (tmp_path / "APPROVAL_QUEUE.md").write_text(
        "# Approval Queue\n\n## Pending\n\n- [ ] approve budget\n\n## Completed\n",
        encoding="utf-8",
    )
    experiment = study / "experiments" / "exp-a"
    experiment.mkdir(parents=True)
    (experiment / "EXPERIMENT.md").write_text(
        "---\nid: exp-a\nstatus: completed\ndate: 2026-08-01\n"
        "study: demo\nprotocol: test.v1\nproducer: autonomous\n---\n\n"
        "# exp-a\n\n## Findings\n\n- Faster and stable.\n",
        encoding="utf-8",
    )
    (experiment / "progress.json").write_text('{"status": "running"}\n', encoding="utf-8")
    session = study / "sessions" / "run.yaml"
    session.parent.mkdir()
    session.write_text(
        yaml.safe_dump(
            completed_session_data(
                "demo",
                "run",
                next_state="needs_human",
                summary="Compared methods",
                artifacts=["projects/demo/artifacts/plot.png"],
            )
        ),
        encoding="utf-8",
    )
    commit_all(tmp_path, "Record evidence")

    data = core.status_json(tmp_path)
    assert data["approvals"]["pending"] == 1
    assert data["experiments"]["running"] == 1
    assert generate_kanban(tmp_path) == [tmp_path / "reports" / "kanban" / "demo.md"]
    text = (tmp_path / "reports" / "kanban" / "demo.md").read_text(encoding="utf-8")
    assert "Lifecycle: **needs_human**" in text
    assert "Faster and stable" in text
    assert "projects/demo/artifacts/plot.png" in text


def test_fake_overnight_sequence_resumes_study_thread_without_overlap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    core.init_workspace(tmp_path)
    write_study(tmp_path, "alpha")
    write_study(tmp_path, "beta")
    config = load_config(tmp_path / ".a-exp" / "config.yaml")
    config.defaults["cooldown_seconds"] = 0
    config.projects["alpha"] = ProjectConfig(priority=1)
    config.projects["beta"] = ProjectConfig(priority=2)
    dump_config(config, tmp_path / ".a-exp" / "config.yaml")
    commit_all(tmp_path, "Configure overnight studies")
    calls: list[tuple[str, str | None]] = []
    beta_runs = 0

    def fake_run_codex(**kwargs: Any) -> CodexRunResult:
        nonlocal beta_runs
        markers = list((tmp_path / ".a-exp" / "running").glob("*.json"))
        assert len(markers) == 1
        study = kwargs["study"]
        calls.append((study, kwargs["thread_id"]))
        if study == "alpha":
            return result(
                successful_closeout(next_state="needs_human", experiments=["alpha-1", "alpha-2"]),
                thread_id="thread-alpha",
            )
        beta_runs += 1
        next_state = "ready" if beta_runs == 1 else "completed"
        return result(
            successful_closeout(next_state=next_state, experiments=[f"beta-{beta_runs}"]),
            thread_id="thread-beta",
        )

    monkeypatch.setattr(core, "run_codex", fake_run_codex)
    first = core.run_once(tmp_path)
    second = core.run_once(tmp_path)
    third = core.run_once(tmp_path)

    assert first["next_state"] == "needs_human"
    assert second["next_state"] == "ready"
    assert third["next_state"] == "completed"
    assert calls == [
        ("alpha", None),
        ("beta", None),
        ("beta", "thread-beta"),
    ]
    assert core.load_study_state(tmp_path / "projects" / "alpha" / "STATE.yaml").state == (
        "needs_human"
    )
    assert core.load_study_state(tmp_path / "projects" / "beta" / "STATE.yaml").state == (
        "completed"
    )
    assert len(list((tmp_path / "projects" / "beta" / "sessions").glob("*.yaml"))) == 2
    assert list((tmp_path / ".a-exp" / "running").glob("*.json")) == []


def test_revision_zero_is_shaping_only_and_context_is_mandatory(tmp_path: Path) -> None:
    core.init_workspace(tmp_path)
    study = write_study(tmp_path, "shape", state="shaping")
    studies, issues = core.discover_studies(tmp_path)
    assert issues == []
    assert studies[0].context_data.revision == 0

    (study / "CONTEXT.yaml").unlink()
    commit_all(tmp_path, "Remove mandatory context")
    assert core.status_json(tmp_path)["studies"]["invalid"] == 1
    assert any("CONTEXT.yaml" in issue for issue in core.discover_studies(tmp_path)[1])


def test_direct_ready_transition_at_revision_zero_is_rejected(tmp_path: Path) -> None:
    core.init_workspace(tmp_path)
    study = write_study(tmp_path, "demo", state="shaping")
    state = core.load_study_state(study / "STATE.yaml")
    core.write_study_state(study / "STATE.yaml", replace(state, state="ready"))
    commit_all(tmp_path, "Unsupported direct ready transition")

    data = core.status_json(tmp_path)
    assert data["studies"]["invalid"] == 1
    assert any("revision 0" in warning for warning in data["warnings"])


def test_continuation_and_major_change_transition_invariants(tmp_path: Path) -> None:
    core.init_workspace(tmp_path)
    continuation = write_study(tmp_path, "continue")
    append_handoff(
        tmp_path,
        continuation,
        change_class="continuation",
        thread_policy="resume",
    )
    commit_all(tmp_path, "Continue unchanged goal")
    studies, issues = core.discover_studies(tmp_path)
    assert issues == []
    assert studies[0].context_data.revision == 2

    major = write_study(tmp_path, "major", commit=False)
    (major / "GOAL.md").write_text("# Goal\n\nA substantially revised objective.\n", encoding="utf-8")
    append_handoff(
        tmp_path,
        major,
        change_class="major_change",
        thread_policy="replace",
        superseded_assumptions=["The original objective still controls the study"],
    )
    commit_all(tmp_path, "Replace changed goal")
    studies, issues = core.discover_studies(tmp_path)
    assert issues == []
    assert {study.handoff_data.change_class for study in studies} == {
        "continuation",
        "major_change",
    }


@pytest.mark.parametrize(
    ("change_class", "thread_policy", "change_goal", "superseded", "message"),
    [
        ("continuation", "resume", True, [], "unchanged GOAL.md hash"),
        ("continuation", "replace", False, [], "resume policy"),
        ("major_change", "replace", False, ["old"], "changed GOAL.md hash"),
        ("major_change", "replace", True, [], "superseded_assumptions"),
    ],
)
def test_invalid_handoff_transition_is_rejected(
    tmp_path: Path,
    change_class: str,
    thread_policy: str,
    change_goal: bool,
    superseded: list[str],
    message: str,
) -> None:
    core.init_workspace(tmp_path)
    study = write_study(tmp_path, "demo")
    if change_goal:
        (study / "GOAL.md").write_text("# Goal\n\nChanged bytes.\n", encoding="utf-8")
    append_handoff(
        tmp_path,
        study,
        change_class=change_class,
        thread_policy=thread_policy,
        superseded_assumptions=superseded,
    )
    commit_all(tmp_path, "Write invalid transition")

    _, issues = core.discover_studies(tmp_path)
    assert any(message in issue for issue in issues)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("unsafe_path", "repo-relative"),
        ("secret", "secret"),
        ("transcript", "transcripts"),
        ("oversize", "exceeds"),
    ],
)
def test_handoff_safety_limits(tmp_path: Path, mutation: str, message: str) -> None:
    core.init_workspace(tmp_path)
    study = write_study(tmp_path, "demo")
    path = study / "handoffs" / "r0001-initial.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if mutation == "unsafe_path":
        data["relevant_paths"] = ["../outside"]
    elif mutation == "secret":
        data["summary"] = "api_key: super-secret-value"
    elif mutation == "transcript":
        data["summary"] = "transcript: copied conversation"
    else:
        data["summary"] = "x" * (core.MAX_HANDOFF_BYTES + 1)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    commit_all(tmp_path, f"Write {mutation} handoff")

    _, issues = core.discover_studies(tmp_path)
    assert any(message in issue for issue in issues)


def test_handoff_writer_is_append_only(tmp_path: Path) -> None:
    core.init_workspace(tmp_path)
    study = write_study(tmp_path, "demo")
    latest, _ = core.load_handoff_chain(
        tmp_path,
        study,
        core.load_study_context(study / "CONTEXT.yaml"),
    )
    assert latest is not None
    new = replace(
        latest,
        handoff_id="r0002-writer",
        context_revision=2,
        previous_handoff=latest.handoff_id,
        path="projects/demo/handoffs/r0002-writer.yaml",
    )
    written = core.write_handoff_record(tmp_path, study, new)
    assert written.is_file()
    with pytest.raises(core.WorkspaceError, match="append-only"):
        core.write_handoff_record(tmp_path, study, new)


def test_interactive_evidence_is_referenced_and_producer_checked(tmp_path: Path) -> None:
    core.init_workspace(tmp_path)
    study = write_study(tmp_path, "demo")
    experiment_ids = ["positive", "negative", "failed"]
    for experiment_id in experiment_ids:
        directory = study / "experiments" / experiment_id
        directory.mkdir(parents=True)
        (directory / "EXPERIMENT.md").write_text(
            "---\n"
            f"id: {experiment_id}\n"
            f"status: {'failed' if experiment_id == 'failed' else 'completed'}\n"
            "date: 2026-08-02\n"
            "study: demo\n"
            "protocol: test.v1\n"
            "producer: interactive\n"
            "---\n\n"
            f"# {experiment_id}\n\n"
            "## Execution\n\nCommand, configuration, revision, and GPU recorded.\n\n"
            "## Results\n\nMetrics and artifact paths recorded.\n\n"
            "## Findings\n\nNegative and failed evidence is retained.\n\n"
            "## Caveats\n\nKnown limits.\n\n"
            "## Verification\n\nChecked output.\n",
            encoding="utf-8",
        )
    append_handoff(
        tmp_path,
        study,
        change_class="continuation",
        thread_policy="resume",
        interactive_experiments=experiment_ids,
        artifacts=["projects/demo/experiments/negative/metrics.json"],
    )
    commit_all(tmp_path, "Record material interactive evidence")
    studies, issues = core.discover_studies(tmp_path)
    assert issues == []
    assert studies[0].handoff_data.interactive_experiments == experiment_ids
    assert not (study / "sessions").exists()

    failed_record = study / "experiments" / "failed" / "EXPERIMENT.md"
    failed_record.write_text(
        failed_record.read_text(encoding="utf-8").replace(
            "producer: interactive", "producer: autonomous"
        ),
        encoding="utf-8",
    )
    commit_all(tmp_path, "Misclassify interactive evidence")
    assert any("producer: interactive" in issue for issue in core.discover_studies(tmp_path)[1])


def test_legacy_session_schema_is_rejected(tmp_path: Path) -> None:
    core.init_workspace(tmp_path)
    study = write_study(tmp_path, "demo", state="needs_human")
    sessions = study / "sessions"
    sessions.mkdir()
    (sessions / "old.yaml").write_text(
        "schema_version: 1\nrun_id: old\nstudy: demo\nstatus: completed\n",
        encoding="utf-8",
    )
    commit_all(tmp_path, "Add legacy session")

    _, issues = core.discover_studies(tmp_path)
    assert any("schema_version must be 2" in issue for issue in issues)


def test_context_consumption_uses_only_committed_sessions(tmp_path: Path) -> None:
    core.init_workspace(tmp_path)
    study = write_study(tmp_path, "demo")
    sessions = study / "sessions"
    sessions.mkdir()
    record = completed_session_data("demo", "manual")
    (sessions / "manual.yaml").write_text(
        yaml.safe_dump(record, sort_keys=False), encoding="utf-8"
    )

    item = core.status_json(tmp_path)["studies"]["items"][0]
    assert item["consumed_context_revision"] == 0
    assert item["context_pending"] is True

    commit_all(tmp_path, "Commit completed session")
    item = core.status_json(tmp_path)["studies"]["items"][0]
    assert item["consumed_context_revision"] == 1
    assert item["context_pending"] is False


def test_stale_ready_requires_a_new_context_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    core.init_workspace(tmp_path)
    study = write_study(tmp_path, "demo")
    monkeypatch.setattr(
        core,
        "run_codex",
        lambda **_: result(successful_closeout(next_state="completed"), thread_id="thread-1"),
    )
    core.run_once(tmp_path)
    completed_state = core.load_study_state(study / "STATE.yaml")
    core.write_study_state(study / "STATE.yaml", replace(completed_state, state="ready"))
    commit_all(tmp_path, "Unsupported stale reactivation")
    assert any("stale interactive ready transition" in issue for issue in core.discover_studies(tmp_path)[1])

    append_handoff(
        tmp_path,
        study,
        change_class="continuation",
        thread_policy="resume",
    )
    commit_all(tmp_path, "Advance context for reactivation")
    studies, issues = core.discover_studies(tmp_path)
    assert issues == []
    assert studies[0].context_data.revision == 2


def test_continuation_resumes_and_advances_thread_mapping(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    core.init_workspace(tmp_path)
    study = write_study(tmp_path, "demo")
    core.write_thread_record(tmp_path, "demo", "thread-old", "old-run", 1)
    append_handoff(
        tmp_path,
        study,
        change_class="continuation",
        thread_policy="resume",
    )
    commit_all(tmp_path, "Continue to revision 2")
    calls: list[str | None] = []

    def fake_run_codex(**kwargs: Any) -> CodexRunResult:
        calls.append(kwargs["thread_id"])
        return result(successful_closeout(next_state="completed"), thread_id="thread-old")

    monkeypatch.setattr(core, "run_codex", fake_run_codex)
    record = core.run_once(tmp_path)
    assert calls == ["thread-old"]
    assert record["requested_thread_policy"] == "resume"
    assert record["applied_thread_action"] == "resume"
    assert core.read_thread_record(tmp_path, "demo")["context_revision"] == 2


def test_major_replacement_is_not_repeated_after_failed_closeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    core.init_workspace(tmp_path)
    study = write_study(tmp_path, "demo")
    core.write_thread_record(tmp_path, "demo", "thread-old", "old-run", 1)
    (study / "GOAL.md").write_text("# Goal\n\nReplacement objective.\n", encoding="utf-8")
    append_handoff(
        tmp_path,
        study,
        change_class="major_change",
        thread_policy="replace",
        superseded_assumptions=["Original objective controls the work"],
    )
    commit_all(tmp_path, "Major change revision 2")
    calls: list[str | None] = []

    def fake_run_codex(**kwargs: Any) -> CodexRunResult:
        calls.append(kwargs["thread_id"])
        if len(calls) == 1:
            return result(None, returncode=1, thread_id="thread-new", turn_started=True)
        return result(successful_closeout(next_state="completed"), thread_id="thread-new")

    monkeypatch.setattr(core, "run_codex", fake_run_codex)
    with pytest.raises(core.AgentRunFailed):
        core.run_once(tmp_path)
    mapping = core.read_thread_record(tmp_path, "demo")
    assert mapping["thread_id"] == "thread-new"
    assert mapping["context_revision"] == 2
    failed_state = core.load_study_state(study / "STATE.yaml")
    core.write_study_state(study / "STATE.yaml", replace(failed_state, ready_after=None))
    commit_all(tmp_path, "Make replacement retry due")

    completed = core.run_once(tmp_path)
    assert calls == [None, "thread-new"]
    assert completed["requested_thread_policy"] == "replace"
    assert completed["applied_thread_action"] == "resume"
    sessions = core.session_records(tmp_path, "demo")
    assert sessions[0]["applied_thread_action"] == "replace"
    assert sessions[0]["context_consumed"] is False
    assert sessions[0]["replaced_thread_id"] == "thread-old"
    assert sessions[1]["context_consumed"] is True
    status = core.status_json(tmp_path)["studies"]["items"][0]
    assert status["context_pending"] is False
    assert status["superseded_thread_id"] == "thread-old"


def test_replacement_retries_when_no_new_thread_started(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    core.init_workspace(tmp_path)
    study = write_study(tmp_path, "demo")
    core.write_thread_record(tmp_path, "demo", "thread-old", "old-run", 1)
    (study / "GOAL.md").write_text("# Goal\n\nReplacement objective.\n", encoding="utf-8")
    append_handoff(
        tmp_path,
        study,
        change_class="major_change",
        thread_policy="replace",
        superseded_assumptions=["Original objective controls the work"],
    )
    commit_all(tmp_path, "Major change revision 2")
    calls: list[str | None] = []

    def fake_run_codex(**kwargs: Any) -> CodexRunResult:
        calls.append(kwargs["thread_id"])
        if len(calls) == 1:
            return result(None, returncode=1, thread_id=None, turn_started=False)
        return result(successful_closeout(next_state="completed"), thread_id="thread-new")

    monkeypatch.setattr(core, "run_codex", fake_run_codex)
    with pytest.raises(core.AgentRunFailed):
        core.run_once(tmp_path)
    assert core.read_thread_record(tmp_path, "demo")["thread_id"] == "thread-old"
    assert core.read_thread_record(tmp_path, "demo")["context_revision"] == 1
    failed_state = core.load_study_state(study / "STATE.yaml")
    core.write_study_state(study / "STATE.yaml", replace(failed_state, ready_after=None))
    commit_all(tmp_path, "Make replacement retry due")

    completed = core.run_once(tmp_path)
    assert calls == [None, None]
    assert completed["applied_thread_action"] == "replace"
    assert completed["replaced_thread_id"] == "thread-old"
    assert core.read_thread_record(tmp_path, "demo")["thread_id"] == "thread-new"


@pytest.mark.parametrize(
    "relative_path",
    [
        "projects/demo/GOAL.md",
        "projects/demo/STEERING.md",
        "projects/demo/CONTEXT.yaml",
        "projects/demo/handoffs/agent.yaml",
    ],
)
def test_autonomous_control_file_edits_are_forbidden(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    relative_path: str,
) -> None:
    core.init_workspace(tmp_path)
    write_study(tmp_path, "demo")

    def fake_run_codex(**_: Any) -> CodexRunResult:
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("agent edit\n", encoding="utf-8")
        return result(successful_closeout(files=[relative_path]))

    monkeypatch.setattr(core, "run_codex", fake_run_codex)
    with pytest.raises(core.AgentRunFailed, match="scheduler-owned"):
        core.run_once(tmp_path)


@pytest.mark.parametrize("producer", ["interactive", "missing"])
def test_autonomous_experiment_requires_autonomous_producer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    producer: str,
) -> None:
    core.init_workspace(tmp_path)
    study = write_study(tmp_path, "demo")

    def fake_run_codex(**_: Any) -> CodexRunResult:
        record = study / "experiments" / "gpu-exp" / "EXPERIMENT.md"
        record.parent.mkdir(parents=True)
        producer_line = "" if producer == "missing" else f"producer: {producer}\n"
        record.write_text(
            "---\nid: gpu-exp\nstatus: completed\ndate: 2026-08-02\n"
            f"study: demo\nprotocol: test.v1\n{producer_line}---\n\n# GPU experiment\n",
            encoding="utf-8",
        )
        return result(
            successful_closeout(
                files=["projects/demo/experiments/gpu-exp/EXPERIMENT.md"],
                experiments=["gpu-exp"],
            )
        )

    monkeypatch.setattr(core, "run_codex", fake_run_codex)
    with pytest.raises(core.AgentRunFailed, match="producer"):
        core.run_once(tmp_path)


def test_autonomous_experiment_accepts_autonomous_producer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    core.init_workspace(tmp_path)
    study = write_study(tmp_path, "demo")

    def fake_run_codex(**_: Any) -> CodexRunResult:
        record = study / "experiments" / "gpu-exp" / "EXPERIMENT.md"
        record.parent.mkdir(parents=True)
        record.write_text(
            "---\nid: gpu-exp\nstatus: completed\ndate: 2026-08-02\n"
            "study: demo\nprotocol: test.v1\nproducer: autonomous\n---\n\n"
            "# GPU experiment\n",
            encoding="utf-8",
        )
        return result(
            successful_closeout(
                next_state="completed",
                files=["projects/demo/experiments/gpu-exp/EXPERIMENT.md"],
                experiments=["gpu-exp"],
            )
        )

    monkeypatch.setattr(core, "run_codex", fake_run_codex)
    completed = core.run_once(tmp_path)
    assert completed["next_state"] == "completed"
    assert core.status_json(tmp_path)["health"] == "ok"


def test_packaged_handoff_skills_have_ui_invocation_policy(tmp_path: Path) -> None:
    core.init_workspace(tmp_path)
    skills = tmp_path / ".agents" / "skills"
    expected = {
        "reconcile": True,
        "handoff-continue": False,
        "handoff-change": False,
    }
    for name, implicit in expected.items():
        skill_text = (skills / name / "SKILL.md").read_text(encoding="utf-8")
        metadata = yaml.safe_load(
            (skills / name / "agents" / "openai.yaml").read_text(encoding="utf-8")
        )
        assert metadata["policy"]["allow_implicit_invocation"] is implicit
        assert f"${name}" in metadata["interface"]["default_prompt"]
        assert "docs/schemas/context-handoff.md" in skill_text
