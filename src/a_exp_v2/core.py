from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from importlib import resources
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

import yaml

from .config import (
    DEFAULT_APPROVAL_POLICY,
    DEFAULT_COOLDOWN_SECONDS,
    DEFAULT_MAX_RUN_DURATION_MS,
    DEFAULT_MODEL,
    DEFAULT_PRIORITY,
    DEFAULT_RETRY_BACKOFF_SECONDS,
    DEFAULT_SANDBOX,
    LAYOUT_VERSION,
    ProjectConfig,
    WorkspaceConfig,
    dump_config,
    load_config,
    validate_project_id,
)
from .runner import CodexRunResult, run_codex, summarize_events


CONFIG_PATH = Path(".a-exp/config.yaml")
RUNS_DIR = Path(".a-exp/runs")
LOGS_DIR = Path(".a-exp/logs")
RUNNING_DIR = Path(".a-exp/running")
THREADS_DIR = Path(".a-exp/threads")
OUTPUT_DIR = Path(".a-exp/output")
RECOVERY_DIR = Path(".a-exp/recovery")
LOCK_PATH = Path(".a-exp/workspace.lock")

DURABLE_STATES = {
    "shaping",
    "ready",
    "needs_human",
    "paused",
    "blocked",
    "failed",
    "completed",
}
EFFECTIVE_STATES = DURABLE_STATES | {"running", "disabled", "ineligible", "invalid"}
AGENT_NEXT_STATES = {"ready", "needs_human", "paused", "blocked", "completed"}
OUTCOME_NEXT_STATE = {
    "progress": "ready",
    "needs_human": "needs_human",
    "paused": "paused",
    "blocked": "blocked",
    "completed": "completed",
}
ACTIVE_EXPERIMENT_STATUSES = {"running", "retrying", "stopping"}
STATE_KEYS = {
    "schema_version",
    "state",
    "ready_after",
    "summary",
    "next_direction",
    "open_questions",
    "requires",
    "last_run_id",
    "consecutive_failures",
}


class AExpError(Exception):
    exit_code = 1


class WorkspaceError(AExpError):
    exit_code = 2


class AgentRunFailed(AExpError):
    exit_code = 1


@dataclass(frozen=True)
class StudyState:
    state: str
    ready_after: str | None
    summary: str
    next_direction: str | None
    open_questions: list[str]
    requires: list[str]
    last_run_id: str | None
    consecutive_failures: int
    schema_version: int = 1


@dataclass(frozen=True)
class Study:
    project: str
    path: Path
    state_data: StudyState
    enabled: bool
    priority: int
    model: str | None
    max_run_duration_ms: int
    cooldown_seconds: int
    retry_backoff_seconds: int
    sandbox: str
    approval_policy: str
    eligible: bool
    ineligible_reason: str | None
    valid: bool = True
    invalid_reason: str | None = None
    active_run_id: str | None = None

    @property
    def effective_state(self) -> str:
        if not self.valid:
            return "invalid"
        if not self.enabled:
            return "disabled"
        if self.active_run_id:
            return "running"
        if not self.eligible:
            return "ineligible"
        return self.state_data.state

    @property
    def ready_due(self) -> bool:
        return self.effective_state == "ready" and timestamp_due(self.state_data.ready_after)


def utc_now_dt() -> datetime:
    return datetime.now(timezone.utc)


def utc_now() -> str:
    return utc_now_dt().isoformat().replace("+00:00", "Z")


def timestamp_due(value: str | None, *, now: datetime | None = None) -> bool:
    if value is None:
        return True
    parsed = parse_timestamp(value)
    if parsed is None:
        return False
    return parsed <= (now or utc_now_dt())


