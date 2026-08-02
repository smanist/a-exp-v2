from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


LAYOUT_VERSION = 2
DEFAULT_PRIORITY = 100
DEFAULT_MODEL: str | None = None
DEFAULT_MAX_RUN_DURATION_MS = 43_200_000
DEFAULT_COOLDOWN_SECONDS = 60
DEFAULT_RETRY_BACKOFF_SECONDS = 300
DEFAULT_SANDBOX = "workspace-write"
DEFAULT_APPROVAL_POLICY = "never"
VALID_SANDBOXES = {"read-only", "workspace-write", "danger-full-access"}
VALID_APPROVAL_POLICIES = {"untrusted", "on-failure", "on-request", "never"}
DEFAULT_KEYS = {
    "model",
    "max_run_duration_ms",
    "cooldown_seconds",
    "retry_backoff_seconds",
    "sandbox",
    "approval_policy",
}
PROJECT_KEYS = {"enabled", "priority", *DEFAULT_KEYS}
PROJECT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


@dataclass
class ProjectConfig:
    enabled: bool | None = None
    priority: int = DEFAULT_PRIORITY
    model: str | None = None
    max_run_duration_ms: int | None = None
    cooldown_seconds: int | None = None
    retry_backoff_seconds: int | None = None
    sandbox: str | None = None
    approval_policy: str | None = None


@dataclass
class WorkspaceConfig:
    layout_version: int = LAYOUT_VERSION
    defaults: dict[str, Any] = field(default_factory=dict)
    projects: dict[str, ProjectConfig] = field(default_factory=dict)


def validate_project_id(value: Any) -> str:
    if not isinstance(value, str) or not PROJECT_ID_PATTERN.fullmatch(value):
        raise ValueError(
            "study ID must start with an ASCII letter or digit and contain only "
            "ASCII letters, digits, '.', '_', or '-'"
        )
    return value


