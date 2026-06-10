from __future__ import annotations

from typing import Any


JOB_STATES = {"disabled", "running", "runnable", "blocked", "empty", "invalid"}
HEALTH_VALUES = {"ok", "degraded"}
RUN_STATUSES = {"completed", "failed"}
EXECUTION_MODES = {"conventional", "goal", None}
MODE_POLICIES = {"hard", None}


def validate_status_json(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in ["health", "sessions", "experiments", "approvals", "jobs"]:
        if key not in data:
            errors.append(f"missing top-level field: {key}")
    if data.get("health") not in HEALTH_VALUES:
        errors.append("health must be ok or degraded")
    jobs = data.get("jobs")
    if not isinstance(jobs, dict):
        return errors + ["jobs must be an object"]
    for key in ["total", "enabled", "disabled", "runnable", "blocked", "running", "empty", "invalid", "items"]:
        if key not in jobs:
            errors.append(f"missing jobs field: {key}")
    items = jobs.get("items")
    if not isinstance(items, list):
        errors.append("jobs.items must be a list")
        return errors

    counts = {state: 0 for state in JOB_STATES if state != "disabled"}
    disabled = 0
    enabled = 0
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"jobs.items[{index}] must be an object")
            continue
        for key in [
            "id",
            "kind",
            "project",
            "enabled",
            "priority",
            "state",
            "running",
            "active_run_id",
            "open_tasks",
            "blocked_tasks",
            "runnable_tasks",
            "last_run_at",
            "run_count",
        ]:
            if key not in item:
                errors.append(f"jobs.items[{index}] missing field: {key}")
        state = item.get("state")
        if state not in JOB_STATES:
            errors.append(f"jobs.items[{index}].state invalid: {state}")
        if item.get("enabled") is True:
            enabled += 1
        elif item.get("enabled") is False:
            disabled += 1
        if state in counts:
            counts[state] += 1
    expected = {
        "total": len(items),
        "enabled": enabled,
        "disabled": disabled,
        **counts,
    }
    for key, value in expected.items():
        if jobs.get(key) != value:
            errors.append(f"jobs.{key} expected {value}, got {jobs.get(key)}")
    return errors


def validate_run_record(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in [
        "run_id",
        "project",
        "task",
        "mode",
        "status",
        "started_at",
        "ended_at",
        "exit_code",
        "log_file",
        "brief_log_file",
        "closeout_validation",
    ]:
        if key not in data:
            errors.append(f"missing run field: {key}")
    if data.get("status") not in RUN_STATUSES:
        errors.append("status must be completed or failed")
    if data.get("execution_mode") not in EXECUTION_MODES:
        errors.append("execution_mode must be conventional, goal, or null")
    if data.get("mode_policy") not in MODE_POLICIES:
        errors.append("mode_policy must be hard or null")
    if "task_spec" in data and data.get("task_spec") is not None and not isinstance(data.get("task_spec"), str):
        errors.append("task_spec must be a string or null")
    closeout = data.get("closeout_validation")
    if not isinstance(closeout, dict):
        return errors + ["closeout_validation must be an object"]
    if "ok" not in closeout:
        errors.append("closeout_validation missing field: ok")
    checks = closeout.get("checks")
    if not isinstance(checks, dict):
        errors.append("closeout_validation.checks must be an object")
    else:
        for key in [
            "durable_memory_changed",
            "task_mentioned",
            "outcome_recorded",
            "verification_recorded",
        ]:
            if key not in checks:
                errors.append(f"closeout_validation.checks missing field: {key}")
    return errors
