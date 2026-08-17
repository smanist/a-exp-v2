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
RUNTIME_DIRS = (RUNS_DIR, LOGS_DIR, RUNNING_DIR, THREADS_DIR, OUTPUT_DIR, RECOVERY_DIR)
CONTEXT_FILENAME = "CONTEXT.yaml"
HANDOFFS_DIRNAME = "handoffs"
MAX_HANDOFF_BYTES = 64 * 1024
HANDOFF_CHANGE_CLASSES = {"initial", "continuation", "major_change"}
THREAD_POLICIES = {"resume", "replace"}
THREAD_ACTIONS = {"new", "resume", "replace", "resume_fallback"}
EXPERIMENT_PRODUCERS = {"interactive", "autonomous"}
HANDOFF_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40,64}$")

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
HUMAN_BLOCKER_KINDS = {
    "scientific_decision",
    "approval_required",
    "external_resource_unavailable",
}
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
CONTEXT_KEYS = {"schema_version", "revision", "latest_handoff"}
HANDOFF_KEYS = {
    "schema_version",
    "handoff_id",
    "study",
    "created_at",
    "context_revision",
    "previous_handoff",
    "source_commit",
    "based_on_run_id",
    "change_class",
    "thread_policy",
    "goal_sha256",
    "steering_sha256",
    "summary",
    "decisions",
    "constraints",
    "retained_evidence",
    "superseded_assumptions",
    "rejected_alternatives",
    "next_direction",
    "open_questions",
    "relevant_paths",
    "interactive_experiments",
    "interactive_commits",
    "artifacts",
    "source_thread_id",
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
class StudyContext:
    revision: int
    latest_handoff: str | None
    schema_version: int = 1


@dataclass(frozen=True)
class Handoff:
    handoff_id: str
    study: str
    created_at: str
    context_revision: int
    previous_handoff: str | None
    source_commit: str
    based_on_run_id: str | None
    change_class: str
    thread_policy: str
    goal_sha256: str
    steering_sha256: str | None
    summary: str
    decisions: list[str]
    constraints: list[str]
    retained_evidence: list[str]
    superseded_assumptions: list[str]
    rejected_alternatives: list[str]
    next_direction: str | None
    open_questions: list[str]
    relevant_paths: list[str]
    interactive_experiments: list[str]
    interactive_commits: list[str]
    artifacts: list[str]
    source_thread_id: str | None
    path: str
    schema_version: int = 1


@dataclass(frozen=True)
class Study:
    project: str
    path: Path
    state_data: StudyState
    context_data: StudyContext
    handoff_data: Handoff | None
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
    runtime_root_path(root, create=True)
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

    for relative in RUNTIME_DIRS:
        runtime_directory(root, relative, create=True)

    files = {
        runtime_file_path(root, CONFIG_PATH): default_config_text(),
        runtime_file_path(root, Path(".a-exp/kit.lock.yaml")): "source: local\nversion: 0.3.1\n",
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


def runtime_control_hashes(root: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    paths: list[Path] = [root / CONFIG_PATH, root / ".a-exp/kit.lock.yaml"]
    for relative in (THREADS_DIR, RUNNING_DIR, RECOVERY_DIR):
        directory = root / relative
        if not os.path.lexists(directory):
            continue
        if directory.is_symlink() or not directory.is_dir():
            paths.append(directory)
            continue
        try:
            paths.extend(sorted(directory.rglob("*")))
        except OSError as exc:
            values[relative.as_posix()] = f"scan-error:{exc}"
    for path in paths:
        if not os.path.lexists(path):
            continue
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            try:
                target = os.readlink(path)
            except OSError as exc:
                target = f"unreadable:{exc}"
            values[relative] = f"symlink:{target}"
        elif path.is_file():
            try:
                values[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
            except OSError as exc:
                values[relative] = f"unreadable:{exc}"
    return values


def git_changed_paths_since(root: Path, base_commit: str) -> list[str]:
    result = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "log",
            "--format=",
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
        raise WorkspaceError(result.stderr.strip() or "git history inspection failed")
    return sorted(
        {value for value in result.stdout.split("\0") if value}
        | set(git_status_paths(root))
    )


def git_head_descends_from(root: Path, base_commit: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(root), "merge-base", "--is-ancestor", base_commit, "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    raise WorkspaceError(result.stderr.strip() or "Git ancestry inspection failed")


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
    try:
        source.relative_to(root.resolve())
    except ValueError:
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
- `projects/<study>/CONTEXT.yaml` and `handoffs/`: interactive context revision
  and append-only ownership handoffs.
- `projects/<study>/PLAN.md` and `DECISIONS.md`: evolving strategy and decisions.
- `projects/<study>/experiments/`: experiment manifests, progress, results, and findings.
- `projects/<study>/sessions/`: committed autonomous-run closeouts.
- `APPROVAL_QUEUE.md`: durable requests that need human approval.

## Work Cycle

External schedulers call `a-exp run-once`. The command selects one ready study
and starts or resumes one bounded Codex turn. Use the workflow skill, advance the
study goal within its autonomy envelope, run foreground experiments as needed,
record each material checkpoint in the study worktree, and finish with the
required structured closeout. Do not edit `STATE.yaml` during an autonomous
run; a-exp owns the state transition after validating closeout.

Interactive shaping may update and commit project files directly. Material
Remote Project computations use experiment records with `producer: interactive`.
After GPU work use `$reconcile`; return control with explicit
`$handoff-continue` or `$handoff-change`. Only those handoff skills advance
context and set `state: ready`.

Autonomous GPU experiments declare `producer: autonomous`. During autonomous
work do not edit `GOAL.md`, `STEERING.md`, `CONTEXT.yaml`, `handoffs/`,
`STATE.yaml`, or `sessions/`, and do not edit files under another study.

For experiment-heavy work, check `protocols/registry.yaml`, follow any matching
playbook and checklist, and record the protocol id in experiment memory.

## Git Rule

Interactive work commits every material experiment or coherent code change and
leaves the workspace clean. During an autonomous run (`A_EXP_RUN_ID` is set),
do not run `git add` or `git commit`: leave intended study changes in the
worktree and declare every changed path. The outer runner validates and commits
those changes with the state and session closeout. Read-only `.git` access is
expected and is not a reason to request `needs_human`.
"""


def default_approval_queue() -> str:
    return "# Approval Queue\n\n## Pending\n\n## Completed\n"


def load_workspace_config(root: Path) -> WorkspaceConfig:
    config_path = runtime_file_path(root, CONFIG_PATH)
    try:
        return load_config(config_path)
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


def optional_string(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string or null")
    return value.strip()


def load_study_context(path: Path) -> StudyContext:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(str(exc)) from exc
    if not isinstance(raw, dict):
        raise ValueError("CONTEXT.yaml root must be an object")
    unknown = sorted(set(raw) - CONTEXT_KEYS)
    missing = sorted(CONTEXT_KEYS - set(raw))
    if unknown:
        raise ValueError(f"unknown field(s): {', '.join(unknown)}")
    if missing:
        raise ValueError(f"missing field(s): {', '.join(missing)}")
    if raw.get("schema_version") != 1:
        raise ValueError("schema_version must be 1")
    revision = raw.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise ValueError("revision must be a non-negative integer")
    latest_handoff = optional_string(raw.get("latest_handoff"), "latest_handoff")
    if revision == 0 and latest_handoff is not None:
        raise ValueError("revision 0 must not name a latest_handoff")
    if revision > 0 and latest_handoff is None:
        raise ValueError("revision greater than 0 requires latest_handoff")
    if latest_handoff is not None and not HANDOFF_ID_PATTERN.fullmatch(latest_handoff):
        raise ValueError("latest_handoff is not a safe handoff ID")
    return StudyContext(revision=revision, latest_handoff=latest_handoff)


def write_study_context(path: Path, context: StudyContext) -> None:
    if context.schema_version != 1:
        raise ValueError("schema_version must be 1")
    if (
        isinstance(context.revision, bool)
        or not isinstance(context.revision, int)
        or context.revision < 0
    ):
        raise ValueError("revision must be a non-negative integer")
    if context.revision == 0 and context.latest_handoff is not None:
        raise ValueError("revision 0 must not name a latest_handoff")
    if context.revision > 0 and (
        not isinstance(context.latest_handoff, str)
        or not HANDOFF_ID_PATTERN.fullmatch(context.latest_handoff)
    ):
        raise ValueError("positive revision requires a safe latest_handoff ID")
    data = {
        "schema_version": 1,
        "revision": context.revision,
        "latest_handoff": context.latest_handoff,
    }
    atomic_write_text(path, yaml.safe_dump(data, sort_keys=False))


def handoff_record_path(root: Path, study_path_value: Path, handoff_id: str) -> Path:
    if not HANDOFF_ID_PATTERN.fullmatch(handoff_id):
        raise WorkspaceError(f"Invalid handoff ID: {handoff_id!r}")
    directory = study_directory_path(root, study_path_value, HANDOFFS_DIRNAME)
    return safe_file(
        root,
        directory / f"{handoff_id}.yaml",
        f"handoff record {study_path_value.name}/{handoff_id}",
        within=directory,
    )


def _validate_handoff_text(raw_text: str) -> None:
    if len(raw_text.encode("utf-8")) > MAX_HANDOFF_BYTES:
        raise ValueError(f"handoff record exceeds {MAX_HANDOFF_BYTES} bytes")
    lowered = raw_text.lower()
    secret_patterns = (
        r"-----begin (?:rsa |ec |openssh )?private key-----",
        r"\b(?:api[_ -]?key|access[_ -]?token|client[_ -]?secret)\s*[:=]\s*[^\s]{8,}",
        r"\bbearer\s+[a-z0-9._~+/-]{12,}",
        r"\bsk-[a-z0-9_-]{12,}",
    )
    if any(re.search(pattern, lowered, flags=re.IGNORECASE) for pattern in secret_patterns):
        raise ValueError("handoff record appears to contain a secret")
    transcript_markers = ("raw_transcript:", "transcript:", "messages:", "event_log:")
    if any(marker in lowered for marker in transcript_markers):
        raise ValueError("handoff records must not contain raw transcripts or embedded logs")
    role_lines = re.findall(
        r"(?im)^\s*(?:[-|>]\s*)?(?:user|assistant|system|developer)\s*:",
        raw_text,
    )
    json_log_lines = re.findall(r"(?m)^\s*[-|>]?[ \t]*\{.*\}\s*$", raw_text)
    if len(role_lines) >= 2 or len(json_log_lines) >= 3:
        raise ValueError("handoff records must not contain raw transcripts or embedded logs")


def _handoff_path_list(
    root: Path,
    values: Any,
    field_name: str,
) -> list[str]:
    result = string_list(values, field_name)
    normalized: list[str] = []
    for value in result:
        try:
            normalized.append(safe_repo_path(root, value))
        except WorkspaceError as exc:
            raise ValueError(str(exc)) from exc
    return normalized


def load_handoff_record(root: Path, study_path_value: Path, path: Path) -> Handoff:
    directory = study_directory_path(root, study_path_value, HANDOFFS_DIRNAME)
    try:
        record_path = safe_file(
            root,
            path,
            f"handoff record for {study_path_value.name}",
            within=directory,
        )
        if record_path.stat().st_size > MAX_HANDOFF_BYTES:
            raise ValueError(f"handoff record exceeds {MAX_HANDOFF_BYTES} bytes")
        raw_text = record_path.read_text(encoding="utf-8")
    except (OSError, WorkspaceError) as exc:
        raise ValueError(str(exc)) from exc
    _validate_handoff_text(raw_text)
    try:
        raw = yaml.safe_load(raw_text) or {}
    except yaml.YAMLError as exc:
        raise ValueError(str(exc)) from exc
    if not isinstance(raw, dict):
        raise ValueError("handoff root must be an object")
    unknown = sorted(set(raw) - HANDOFF_KEYS)
    missing = sorted(HANDOFF_KEYS - set(raw))
    if unknown:
        raise ValueError(f"unknown field(s): {', '.join(unknown)}")
    if missing:
        raise ValueError(f"missing field(s): {', '.join(missing)}")
    if raw.get("schema_version") != 1:
        raise ValueError("schema_version must be 1")
    handoff_id = raw.get("handoff_id")
    if not isinstance(handoff_id, str) or not HANDOFF_ID_PATTERN.fullmatch(handoff_id):
        raise ValueError("handoff_id must be a safe non-empty ID")
    if record_path.name != f"{handoff_id}.yaml":
        raise ValueError("handoff filename must match handoff_id")
    study = raw.get("study")
    if study != study_path_value.name:
        raise ValueError(f"study must be {study_path_value.name!r}")
    created_at = raw.get("created_at")
    if isinstance(created_at, datetime):
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        created_at = created_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if not isinstance(created_at, str) or parse_timestamp(created_at) is None:
        raise ValueError("created_at must be an ISO timestamp")
    revision = raw.get("context_revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        raise ValueError("context_revision must be a positive integer")
    previous = optional_string(raw.get("previous_handoff"), "previous_handoff")
    if previous is not None and not HANDOFF_ID_PATTERN.fullmatch(previous):
        raise ValueError("previous_handoff is not a safe handoff ID")
    source_commit = raw.get("source_commit")
    if not isinstance(source_commit, str) or not COMMIT_PATTERN.fullmatch(source_commit):
        raise ValueError("source_commit must be a full Git object ID")
    based_on_run_id = optional_string(raw.get("based_on_run_id"), "based_on_run_id")
    change_class = raw.get("change_class")
    if change_class not in HANDOFF_CHANGE_CLASSES:
        raise ValueError("change_class must be initial, continuation, or major_change")
    thread_policy = raw.get("thread_policy")
    if thread_policy not in THREAD_POLICIES:
        raise ValueError("thread_policy must be resume or replace")
    goal_sha256 = raw.get("goal_sha256")
    if not isinstance(goal_sha256, str) or not SHA256_PATTERN.fullmatch(goal_sha256):
        raise ValueError("goal_sha256 must be a lowercase SHA-256 digest")
    steering_sha256 = optional_string(raw.get("steering_sha256"), "steering_sha256")
    if steering_sha256 is not None and not SHA256_PATTERN.fullmatch(steering_sha256):
        raise ValueError("steering_sha256 must be a lowercase SHA-256 digest or null")
    summary = raw.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise ValueError("summary must be a non-empty string")
    next_direction = optional_string(raw.get("next_direction"), "next_direction")
    source_thread_id = optional_string(raw.get("source_thread_id"), "source_thread_id")
    interactive_commits = string_list(raw.get("interactive_commits"), "interactive_commits")
    if any(not COMMIT_PATTERN.fullmatch(value) for value in interactive_commits):
        raise ValueError("interactive_commits entries must be full Git object IDs")
    return Handoff(
        handoff_id=handoff_id,
        study=study,
        created_at=created_at,
        context_revision=revision,
        previous_handoff=previous,
        source_commit=source_commit,
        based_on_run_id=based_on_run_id,
        change_class=change_class,
        thread_policy=thread_policy,
        goal_sha256=goal_sha256,
        steering_sha256=steering_sha256,
        summary=summary.strip(),
        decisions=string_list(raw.get("decisions"), "decisions"),
        constraints=string_list(raw.get("constraints"), "constraints"),
        retained_evidence=string_list(raw.get("retained_evidence"), "retained_evidence"),
        superseded_assumptions=string_list(
            raw.get("superseded_assumptions"), "superseded_assumptions"
        ),
        rejected_alternatives=string_list(
            raw.get("rejected_alternatives"), "rejected_alternatives"
        ),
        next_direction=next_direction,
        open_questions=string_list(raw.get("open_questions"), "open_questions"),
        relevant_paths=_handoff_path_list(root, raw.get("relevant_paths"), "relevant_paths"),
        interactive_experiments=string_list(
            raw.get("interactive_experiments"), "interactive_experiments"
        ),
        interactive_commits=interactive_commits,
        artifacts=_handoff_path_list(root, raw.get("artifacts"), "artifacts"),
        source_thread_id=source_thread_id,
        path=record_path.relative_to(root).as_posix(),
    )


def handoff_record_data(handoff: Handoff) -> dict[str, Any]:
    return {
        "schema_version": handoff.schema_version,
        "handoff_id": handoff.handoff_id,
        "study": handoff.study,
        "created_at": handoff.created_at,
        "context_revision": handoff.context_revision,
        "previous_handoff": handoff.previous_handoff,
        "source_commit": handoff.source_commit,
        "based_on_run_id": handoff.based_on_run_id,
        "change_class": handoff.change_class,
        "thread_policy": handoff.thread_policy,
        "goal_sha256": handoff.goal_sha256,
        "steering_sha256": handoff.steering_sha256,
        "summary": handoff.summary,
        "decisions": handoff.decisions,
        "constraints": handoff.constraints,
        "retained_evidence": handoff.retained_evidence,
        "superseded_assumptions": handoff.superseded_assumptions,
        "rejected_alternatives": handoff.rejected_alternatives,
        "next_direction": handoff.next_direction,
        "open_questions": handoff.open_questions,
        "relevant_paths": handoff.relevant_paths,
        "interactive_experiments": handoff.interactive_experiments,
        "interactive_commits": handoff.interactive_commits,
        "artifacts": handoff.artifacts,
        "source_thread_id": handoff.source_thread_id,
    }


def write_handoff_record(root: Path, study_path_value: Path, handoff: Handoff) -> Path:
    directory = study_directory_path(
        root, study_path_value, HANDOFFS_DIRNAME, create=True
    )
    path = safe_file(
        root,
        directory / f"{handoff.handoff_id}.yaml",
        f"handoff record {study_path_value.name}/{handoff.handoff_id}",
        within=directory,
    )
    if os.path.lexists(path):
        raise WorkspaceError(f"handoff records are append-only: {path.relative_to(root)}")
    text_value = yaml.safe_dump(handoff_record_data(handoff), sort_keys=False)
    _validate_handoff_text(text_value)
    atomic_write_text(path, text_value)
    try:
        load_handoff_record(root, study_path_value, path)
    except ValueError:
        path.unlink(missing_ok=True)
        raise
    return path


def load_handoff_chain(
    root: Path,
    study_path_value: Path,
    context: StudyContext,
) -> tuple[Handoff | None, list[Handoff]]:
    directory = study_directory_path(root, study_path_value, HANDOFFS_DIRNAME)
    for entry in directory.iterdir() if directory.exists() else []:
        if entry.name == ".gitkeep":
            if entry.is_symlink() or not entry.is_file():
                raise ValueError("handoffs/.gitkeep must be a regular file")
            continue
        if entry.suffix != ".yaml" or entry.is_dir():
            raise ValueError(
                f"unexpected entry in handoffs directory: {entry.name}"
            )
    record_paths = sorted(directory.glob("*.yaml"))
    if context.revision == 0:
        if record_paths:
            raise ValueError("revision 0 must have an empty handoffs directory")
        return None, []
    records: dict[str, Handoff] = {}
    for path in record_paths:
        record = load_handoff_record(root, study_path_value, path)
        if record.handoff_id in records:
            raise ValueError(f"duplicate handoff_id: {record.handoff_id}")
        records[record.handoff_id] = record
    assert context.latest_handoff is not None
    latest = records.get(context.latest_handoff)
    if latest is None:
        raise ValueError(f"latest_handoff {context.latest_handoff!r} does not exist")
    chain: list[Handoff] = []
    current: Handoff | None = latest
    seen: set[str] = set()
    expected_revision = context.revision
    while current is not None:
        if current.handoff_id in seen:
            raise ValueError("handoff chain contains a cycle")
        seen.add(current.handoff_id)
        if current.context_revision != expected_revision:
            raise ValueError("handoff revisions must form a contiguous descending chain")
        chain.append(current)
        if current.previous_handoff is None:
            current = None
        else:
            current = records.get(current.previous_handoff)
            if current is None:
                raise ValueError("previous_handoff does not exist")
        expected_revision -= 1
    if expected_revision != 0:
        raise ValueError("handoff chain does not reach revision 1")
    if set(records) != seen:
        raise ValueError("handoffs directory contains records outside the active revision chain")
    ordered = list(reversed(chain))
    for index, record in enumerate(ordered):
        previous_record = ordered[index - 1] if index else None
        if index == 0:
            if record.change_class != "initial" or record.thread_policy != "resume":
                raise ValueError("revision 1 must be initial with resume policy")
            if record.previous_handoff is not None:
                raise ValueError("initial handoff must not have previous_handoff")
        elif record.change_class == "continuation":
            assert previous_record is not None
            if parse_timestamp(record.created_at) < parse_timestamp(previous_record.created_at):
                raise ValueError("handoff created_at timestamps must be nondecreasing")
            if record.thread_policy != "resume":
                raise ValueError("continuation handoffs require resume policy")
            if record.goal_sha256 != previous_record.goal_sha256:
                raise ValueError("continuation handoff requires an unchanged GOAL.md hash")
        elif record.change_class == "major_change":
            assert previous_record is not None
            if parse_timestamp(record.created_at) < parse_timestamp(previous_record.created_at):
                raise ValueError("handoff created_at timestamps must be nondecreasing")
            if record.thread_policy != "replace":
                raise ValueError("major_change handoffs require replace policy")
            if record.goal_sha256 == previous_record.goal_sha256:
                raise ValueError("major_change handoff requires a changed GOAL.md hash")
            if not record.superseded_assumptions:
                raise ValueError("major_change handoff requires superseded_assumptions")
        else:
            raise ValueError("only revision 1 may use change_class initial")
    if latest.context_revision != context.revision:
        raise ValueError("latest handoff revision does not match CONTEXT.yaml")
    goal_path = study_file_path(root, study_path_value, "GOAL.md")
    if content_hash(goal_path) != latest.goal_sha256:
        raise ValueError("latest handoff goal_sha256 does not match GOAL.md")
    steering_path = study_path_value / "STEERING.md"
    current_steering_hash = (
        content_hash(study_file_path(root, study_path_value, "STEERING.md"))
        if os.path.lexists(steering_path)
        else None
    )
    if current_steering_hash != latest.steering_sha256:
        raise ValueError("latest handoff steering_sha256 does not match STEERING.md")
    return latest, ordered


def experiment_producer(path: Path) -> str:
    try:
        text_value = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(str(exc)) from exc
    lines = text_value.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("EXPERIMENT.md must begin with YAML frontmatter")
    try:
        end = next(index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---")
    except StopIteration as exc:
        raise ValueError("EXPERIMENT.md frontmatter is not terminated") from exc
    try:
        frontmatter = yaml.safe_load("\n".join(lines[1:end])) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid EXPERIMENT.md frontmatter: {exc}") from exc
    if not isinstance(frontmatter, dict):
        raise ValueError("EXPERIMENT.md frontmatter must be an object")
    if frontmatter.get("id") != path.parent.name:
        raise ValueError("EXPERIMENT.md frontmatter id must match its directory")
    if len(path.parents) < 3 or frontmatter.get("study") != path.parents[2].name:
        raise ValueError("EXPERIMENT.md frontmatter study must match its study directory")
    producer = frontmatter.get("producer")
    if producer not in EXPERIMENT_PRODUCERS:
        raise ValueError("EXPERIMENT.md frontmatter producer must be interactive or autonomous")
    return producer


def validate_session_handoff_links(
    records: list[dict[str, Any]],
    handoffs: list[Handoff],
) -> None:
    by_revision = {handoff.context_revision: handoff for handoff in handoffs}
    by_run_id = {record.get("run_id"): record for record in records}
    for handoff in handoffs:
        if handoff.based_on_run_id is None:
            continue
        based_on = by_run_id.get(handoff.based_on_run_id)
        if based_on is None:
            raise ValueError(
                f"handoff {handoff.handoff_id!r} based_on_run_id does not exist"
            )
        if based_on.get("context_revision", handoff.context_revision) >= handoff.context_revision:
            raise ValueError(
                f"handoff {handoff.handoff_id!r} must be based on an earlier context revision"
            )
    for record in records:
        run_id = str(record.get("run_id", "unknown"))
        revision = record.get("context_revision")
        handoff = by_revision.get(revision)
        if handoff is None:
            raise ValueError(
                f"session {run_id!r} references unknown context revision {revision!r}"
            )
        if record.get("handoff_id") != handoff.handoff_id:
            raise ValueError(
                f"session {run_id!r} handoff_id does not match context revision {revision}"
            )
        if record.get("requested_thread_policy") != handoff.thread_policy:
            raise ValueError(
                f"session {run_id!r} requested policy does not match its handoff"
            )
        if record.get("goal_sha256") != handoff.goal_sha256:
            raise ValueError(
                f"session {run_id!r} goal_sha256 does not match its handoff"
            )
        if record.get("steering_sha256") != handoff.steering_sha256:
            raise ValueError(
                f"session {run_id!r} steering_sha256 does not match its handoff"
            )


def validate_committed_session_record(record: dict[str, Any]) -> None:
    from .validators import validate_run_record

    errors = validate_run_record(record, committed=True)
    if errors:
        raise WorkspaceError("invalid runner-owned session record: " + "; ".join(errors))


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


def contained_path(
    root: Path,
    path: Path,
    description: str,
    *,
    within: Path | None = None,
) -> Path:
    try:
        workspace = root.resolve()
        boundary = (within or root).resolve(strict=False)
        resolved = path.resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise WorkspaceError(f"{description} cannot be resolved safely: {path}: {exc}") from exc
    try:
        boundary.relative_to(workspace)
    except ValueError as exc:
        raise WorkspaceError(f"{description} boundary escapes workspace: {within or root}") from exc
    try:
        resolved.relative_to(boundary)
    except ValueError as exc:
        raise WorkspaceError(f"{description} escapes workspace: {path}") from exc
    return path


def safe_directory(
    root: Path,
    path: Path,
    description: str,
    *,
    within: Path,
    create: bool = False,
) -> Path:
    contained_path(root, path, description, within=within)
    if path.is_symlink():
        raise WorkspaceError(f"{description} must not be a symlink: {path}")
    if path.exists() and not path.is_dir():
        raise WorkspaceError(f"{description} must be a directory: {path}")
    if create:
        path.mkdir(parents=True, exist_ok=True)
        contained_path(root, path, description, within=within)
    return path


def safe_file(
    root: Path,
    path: Path,
    description: str,
    *,
    within: Path,
) -> Path:
    contained_path(root, path, description, within=within)
    if path.is_symlink():
        raise WorkspaceError(f"{description} must not be a symlink: {path}")
    if path.exists() and not path.is_file():
        raise WorkspaceError(f"{description} must be a regular file: {path}")
    return path


def runtime_root_path(root: Path, *, create: bool = False) -> Path:
    path = root / ".a-exp"
    return safe_directory(root, path, "runtime directory", within=root, create=create)


def runtime_directory(root: Path, relative: Path, *, create: bool = False) -> Path:
    if not relative.parts or relative.parts[0] != ".a-exp":
        raise WorkspaceError(f"runtime path must be under .a-exp: {relative}")
    runtime_root = runtime_root_path(root, create=create)
    path = root / relative
    return safe_directory(
        root,
        path,
        f"runtime directory {relative}",
        within=runtime_root,
        create=create,
    )


def runtime_file_path(root: Path, relative: Path) -> Path:
    if not relative.parts or relative.parts[0] != ".a-exp":
        raise WorkspaceError(f"runtime path must be under .a-exp: {relative}")
    parent = runtime_directory(root, relative.parent, create=True)
    return safe_file(root, root / relative, f"runtime file {relative}", within=parent)


def study_file_path(root: Path, path: Path, filename: str) -> Path:
    return safe_file(
        root,
        path / filename,
        f"study file {path.name}/{filename}",
        within=path,
    )


def study_directory_path(
    root: Path,
    path: Path,
    dirname: str,
    *,
    create: bool = False,
) -> Path:
    return safe_directory(
        root,
        path / dirname,
        f"study directory {path.name}/{dirname}",
        within=path,
        create=create,
    )


def runtime_layout_issues(root: Path) -> list[str]:
    issues: list[str] = []
    for relative in RUNTIME_DIRS:
        try:
            runtime_directory(root, relative, create=True)
        except WorkspaceError as exc:
            issues.append(str(exc))
    return sorted(set(issues))


def study_path(root: Path, project: str) -> Path:
    try:
        name = validate_project_id(project)
    except ValueError as exc:
        raise WorkspaceError(f"Invalid study ID {project!r}: {exc}") from exc
    projects_root = safe_directory(
        root,
        root / "projects",
        "projects directory",
        within=root,
    )
    path = projects_root / name
    safe_directory(root, path, f"study {name!r}", within=projects_root)
    return path


def discover_studies(root: Path) -> tuple[list[Study], list[str]]:
    config = load_workspace_config(root)
    active, marker_issues = reconcile_running_markers(root)
    layout_issues = runtime_layout_issues(root)
    capabilities = load_host_capabilities()
    projects_root = root / "projects"
    try:
        safe_directory(root, projects_root, "projects directory", within=root)
    except WorkspaceError as exc:
        return [], sorted({*marker_issues, *layout_issues, str(exc)})
    names = set(config.projects)
    if projects_root.is_dir():
        names.update(path.name for path in projects_root.iterdir() if path.is_dir())
    studies: list[Study] = []
    issues = [*marker_issues, *layout_issues]
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
                    context_data=default_invalid_context(),
                    handoff_data=None,
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
        required: list[Path] = []
        invalid_reason: str | None = None
        session_record_values: list[dict[str, Any]] = []
        try:
            required = [
                study_file_path(root, path, filename)
                for filename in ("README.md", "GOAL.md", "STATE.yaml", CONTEXT_FILENAME)
            ]
            missing = [str(item.relative_to(root)) for item in required if not item.is_file()]
            if missing:
                invalid_reason = f"Missing {', '.join(missing)}"
            for filename in ("PLAN.md", "DECISIONS.md", "STEERING.md"):
                candidate = path / filename
                if os.path.lexists(candidate):
                    study_file_path(root, path, filename)
            handoffs_candidate = path / HANDOFFS_DIRNAME
            if not handoffs_candidate.is_dir():
                invalid_reason = invalid_reason or f"Missing {handoffs_candidate.relative_to(root)}"
            else:
                study_directory_path(root, path, HANDOFFS_DIRNAME)
            for dirname in ("sessions", "experiments"):
                candidate = path / dirname
                if os.path.lexists(candidate):
                    directory = study_directory_path(root, path, dirname)
                    if dirname == "sessions":
                        for entry in directory.iterdir():
                            if entry.suffix != ".yaml" or entry.is_dir():
                                raise ValueError(
                                    "unexpected entry in sessions directory: "
                                    f"{entry.name}"
                                )
                        for record_path in directory.glob("*.yaml"):
                            validated_record_path = safe_file(
                                root,
                                record_path,
                                f"session record for {name}",
                                within=directory,
                            )
                            try:
                                record_data = (
                                    yaml.safe_load(
                                        validated_record_path.read_text(encoding="utf-8")
                                    )
                                    or {}
                                )
                            except (OSError, yaml.YAMLError) as exc:
                                raise ValueError(
                                    f"{validated_record_path.relative_to(root)}: {exc}"
                                ) from exc
                            if not isinstance(record_data, dict):
                                raise ValueError(
                                    f"{validated_record_path.relative_to(root)}: root must be an object"
                                )
                            from .validators import validate_run_record

                            record_errors = validate_run_record(record_data, committed=True)
                            if record_errors:
                                raise ValueError(
                                    f"{validated_record_path.relative_to(root)}: "
                                    + "; ".join(record_errors)
                                )
                            if record_data.get("study") != name:
                                raise ValueError(
                                    f"{validated_record_path.relative_to(root)}: "
                                    f"study must be {name!r}"
                                )
                            if record_data.get("run_id") != validated_record_path.stem:
                                raise ValueError(
                                    f"{validated_record_path.relative_to(root)}: "
                                    "filename must match run_id"
                                )
                            session_record_values.append(record_data)
                    else:
                        for pattern in ("*/EXPERIMENT.md", "*/progress.json"):
                            for experiment_path in directory.glob(pattern):
                                safe_file(
                                    root,
                                    experiment_path,
                                    f"experiment record for {name}",
                                    within=directory,
                                )
            valid = invalid_reason is None
            state_data = load_study_state(required[2]) if valid else default_invalid_state()
            context_data = (
                load_study_context(required[3]) if valid else default_invalid_context()
            )
            handoff_data: Handoff | None = None
            if valid:
                handoff_data, handoff_chain = load_handoff_chain(root, path, context_data)
                validate_session_handoff_links(session_record_values, handoff_chain)
                if context_data.revision == 0 and state_data.state != "shaping":
                    raise ValueError("revision 0 is valid only while state is shaping")
                if state_data.state == "ready" and context_data.revision < 1:
                    raise ValueError("ready studies require context revision at least 1")
                experiments_directory = study_directory_path(root, path, "experiments")
                for experiment_path in sorted(experiments_directory.rglob("EXPERIMENT.md")):
                    if experiment_path.parent.parent != experiments_directory:
                        relative = experiment_path.relative_to(root)
                        raise ValueError(
                            f"{relative}: EXPERIMENT.md must use "
                            "experiments/<experiment-id>/EXPERIMENT.md"
                        )
                    try:
                        experiment_producer(experiment_path)
                    except ValueError as exc:
                        relative = experiment_path.relative_to(root)
                        raise ValueError(f"{relative}: {exc}") from exc
                if handoff_data is not None:
                    for experiment_id in handoff_data.interactive_experiments:
                        try:
                            validate_project_id(experiment_id)
                        except ValueError as exc:
                            raise ValueError(
                                f"invalid interactive experiment ID {experiment_id!r}: {exc}"
                            ) from exc
                        record_path = experiments_directory / experiment_id / "EXPERIMENT.md"
                        if not record_path.is_file():
                            raise ValueError(
                                f"interactive experiment {experiment_id!r} has no EXPERIMENT.md"
                            )
                        if experiment_producer(record_path) != "interactive":
                            raise ValueError(
                                f"handoff experiment {experiment_id!r} must declare producer: interactive"
                            )
                stale_reason = stale_ready_reason(root, name, state_data, context_data)
                if stale_reason:
                    raise ValueError(stale_reason)
        except WorkspaceError as exc:
            valid = False
            invalid_reason = f"Invalid projects/{name}: {exc}"
            state_data = default_invalid_state()
            context_data = default_invalid_context()
            handoff_data = None
        except ValueError as exc:
            valid = False
            invalid_reason = f"Invalid projects/{name}: {exc}"
            state_data = default_invalid_state()
            context_data = default_invalid_context()
            handoff_data = None
        if invalid_reason:
            issues.append(invalid_reason)
        missing_capabilities = sorted(set(state_data.requires) - capabilities)
        eligible = not missing_capabilities
        studies.append(
            Study(
                project=name,
                path=path,
                state_data=state_data,
                context_data=context_data,
                handoff_data=handoff_data,
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
    try:
        recovery_directory = runtime_directory(root, RECOVERY_DIR, create=True)
    except WorkspaceError as exc:
        issues.append(str(exc))
    else:
        if any(recovery_directory.glob("*.json")):
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


def default_invalid_context() -> StudyContext:
    return StudyContext(revision=0, latest_handoff=None)


def stale_ready_reason(
    root: Path,
    project: str,
    state: StudyState,
    context: StudyContext,
) -> str | None:
    if state.state != "ready":
        return None
    records = session_records(root, project)
    if not records:
        return None
    last = records[-1]
    if last.get("next_state") == "ready":
        return None
    last_revision = last.get("context_revision")
    if isinstance(last_revision, bool) or not isinstance(last_revision, int):
        return "session records must use schema version 2 with context_revision"
    if context.revision <= last_revision:
        return (
            "stale interactive ready transition: advance CONTEXT.yaml after a "
            "non-ready autonomous session"
        )
    return None


def set_project_enabled(root: Path, project: str, enabled: bool) -> None:
    path = study_path(root, project)
    for filename in ("README.md", "GOAL.md", "STATE.yaml", CONTEXT_FILENAME):
        if not study_file_path(root, path, filename).is_file():
            raise WorkspaceError(f"Project is not a valid study: projects/{project}")
    if not (path / HANDOFFS_DIRNAME).is_dir():
        raise WorkspaceError(f"Project is not a valid study: projects/{project}")
    studies, _ = discover_studies(root)
    study = next((item for item in studies if item.project == project), None)
    if study is None or not study.valid:
        detail = f": {study.invalid_reason}" if study and study.invalid_reason else ""
        raise WorkspaceError(f"Project is not a valid study: projects/{project}{detail}")
    config_path = runtime_file_path(root, CONFIG_PATH)
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
    paths: list[tuple[Study, Path]] = []
    for study in valid_studies:
        if not study.valid:
            continue
        directory = study_directory_path(root, study.path, "experiments")
        paths.extend((study, path) for path in sorted(directory.glob("*/progress.json")))
    for study, path in paths:
        try:
            directory = study_directory_path(root, study.path, "experiments")
            progress_path = safe_file(
                root,
                path,
                f"experiment progress for {study.project}",
                within=directory,
            )
            status = json.loads(progress_path.read_text(encoding="utf-8")).get("status")
        except (OSError, WorkspaceError, json.JSONDecodeError):
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
        records = session_records(root, study.project) if study.valid else []
        last = last_run_at_from_records(records)
        consumed_revision = consumed_context_revision(records)
        last_record = records[-1] if records else {}
        superseded_id = superseded_thread_id(records)
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
                "run_count": len(records),
                "consecutive_failures": study.state_data.consecutive_failures,
                "context_revision": study.context_data.revision,
                "consumed_context_revision": consumed_revision,
                "context_pending": study.context_data.revision > consumed_revision,
                "latest_handoff": study.context_data.latest_handoff,
                "requested_thread_policy": (
                    study.handoff_data.thread_policy if study.handoff_data else None
                ),
                "last_thread_action": last_record.get("applied_thread_action"),
                "superseded_thread_id": superseded_id,
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
            f"last={last}\truns={item['run_count']}\tfailures={item['consecutive_failures']}\t"
            f"context={item['consumed_context_revision']}/{item['context_revision']}"
        )
    for warning in data.get("warnings", []):
        lines.append(f"Warning: {warning}")
    return "\n".join(lines)


def last_run_at(root: Path, project: str) -> str | None:
    return last_run_at_from_records(session_records(root, project))


def last_run_at_from_records(records: list[dict[str, Any]]) -> str | None:
    values: list[datetime] = []
    for data in records:
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
    directory = study_directory_path(root, path, "sessions")
    prefix = directory.relative_to(root).as_posix()
    listed = subprocess.run(
        ["git", "-C", str(root), "ls-tree", "-r", "--name-only", "-z", "HEAD", "--", prefix],
        capture_output=True,
        text=True,
        check=False,
    )
    if listed.returncode != 0:
        return []
    for relative in sorted(value for value in listed.stdout.split("\0") if value.endswith(".yaml")):
        try:
            normalized = safe_repo_path(root, relative)
            if not normalized.startswith(prefix + "/"):
                continue
            shown = subprocess.run(
                ["git", "-C", str(root), "show", f"HEAD:{normalized}"],
                capture_output=True,
                text=True,
                check=False,
            )
            if shown.returncode != 0:
                continue
            data = yaml.safe_load(shown.stdout) or {}
        except (WorkspaceError, yaml.YAMLError):
            continue
        if isinstance(data, dict):
            values.append(data)
    return sorted(values, key=session_record_sort_key)


def session_record_sort_key(record: dict[str, Any]) -> tuple[datetime, str]:
    value = record.get("ended_at", record.get("started_at"))
    if isinstance(value, datetime):
        parsed = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
        parsed = parsed.astimezone(timezone.utc)
    else:
        parsed = parse_timestamp(value) if isinstance(value, str) else None
    return (
        parsed or datetime.min.replace(tzinfo=timezone.utc),
        str(record.get("run_id", "")),
    )


def consumed_context_revision(records: list[dict[str, Any]]) -> int:
    revisions = [
        record.get("context_revision")
        for record in records
        if record.get("status") == "completed"
        and record.get("context_consumed") is True
        and isinstance(record.get("context_revision"), int)
        and not isinstance(record.get("context_revision"), bool)
    ]
    return max(revisions, default=0)


def superseded_thread_id(records: list[dict[str, Any]]) -> str | None:
    return next(
        (
            str(record["replaced_thread_id"])
            for record in reversed(records)
            if record.get("applied_thread_action") in {"replace", "resume_fallback"}
            and isinstance(record.get("replaced_thread_id"), str)
            and record.get("replaced_thread_id")
            and isinstance(record.get("codex_thread_id"), str)
            and record.get("codex_thread_id") != record.get("replaced_thread_id")
        ),
        None,
    )


@contextlib.contextmanager
def workspace_lock(root: Path) -> Iterator[None]:
    path = runtime_file_path(root, LOCK_PATH)
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
    try:
        directory = runtime_directory(root, RUNNING_DIR, create=True)
    except WorkspaceError as exc:
        return active, [str(exc)]
    for path in sorted(directory.glob("*.json")):
        try:
            marker_path = safe_file(
                root,
                path,
                "running marker",
                within=directory,
            )
            data = json.loads(marker_path.read_text(encoding="utf-8"))
        except (OSError, WorkspaceError, json.JSONDecodeError):
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
        marker_path = runtime_file_path(root, RUNNING_DIR / f"{run_id}.json")
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
    return runtime_file_path(root, THREADS_DIR / f"{name}.json")


def read_thread_record(root: Path, project: str) -> dict[str, Any] | None:
    path = thread_record_path(root, project)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or set(data) != {
        "schema_version",
        "thread_id",
        "context_revision",
        "last_run_id",
        "updated_at",
    }:
        return None
    thread_id = data.get("thread_id")
    revision = data.get("context_revision")
    if (
        data.get("schema_version") != 1
        or not isinstance(thread_id, str)
        or not thread_id
        or isinstance(revision, bool)
        or not isinstance(revision, int)
        or revision < 1
    ):
        return None
    return data


def read_thread_id(root: Path, project: str) -> str | None:
    record = read_thread_record(root, project)
    return str(record["thread_id"]) if record else None


def write_thread_record(
    root: Path,
    project: str,
    thread_id: str,
    run_id: str,
    context_revision: int,
) -> None:
    atomic_write_json(
        thread_record_path(root, project),
        {
            "schema_version": 1,
            "thread_id": thread_id,
            "context_revision": context_revision,
            "last_run_id": run_id,
            "updated_at": utc_now(),
        },
    )


def workflow_prompt(study: Study, run_id: str) -> str:
    steering = study.path / "STEERING.md"
    handoff = study.handoff_data
    if handoff is None:
        raise WorkspaceError("ready study has no validated handoff")
    lines = [
        "Run one a-exp-v2 autonomous study session.",
        f"Study: {study.project}",
        f"Run ID: {run_id}",
        f"Context revision: {study.context_data.revision}",
        f"Validated handoff: {handoff.path}",
        f"Requested thread policy: {handoff.thread_policy}",
        "",
        "Use the workflow skill if available. Read AGENTS.md, the study README, GOAL.md, CONTEXT.yaml, the validated latest handoff, STATE.yaml, and any PLAN.md, DECISIONS.md, STEERING.md, prior sessions, experiments, reports, and applicable protocols.",
        "Precedence is: current committed study files, latest validated handoff, older handoffs and session records, then Codex thread memory. Resolve conflicts in that order.",
        f"Handoff summary: {handoff.summary}",
        f"Next direction: {handoff.next_direction or 'not specified'}",
        "Advance the study goal within its autonomy envelope. You may implement code and run multiple coherent foreground experiments. Do not launch unmanaged detached processes.",
        "During this autonomous run, do not run `git add` or `git commit`. Leave every intended study change in the worktree and declare every changed path in `files_changed`; the outer runner validates and commits those changes during closeout. Read-only `.git` access is expected and is not a reason to request `needs_human`. GPU-produced experiment records must declare `producer: autonomous`.",
        "Do not edit GOAL.md, STEERING.md, CONTEXT.yaml, anything under handoffs/, STATE.yaml, or anything under sessions/. These are interactive- or runner-owned control files.",
        "Do not edit files under any other projects/<study>/ directory during this selected study run.",
        "Use an explicit packet for separately scoped a-dev work rather than adding scheduler work units.",
        "",
        "Your final response must satisfy the supplied JSON schema. Declare every repo path changed during this run. Request exactly one next state: ready, needs_human, paused, blocked, or completed. `needs_human` requires a concrete human-owned blocker classified as `scientific_decision`, `approval_required`, or `external_resource_unavailable`; runner-owned Git closeout and transient infrastructure failures do not qualify.",
    ]
    if steering.exists():
        lines.append("STEERING.md is present and must be incorporated before choosing further work.")
    if handoff.interactive_experiments:
        lines.append(
            "Interactive evidence baseline: " + ", ".join(handoff.interactive_experiments)
        )
    return "\n".join(lines)


def validate_closeout(value: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, dict):
        return ["closeout must be an object"]
    required = {
        "outcome",
        "next_state",
        "blocker_kind",
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
    blocker_kind = value.get("blocker_kind")
    if blocker_kind == "runner_git_commit":
        errors.append(
            "blocker_kind runner_git_commit is invalid because Git closeout is runner-owned"
        )
    elif next_state == "needs_human":
        if blocker_kind not in HUMAN_BLOCKER_KINDS:
            errors.append(
                "needs_human requires blocker_kind to be one of: "
                + ", ".join(sorted(HUMAN_BLOCKER_KINDS))
            )
        open_questions = value.get("open_questions")
        if isinstance(open_questions, list) and not open_questions:
            errors.append("needs_human requires at least one open question")
    elif blocker_kind is not None:
        errors.append("blocker_kind must be null unless next_state is needs_human")
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


def plan_thread_action(
    study: Study,
    record: dict[str, Any] | None,
) -> tuple[str | None, str, str | None]:
    handoff = study.handoff_data
    if handoff is None:
        raise WorkspaceError("ready study has no validated handoff")
    if record is None:
        return None, "new", None
    mapped_revision = int(record["context_revision"])
    mapped_thread_id = str(record["thread_id"])
    if mapped_revision > study.context_data.revision:
        raise WorkspaceError(
            "machine-local thread mapping is newer than committed CONTEXT.yaml"
        )
    root = study.path.parents[1]
    _, chain = load_handoff_chain(root, study.path, study.context_data)
    pending_handoffs = [
        item for item in chain if item.context_revision > mapped_revision
    ]
    if any(item.thread_policy == "replace" for item in pending_handoffs):
        return None, "replace", mapped_thread_id
    return mapped_thread_id, "resume", None


def run_once(root: Path) -> dict[str, Any] | None:
    claim = claim_next_study(root)
    if claim is None:
        return None
    study, run_id, marker_path, started_at = claim
    try:
        run_path = runtime_file_path(root, RUNS_DIR / f"{run_id}.json")
        log_path = runtime_file_path(root, LOGS_DIR / f"{study.project}-{run_id}.jsonl")
        brief_log_path = brief_log_path_for(log_path)
        runtime_file_path(root, brief_log_path.relative_to(root))
        output_message = runtime_file_path(root, OUTPUT_DIR / f"{run_id}.json")
        base_commit = git_head(root)
        goal_hash = content_hash(study_file_path(root, study.path, "GOAL.md"))
        steering_path = study.path / "STEERING.md"
        steering_hash = (
            content_hash(study_file_path(root, study.path, "STEERING.md"))
            if os.path.lexists(steering_path)
            else None
        )
        prior_thread_record = read_thread_record(root, study.project)
        previous_thread_id = (
            str(prior_thread_record["thread_id"]) if prior_thread_record else None
        )
        run_thread_id, thread_action, replaced_thread_id = plan_thread_action(
            study, prior_thread_record
        )
        assert study.handoff_data is not None
        requested_thread_policy = study.handoff_data.thread_policy
        prompt = workflow_prompt(study, run_id)
        runtime_before = runtime_control_hashes(root)
    except Exception:
        marker_path.unlink(missing_ok=True)
        raise
    result: CodexRunResult | None = None
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
                    thread_id=run_thread_id,
                )
                if run_thread_id and result.returncode != 0 and not result.turn_started:
                    replaced_thread_id = run_thread_id
                    thread_action = "resume_fallback"
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
        runtime_after = runtime_control_hashes(root)
        runtime_owned_changes = sorted(
            path
            for path in set(runtime_before) | set(runtime_after)
            if runtime_before.get(path) != runtime_after.get(path)
        )
        thread_id = result.thread_id or run_thread_id or previous_thread_id
        replacement_attempt = thread_action in {"replace", "resume_fallback"}
        if result.thread_id and not (
            replacement_attempt and result.thread_id == replaced_thread_id
        ):
            write_thread_record(
                root,
                study.project,
                result.thread_id,
                run_id,
                study.context_data.revision,
            )
        elif run_thread_id and result.turn_started and not replacement_attempt:
            write_thread_record(
                root,
                study.project,
                run_thread_id,
                run_id,
                study.context_data.revision,
            )
        errors = validate_closeout(result.closeout)
        if result.closeout_error:
            errors.append(result.closeout_error)
        if result.returncode != 0:
            errors.append(f"codex exited {result.returncode}")
        if result.returncode == 0 and not result.turn_started:
            errors.append("codex reported success without starting a turn")
        if thread_action in {"new", "replace", "resume_fallback"} and not result.thread_id:
            errors.append(f"{thread_action} did not produce a new Codex thread ID")
        if (
            replacement_attempt
            and result.thread_id
            and result.thread_id == replaced_thread_id
        ):
            errors.append(f"{thread_action} returned the superseded Codex thread ID")
        if runtime_owned_changes:
            errors.append(
                "autonomous run modified runner-owned runtime path(s): "
                + ", ".join(runtime_owned_changes)
            )
        history_rewritten = not git_head_descends_from(root, base_commit)
        if history_rewritten:
            errors.append("autonomous run rewrote Git history before its claimed base commit")
        actual_paths = set(git_changed_paths_since(root, base_commit))
        experiment_contract_violated = False
        for changed_path in sorted(actual_paths):
            parts = Path(changed_path).parts
            if (
                len(parts) >= 4
                and parts[0] == "projects"
                and parts[2] == "experiments"
                and parts[-1] == "EXPERIMENT.md"
            ):
                if len(parts) != 5:
                    experiment_contract_violated = True
                    errors.append(
                        f"{changed_path}: EXPERIMENT.md must use "
                        "experiments/<experiment-id>/EXPERIMENT.md"
                    )
                else:
                    try:
                        producer = experiment_producer(root / changed_path)
                    except ValueError as exc:
                        experiment_contract_violated = True
                        errors.append(f"{changed_path}: {exc}")
                    else:
                        if producer != "autonomous":
                            experiment_contract_violated = True
                            errors.append(
                                f"autonomous run experiment {changed_path} must declare "
                                "producer: autonomous"
                            )
        control_filenames = {"GOAL.md", "STEERING.md", CONTEXT_FILENAME, "STATE.yaml"}
        forbidden_changes = []
        for changed_path in actual_paths:
            parts = Path(changed_path).parts
            forbidden = changed_path.startswith(".a-exp/")
            if len(parts) >= 2 and parts[0] == "projects":
                forbidden = forbidden or parts[1] != study.project
                if len(parts) >= 3:
                    forbidden = forbidden or parts[2] in control_filenames
                    forbidden = forbidden or parts[2] in {HANDOFFS_DIRNAME, "sessions"}
            if forbidden:
                forbidden_changes.append(changed_path)
        forbidden_changes.sort()
        state_changed = bool(
            forbidden_changes
            or runtime_owned_changes
            or experiment_contract_violated
            or history_rewritten
        )
        if forbidden_changes:
            errors.append(
                "autonomous run modified forbidden path(s): "
                + ", ".join(forbidden_changes)
            )
        _, post_run_issues = discover_studies(root)
        if post_run_issues:
            errors.append(
                "autonomous run left an invalid workspace: "
                + "; ".join(sorted(set(post_run_issues)))
            )
            state_changed = True
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
            state_changed = True
        if errors:
            failure_record = handle_failed_run_safely(
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
                requested_thread_policy=requested_thread_policy,
                thread_action=thread_action,
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
                requested_thread_policy=requested_thread_policy,
                thread_action=thread_action,
                declared=declared,
                run_path=run_path,
                log_path=log_path,
                brief_log_path=brief_log_path,
            )
        except Exception as exc:
            detail = f"{type(exc).__name__}: {exc}"
            failure_record = handle_failed_run_safely(
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
                requested_thread_policy=requested_thread_policy,
                thread_action=thread_action,
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
    requested_thread_policy: str,
    thread_action: str,
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
    sessions_directory = study_directory_path(root, study.path, "sessions", create=True)
    session_path = safe_file(
        root,
        sessions_directory / f"{run_id}.yaml",
        f"session record for {study.project}",
        within=sessions_directory,
    )
    state_path = study_file_path(root, study.path, "STATE.yaml")
    session_record = {
        "schema_version": 2,
        "run_id": run_id,
        "study": study.project,
        "status": "completed",
        "outcome": closeout["outcome"],
        "blocker_kind": closeout["blocker_kind"],
        "previous_state": study.state_data.state,
        "next_state": next_state,
        "started_at": started_at,
        "ended_at": ended_at,
        "codex_thread_id": thread_id,
        "replaced_thread_id": replaced_thread_id,
        "context_revision": study.context_data.revision,
        "handoff_id": study.context_data.latest_handoff,
        "requested_thread_policy": requested_thread_policy,
        "applied_thread_action": thread_action,
        "context_consumed": True,
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
    validate_committed_session_record(session_record)
    atomic_write_text(session_path, yaml.safe_dump(session_record, sort_keys=False))
    write_study_state(state_path, state)
    owned = {
        session_path.relative_to(root).as_posix(),
        state_path.relative_to(root).as_posix(),
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
    atomic_write_json(runtime_file_path(root, run_path.relative_to(root)), runtime)
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
    requested_thread_policy: str,
    thread_action: str,
    errors: list[str],
    unsafe: bool,
    run_path: Path,
    log_path: Path,
    brief_log_path: Path,
) -> dict[str, Any]:
    clean = git_clean(root)
    runtime = {
        "schema_version": 2,
        "run_id": run_id,
        "project": study.project,
        "study": study.project,
        "status": "failed",
        "study_outcome": "infrastructure_failed",
        "blocker_kind": None,
        "previous_state": study.state_data.state,
        "next_state": "recovery_required" if not clean or unsafe else "ready",
        "started_at": started_at,
        "ended_at": utc_now(),
        "codex_thread_id": thread_id,
        "replaced_thread_id": replaced_thread_id,
        "context_revision": study.context_data.revision,
        "handoff_id": study.context_data.latest_handoff,
        "requested_thread_policy": requested_thread_policy,
        "applied_thread_action": thread_action,
        "context_consumed": False,
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
        atomic_write_json(runtime_file_path(root, run_path.relative_to(root)), runtime)
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
    sessions_directory = study_directory_path(root, study.path, "sessions", create=True)
    session_path = safe_file(
        root,
        sessions_directory / f"{run_id}.yaml",
        f"failure session record for {study.project}",
        within=sessions_directory,
    )
    state_path = study_file_path(root, study.path, "STATE.yaml")
    failure_session = {
        "schema_version": 2,
        "run_id": run_id,
        "study": study.project,
        "status": "failed",
        "outcome": "infrastructure_failed",
        "blocker_kind": None,
        "previous_state": study.state_data.state,
        "next_state": next_state,
        "started_at": started_at,
        "ended_at": runtime["ended_at"],
        "codex_thread_id": thread_id,
        "replaced_thread_id": replaced_thread_id,
        "context_revision": study.context_data.revision,
        "handoff_id": study.context_data.latest_handoff,
        "requested_thread_policy": requested_thread_policy,
        "applied_thread_action": thread_action,
        "context_consumed": False,
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
    validate_committed_session_record(failure_session)
    runtime.update(
        {
            "summary": failure_session["summary"],
            "blocker_kind": failure_session["blocker_kind"],
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
    write_study_state(state_path, state)
    closeout_commit = commit_workspace_changes(
        root,
        f"Record failed a-exp run {run_id} for {study.project}",
        [session_path.relative_to(root), state_path.relative_to(root)],
    )
    runtime["closeout_commit"] = closeout_commit
    atomic_write_json(runtime_file_path(root, run_path.relative_to(root)), runtime)
    return runtime


def handle_failed_run_safely(**kwargs: Any) -> dict[str, Any]:
    try:
        return handle_failed_run(**kwargs)
    except Exception as exc:
        root = kwargs["root"]
        study = kwargs["study"]
        run_id = kwargs["run_id"]
        result = kwargs["result"]
        run_path = kwargs["run_path"]
        log_path = kwargs["log_path"]
        brief_log_path = kwargs["brief_log_path"]
        errors = list(kwargs["errors"])
        errors.append(f"failure closeout failed: {type(exc).__name__}: {exc}")
        fallback = {
            "schema_version": 2,
            "run_id": run_id,
            "project": study.project,
            "study": study.project,
            "status": "failed",
            "study_outcome": "infrastructure_failed",
            "previous_state": study.state_data.state,
            "next_state": "recovery_required",
            "started_at": kwargs["started_at"],
            "ended_at": utc_now(),
            "codex_thread_id": kwargs["thread_id"],
            "replaced_thread_id": kwargs["replaced_thread_id"],
            "context_revision": study.context_data.revision,
            "handoff_id": study.context_data.latest_handoff,
            "requested_thread_policy": kwargs["requested_thread_policy"],
            "applied_thread_action": kwargs["thread_action"],
            "context_consumed": False,
            "exit_code": result.returncode,
            "timed_out": result.timed_out,
            "duration_seconds": result.duration_seconds,
            "log_file": log_path.relative_to(root).as_posix(),
            "brief_log_file": brief_log_path.relative_to(root).as_posix(),
            "closeout_validation": {"ok": False, "errors": sorted(set(errors))},
        }
        try:
            write_recovery(root, run_id, study.project, errors)
        except Exception as recovery_exc:
            errors.append(
                f"recovery record failed: {type(recovery_exc).__name__}: {recovery_exc}"
            )
            fallback["closeout_validation"]["errors"] = sorted(set(errors))
        try:
            atomic_write_json(runtime_file_path(root, run_path.relative_to(root)), fallback)
        except Exception:
            pass
        return fallback


def write_recovery(root: Path, run_id: str, project: str, errors: list[str]) -> None:
    atomic_write_json(
        runtime_file_path(root, RECOVERY_DIR / f"{run_id}.json"),
        {
            "run_id": run_id,
            "project": project,
            "created_at": utc_now(),
            "errors": sorted(set(errors)),
            "git_status": git_status_paths(root),
        },
    )
