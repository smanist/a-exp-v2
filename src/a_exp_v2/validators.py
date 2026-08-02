from __future__ import annotations

from typing import Any


HEALTH_VALUES = {"ok", "degraded"}
STUDY_STATES = {
    "shaping",
    "ready",
    "running",
    "needs_human",
    "paused",
    "blocked",
    "failed",
    "completed",
    "disabled",
    "ineligible",
    "invalid",
}
RUN_STATUSES = {"completed", "failed"}
THREAD_POLICIES = {"resume", "replace"}
THREAD_ACTIONS = {"new", "resume", "replace", "resume_fallback"}


def _non_negative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def validate_status_json(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in ["health", "sessions", "experiments", "approvals", "work", "studies"]:
        if key not in data:
            errors.append(f"missing top-level field: {key}")
    if data.get("health") not in HEALTH_VALUES:
        errors.append("health must be ok or degraded")
    for section, field in (
        ("sessions", "active"),
        ("experiments", "running"),
        ("approvals", "pending"),
        ("work", "runnable"),
    ):
        value = data.get(section)
        if not isinstance(value, dict):
            errors.append(f"{section} must be an object")
        elif not _non_negative_int(value.get(field)):
            errors.append(f"{section}.{field} must be a non-negative integer")

    studies = data.get("studies")
    if not isinstance(studies, dict):
        return errors + ["studies must be an object"]
    count_fields = [
        "total",
        "enabled",
        "disabled",
        "ready",
        "running",
        "needs_human",
        "paused",
        "blocked",
        "failed",
        "completed",
        "ineligible",
        "invalid",
    ]
    for key in [*count_fields, "items"]:
        if key not in studies:
            errors.append(f"missing studies field: {key}")
    for key in count_fields:
        if key in studies and not _non_negative_int(studies.get(key)):
            errors.append(f"studies.{key} must be a non-negative integer")
    items = studies.get("items")
    if not isinstance(items, list):
        return errors + ["studies.items must be a list"]

    required_item_fields = [
        "id",
        "configured_state",
        "state",
        "enabled",
        "priority",
        "eligible",
        "ineligible_reason",
        "ready_after",
        "active_run_id",
        "last_run_at",
        "run_count",
        "consecutive_failures",
        "context_revision",
        "consumed_context_revision",
        "context_pending",
        "latest_handoff",
        "requested_thread_policy",
        "last_thread_action",
        "superseded_thread_id",
    ]
    effective_counts = {
        key: 0 for key in count_fields if key not in {"total", "enabled", "disabled"}
    }
    enabled = 0
    disabled = 0
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"studies.items[{index}] must be an object")
            continue
        for key in required_item_fields:
            if key not in item:
                errors.append(f"studies.items[{index}] missing field: {key}")
        state = item.get("state")
        if state not in STUDY_STATES:
            errors.append(f"studies.items[{index}].state invalid: {state}")
        if item.get("configured_state") not in STUDY_STATES - {
            "running",
            "disabled",
            "ineligible",
            "invalid",
        }:
            errors.append(f"studies.items[{index}].configured_state invalid")
        if item.get("enabled") is True:
            enabled += 1
        elif item.get("enabled") is False:
            disabled += 1
        if state in effective_counts:
            effective_counts[state] += 1
        if not _non_negative_int(item.get("run_count")):
            errors.append(f"studies.items[{index}].run_count must be non-negative")
        if not _non_negative_int(item.get("consecutive_failures")):
            errors.append(
                f"studies.items[{index}].consecutive_failures must be non-negative"
            )
        if not _non_negative_int(item.get("context_revision")):
            errors.append(f"studies.items[{index}].context_revision must be non-negative")
        if not _non_negative_int(item.get("consumed_context_revision")):
            errors.append(
                f"studies.items[{index}].consumed_context_revision must be non-negative"
            )
        if not isinstance(item.get("context_pending"), bool):
            errors.append(f"studies.items[{index}].context_pending must be boolean")
        revision = item.get("context_revision")
        consumed = item.get("consumed_context_revision")
        if _non_negative_int(revision) and _non_negative_int(consumed):
            if item.get("context_pending") != (revision > consumed):
                errors.append(f"studies.items[{index}].context_pending is inconsistent")
        latest_handoff = item.get("latest_handoff")
        if latest_handoff is not None and (
            not isinstance(latest_handoff, str) or not latest_handoff
        ):
            errors.append(f"studies.items[{index}].latest_handoff invalid")
        if revision == 0 and latest_handoff is not None:
            errors.append(f"studies.items[{index}].revision 0 cannot have a handoff")
        if isinstance(revision, int) and revision > 0 and latest_handoff is None:
            errors.append(f"studies.items[{index}] positive revision requires a handoff")
        policy = item.get("requested_thread_policy")
        if policy is not None and policy not in THREAD_POLICIES:
            errors.append(f"studies.items[{index}].requested_thread_policy invalid")
        action = item.get("last_thread_action")
        if action is not None and action not in THREAD_ACTIONS:
            errors.append(f"studies.items[{index}].last_thread_action invalid")
        superseded = item.get("superseded_thread_id")
        if superseded is not None and (
            not isinstance(superseded, str) or not superseded
        ):
            errors.append(f"studies.items[{index}].superseded_thread_id invalid")
    expected = {
        "total": len(items),
        "enabled": enabled,
        "disabled": disabled,
        **effective_counts,
    }
    for key, value in expected.items():
        if studies.get(key) != value:
            errors.append(f"studies.{key} expected {value}, got {studies.get(key)}")
    return errors


def validate_run_record(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required = [
        "schema_version",
        "run_id",
        "study",
        "status",
        "previous_state",
        "next_state",
        "started_at",
        "ended_at",
        "codex_thread_id",
        "replaced_thread_id",
        "context_revision",
        "handoff_id",
        "requested_thread_policy",
        "applied_thread_action",
        "context_consumed",
    ]
    for key in required:
        if key not in data:
            errors.append(f"missing run field: {key}")
    if data.get("schema_version") != 2:
        errors.append("schema_version must be 2")
    if data.get("status") not in RUN_STATUSES:
        errors.append("status must be completed or failed")
    if data.get("status") == "completed":
        for key in [
            "outcome",
            "summary",
            "experiments",
            "verification",
            "files_changed",
            "artifacts",
            "budget_used",
            "commits",
            "next_direction",
            "open_questions",
        ]:
            if key not in data:
                errors.append(f"missing completed run field: {key}")
        if data.get("context_consumed") is not True:
            errors.append("completed runs must consume context")
    elif data.get("context_consumed") is not False:
        errors.append("failed runs must not consume context")
    if not _non_negative_int(data.get("context_revision")) or data.get(
        "context_revision"
    ) < 1:
        errors.append("context_revision must be a positive integer")
    if not isinstance(data.get("handoff_id"), str) or not data.get("handoff_id"):
        errors.append("handoff_id must be a non-empty string")
    if data.get("requested_thread_policy") not in THREAD_POLICIES:
        errors.append("requested_thread_policy must be resume or replace")
    if data.get("applied_thread_action") not in THREAD_ACTIONS:
        errors.append("applied_thread_action is invalid")
    closeout = data.get("closeout_validation")
    if closeout is not None:
        if not isinstance(closeout, dict):
            errors.append("closeout_validation must be an object")
        elif not isinstance(closeout.get("ok"), bool) or not isinstance(
            closeout.get("errors"), list
        ):
            errors.append("closeout_validation requires boolean ok and list errors")
    return errors
