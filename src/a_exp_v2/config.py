from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


DEFAULT_PRIORITY = 100
DEFAULT_MODEL = "strong"
DEFAULT_MAX_DURATION_MS = 1_800_000


@dataclass
class ProjectLaneConfig:
    enabled: bool | None = None
    priority: int = DEFAULT_PRIORITY
    model: str | None = None
    max_duration_ms: int | None = None


@dataclass
class WorkspaceConfig:
    layout_version: int = 1
    defaults: dict[str, Any] = field(default_factory=dict)
    projects: dict[str, ProjectLaneConfig] = field(default_factory=dict)


def _as_project_config(value: Any) -> ProjectLaneConfig:
    if not isinstance(value, dict):
        return ProjectLaneConfig()
    return ProjectLaneConfig(
        enabled=value.get("enabled") if isinstance(value.get("enabled"), bool) else None,
        priority=int(value.get("priority", DEFAULT_PRIORITY)),
        model=value.get("model") if isinstance(value.get("model"), str) else None,
        max_duration_ms=(
            int(value["max_duration_ms"])
            if isinstance(value.get("max_duration_ms"), int)
            else None
        ),
    )


def load_config(path: Path) -> WorkspaceConfig:
    if not path.exists():
        return WorkspaceConfig()
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        return WorkspaceConfig()
    projects_raw = raw.get("projects", {})
    projects = {}
    if isinstance(projects_raw, dict):
        projects = {
            str(name): _as_project_config(value)
            for name, value in projects_raw.items()
        }
    defaults = raw.get("defaults", {})
    return WorkspaceConfig(
        layout_version=int(raw.get("layout_version", 1)),
        defaults=defaults if isinstance(defaults, dict) else {},
        projects=projects,
    )


def dump_config(config: WorkspaceConfig, path: Path) -> None:
    raw: dict[str, Any] = {
        "layout_version": config.layout_version,
        "defaults": {
            "model": config.defaults.get("model", DEFAULT_MODEL),
            "max_duration_ms": int(
                config.defaults.get("max_duration_ms", DEFAULT_MAX_DURATION_MS)
            ),
        },
        "projects": {},
    }
    for project in sorted(config.projects):
        lane = config.projects[project]
        item: dict[str, Any] = {
            "priority": lane.priority,
        }
        if lane.enabled is not None:
            item["enabled"] = lane.enabled
        if lane.model is not None:
            item["model"] = lane.model
        if lane.max_duration_ms is not None:
            item["max_duration_ms"] = lane.max_duration_ms
        raw["projects"][project] = item

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
