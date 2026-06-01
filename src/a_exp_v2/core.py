from __future__ import annotations

import json
import hashlib
import os
import re
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path
from typing import Any
from uuid import uuid4

from .config import (
    DEFAULT_MAX_DURATION_MS,
    DEFAULT_MODEL,
    DEFAULT_PRIORITY,
    ProjectLaneConfig,
    WorkspaceConfig,
    dump_config,
    load_config,
)


CONFIG_PATH = Path(".a-exp/config.yaml")
RUNS_DIR = Path(".a-exp/runs")
LOGS_DIR = Path(".a-exp/logs")
RUNNING_DIR = Path(".a-exp/running")

TASK_RE = re.compile(r"^- \[([ xX])\]\s+(.+?)\s*$")
BLOCKED_RE = re.compile(r"\[(?:blocked-by:\s*[^\]]+|approval-needed(?::\s*[^\]]+)?)\]", re.I)
ACTIVE_EXPERIMENT_STATUSES = {"running", "retrying", "stopping"}


class AExpError(Exception):
    exit_code = 3


class WorkspaceError(AExpError):
    exit_code = 2


class AgentRunFailed(AExpError):
    exit_code = 1


@dataclass
class Task:
    title: str
    done: bool
    blocked: bool
    line_number: int


@dataclass
class Lane:
    project: str
    enabled: bool
    priority: int
    model: str
    max_duration_ms: int
    tasks: list[Task]
    valid: bool = True
    invalid_reason: str | None = None
    active_run_id: str | None = None

    @property
    def open_tasks(self) -> int:
        return sum(1 for task in self.tasks if not task.done)

    @property
    def blocked_tasks(self) -> int:
        return sum(1 for task in self.tasks if not task.done and task.blocked)

    @property
    def runnable_tasks(self) -> int:
        if not self.enabled or self.active_run_id or not self.valid:
            return 0
        return sum(1 for task in self.tasks if not task.done and not task.blocked)

    @property
    def first_runnable_task(self) -> Task | None:
        for task in self.tasks:
            if not task.done and not task.blocked:
                return task
        return None

    @property
    def state(self) -> str:
        if not self.valid:
            return "invalid"
        if not self.enabled:
            return "disabled"
        if self.active_run_id:
            return "running"
        if self.runnable_tasks > 0:
            return "runnable"
        if self.open_tasks > 0:
            return "blocked"
        return "empty"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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
    paths = [
        root / ".a-exp",
        root / ".a-exp" / "runs",
        root / ".a-exp" / "logs",
        root / ".a-exp" / "running",
        root / ".agents" / "skills",
        root / "docs",
        root / "projects",
        root / "modules",
        root / "reports" / "kanban",
        root / "reports" / "packet",
        root / "reports" / "project",
        root / "reports" / "research",
    ]
    for path in paths:
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            created.append(path)

    files = {
        root / CONFIG_PATH: default_config_text(),
        root / ".a-exp" / "kit.lock.yaml": "source: local\nversion: 2\n",
        root / ".gitignore": default_gitignore_text(),
        root / "AGENTS.md": default_agents_text(),
        root / "modules" / "registry.yaml": "entries: []\n",
        root / "APPROVAL_QUEUE.md": default_approval_queue(),
    }
    for path, content in files.items():
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            created.append(path)
    created.extend(copy_package_tree(root, "skill_templates/skills", ".agents/skills"))
    created.extend(copy_package_tree(root, "doc_templates", "docs"))
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


def commit_created_workspace_files(root: Path, created: list[Path]) -> None:
    stage_paths = sorted(
        {
            str(path.relative_to(root))
            for path in created
            if path.exists() and not path.is_dir() and path.name != ".git"
        }
    )
    if not stage_paths:
        return

    result = subprocess.run(
        ["git", "-C", str(root), "add", "--", *stage_paths],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "git add failed"
        raise WorkspaceError(detail)

    diff = subprocess.run(
        ["git", "-C", str(root), "diff", "--cached", "--quiet", "--exit-code"],
        capture_output=True,
        text=True,
        check=False,
    )
    if diff.returncode == 0:
        return
    if diff.returncode != 1:
        detail = diff.stderr.strip() or diff.stdout.strip() or "git diff --cached failed"
        raise WorkspaceError(detail)

    commit = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-m",
            "Initialize a-exp-v2 workspace",
        ],
        capture_output=True,
        text=True,
        check=False,
        env=git_commit_env(),
    )
    if commit.returncode != 0:
        detail = commit.stderr.strip() or commit.stdout.strip() or "git commit failed"
        raise WorkspaceError(detail)