def parse_timestamp(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def future_timestamp(seconds: int) -> str:
    return (utc_now_dt() + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


def find_workspace(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for path in [current, *current.parents]:
        if (path / CONFIG_PATH).exists():
            return path
    raise WorkspaceError("No a-exp-v2 workspace found. Run `a-exp-v2 init` first.")


def init_workspace(root: Path) -> list[Path]:
    created: list[Path] = []
    root.mkdir(parents=True, exist_ok=True)
    git_dir = init_git_repo_if_needed(root)
    if git_dir is not None:
        created.append(git_dir)
    for relative in (
        ".a-exp/runs",
        ".a-exp/logs",
        ".a-exp/running",
        ".a-exp/threads",
        ".a-exp/output",
        ".a-exp/recovery",
        ".agents",
        "projects",
        "modules",
        "reports/kanban",
        "reports/packet",
        "reports/project",
        "reports/research",
    ):
        path = root / relative
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            created.append(path)

    files = {
        root / CONFIG_PATH: default_config_text(),
        root / ".a-exp/kit.lock.yaml": "source: local\nversion: 0.2.0\n",
        root / ".gitignore": default_gitignore_text(),
        root / "AGENTS.md": default_agents_text(),
        root / "modules/registry.yaml": "entries: []\n",
        root / "APPROVAL_QUEUE.md": default_approval_queue(),
    }
    for path, content in files.items():
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            created.append(path)
    created.extend(materialize_package_tree(root, "skill_templates/skills", ".agents/skills"))
    created.extend(materialize_package_tree(root, "doc_templates", "docs"))
    created.extend(materialize_package_tree(root, "protocol_templates/protocols", "protocols"))
    commit_created_workspace_files(root, created)
    return created


def init_git_repo_if_needed(root: Path) -> Path | None:
    try:
        status = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise WorkspaceError("Git is required to initialize an a-exp-v2 workspace.") from exc
    if status.returncode == 0 and Path(status.stdout.strip()).resolve() == root.resolve():
        return None
    result = subprocess.run(
        ["git", "-C", str(root), "init"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "git init failed"
        raise WorkspaceError(detail)
    git_dir = root / ".git"
    return git_dir if git_dir.exists() else None


def git_commit_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("GIT_AUTHOR_NAME", "a-exp-v2")
    env.setdefault("GIT_AUTHOR_EMAIL", "a-exp-v2@example.local")
    env.setdefault("GIT_COMMITTER_NAME", "a-exp-v2")
    env.setdefault("GIT_COMMITTER_EMAIL", "a-exp-v2@example.local")
    return env


def commit_created_workspace_files(root: Path, created: list[Path]) -> None:
    paths = sorted(
        {
            str(path.relative_to(root))
            for path in created
            if path.exists() and (path.is_symlink() or not path.is_dir()) and path.name != ".git"
        }
    )
    if paths:
        commit_workspace_changes(root, "Initialize a-exp-v2 workspace", paths)


def commit_workspace_changes(root: Path, message: str, paths: list[str | Path]) -> str | None:
    normalized = sorted({safe_repo_path(root, path) for path in paths})
    if not normalized:
        return None
    unexpected_staged = sorted(set(git_staged_paths(root)) - set(normalized))
    if unexpected_staged:
        raise WorkspaceError(
            "Refusing to commit unrelated staged path(s): " + ", ".join(unexpected_staged)
        )
    add = subprocess.run(
        ["git", "-C", str(root), "add", "-A", "--", *normalized],
        capture_output=True,
        text=True,
        check=False,
    )
    if add.returncode != 0:
        detail = add.stderr.strip() or add.stdout.strip() or "git add failed"
        raise WorkspaceError(detail)
    unexpected_staged = sorted(set(git_staged_paths(root)) - set(normalized))
    if unexpected_staged:
        raise WorkspaceError(
            "Refusing to commit unrelated staged path(s): " + ", ".join(unexpected_staged)
        )
    diff = subprocess.run(
        ["git", "-C", str(root), "diff", "--cached", "--quiet", "--exit-code"],
        capture_output=True,
        text=True,
        check=False,
    )
    if diff.returncode == 0:
        return None
    if diff.returncode != 1:
        detail = diff.stderr.strip() or diff.stdout.strip() or "git diff --cached failed"
        raise WorkspaceError(detail)
    commit = subprocess.run(
        ["git", "-C", str(root), "-c", "commit.gpgsign=false", "commit", "-m", message],
        capture_output=True,
        text=True,
        check=False,
        env=git_commit_env(),
    )
    if commit.returncode != 0:
        detail = commit.stderr.strip() or commit.stdout.strip() or "git commit failed"
        raise WorkspaceError(detail)
    return git_head(root)


def git_staged_paths(root: Path) -> list[str]:
    result = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "diff",
            "--cached",
            "--name-only",
            "--no-renames",
            "-z",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise WorkspaceError(result.stderr.strip() or "git staged-path inspection failed")
    return sorted({value for value in result.stdout.split("\0") if value})


def git_head(root: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise WorkspaceError(result.stderr.strip() or "unable to resolve Git HEAD")
    return result.stdout.strip()


def git_status_paths(root: Path) -> list[str]:
    result = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--no-renames",
            "-z",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise WorkspaceError(result.stderr.strip() or "git status failed")
    paths: list[str] = []
    for entry in result.stdout.split("\0"):
        if entry:
            paths.append(entry[3:] if len(entry) >= 4 else entry)
    return sorted(set(paths))


def git_clean(root: Path) -> bool:
    return not git_status_paths(root)


def git_changed_paths_since(root: Path, base_commit: str) -> list[str]:
    result = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "diff",
            "--name-only",
            "--no-renames",
            "-z",
            f"{base_commit}..HEAD",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise WorkspaceError(result.stderr.strip() or "git diff failed")
    return sorted(
        {value for value in result.stdout.split("\0") if value}
        | set(git_status_paths(root))
    )


def git_commits_since(root: Path, base_commit: str) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(root), "rev-list", "--reverse", f"{base_commit}..HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    return [line for line in result.stdout.splitlines() if line]


def safe_repo_path(root: Path, value: str | Path) -> str:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise WorkspaceError(f"path must be repo-relative and stay inside the workspace: {value}")
    normalized = path.as_posix()
    resolved = (root / path).resolve(strict=False)
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise WorkspaceError(f"path escapes workspace: {value}") from exc
    return normalized


def materialize_package_tree(root: Path, package_subdir: str, destination: str) -> list[Path]:
    linked = symlink_package_tree(root, package_subdir, destination)
    if linked is not None:
        return [linked]
    return copy_package_tree(root, package_subdir, destination)


def symlink_package_tree(root: Path, package_subdir: str, destination: str) -> Path | None:
    source = package_resource_path(package_subdir)
    dest = root / destination
    if source is None or os.path.lexists(dest):
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    target = relative_symlink_target(dest.parent, source)
    if target is None:
        return None
    try:
        dest.symlink_to(target, target_is_directory=True)
    except OSError:
        return None
    return dest


def package_resource_path(package_subdir: str) -> Path | None:
    source = resources.files("a_exp_v2").joinpath(package_subdir)
    if not isinstance(source, Path):
        return None
    path = source.resolve()
    return path if path.is_dir() else None


def relative_symlink_target(dest_parent: Path, source: Path) -> str | None:
    target = os.path.relpath(source.resolve(), dest_parent.resolve())
    target_path = Path(target)
    if target_path.is_absolute() or path_mentions_home_user(target_path):
        return None
    return target


def path_mentions_home_user(path: Path) -> bool:
    home_user = Path.home().name
    return bool(home_user and home_user in path.parts)


def copy_package_tree(root: Path, package_subdir: str, destination: str) -> list[Path]:
    created: list[Path] = []
    source = resources.files("a_exp_v2").joinpath(package_subdir)
    dest_root = root / destination

    def copy_dir(current: Any, rel_parts: tuple[str, ...] = ()) -> None:
        for item in current.iterdir():
            if item.name == "__pycache__" or item.name.endswith(".pyc"):
                continue
            next_parts = (*rel_parts, item.name)
            if item.is_dir():
                copy_dir(item, next_parts)
            elif item.is_file():
                dest = dest_root.joinpath(*next_parts)
                if not dest.exists():
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(item.read_bytes())
                    created.append(dest)

    copy_dir(source)
    return created


def default_config_text() -> str:
    data = {
        "layout_version": LAYOUT_VERSION,
        "defaults": {
            "model": DEFAULT_MODEL,
            "max_run_duration_ms": DEFAULT_MAX_RUN_DURATION_MS,
            "cooldown_seconds": DEFAULT_COOLDOWN_SECONDS,
            "retry_backoff_seconds": DEFAULT_RETRY_BACKOFF_SECONDS,
            "sandbox": DEFAULT_SANDBOX,
            "approval_policy": DEFAULT_APPROVAL_POLICY,
        },
        "projects": {},
    }
    return yaml.safe_dump(data, sort_keys=False)


def default_gitignore_text() -> str:
    return """.DS_Store
.env
.env.local
__pycache__/
*.pyc
.a-exp/*
!.a-exp/
!.a-exp/config.yaml
!.a-exp/kit.lock.yaml
reports/*.tmp
**/artifacts/**/*.zip
**/artifacts/**/*.npz
**/artifacts/**/*.parquet
"""


def default_agents_text() -> str:
    return """# AGENTS.md

This repository is an a-exp-v2 study workspace.

## Fast Orientation

- `.a-exp/config.yaml`: study scheduling and Codex run defaults.
- `.a-exp/runs/`, `.a-exp/logs/`, `.a-exp/running/`, and `.a-exp/threads/`:
  ignored machine-local runtime state.
- `.agents/skills/`: reusable study workflows.
- `protocols/`: experiment playbooks and validation checklists.
- `projects/<study>/README.md`: environment and orientation.
- `projects/<study>/GOAL.md`: objective, evidence, autonomy, and stop criteria.
- `projects/<study>/STATE.yaml`: scheduler-owned durable lifecycle state.
- `projects/<study>/PLAN.md` and `DECISIONS.md`: evolving strategy and decisions.
- `projects/<study>/experiments/`: experiment manifests, progress, results, and findings.
- `projects/<study>/sessions/`: committed autonomous-run closeouts.
- `APPROVAL_QUEUE.md`: durable requests that need human approval.

## Work Cycle

External schedulers call `a-exp run-once`. The command selects one ready study
and starts or resumes one bounded Codex turn. Use the workflow skill, advance the
study goal within its autonomy envelope, run foreground experiments as needed,
commit each material checkpoint, and finish with the required structured
closeout. Do not edit `STATE.yaml` during an autonomous run; a-exp owns the
state transition after validating closeout.

Interactive shaping may update and commit project files directly. Set
`state: ready` in `STATE.yaml` only when the study is ready for autonomous work.

For experiment-heavy work, check `protocols/registry.yaml`, follow any matching
playbook and checklist, and record the protocol id in experiment memory.

## Git Rule

Commit every material experiment or coherent code change. Leave the workspace
clean after interactive shaping and after every successful autonomous run.
"""


def default_approval_queue() -> str:
    return "# Approval Queue\n\n## Pending\n\n## Completed\n"


def load_workspace_config(root: Path) -> WorkspaceConfig:
    try:
        return load_config(root / CONFIG_PATH)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        raise WorkspaceError(f"Invalid {CONFIG_PATH}: {exc}") from exc


def load_study_state(path: Path) -> StudyState:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(str(exc)) from exc
    if not isinstance(raw, dict):
        raise ValueError("STATE.yaml root must be an object")
    unknown = sorted(set(raw) - STATE_KEYS)
    if unknown:
        raise ValueError(f"unknown field(s): {', '.join(unknown)}")
    if raw.get("schema_version") != 1:
        raise ValueError("schema_version must be 1")
    state = raw.get("state")
    if state not in DURABLE_STATES:
        raise ValueError(f"state must be one of: {', '.join(sorted(DURABLE_STATES))}")
    ready_after = raw.get("ready_after")
    if ready_after is not None:
        if isinstance(ready_after, datetime):
            if ready_after.tzinfo is None:
                ready_after = ready_after.replace(tzinfo=timezone.utc)
            ready_after = ready_after.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        if not isinstance(ready_after, str) or not ready_after.strip():
            raise ValueError("ready_after must be an ISO timestamp or null")
        if not timestamp_due(ready_after, now=datetime.max.replace(tzinfo=timezone.utc)):
            raise ValueError("ready_after must be an ISO timestamp or null")
    summary = raw.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise ValueError("summary must be a non-empty string")
    next_direction = raw.get("next_direction")
    if next_direction is not None and not isinstance(next_direction, str):
        raise ValueError("next_direction must be a string or null")
    open_questions = string_list(raw.get("open_questions"), "open_questions")
    requires = string_list(raw.get("requires"), "requires")
    last_run_id = raw.get("last_run_id")
    if last_run_id is not None and not isinstance(last_run_id, str):
        raise ValueError("last_run_id must be a string or null")
    failures = raw.get("consecutive_failures")
    if isinstance(failures, bool) or not isinstance(failures, int) or failures < 0:
        raise ValueError("consecutive_failures must be a non-negative integer")
    return StudyState(
        state=state,
        ready_after=ready_after,
        summary=summary.strip(),
        next_direction=next_direction,
        open_questions=open_questions,
        requires=requires,
        last_run_id=last_run_id,
        consecutive_failures=failures,
    )


def string_list(value: Any, field_name: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"{field_name} must be a list of non-empty strings")
    return [item.strip() for item in value]


def write_study_state(path: Path, state: StudyState) -> None:
    data = {
        "schema_version": 1,
        "state": state.state,
        "ready_after": state.ready_after,
        "summary": state.summary,
        "next_direction": state.next_direction,
        "open_questions": state.open_questions,
        "requires": state.requires,
        "last_run_id": state.last_run_id,
        "consecutive_failures": state.consecutive_failures,
    }
    atomic_write_text(path, yaml.safe_dump(data, sort_keys=False))


def load_host_capabilities() -> set[str]:
    capabilities = {"cpu"}
    if sys.platform.startswith("linux"):
        capabilities.add("linux")
    elif sys.platform == "darwin":
        capabilities.add("macos")
    else:
        capabilities.add(sys.platform)
    configured = os.environ.get("A_EXP_HOST_CONFIG")
    path = Path(configured).expanduser() if configured else Path.home() / ".config/a-exp/host.yaml"
    if not path.exists():
        return capabilities
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise WorkspaceError(f"Invalid host config {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise WorkspaceError(f"Invalid host config {path}: root must be an object")
    try:
        capabilities.update(string_list(raw.get("capabilities", []), "capabilities"))
    except ValueError as exc:
        raise WorkspaceError(f"Invalid host config {path}: {exc}") from exc
    return capabilities


def project_value(config: WorkspaceConfig, project: ProjectConfig, key: str, default: Any) -> Any:
    value = getattr(project, key)
    if value is not None:
        return value
    return config.defaults.get(key, default)


def contained_path(root: Path, path: Path, description: str) -> Path:
    workspace = root.resolve()
    resolved = path.resolve(strict=False)
    try:
        resolved.relative_to(workspace)
    except ValueError as exc:
        raise WorkspaceError(f"{description} escapes workspace: {path}") from exc
    return path


def study_path(root: Path, project: str) -> Path:
    try:
        name = validate_project_id(project)
    except ValueError as exc:
        raise WorkspaceError(f"Invalid study ID {project!r}: {exc}") from exc
    projects_root = contained_path(root, root / "projects", "projects directory")
    path = projects_root / name
    contained_path(root, path, f"study {name!r}")
    return path


def discover_studies(root: Path) -> tuple[list[Study], list[str]]:
    config = load_workspace_config(root)
    active, marker_issues = reconcile_running_markers(root)
    capabilities = load_host_capabilities()
    projects_root = root / "projects"
    try:
        contained_path(root, projects_root, "projects directory")
    except WorkspaceError as exc:
        return [], sorted({*marker_issues, str(exc)})
    names = set(config.projects)
    if projects_root.is_dir():
        names.update(path.name for path in projects_root.iterdir() if path.is_dir())
    studies: list[Study] = []
    issues = list(marker_issues)
    for project in sorted(set(active) - names):
        issues.append(f"Active marker references unknown study: {project}")
    for name in sorted(names):
        path = projects_root / name
        project_config = config.projects.get(name, ProjectConfig())
        try:
            path = study_path(root, name)
        except WorkspaceError as exc:
            invalid_reason = str(exc)
            issues.append(invalid_reason)
            studies.append(
                Study(
                    project=name,
                    path=path,
                    state_data=default_invalid_state(),
                    enabled=project_config.enabled is not False,
                    priority=project_config.priority,
                    model=None,
                    max_run_duration_ms=DEFAULT_MAX_RUN_DURATION_MS,
                    cooldown_seconds=DEFAULT_COOLDOWN_SECONDS,
                    retry_backoff_seconds=DEFAULT_RETRY_BACKOFF_SECONDS,
                    sandbox=DEFAULT_SANDBOX,
                    approval_policy=DEFAULT_APPROVAL_POLICY,
                    eligible=False,
                    ineligible_reason=None,
                    valid=False,
                    invalid_reason=invalid_reason,
                    active_run_id=None,
                )
            )
            continue
        required = [path / "README.md", path / "GOAL.md", path / "STATE.yaml"]
        missing = [str(item.relative_to(root)) for item in required if not item.is_file()]
        valid = not missing
        invalid_reason = f"Missing {', '.join(missing)}" if missing else None
        try:
            state_data = load_study_state(path / "STATE.yaml") if valid else default_invalid_state()
        except ValueError as exc:
            valid = False
            invalid_reason = f"Invalid projects/{name}/STATE.yaml: {exc}"
            state_data = default_invalid_state()
        if invalid_reason:
            issues.append(invalid_reason)
        missing_capabilities = sorted(set(state_data.requires) - capabilities)
        eligible = not missing_capabilities
        studies.append(
            Study(
                project=name,
                path=path,
                state_data=state_data,
                enabled=project_config.enabled is not False,
                priority=project_config.priority,
                model=project_value(config, project_config, "model", DEFAULT_MODEL),
                max_run_duration_ms=int(
                    project_value(
                        config,
                        project_config,
                        "max_run_duration_ms",
                        DEFAULT_MAX_RUN_DURATION_MS,
                    )
                ),
                cooldown_seconds=int(
                    project_value(config, project_config, "cooldown_seconds", DEFAULT_COOLDOWN_SECONDS)
                ),
                retry_backoff_seconds=int(
                    project_value(
                        config,
                        project_config,
                        "retry_backoff_seconds",
                        DEFAULT_RETRY_BACKOFF_SECONDS,
                    )
                ),
                sandbox=str(project_value(config, project_config, "sandbox", DEFAULT_SANDBOX)),
                approval_policy=str(
                    project_value(
                        config,
                        project_config,
                        "approval_policy",
                        DEFAULT_APPROVAL_POLICY,
                    )
                ),
                eligible=eligible,
                ineligible_reason=(
                    f"Missing host capabilities: {', '.join(missing_capabilities)}"
                    if missing_capabilities
                    else None
                ),
                valid=valid,
                invalid_reason=invalid_reason,
                active_run_id=active.get(name),
            )
        )
    if any((root / RECOVERY_DIR).glob("*.json")):
        issues.append("Recovery records require human resolution under .a-exp/recovery/")
    return studies, sorted(set(issues))


def default_invalid_state() -> StudyState:
    return StudyState(
        state="shaping",
        ready_after=None,
        summary="Invalid study",
        next_direction=None,
        open_questions=[],
        requires=[],
        last_run_id=None,
        consecutive_failures=0,
    )


def set_project_enabled(root: Path, project: str, enabled: bool) -> None:
    path = study_path(root, project)
    for filename in ("README.md", "GOAL.md", "STATE.yaml"):
        if not (path / filename).is_file():
            raise WorkspaceError(f"Project is not a valid study: projects/{project}")
    try:
        load_study_state(path / "STATE.yaml")
    except ValueError as exc:
        raise WorkspaceError(f"Project is not a valid study: projects/{project}: {exc}") from exc
    config_path = root / CONFIG_PATH
    config = load_workspace_config(root)
    item = config.projects.get(project, ProjectConfig())
    item.enabled = enabled
    config.projects[project] = item
    dump_config(config, config_path)
    commit_workspace_changes(
        root,
        f"{'Enable' if enabled else 'Disable'} a-exp-v2 study {project}",
        [CONFIG_PATH],
    )


def pending_approvals(root: Path) -> int:
    path = root / "APPROVAL_QUEUE.md"
    if not path.exists():
        return 0
    text = path.read_text(encoding="utf-8")
    match = re.search(r"(?ims)^## Pending\s*$\n(?P<body>.*?)(?=^##\s+|\Z)", text)
    body = match.group("body") if match else ""
    return sum(1 for line in body.splitlines() if line.strip().startswith("- [ ]"))


def running_experiments(root: Path, studies: list[Study] | None = None) -> int:
    count = 0
    valid_studies = studies
    if valid_studies is None:
        valid_studies, _ = discover_studies(root)
    paths = (
        path
        for study in valid_studies
        if study.valid
        for path in sorted((study.path / "experiments").glob("*/progress.json"))
    )
    for path in paths:
        try:
            status = json.loads(path.read_text(encoding="utf-8")).get("status")
        except (OSError, json.JSONDecodeError):
            continue
        if status in ACTIVE_EXPERIMENT_STATUSES:
            count += 1
    return count


def status_json(root: Path) -> dict[str, Any]:
    studies, issues = discover_studies(root)
    active_count = sum(1 for study in studies if study.effective_state == "running")
    dirty = active_count == 0 and not git_clean(root)
    if dirty:
        issues.append("Workspace has uncommitted changes")
    items: list[dict[str, Any]] = []
    for study in studies:
        last = last_run_at(root, study.project) if study.valid else None
        items.append(
            {
                "id": study.project,
                "kind": "study",
                "project": study.project,
                "enabled": study.enabled,
                "priority": study.priority,
                "configured_state": study.state_data.state,
                "state": study.effective_state,
                "running": study.effective_state == "running",
                "active_run_id": study.active_run_id,
                "eligible": study.eligible,
                "ineligible_reason": study.ineligible_reason,
                "ready_after": study.state_data.ready_after,
                "last_run_at": last,
                "run_count": run_count(root, study.project) if study.valid else 0,
                "consecutive_failures": study.state_data.consecutive_failures,
            }
        )
    counts = {state: 0 for state in EFFECTIVE_STATES}
    for study in studies:
        counts[study.effective_state] += 1
    health = "ok" if not issues else "degraded"
    runnable = sum(1 for study in studies if study.ready_due) if health == "ok" and not active_count else 0
    return {
        "health": health,
        "warnings": sorted(set(issues)),
        "sessions": {"active": active_count},
        "experiments": {"running": running_experiments(root, studies)},
        "approvals": {"pending": pending_approvals(root)},
        "work": {"runnable": runnable},
        "studies": {
            "total": len(studies),
            "enabled": sum(1 for study in studies if study.enabled),
            "disabled": sum(1 for study in studies if not study.enabled),
            "ready": counts["ready"],
            "running": counts["running"],
            "needs_human": counts["needs_human"],
            "paused": counts["paused"],
            "blocked": counts["blocked"],
            "failed": counts["failed"],
            "completed": counts["completed"],
            "ineligible": counts["ineligible"],
            "invalid": counts["invalid"],
            "items": items,
        },
    }


def format_status(data: dict[str, Any]) -> str:
    studies = data["studies"]
    lines = [
        "=== a-exp-v2 Status ===",
        f"Health: {data['health']}  |  Active Sessions: {data['sessions']['active']}  |  Running Experiments: {data['experiments']['running']}",
        f"Runnable: {data['work']['runnable']}  |  Ready: {studies['ready']}  |  Needs Human: {studies['needs_human']}  |  Pending Approvals: {data['approvals']['pending']}",
        "",
        "--- Studies ---",
    ]
    if not studies["items"]:
        lines.append("  none")
    for item in studies["items"]:
        last = item["last_run_at"] or "never"
        reason = f" ({item['ineligible_reason']})" if item["ineligible_reason"] else ""
        lines.append(
            f"  {item['id']}\t{item['state']}{reason}\tpriority={item['priority']}\t"
            f"last={last}\truns={item['run_count']}\tfailures={item['consecutive_failures']}"
        )
    for warning in data.get("warnings", []):
        lines.append(f"Warning: {warning}")
    return "\n".join(lines)


def last_run_at(root: Path, project: str) -> str | None:
    values: list[datetime] = []
    for data in session_records(root, project):
        value = data.get("started_at")
        if isinstance(value, datetime):
            parsed = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
            parsed = parsed.astimezone(timezone.utc)
        else:
            parsed = parse_timestamp(value) if isinstance(value, str) else None
        if parsed is not None:
            values.append(parsed)
    if not values:
        return None
    return max(values).isoformat().replace("+00:00", "Z")


def last_run_sort_key(root: Path, project: str) -> datetime:
    value = last_run_at(root, project)
    if value is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    return parse_timestamp(value) or datetime.min.replace(tzinfo=timezone.utc)


def run_count(root: Path, project: str) -> int:
    return len(session_records(root, project))


def session_records(root: Path, project: str) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    path = study_path(root, project)
    for path in sorted((path / "sessions").glob("*.yaml")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            continue
        if isinstance(data, dict):
            values.append(data)
    return values


@contextlib.contextmanager
def workspace_lock(root: Path) -> Iterator[None]:
    path = root / LOCK_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def reconcile_running_markers(root: Path) -> tuple[dict[str, str], list[str]]:
    active: dict[str, str] = {}
    issues: list[str] = []
    directory = root / RUNNING_DIR
    directory.mkdir(parents=True, exist_ok=True)
    for path in sorted(directory.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            issues.append(f"Invalid running marker: {path.relative_to(root)}")
            continue
        project = data.get("project")
        pid = data.get("pid")
        if not isinstance(project, str) or not isinstance(pid, int):
            issues.append(f"Invalid running marker: {path.relative_to(root)}")
            continue
        try:
            validate_project_id(project)
        except ValueError:
            issues.append(f"Invalid running marker study ID: {path.relative_to(root)}")
            continue
        if not _pid_alive(pid):
            if git_clean(root):
                path.unlink(missing_ok=True)
            else:
                issues.append(f"Stale running marker with dirty workspace: {path.relative_to(root)}")
            continue
        if project in active:
            issues.append(f"Multiple active markers for study {project}")
            continue
        active[project] = str(data.get("run_id", path.stem))
    return active, issues


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temp.write_text(content, encoding="utf-8")
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    atomic_write_text(path, json.dumps(data, indent=2, sort_keys=True) + "\n")


def select_study(studies: list[Study]) -> Study | None:
    candidates = [study for study in studies if study.ready_due]
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda study: (
            (
                parse_timestamp(study.state_data.ready_after)
                if study.state_data.ready_after
                else datetime.min.replace(tzinfo=timezone.utc)
            ),
            study.priority,
            last_run_sort_key(study.path.parents[1], study.project),
            study.project,
        ),
    )[0]


def claim_next_study(root: Path) -> tuple[Study, str, Path, str] | None:
    with workspace_lock(root):
        studies, issues = discover_studies(root)
        if any(study.active_run_id for study in studies):
            return None
        if not git_clean(root):
            raise WorkspaceError("Workspace has uncommitted changes; commit or discard them before run-once")
        if issues:
            raise WorkspaceError("Workspace is degraded: " + "; ".join(issues))
        study = select_study(studies)
        if study is None:
            return None
        run_id = f"{utc_now_dt().strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"
        started_at = utc_now()
        marker_path = root / RUNNING_DIR / f"{run_id}.json"
        atomic_write_json(
            marker_path,
            {
                "run_id": run_id,
                "project": study.project,
                "pid": os.getpid(),
                "started_at": started_at,
            },
        )
        return study, run_id, marker_path, started_at


def thread_record_path(root: Path, project: str) -> Path:
    try:
        name = validate_project_id(project)
    except ValueError as exc:
        raise WorkspaceError(f"Invalid study ID {project!r}: {exc}") from exc
    directory = contained_path(root, root / THREADS_DIR, "thread-record directory")
    return contained_path(root, directory / f"{name}.json", f"thread record for {name!r}")


def read_thread_id(root: Path, project: str) -> str | None:
    path = thread_record_path(root, project)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    value = data.get("thread_id") if isinstance(data, dict) else None
    return value if isinstance(value, str) and value else None


def write_thread_record(root: Path, project: str, thread_id: str, run_id: str) -> None:
    atomic_write_json(
        thread_record_path(root, project),
        {"thread_id": thread_id, "last_run_id": run_id, "updated_at": utc_now()},
    )


def workflow_prompt(study: Study, run_id: str) -> str:
    steering = study.path / "STEERING.md"
    lines = [
        "Run one a-exp-v2 autonomous study session.",
        f"Study: {study.project}",
        f"Run ID: {run_id}",
        "",
        "Use the workflow skill if available. Read AGENTS.md, the study README, GOAL.md, STATE.yaml, and any PLAN.md, DECISIONS.md, STEERING.md, prior sessions, experiments, reports, and applicable protocols.",
        "Advance the study goal within its autonomy envelope. You may implement code and run multiple coherent foreground experiments. Do not launch unmanaged detached processes.",
        "Commit after every material experiment or coherent code change. Do not edit STATE.yaml; a-exp owns the state transition after validating your final response.",
        "Use an explicit packet for separately scoped a-dev work rather than adding scheduler work units.",
        "",
        "Your final response must satisfy the supplied JSON schema. Declare every repo path changed during this run, including paths already committed. Request exactly one next state: ready, needs_human, paused, blocked, or completed.",
    ]
    if steering.exists():
        lines.append("STEERING.md is present and must be incorporated before choosing further work.")
    return "\n".join(lines)


def validate_closeout(value: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, dict):
        return ["closeout must be an object"]
    required = {
        "outcome",
        "next_state",
        "summary",
        "experiments",
        "verification",
        "files_changed",
        "artifacts",
        "next_direction",
        "open_questions",
        "budget_used",
    }
    missing = sorted(required - set(value))
    if missing:
        errors.append(f"missing closeout field(s): {', '.join(missing)}")
    outcome = value.get("outcome")
    next_state = value.get("next_state")
    if outcome not in OUTCOME_NEXT_STATE:
        errors.append("invalid outcome")
    if next_state not in AGENT_NEXT_STATES:
        errors.append("invalid next_state")
    if outcome in OUTCOME_NEXT_STATE and next_state != OUTCOME_NEXT_STATE[outcome]:
        errors.append(f"outcome {outcome} requires next_state {OUTCOME_NEXT_STATE[outcome]}")
    if not isinstance(value.get("summary"), str) or not value.get("summary", "").strip():
        errors.append("summary must be a non-empty string")
    for field_name in ("experiments", "files_changed", "artifacts", "open_questions"):
        field_value = value.get(field_name)
        if not isinstance(field_value, list) or any(not isinstance(item, str) for item in field_value):
            errors.append(f"{field_name} must be a list of strings")
    verification = value.get("verification")
    if not isinstance(verification, list) or not verification:
        errors.append("verification must be a non-empty list")
    elif any(
        not isinstance(item, dict)
        or not isinstance(item.get("command"), str)
        or not item.get("command", "").strip()
        or not isinstance(item.get("result"), str)
        or not item.get("result", "").strip()
        for item in verification
    ):
        errors.append("verification items require non-empty command and result")
    next_direction = value.get("next_direction")
    if next_direction is not None and not isinstance(next_direction, str):
        errors.append("next_direction must be a string or null")
    budget = value.get("budget_used")
    if not isinstance(budget, dict):
        errors.append("budget_used must be an object")
    else:
        wall = budget.get("wall_seconds")
        experiments = budget.get("experiments")
        if isinstance(wall, bool) or not isinstance(wall, (int, float)) or wall < 0:
            errors.append("budget_used.wall_seconds must be non-negative")
        if isinstance(experiments, bool) or not isinstance(experiments, int) or experiments < 0:
            errors.append("budget_used.experiments must be a non-negative integer")
    return errors


def content_hash(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def brief_log_path_for(log_path: Path) -> Path:
    return log_path.with_name(f"{log_path.stem}.brief{log_path.suffix}")


def run_once(root: Path) -> dict[str, Any] | None:
    claim = claim_next_study(root)
    if claim is None:
        return None
    study, run_id, marker_path, started_at = claim
    run_path = root / RUNS_DIR / f"{run_id}.json"
    log_path = root / LOGS_DIR / f"{study.project}-{run_id}.jsonl"
    brief_log_path = brief_log_path_for(log_path)
    output_message = root / OUTPUT_DIR / f"{run_id}.json"
    base_commit = git_head(root)
    goal_hash = content_hash(study.path / "GOAL.md")
    steering_hash = content_hash(study.path / "STEERING.md")
    previous_thread_id = read_thread_id(root, study.project)
    prompt = workflow_prompt(study, run_id)
    result: CodexRunResult | None = None
    replaced_thread_id: str | None = None
    try:
        try:
            schema_resource = resources.files("a_exp_v2").joinpath("schemas/session-closeout.json")
            with resources.as_file(schema_resource) as schema_path:
                output_message.unlink(missing_ok=True)
                result = run_codex(
                    root=root,
                    study=study.project,
                    run_id=run_id,
                    prompt=prompt,
                    output_schema=schema_path,
                    log_path=log_path,
                    brief_log_path=brief_log_path,
                    output_message=output_message,
                    timeout_seconds=max(1, study.max_run_duration_ms // 1000),
                    model=study.model,
                    sandbox=study.sandbox,
                    approval_policy=study.approval_policy,
                    thread_id=previous_thread_id,
                )
                if previous_thread_id and result.returncode != 0 and not result.turn_started:
                    replaced_thread_id = previous_thread_id
                    output_message.unlink(missing_ok=True)
                    result = run_codex(
                        root=root,
                        study=study.project,
                        run_id=run_id,
                        prompt=prompt,
                        output_schema=schema_path,
                        log_path=log_path,
                        brief_log_path=brief_log_path,
                        output_message=output_message,
                        timeout_seconds=max(1, study.max_run_duration_ms // 1000),
                        model=study.model,
                        sandbox=study.sandbox,
                        approval_policy=study.approval_policy,
                        thread_id=None,
                        append=True,
                    )
        except Exception as exc:
            result = CodexRunResult(
                command=[],
                returncode=1,
                stdout="",
                stderr=str(exc),
                thread_id=None,
                turn_started=False,
                closeout_error=f"runner exception: {type(exc).__name__}: {exc}",
            )
        assert result is not None
        thread_id = result.thread_id or (None if replaced_thread_id else previous_thread_id)
        if thread_id:
            write_thread_record(root, study.project, thread_id, run_id)
        errors = validate_closeout(result.closeout)
        if result.closeout_error:
            errors.append(result.closeout_error)
        if result.returncode != 0:
            errors.append(f"codex exited {result.returncode}")
        actual_paths = set(git_changed_paths_since(root, base_commit))
        scheduler_owned_changes = sorted(
            path
            for path in actual_paths
            if path.startswith(".a-exp/")
            or (
                len(Path(path).parts) == 3
                and Path(path).parts[0] == "projects"
                and Path(path).name == "STATE.yaml"
            )
            or (
                len(Path(path).parts) >= 4
                and Path(path).parts[0] == "projects"
                and Path(path).parts[2] == "sessions"
            )
        )
        state_changed = bool(scheduler_owned_changes)
        if scheduler_owned_changes:
            errors.append(
                "autonomous run modified scheduler-owned path(s): "
                + ", ".join(scheduler_owned_changes)
            )
        declared: set[str] = set()
        if isinstance(result.closeout, dict) and isinstance(result.closeout.get("files_changed"), list):
            for value in result.closeout["files_changed"]:
                if not isinstance(value, str):
                    continue
                try:
                    path = safe_repo_path(root, value)
                except WorkspaceError as exc:
                    errors.append(str(exc))
                    continue
                if path.startswith(".a-exp/"):
                    errors.append(f"runtime path cannot be declared as a project change: {path}")
                declared.add(path)
        undeclared = sorted(actual_paths - declared)
        if undeclared:
            errors.append(f"undeclared changed path(s): {', '.join(undeclared)}")
        if errors:
            failure_record = handle_failed_run(
                root=root,
                study=study,
                run_id=run_id,
                started_at=started_at,
                base_commit=base_commit,
                result=result,
                thread_id=thread_id,
                replaced_thread_id=replaced_thread_id,
                goal_hash=goal_hash,
                steering_hash=steering_hash,
                errors=errors,
                unsafe=state_changed,
                run_path=run_path,
                log_path=log_path,
                brief_log_path=brief_log_path,
            )
            raise AgentRunFailed(
                f"Agent run failed or closeout validation failed: {run_id}: "
                + "; ".join(failure_record["closeout_validation"]["errors"])
            )
        assert isinstance(result.closeout, dict)
        try:
            record = close_successful_run(
                root=root,
                study=study,
                run_id=run_id,
                started_at=started_at,
                base_commit=base_commit,
                result=result,
                thread_id=thread_id,
                replaced_thread_id=replaced_thread_id,
                goal_hash=goal_hash,
                steering_hash=steering_hash,
                declared=declared,
                run_path=run_path,
                log_path=log_path,
                brief_log_path=brief_log_path,
            )
        except Exception as exc:
            detail = f"{type(exc).__name__}: {exc}"
            failure_record = handle_failed_run(
                root=root,
                study=study,
                run_id=run_id,
                started_at=started_at,
                base_commit=base_commit,
                result=result,
                thread_id=thread_id,
                replaced_thread_id=replaced_thread_id,
                goal_hash=goal_hash,
                steering_hash=steering_hash,
                errors=[f"closeout failure: {detail}"],
                unsafe=True,
                run_path=run_path,
                log_path=log_path,
                brief_log_path=brief_log_path,
            )
            raise AgentRunFailed(
                f"Closeout failed: {run_id}: "
                + "; ".join(failure_record["closeout_validation"]["errors"])
            ) from exc
        return record
    finally:
        marker_path.unlink(missing_ok=True)


def close_successful_run(
    *,
    root: Path,
    study: Study,
    run_id: str,
    started_at: str,
    base_commit: str,
    result: CodexRunResult,
    thread_id: str | None,
    replaced_thread_id: str | None,
    goal_hash: str | None,
    steering_hash: str | None,
    declared: set[str],
    run_path: Path,
    log_path: Path,
    brief_log_path: Path,
) -> dict[str, Any]:
    closeout = result.closeout
    assert isinstance(closeout, dict)
    ended_at = utc_now()
    next_state = str(closeout["next_state"])
    state = replace(
        study.state_data,
        state=next_state,
        ready_after=future_timestamp(study.cooldown_seconds) if next_state == "ready" else None,
        summary=str(closeout["summary"]).strip(),
        next_direction=closeout.get("next_direction"),
        open_questions=list(closeout.get("open_questions", [])),
        last_run_id=run_id,
        consecutive_failures=0,
    )
    session_path = study.path / "sessions" / f"{run_id}.yaml"
    session_record = {
        "schema_version": 1,
        "run_id": run_id,
        "study": study.project,
        "status": "completed",
        "outcome": closeout["outcome"],
        "previous_state": study.state_data.state,
        "next_state": next_state,
        "started_at": started_at,
        "ended_at": ended_at,
        "codex_thread_id": thread_id,
        "replaced_thread_id": replaced_thread_id,
        "goal_sha256": goal_hash,
        "steering_sha256": steering_hash,
        "summary": closeout["summary"],
        "experiments": closeout["experiments"],
        "verification": closeout["verification"],
        "files_changed": sorted(declared),
        "artifacts": closeout["artifacts"],
        "budget_used": closeout["budget_used"],
        "commits": git_commits_since(root, base_commit),
        "next_direction": closeout["next_direction"],
        "open_questions": closeout["open_questions"],
    }
    atomic_write_text(session_path, yaml.safe_dump(session_record, sort_keys=False))
    write_study_state(study.path / "STATE.yaml", state)
    owned = {
        session_path.relative_to(root).as_posix(),
        (study.path / "STATE.yaml").relative_to(root).as_posix(),
    }
    dirty = set(git_status_paths(root))
    unexpected = sorted(dirty - declared - owned)
    if unexpected:
        write_recovery(root, run_id, study.project, [f"unexpected dirty path(s): {', '.join(unexpected)}"])
        raise AgentRunFailed(f"Closeout left unexpected dirty paths: {', '.join(unexpected)}")
    closeout_commit = commit_workspace_changes(
        root,
        f"Close a-exp run {run_id} for {study.project}",
        sorted(dirty),
    )
    if not git_clean(root):
        write_recovery(root, run_id, study.project, ["workspace remained dirty after closeout commit"])
        raise AgentRunFailed(f"Workspace remained dirty after closeout: {run_id}")
    runtime = {
        **session_record,
        "project": study.project,
        "exit_code": result.returncode,
        "timed_out": result.timed_out,
        "duration_seconds": result.duration_seconds,
        "log_file": log_path.relative_to(root).as_posix(),
        "brief_log_file": brief_log_path.relative_to(root).as_posix(),
        "closeout_commit": closeout_commit,
        "codex_events": summarize_events(
            result.events,
            timed_out=result.timed_out,
            returncode=result.returncode,
        ),
        "closeout_validation": {"ok": True, "errors": []},
    }
    atomic_write_json(run_path, runtime)
    return runtime


def handle_failed_run(
    *,
    root: Path,
    study: Study,
    run_id: str,
    started_at: str,
    base_commit: str,
    result: CodexRunResult,
    thread_id: str | None,
    replaced_thread_id: str | None,
    goal_hash: str | None,
    steering_hash: str | None,
    errors: list[str],
    unsafe: bool,
    run_path: Path,
    log_path: Path,
    brief_log_path: Path,
) -> dict[str, Any]:
    clean = git_clean(root)
    runtime = {
        "schema_version": 1,
        "run_id": run_id,
        "project": study.project,
        "study": study.project,
        "status": "failed",
        "study_outcome": "infrastructure_failed",
        "previous_state": study.state_data.state,
        "next_state": "recovery_required" if not clean or unsafe else "ready",
        "started_at": started_at,
        "ended_at": utc_now(),
        "codex_thread_id": thread_id,
        "replaced_thread_id": replaced_thread_id,
        "exit_code": result.returncode,
        "timed_out": result.timed_out,
        "duration_seconds": result.duration_seconds,
        "log_file": log_path.relative_to(root).as_posix(),
        "brief_log_file": brief_log_path.relative_to(root).as_posix(),
        "closeout_validation": {"ok": False, "errors": sorted(set(errors))},
        "goal_sha256": goal_hash,
        "steering_sha256": steering_hash,
        "summary": (
            result.closeout.get("summary")
            if isinstance(result.closeout, dict)
            else f"Autonomous run failed: {errors[0] if errors else 'unknown failure'}"
        ),
        "experiments": (
            result.closeout.get("experiments", []) if isinstance(result.closeout, dict) else []
        ),
        "verification": (
            result.closeout.get("verification", []) if isinstance(result.closeout, dict) else []
        ),
        "files_changed": (
            result.closeout.get("files_changed", []) if isinstance(result.closeout, dict) else []
        ),
        "artifacts": (
            result.closeout.get("artifacts", []) if isinstance(result.closeout, dict) else []
        ),
        "budget_used": (
            result.closeout.get("budget_used", {}) if isinstance(result.closeout, dict) else {}
        ),
        "commits": git_commits_since(root, base_commit),
        "next_direction": (
            result.closeout.get("next_direction") if isinstance(result.closeout, dict) else None
        ),
        "open_questions": (
            result.closeout.get("open_questions", []) if isinstance(result.closeout, dict) else []
        ),
        "codex_events": summarize_events(
            result.events,
            timed_out=result.timed_out,
            returncode=result.returncode,
        ),
    }
    if not clean or unsafe:
        write_recovery(root, run_id, study.project, errors)
        atomic_write_json(run_path, runtime)
        return runtime
    failures = study.state_data.consecutive_failures + 1
    next_state = "failed" if failures >= 2 else "ready"
    state = replace(
        study.state_data,
        state=next_state,
        ready_after=(future_timestamp(study.retry_backoff_seconds) if next_state == "ready" else None),
        summary=f"Autonomous run failed: {errors[0] if errors else 'unknown failure'}",
        next_direction="Retry after backoff" if next_state == "ready" else "Human recovery required",
        open_questions=[],
        last_run_id=run_id,
        consecutive_failures=failures,
    )
    runtime["next_state"] = next_state
    session_path = study.path / "sessions" / f"{run_id}.yaml"
    failure_session = {
        "schema_version": 1,
        "run_id": run_id,
        "study": study.project,
        "status": "failed",
        "outcome": "infrastructure_failed",
        "previous_state": study.state_data.state,
        "next_state": next_state,
        "started_at": started_at,
        "ended_at": runtime["ended_at"],
        "codex_thread_id": thread_id,
        "replaced_thread_id": replaced_thread_id,
        "goal_sha256": goal_hash,
        "steering_sha256": steering_hash,
        "summary": state.summary,
        "experiments": runtime["experiments"],
        "verification": runtime["verification"],
        "files_changed": runtime["files_changed"],
        "artifacts": runtime["artifacts"],
        "budget_used": runtime["budget_used"],
        "errors": sorted(set(errors)),
        "commits": git_commits_since(root, base_commit),
        "next_direction": state.next_direction,
        "open_questions": state.open_questions,
    }
    runtime.update(
        {
            "summary": failure_session["summary"],
            "experiments": failure_session["experiments"],
            "verification": failure_session["verification"],
            "files_changed": failure_session["files_changed"],
            "artifacts": failure_session["artifacts"],
            "budget_used": failure_session["budget_used"],
            "commits": failure_session["commits"],
            "next_direction": failure_session["next_direction"],
            "open_questions": failure_session["open_questions"],
        }
    )
    atomic_write_text(session_path, yaml.safe_dump(failure_session, sort_keys=False))
    write_study_state(study.path / "STATE.yaml", state)
    closeout_commit = commit_workspace_changes(
        root,
        f"Record failed a-exp run {run_id} for {study.project}",
        [session_path.relative_to(root), (study.path / "STATE.yaml").relative_to(root)],
    )
    runtime["closeout_commit"] = closeout_commit
    atomic_write_json(run_path, runtime)
    return runtime


def write_recovery(root: Path, run_id: str, project: str, errors: list[str]) -> None:
    atomic_write_json(
        root / RECOVERY_DIR / f"{run_id}.json",
        {
            "run_id": run_id,
            "project": project,
            "created_at": utc_now(),
            "errors": sorted(set(errors)),
            "git_status": git_status_paths(root),
        },
    )
