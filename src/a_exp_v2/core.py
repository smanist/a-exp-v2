from __future__ import annotations

import json
import hashlib
import os
import re
import subprocess
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
    return created


def init_git_repo_if_needed(root: Path) -> Path | None:
    try:
        status = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise WorkspaceError("Git is required to initialize an a-exp-v2 workspace.") from exc
    if status.returncode == 0 and status.stdout.strip() == "true":
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


def default_agents_text() -> str:
    return """# AGENTS.md

This repository is an a-exp-v2 workspace.

## Fast Orientation

- `AGENTS.md`: first-read orientation for this workspace.
- `.a-exp/config.yaml`: lane defaults and per-project enablement, priority,
  model, and timeout.
- `.a-exp/runs/*.json`: completed or failed run records.
- `.a-exp/logs/`: captured `codex exec` stdout/stderr for each run.
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
    marker_path = root / RUNNING_DIR / f"{run_id}.json"
    started_at = utc_now()
    marker = {
        "run_id": run_id,
        "project": lane.project,
        "task": task.title,
        "pid": os.getpid(),
        "started_at": started_at,
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
            "closeout_validation": validation,
        }
        run_path.parent.mkdir(parents=True, exist_ok=True)
        run_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        if status != "completed":
            raise AgentRunFailed(f"Agent run failed or closeout validation failed: {run_id}")
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


def launch_agent(root: Path, prompt: str, lane: Lane, log_path: Path) -> subprocess.CompletedProcess[str]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["A_EXP_PROJECT"] = lane.project
    env["A_EXP_MODEL"] = lane.model
    env["A_EXP_MAX_DURATION_MS"] = str(lane.max_duration_ms)
    command = ["codex", "exec", prompt]
    started = time.time()
    try:
        result = subprocess.run(
            command,
            cwd=root,
            env=env,
            text=True,
            capture_output=True,
            timeout=max(1, int(lane.max_duration_ms / 1000)),
        )
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or "") + "\n" + (exc.stderr or "")
        log_path.write_text(output, encoding="utf-8")
        return subprocess.CompletedProcess(command, 124, exc.stdout or "", exc.stderr or "timed out")
    duration = round(time.time() - started)
    log_path.write_text(
        f"# Duration: {duration}s, Cost: unknown, Turns: unknown, Tokens: unknown total\n\n"
        f"## stdout\n{result.stdout}\n\n## stderr\n{result.stderr}\n",
        encoding="utf-8",
    )
    return result