def commit_workspace_changes(root: Path, message: str) -> None:
    add = subprocess.run(
        ["git", "-C", str(root), "add", "--all", "--", "."],
        capture_output=True,
        text=True,
        check=False,
    )
    if add.returncode != 0:
        detail = add.stderr.strip() or add.stdout.strip() or "git add failed"
        raise WorkspaceError(detail)

    diff = subprocess.run(
        ["git", "-C", str(root), "diff", "--cached", "--quiet", "--exit-code"],
        capture_output=True,
        text=True,
        check=False,
    )
    if diff.returncode == 0:
        return
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


def git_commit_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("GIT_AUTHOR_NAME", "a-exp-v2")
    env.setdefault("GIT_AUTHOR_EMAIL", "a-exp-v2@example.local")
    env.setdefault("GIT_COMMITTER_NAME", "a-exp-v2")
    env.setdefault("GIT_COMMITTER_EMAIL", "a-exp-v2@example.local")
    return env


def copy_package_tree(root: Path, package_subdir: str, destination: str) -> list[Path]:
    created: list[Path] = []
    source = resources.files("a_exp_v2").joinpath(package_subdir)
    dest_root = root / destination

    def copy_dir(current: Any, rel_parts: tuple[str, ...] = ()) -> None:
        for item in current.iterdir():
            next_parts = (*rel_parts, item.name)
            if item.is_dir():
                copy_dir(item, next_parts)
                continue
            if not item.is_file():
                continue
            dest = dest_root.joinpath(*next_parts)
            if dest.exists():
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(item.read_bytes())
            created.append(dest)

    copy_dir(source)
    return created


def default_config_text() -> str:
    return (
        "layout_version: 1\n"
        "defaults:\n"
        f"  model: {DEFAULT_MODEL}\n"
        f"  max_duration_ms: {DEFAULT_MAX_DURATION_MS}\n"
        "projects: {}\n"
    )


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

This repository is an a-exp-v2 workspace.

## Fast Orientation

- `AGENTS.md`: first-read orientation for this workspace.
- `.a-exp/config.yaml`: lane defaults and per-project enablement, priority,
  model, and timeout.
- `.a-exp/runs/*.json`: completed or failed run records.
- `.a-exp/logs/`: live-streamed `codex exec` stdout/stderr for each run.
- `.a-exp/running/*.json`: active-run markers used to keep one run active at a
  time.
- `.agents/skills/`: workflow, project, review, report, packet, and diagnose
  skills.
- `projects/<project>/README.md`: durable project context, decisions, closeout
  notes, and artifact references.
- `projects/<project>/TASKS.md`: the project work lane. Unchecked tasks are
  open; `[blocked-by: ...]` and `[approval-needed: ...]` keep tasks from being
  runnable.
- `projects/<project>/plans/`: optional plans for larger work.
- `projects/<project>/experiments/<id>/EXPERIMENT.md`: experiment design,
  results, and findings.
- `projects/<project>/experiments/<id>/progress.json`: active experiment state;
  `running`, `retrying`, and `stopping` count as running.
- `projects/<project>/budget.yaml` and `ledger.yaml`: optional budget and spend
  memory.
- `modules/registry.yaml`: optional registry for reusable modules and artifacts.
- `reports/`: cross-project reports, packets, research, and generated kanban
  summaries.
- `APPROVAL_QUEUE.md`: durable human approval queue.

## Work Cycle

Use the `workflow` skill for external-scheduler-triggered work. Select one
runnable task from a project, triage the execution mode, complete or hand off
that task, and close out into durable project memory.

Durable memory lives under `projects/<project>/`. Runtime provenance lives under
`.a-exp/`.

For project creation, create only the files the project currently needs. The
minimum useful project is `projects/<project>/README.md` plus
`projects/<project>/TASKS.md`; add plans, experiments, budgets, ledgers, and
reports when the task actually needs them.
"""


def default_approval_queue() -> str:
    return """# Approval Queue

## Pending

