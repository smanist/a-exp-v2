from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .core import (
    consumed_context_revision,
    discover_studies,
    session_records,
    superseded_thread_id,
)


def compact(text: str, limit: int = 240) -> str:
    value = re.sub(r"\s+", " ", text).strip()
    return value if len(value) <= limit else value[: limit - 3].rstrip() + "..."


def bullets(title: str, values: list[str], empty: str = "none") -> list[str]:
    lines = [f"### {title}", ""]
    lines.extend(f"- {compact(value)}" for value in values)
    if not values:
        lines.append(f"- {empty}")
    return lines


def experiment_summaries(study_path: Path) -> list[str]:
    values: list[str] = []
    for path in sorted((study_path / "experiments").glob("*/EXPERIMENT.md")):
        text = path.read_text(encoding="utf-8", errors="replace")
        match = re.search(r"(?ims)^##\s+(?:Findings|Results)\s*$\n(?P<body>.*?)(?=^##\s+|\Z)", text)
        body = match.group("body") if match else ""
        finding = next(
            (line.strip()[2:] for line in body.splitlines() if line.strip().startswith("- ")),
            "recorded",
        )
        values.append(f"`{path.parent.name}` — {finding}")
    return values


def artifact_summaries(records: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    for record in records:
        for value in record.get("artifacts", []):
            if isinstance(value, str):
                seen.add(value)
    return sorted(seen)


def recent_run_summaries(records: list[dict[str, Any]], limit: int = 8) -> list[str]:
    values = []
    for record in records[-limit:]:
        run_id = record.get("run_id", "unknown")
        status = record.get("status", "unknown")
        ended = record.get("ended_at", record.get("started_at", "unknown time"))
        summary = compact(str(record.get("summary", "no summary")), 160)
        values.append(f"`{run_id}` — {status}, {ended}: {summary}")
    return values


def generate_study(root: Path, study: Any) -> str:
    state = study.state_data
    records = session_records(root, study.project) if study.valid else []
    consumed_revision = consumed_context_revision(records)
    handoff = study.handoff_data
    last_record = records[-1] if records else {}
    superseded_id = superseded_thread_id(records)
    lines = [
        f"# Study: {study.project}",
        "",
        f"- Lifecycle: **{study.effective_state}**",
        f"- Configured state: `{state.state}`",
        f"- Scheduling: {'enabled' if study.enabled else 'disabled'}, priority {study.priority}",
        f"- Eligibility: {'eligible' if study.eligible else study.ineligible_reason}",
        f"- Ready after: `{state.ready_after or 'now'}`",
        f"- Last run: `{state.last_run_id or 'never'}`",
        f"- Consecutive failures: {state.consecutive_failures}",
        f"- Context revision: `{study.context_data.revision}`",
        f"- Consumed revision: `{consumed_revision}`",
        f"- Pending handoff: `{'yes' if study.context_data.revision > consumed_revision else 'no'}`",
        f"- Latest handoff: `{study.context_data.latest_handoff or 'none'}`",
        f"- Requested thread policy: `{handoff.thread_policy if handoff else 'none'}`",
        f"- Last thread action: `{last_record.get('applied_thread_action') or 'none'}`",
        f"- Superseded thread: `{superseded_id or 'none'}`",
        "",
        "## Current Direction",
        "",
        state.summary,
        "",
        f"Next direction: {state.next_direction or 'not set'}",
        "",
    ]
    lines.extend(bullets("Open Questions", state.open_questions))
    lines.extend([""])
    lines.extend(bullets("Recent Sessions", recent_run_summaries(records), "no sessions recorded"))
    lines.extend([""])
    experiments = experiment_summaries(study.path) if study.valid else []
    lines.extend(bullets("Experiments and Findings", experiments, "no experiment records"))
    lines.extend([""])
    lines.extend(bullets("Artifacts", artifact_summaries(records), "no declared artifacts"))
    return "\n".join(lines).rstrip() + "\n"


def generate(root: Path, project: str | None = None, output_dir: Path | None = None) -> list[Path]:
    studies, _ = discover_studies(root)
    if project:
        studies = [study for study in studies if study.project == project]
        if not studies:
            raise FileNotFoundError(f"Study not found: {project}")
    output_dir = output_dir or root / "reports" / "kanban"
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for study in studies:
        path = output_dir / f"{study.project}.md"
        path.write_text(generate_study(root, study), encoding="utf-8")
        written.append(path)
    return written