def _optional_int(value: Any, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer or null")
    return value


def _required_int(value: Any, field_name: str, *, positive: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer")
    if value < (1 if positive else 0):
        qualifier = "positive" if positive else "non-negative"
        raise ValueError(f"{field_name} must be a {qualifier} integer")
    return value


def _optional_string(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string or null")
    return value.strip()


def _as_project_config(name: str, value: Any) -> ProjectConfig:
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise ValueError(f"projects.{name} must be an object")
    unknown = sorted(set(value) - PROJECT_KEYS)
    if unknown:
        raise ValueError(f"projects.{name} has unknown field(s): {', '.join(unknown)}")
    enabled = value.get("enabled")
    if enabled is not None and not isinstance(enabled, bool):
        raise ValueError(f"projects.{name}.enabled must be true, false, or null")
    priority = value.get("priority", DEFAULT_PRIORITY)
    if isinstance(priority, bool) or not isinstance(priority, int):
        raise ValueError(f"projects.{name}.priority must be an integer")
    max_run_duration_ms = _optional_int(
        value.get("max_run_duration_ms"), f"projects.{name}.max_run_duration_ms"
    )
    if max_run_duration_ms == 0:
        raise ValueError(f"projects.{name}.max_run_duration_ms must be positive or null")
    sandbox = _optional_string(value.get("sandbox"), f"projects.{name}.sandbox")
    if sandbox is not None and sandbox not in VALID_SANDBOXES:
        raise ValueError(
            f"projects.{name}.sandbox must be one of: {', '.join(sorted(VALID_SANDBOXES))}"
        )
    approval_policy = _optional_string(
        value.get("approval_policy"), f"projects.{name}.approval_policy"
    )
    if approval_policy is not None and approval_policy not in VALID_APPROVAL_POLICIES:
        raise ValueError(
            f"projects.{name}.approval_policy must be one of: "
            f"{', '.join(sorted(VALID_APPROVAL_POLICIES))}"
        )
    return ProjectConfig(
        enabled=enabled,
        priority=priority,
        model=_optional_string(value.get("model"), f"projects.{name}.model"),
        max_run_duration_ms=max_run_duration_ms,
        cooldown_seconds=_optional_int(
            value.get("cooldown_seconds"), f"projects.{name}.cooldown_seconds"
        ),
        retry_backoff_seconds=_optional_int(
            value.get("retry_backoff_seconds"), f"projects.{name}.retry_backoff_seconds"
        ),
        sandbox=sandbox,
        approval_policy=approval_policy,
    )


def load_config(path: Path) -> WorkspaceConfig:
    if not path.exists():
        return WorkspaceConfig()
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError("config root must be an object")
    unknown = sorted(set(raw) - {"layout_version", "defaults", "projects"})
    if unknown:
        raise ValueError(f"config has unknown field(s): {', '.join(unknown)}")
    layout_version = raw.get("layout_version", LAYOUT_VERSION)
    if layout_version != LAYOUT_VERSION:
        raise ValueError(f"layout_version must be {LAYOUT_VERSION}")
    defaults = raw.get("defaults", {})
    if not isinstance(defaults, dict):
        raise ValueError("defaults must be an object")
    projects_raw = raw.get("projects", {})
    if not isinstance(projects_raw, dict):
        raise ValueError("projects must be an object")
    projects: dict[str, ProjectConfig] = {}
    for raw_name, value in projects_raw.items():
        name = validate_project_id(raw_name)
        projects[name] = _as_project_config(name, value)
    validate_defaults(defaults)
    return WorkspaceConfig(
        layout_version=layout_version,
        defaults=dict(defaults),
        projects=projects,
    )


def validate_defaults(defaults: dict[str, Any]) -> None:
    unknown = sorted(set(defaults) - DEFAULT_KEYS)
    if unknown:
        raise ValueError(f"defaults has unknown field(s): {', '.join(unknown)}")
    _optional_string(defaults.get("model"), "defaults.model")
    _required_int(
        defaults.get("max_run_duration_ms", DEFAULT_MAX_RUN_DURATION_MS),
        "defaults.max_run_duration_ms",
        positive=True,
    )
    _required_int(
        defaults.get("cooldown_seconds", DEFAULT_COOLDOWN_SECONDS),
        "defaults.cooldown_seconds",
    )
    _required_int(
        defaults.get("retry_backoff_seconds", DEFAULT_RETRY_BACKOFF_SECONDS),
        "defaults.retry_backoff_seconds",
    )
    sandbox = defaults.get("sandbox", DEFAULT_SANDBOX)
    if sandbox not in VALID_SANDBOXES:
        raise ValueError(f"defaults.sandbox must be one of: {', '.join(sorted(VALID_SANDBOXES))}")
    if sandbox == "danger-full-access":
        raise ValueError("defaults.sandbox cannot be danger-full-access; use an explicit project override")
    approval_policy = _optional_string(
        defaults.get("approval_policy", DEFAULT_APPROVAL_POLICY), "defaults.approval_policy"
    )
    if approval_policy not in VALID_APPROVAL_POLICIES:
        raise ValueError(
            "defaults.approval_policy must be one of: "
            + ", ".join(sorted(VALID_APPROVAL_POLICIES))
        )


def dump_config(config: WorkspaceConfig, path: Path) -> None:
    defaults = {
        "model": config.defaults.get("model", DEFAULT_MODEL),
        "max_run_duration_ms": int(
            config.defaults.get("max_run_duration_ms", DEFAULT_MAX_RUN_DURATION_MS)
        ),
        "cooldown_seconds": int(
            config.defaults.get("cooldown_seconds", DEFAULT_COOLDOWN_SECONDS)
        ),
        "retry_backoff_seconds": int(
            config.defaults.get("retry_backoff_seconds", DEFAULT_RETRY_BACKOFF_SECONDS)
        ),
        "sandbox": config.defaults.get("sandbox", DEFAULT_SANDBOX),
        "approval_policy": config.defaults.get("approval_policy", DEFAULT_APPROVAL_POLICY),
    }
    raw: dict[str, Any] = {
        "layout_version": LAYOUT_VERSION,
        "defaults": defaults,
        "projects": {},
    }
    for project in sorted(config.projects):
        validate_project_id(project)
        item = config.projects[project]
        value: dict[str, Any] = {"priority": item.priority}
        for key in (
            "enabled",
            "model",
            "max_run_duration_ms",
            "cooldown_seconds",
            "retry_backoff_seconds",
            "sandbox",
            "approval_policy",
        ):
            field_value = getattr(item, key)
            if field_value is not None:
                value[key] = field_value
        raw["projects"][project] = value
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
