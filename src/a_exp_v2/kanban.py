from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


TASK_RE = re.compile(r"^- \[([ xX])\]\s+(.+?)\s*$")


@dataclass
class Task:
    title: str
    done: bool


def compact_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def truncate(text: str, limit: int = 220) -> str:
    text = compact_space(text)
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def parse_tasks(tasks_path: Path) -> list[Task]:
    if not tasks_path.exists():
        return []
    tasks = []
    for line in read_text(tasks_path).splitlines():
        match = TASK_RE.match(line)
        if match:
            tasks.append(Task(title=match.group(2), done=match.group(1).lower() == "x"))
    return tasks


def extract_section(text: str, heading: str) -> str:
    pattern = re.compile(
        rf"(?ims)^##\s+{re.escape(heading)}\s*$\n(?P<body>.*?)(?=^##\s+|\Z)"
    )
    match = pattern.search(text)
    return match.group("body").strip() if match else ""


def extract_bullets(section: str, max_items: int) -> list[str]:
    bullets = []
    for line in section.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            bullets.append(truncate(stripped[2:]))
        if len(bullets) >= max_items:
            break
    return bullets


def extract_paragraph(section: str) -> str:
    lines = []
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("|") or stripped.startswith("!") or stripped.startswith("#"):
            continue
        if stripped.startswith("- "):
            continue
        lines.append(stripped)
    return truncate(" ".join(lines))


def summarize_markdown(path: Path, max_bullets: int) -> list[str]:
    text = read_text(path)
    findings = extract_bullets(extract_section(text, "Findings"), max_bullets)
    if findings:
        return findings
    results = extract_bullets(extract_section(text, "Results"), max_bullets)
    if results:
        return results
    paragraph = extract_paragraph(extract_section(text, "Results") or text)
    return [paragraph] if paragraph else ["no concise result found"]


def frontmatter_id(text: str, fallback: str) -> str:
    match = re.search(r"(?m)^id:\s*([A-Za-z0-9_.-]+)\s*$", text)
    return match.group(1) if match else fallback


def format_card(done: bool, heading: str, label: str | None, parts: list[str]) -> str:
    status = "x" if done else " "
    label_text = f" {label}" if label else ""
    body = "; <br>- ".join(parts)
    return f"- [{status}] **{heading}**{label_text}: <br>- {body}"


def run_parts(root: Path, project: str, max_items: int) -> list[str]:
    runs = []
    for path in sorted((root / ".a-exp" / "runs").glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if data.get("project") == project:
            runs.append(data)
    if not runs:
        return ["no `.a-exp/runs/*.json` entries found"]
    parts = []
    for run in runs[-max_items:]:
        label = run.get("task") or run.get("run_id") or "run"
        status = run.get("status", "unknown")
        ended = run.get("ended_at") or run.get("started_at") or "unknown time"
        log_file = run.get("log_file", "no log")
        parts.append(f"{label}: {status}, {ended}, {log_file}")
    return parts


def find_reports(root: Path, project: str) -> list[Path]:
    project_reports = sorted((root / "projects" / project / "reports").glob("**/*.md"))
    if project_reports:
        return project_reports
    reports = []
    for path in sorted((root / "reports").glob("**/*.md")):
        if path.name == ".gitkeep" or "kanban" in path.parts:
            continue
        text = read_text(path)
        if f"projects/{project}/" in text or f"Project: {project}" in text or f"Project: `{project}`" in text:
            reports.append(path)
    return reports


def generate_project(root: Path, project_dir: Path, max_run_items: int = 8, max_result_bullets: int = 3) -> str:
    project = project_dir.name
    tasks = parse_tasks(project_dir / "TASKS.md")
    done = sum(1 for task in tasks if task.done)
    lines = [
        f"## {project}-Tasks",
        format_card(True, "Progress", None, [f"{len(tasks)} in total, {done} done"]),
        format_card(True, "Runs", None, run_parts(root, project, max_run_items)),
        "",
        f"## {project}-Results",
    ]

    experiment_paths = sorted((project_dir / "experiments").glob("*/EXPERIMENT.md"))
    if experiment_paths:
        for path in experiment_paths:
            text = read_text(path)
            lines.append(
                format_card(
                    True,
                    "Experiment",
                    frontmatter_id(text, path.parent.name),
                    summarize_markdown(path, max_result_bullets),
                )
            )
    else:
        lines.append(format_card(False, "Experiment", None, ["no experiment records found"]))

    report_paths = find_reports(root, project)
    if report_paths:
        for path in report_paths:
            lines.append(
                format_card(True, "Report", path.stem, summarize_markdown(path, max_result_bullets))
            )
    else:
        lines.append(format_card(False, "Report", None, ["no project reports found"]))

    return "\n".join(lines).rstrip() + "\n"


def generate(root: Path, project: str | None = None, output_dir: Path | None = None) -> list[Path]:
    projects_root = root / "projects"
    if not projects_root.is_dir():
        raise FileNotFoundError(f"No projects directory found under {root}")
    project_dirs = sorted(path for path in projects_root.iterdir() if path.is_dir())
    if project:
        project_dirs = [path for path in project_dirs if path.name == project]
        if not project_dirs:
            raise FileNotFoundError(f"Project not found: {project}")
    output_dir = output_dir or root / "reports" / "kanban"
    output_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for project_dir in project_dirs:
        path = output_dir / f"{project_dir.name}.md"
        path.write_text(generate_project(root, project_dir), encoding="utf-8")
        written.append(path)
    return written