## Completed
"""


def parse_tasks(path: Path) -> list[Task]:
    if not path.exists():
        return []
    tasks = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        match = TASK_RE.match(line)
        if not match:
            continue
        title = match.group(2).strip()
        tasks.append(
            Task(
                title=title,
                done=match.group(1).lower() == "x",
                blocked=bool(BLOCKED_RE.search(title)),
                line_number=line_number,
            )
        )
    return tasks


def _active_run_by_project(root: Path) -> dict[str, str]:
    active: dict[str, str] = {}
    running_dir = root / RUNNING_DIR
    if not running_dir.exists():
        return active
    for path in sorted(running_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        pid = data.get("pid")
        project = data.get("project")
        if isinstance(pid, int) and not _pid_alive(pid):
            path.unlink(missing_ok=True)
            continue
        if isinstance(project, str):
            active[project] = str(data.get("run_id", path.stem))
    return active


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def discover_lanes(root: Path) -> list[Lane]:
    config = load_config(root / CONFIG_PATH)
    active = _active_run_by_project(root)
    projects_dir = root / "projects"
    names = set(config.projects)
    if projects_dir.exists():
        for path in projects_dir.iterdir():
            if path.is_dir() and (path / "TASKS.md").exists():
                names.add(path.name)

    lanes = []
    for name in sorted(names):
        lane_config = config.projects.get(name, ProjectLaneConfig())
        tasks_path = projects_dir / name / "TASKS.md"
        valid = tasks_path.exists()
        defaults = config.defaults
        lanes.append(
            Lane(
                project=name,
                enabled=lane_config.enabled is not False and valid,
                priority=lane_config.priority,
                model=lane_config.model or str(defaults.get("model", DEFAULT_MODEL)),
                max_duration_ms=int(
                    lane_config.max_duration_ms
                    or defaults.get("max_duration_ms", DEFAULT_MAX_DURATION_MS)
                ),
                tasks=parse_tasks(tasks_path),
                valid=valid,
                invalid_reason=None if valid else f"Missing {tasks_path.relative_to(root)}",
                active_run_id=active.get(name),
            )
        )
    return lanes


def set_project_enabled(root: Path, project: str, enabled: bool) -> None:
    tasks_path = root / "projects" / project / "TASKS.md"
    if not tasks_path.exists():
        raise WorkspaceError(f"Project has no TASKS.md: projects/{project}/TASKS.md")
    config_path = root / CONFIG_PATH
    config = load_config(config_path)
    lane = config.projects.get(project, ProjectLaneConfig())
    lane.enabled = enabled
    if lane.priority == DEFAULT_PRIORITY:
        lane.priority = DEFAULT_PRIORITY
    config.projects[project] = lane
    dump_config(config, config_path)


def pending_approvals(root: Path) -> int:
    path = root / "APPROVAL_QUEUE.md"
    if not path.exists():
        return 0
    text = path.read_text(encoding="utf-8")
    pending_match = re.search(r"(?ims)^## Pending\s*$\n(?P<body>.*?)(?=^##\s+|\Z)", text)
    body = pending_match.group("body") if pending_match else ""
    return sum(1 for line in body.splitlines() if line.strip().startswith("- [ ]"))


def running_experiments(root: Path) -> int:
    count = 0
    for path in sorted((root / "projects").glob("*/experiments/*/progress.json")):
        try:
            status = json.loads(path.read_text(encoding="utf-8")).get("status")
        except json.JSONDecodeError:
            continue
        if status in ACTIVE_EXPERIMENT_STATUSES:
            count += 1
    return count


def status_json(root: Path) -> dict[str, Any]:
    lanes = discover_lanes(root)
    items = []
    for lane in lanes:
        item = {
            "id": lane.project,
            "kind": "project",
            "project": lane.project,
            "enabled": lane.enabled,
            "priority": lane.priority,
            "state": lane.state,
            "running": lane.state == "running",
            "active_run_id": lane.active_run_id,
            "open_tasks": lane.open_tasks,
            "blocked_tasks": lane.blocked_tasks,
            "runnable_tasks": lane.runnable_tasks,
            "last_run_at": last_run_at(root, lane.project),
            "run_count": run_count(root, lane.project),
        }
        if lane.invalid_reason:
            item["error"] = lane.invalid_reason
        items.append(item)

    active_sessions = sum(1 for lane in lanes if lane.state == "running")
    return {
        "health": "ok" if not any(lane.state == "invalid" for lane in lanes) else "degraded",
        "sessions": {"active": active_sessions},
        "experiments": {"running": running_experiments(root)},
        "approvals": {"pending": pending_approvals(root)},
        "jobs": {
            "total": len(lanes),
            "enabled": sum(1 for lane in lanes if lane.enabled),
            "disabled": sum(1 for lane in lanes if not lane.enabled),
            "runnable": sum(1 for lane in lanes if lane.state == "runnable"),
            "blocked": sum(1 for lane in lanes if lane.state == "blocked"),
            "running": sum(1 for lane in lanes if lane.state == "running"),
            "empty": sum(1 for lane in lanes if lane.state == "empty"),
            "invalid": sum(1 for lane in lanes if lane.state == "invalid"),
            "items": items,
        },
    }


def last_run_at(root: Path, project: str) -> str | None:
    latest = None
    for path in (root / RUNS_DIR).glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if data.get("project") == project and data.get("started_at"):
            latest = max(latest or data["started_at"], data["started_at"])
    return latest


def run_count(root: Path, project: str) -> int:
    count = 0
    for path in (root / RUNS_DIR).glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if data.get("project") == project and data.get("status") != "skipped":
            count += 1
    return count


def format_status(data: dict[str, Any]) -> str:
    jobs = data["jobs"]
    lines = [
        "=== a-exp-v2 Status ===",
        f"Active Sessions: {data['sessions']['active']}  |  Running Experiments: {data['experiments']['running']}  |  Jobs: {jobs['enabled']}/{jobs['total']} enabled",
        f"Runnable: {jobs['runnable']}  |  Blocked: {jobs['blocked']}  |  Pending Approvals: {data['approvals']['pending']}",
        "",
        "--- Jobs ---",
    ]
    if not jobs["items"]:
        lines.append("  none")
    for item in jobs["items"]:
        last = item["last_run_at"] or "never"
        lines.append(
            f"  {item['id']}\t{item['state']}\tpriority={item['priority']}\t"
            f"tasks={item['runnable_tasks']}/{item['open_tasks']} runnable\t"
            f"last={last}\truns={item['run_count']}"
        )
    return "\n".join(lines)


def select_lane(root: Path) -> Lane | None:
    lanes = [lane for lane in discover_lanes(root) if lane.state == "runnable"]
    if not lanes:
        return None
    return sorted(lanes, key=lambda lane: (lane.priority, lane.project))[0]


def run_once(root: Path) -> dict[str, Any] | None:
    data = status_json(root)
    if data["sessions"]["active"] > 0:
        return None
    lane = select_lane(root)
    if lane is None:
        return None
    task = lane.first_runnable_task
    if task is None:
        return None

    run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"
    run_path = root / RUNS_DIR / f"{run_id}.json"
    log_path = root / LOGS_DIR / f"{lane.project}-{run_id}.log"
    brief_log_path = brief_log_path_for(log_path)
    marker_path = root / RUNNING_DIR / f"{run_id}.json"
    started_at = utc_now()
    marker = {
        "run_id": run_id,
        "project": lane.project,
        "task": task.title,
        "pid": os.getpid(),
        "started_at": started_at,
        "log_file": str(log_path.relative_to(root)),
        "brief_log_file": str(brief_log_path.relative_to(root)),
    }
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    marker_path.write_text(json.dumps(marker, indent=2) + "\n", encoding="utf-8")
    before = durable_memory_snapshot(root, lane.project)
    try:
        prompt = workflow_prompt(lane, task)
        result = launch_agent(root, prompt, lane, log_path)
        after = durable_memory_snapshot(root, lane.project)
        validation = validate_closeout(before, after, task.title)
        status = "completed" if result.returncode == 0 and validation["ok"] else "failed"
        record = {
            "run_id": run_id,
            "project": lane.project,
            "task": task.title,
            "mode": "workflow-selected",
            "status": status,
            "started_at": started_at,
            "ended_at": utc_now(),
            "exit_code": result.returncode,
            "log_file": str(log_path.relative_to(root)),
            "brief_log_file": str(brief_log_path.relative_to(root)),
            "closeout_validation": validation,
        }
        run_path.parent.mkdir(parents=True, exist_ok=True)
        run_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        if status != "completed":
            raise AgentRunFailed(f"Agent run failed or closeout validation failed: {run_id}")
        commit_workspace_changes(root, f"Run a-exp-v2 task for {lane.project}")
        return record
    finally:
        marker_path.unlink(missing_ok=True)


def durable_memory_snapshot(root: Path, project: str) -> dict[str, dict[str, str]]:
    snapshot = {}
    roots = [
        root / "projects" / project,
        root / "reports",
    ]
    files = []
    for memory_root in roots:
        if memory_root.exists():
            files.extend(path for path in memory_root.glob("**/*") if path.is_file())
    approval_queue = root / "APPROVAL_QUEUE.md"
    if approval_queue.exists():
        files.append(approval_queue)

    for path in files:
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            snapshot[str(path.relative_to(root))] = {
                "hash": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                "content": content,
            }
        except OSError:
            continue
    return snapshot


def validate_closeout(
    before: dict[str, dict[str, str]],
    after: dict[str, dict[str, str]],
    task_title: str,
) -> dict[str, Any]:
    changed = sorted(
        path for path, item in after.items()
        if before.get(path, {}).get("hash") != item["hash"]
    )
    durable_changed = [
        path for path in changed
        if path.startswith("projects/") or path.startswith("reports/") or path == "APPROVAL_QUEUE.md"
    ]
    changed_text = "\n\n".join(after[path]["content"] for path in durable_changed)
    task_mentioned = task_title in changed_text
    outcome_recorded = bool(
        re.search(r"(?im)^\s*(Status|Outcome):\s*(completed|blocked|deferred|failed|partial)\b", changed_text)
        or re.search(r"(?im)^-\s+\[x\]\s+" + re.escape(task_title) + r"\b", changed_text)
        or re.search(r"(?im)^-\s+\[ \]\s+" + re.escape(task_title) + r".*\[(blocked-by|approval-needed)", changed_text)
    )
    verification_recorded = bool(
        re.search(r"(?im)^\s*Verification\s*:", changed_text)
        and re.search(r"(?im)^\s*-\s*Command\s*:", changed_text)
        and re.search(r"(?im)^\s*-\s*Result\s*:", changed_text)
    )
    checks = {
        "durable_memory_changed": bool(durable_changed),
        "task_mentioned": task_mentioned,
        "outcome_recorded": outcome_recorded,
        "verification_recorded": verification_recorded,
    }
    ok = all(checks.values())
    return {
        "ok": ok,
        "checks": checks,
        "changed_durable_memory_files": durable_changed,
        "message": "closeout validated" if ok else "closeout missing required evidence",
    }


def workflow_prompt(lane: Lane, task: Task) -> str:
    return "\n".join(
        [
            "Run one a-exp-v2 workflow cycle.",
            f"Project: {lane.project}",
            f"Selected task: {task.title}",
            "",
            "Use the workflow skill if available. Orient on the project README and TASKS.md, triage conventional vs goal-mode vs approval vs defer, execute only this task, and close out into durable project memory.",
            "Do not chain into follow-up tasks unless the human explicitly requested continued work.",
            "Record verification evidence and artifacts in project memory.",
        ]
    )


def brief_log_path_for(log_path: Path) -> Path:
    return log_path.with_name(f"{log_path.stem}.brief{log_path.suffix}")


class BriefLogWriter:
    def __init__(self, log: Any) -> None:
        self.log = log
        self.state = "idle"
        self.agent_lines = 0
        self.final_lines = 0
        self.final_started = False
        self.folded_lines = 0
        self.fold_notice_written = False

    def start(self, lane: Lane, timeout: int) -> None:
        self.log.write(
            "# codex exec brief log\n\n"
            f"Project: {lane.project}\n"
            f"Started: {utc_now()}\n"
            f"Timeout: {timeout}s\n\n"
        )
        self.log.flush()

    def process_line(self, stream: str, line: str) -> None:
        content = line.rstrip("\n")
        if stream == "stdout":
            self._finalize_fold()
            self._write_final_output(content)
            return

        stripped = content.strip()
        if stripped == "codex":
            self._finalize_fold()
            self.state = "agent"
            self.agent_lines = 0
            self.log.write("\n## Agent update\n")
            self.log.flush()
            return
        if stripped == "exec":
            self._finalize_fold()
            self.state = "expect_command"
            self.log.write("\n## Command\n")
            self.log.flush()
            return
        if stripped == "tokens used":
            self._finalize_fold()
            self.state = "expect_tokens"
            return

        if self.state == "expect_command":
            if stripped:
                self.log.write(f"- Command: `{self._truncate(stripped, 260)}`\n")
                self.state = "expect_result"
                self.log.flush()
            return
        if self.state == "expect_result":
            if stripped:
                if stripped.startswith(("succeeded", "failed", "exited", "timed out")):
                    self.log.write(f"- Result: {self._truncate(stripped, 260)}\n")
                    self.state = "tool_output"
                    self.folded_lines = 0
                    self.fold_notice_written = False
                    self.log.flush()
                else:
                    self.log.write(f"- Detail: {self._truncate(stripped, 260)}\n")
                    self.log.flush()
            return
        if self.state == "tool_output":
            if stripped:
                self.folded_lines += 1
                if not self.fold_notice_written:
                    self.log.write("- Output: folding command output; see full log for details.\n")
                    self.fold_notice_written = True
                    self.log.flush()
            return
        if self.state == "expect_tokens":
            if stripped:
                self.log.write(f"\nTokens used: {self._truncate(stripped, 80)}\n")
                self.state = "idle"
                self.log.flush()
            return
        if self.state == "agent":
            if stripped:
                self.agent_lines += 1
                if self.agent_lines <= 4:
                    self.log.write(f"{self._truncate(stripped, 320)}\n")
                elif self.agent_lines == 5:
                    self.log.write("... folded additional agent text; see full log for details.\n")
                self.log.flush()
            return

    def finish(self, returncode: int, duration: int, timed_out: bool) -> None:
        self._finalize_fold()
        if timed_out:
            self.log.write("\nTimed out.\n")
        self.log.write(
            "\n## Summary\n"
            f"Duration: {duration}s\n"
            f"Exit code: {returncode}\n"
        )
        self.log.flush()

    def _write_final_output(self, content: str) -> None:
        if not self.final_started:
            self.final_started = True
            self.log.write("\n## Final output\n")
        if content.strip():
            self.final_lines += 1
            if self.final_lines <= 12:
                self.log.write(f"{self._truncate(content, 360)}\n")
            elif self.final_lines == 13:
                self.log.write("... folded additional final output; see full log for details.\n")
            self.log.flush()

    def _finalize_fold(self) -> None:
        if self.state == "tool_output" and self.folded_lines:
            self.log.write(f"- Folded output lines: {self.folded_lines}\n")
            self.log.flush()
        self.folded_lines = 0
        self.fold_notice_written = False

    @staticmethod
    def _truncate(text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        return text[: limit - 3] + "..."


def launch_agent(root: Path, prompt: str, lane: Lane, log_path: Path) -> subprocess.CompletedProcess[str]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    brief_log_path = brief_log_path_for(log_path)
    env = os.environ.copy()
    env["A_EXP_PROJECT"] = lane.project
    env["A_EXP_MODEL"] = lane.model
    env["A_EXP_MAX_DURATION_MS"] = str(lane.max_duration_ms)
    command = ["codex", "exec", prompt]
    started = time.time()
    timeout = max(1, int(lane.max_duration_ms / 1000))
    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []
    write_lock = threading.Lock()

    with log_path.open("w", encoding="utf-8") as log, brief_log_path.open("w", encoding="utf-8") as brief_log:
        brief_writer = BriefLogWriter(brief_log)
        brief_writer.start(lane, timeout)
        log.write(
            "# codex exec live log\n\n"
            f"Project: {lane.project}\n"
            f"Started: {utc_now()}\n"
            f"Timeout: {timeout}s\n\n"
            "## output\n"
        )
        log.flush()

        process = subprocess.Popen(
            command,
            cwd=root,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=1,
        )

        def stream_output(pipe: Any, chunks: list[str], prefix: str, stream: str) -> None:
            try:
                for line in pipe:
                    chunks.append(line)
                    with write_lock:
                        log.write(f"{prefix}{line}")
                        log.flush()
                        brief_writer.process_line(stream, line)
            finally:
                pipe.close()

        stdout_thread = threading.Thread(
            target=stream_output,
            args=(process.stdout, stdout_chunks, "[stdout] ", "stdout"),
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=stream_output,
            args=(process.stderr, stderr_chunks, "[stderr] ", "stderr"),
            daemon=True,
        )
        stdout_thread.start()
        stderr_thread.start()

        timed_out = False
        try:
            returncode = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            returncode = 124
            process.kill()
            process.wait()
            stderr_chunks.append("timed out")

        stdout_thread.join()
        stderr_thread.join()

        duration = round(time.time() - started)
        with write_lock:
            if timed_out:
                log.write("\n[stderr] timed out\n")
            log.write(
                "\n## summary\n"
                f"Duration: {duration}s\n"
                f"Exit code: {returncode}\n"
                "Cost: unknown\n"
                "Turns: unknown\n"
                "Tokens: unknown total\n"
            )
            log.flush()
            brief_writer.finish(returncode, duration, timed_out)

    return subprocess.CompletedProcess(command, returncode, "".join(stdout_chunks), "".join(stderr_chunks))
