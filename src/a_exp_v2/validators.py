from __future__ import annotations

import re
from datetime import datetime, timezone
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
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
RUN_OUTCOME_NEXT_STATE = {
    "progress": "ready",
    "needs_human": "needs_human",
    "paused": "paused",
    "blocked": "blocked",
    "completed": "completed",
    "infrastructure_failed": None,
}
HUMAN_BLOCKER_KINDS = {
    "scientific_decision",
    "approval_required",
    "external_resource_unavailable",
}
RUN_CONTENT_FIELDS = {
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
}
COMMITTED_RUN_FIELDS = {
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
    "goal_sha256",
    "steering_sha256",
    "blocker_kind",
    *RUN_CONTENT_FIELDS,
    "errors",
}


def _non_negative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


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
            if consumed > revision:
                errors.append(
                    f"studies.items[{index}].consumed_context_revision exceeds current revision"
                )
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


def validate_run_record(
    data: dict[str, Any],
    *,
    committed: bool = False,
) -> list[str]:
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
        "goal_sha256",
        "steering_sha256",
    ]
    for key in required:
        if key not in data:
            errors.append(f"missing run field: {key}")
    if data.get("schema_version") != 2:
        errors.append("schema_version must be 2")
    if data.get("status") not in RUN_STATUSES:
        errors.append("status must be completed or failed")
    if committed:
        unknown = sorted(set(data) - COMMITTED_RUN_FIELDS)
        if unknown:
            errors.append(f"unknown committed run field(s): {', '.join(unknown)}")
        for key in sorted(RUN_CONTENT_FIELDS):
            if key not in data:
                errors.append(f"missing committed run field: {key}")
    if data.get("status") == "completed":
        for key in sorted(RUN_CONTENT_FIELDS):
            if key not in data:
                errors.append(f"missing completed run field: {key}")
        if data.get("context_consumed") is not True:
            errors.append("completed runs must consume context")
    elif data.get("status") == "failed":
        if data.get("context_consumed") is not False:
            errors.append("failed runs must not consume context")
        if committed and "errors" not in data:
            errors.append("missing committed failed run field: errors")
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
    for key in ("run_id", "study", "previous_state", "next_state"):
        if not isinstance(data.get(key), str) or not data.get(key):
            errors.append(f"{key} must be a non-empty string")
    for key in ("codex_thread_id", "replaced_thread_id"):
        value = data.get(key)
        if value is not None and (not isinstance(value, str) or not value):
            errors.append(f"{key} must be a non-empty string or null")
    goal_sha256 = data.get("goal_sha256")
    if not isinstance(goal_sha256, str) or not SHA256_PATTERN.fullmatch(goal_sha256):
        errors.append("goal_sha256 must be a lowercase SHA-256 digest")
    steering_sha256 = data.get("steering_sha256")
    if steering_sha256 is not None and (
        not isinstance(steering_sha256, str)
        or not SHA256_PATTERN.fullmatch(steering_sha256)
    ):
        errors.append("steering_sha256 must be a lowercase SHA-256 digest or null")
    action = data.get("applied_thread_action")
    codex_thread_id = data.get("codex_thread_id")
    replaced_thread_id = data.get("replaced_thread_id")
    if action in {"replace", "resume_fallback"} and not (
        isinstance(replaced_thread_id, str) and replaced_thread_id
    ):
        errors.append(f"{action} requires replaced_thread_id")
    if action in {"new", "resume"} and replaced_thread_id is not None:
        errors.append(f"{action} requires replaced_thread_id to be null")
    if data.get("status") == "completed" and not (
        isinstance(codex_thread_id, str) and codex_thread_id
    ):
        errors.append("completed runs require codex_thread_id")
    if (
        data.get("status") == "completed"
        and action in {"replace", "resume_fallback"}
        and codex_thread_id == replaced_thread_id
    ):
        errors.append(f"completed {action} must use a new codex_thread_id")
    started_at = _timestamp(data.get("started_at"))
    ended_at = _timestamp(data.get("ended_at"))
    if started_at is None:
        errors.append("started_at must be an ISO timestamp")
    if ended_at is None:
        errors.append("ended_at must be an ISO timestamp")
    if started_at is not None and ended_at is not None and ended_at < started_at:
        errors.append("ended_at must not precede started_at")
    outcome = data.get("outcome")
    if outcome is not None and outcome not in RUN_OUTCOME_NEXT_STATE:
        errors.append("outcome is invalid")
    elif outcome in RUN_OUTCOME_NEXT_STATE:
        expected_state = RUN_OUTCOME_NEXT_STATE[outcome]
        if expected_state is not None and data.get("next_state") != expected_state:
            errors.append(f"outcome {outcome} requires next_state {expected_state}")
        if outcome == "infrastructure_failed" and data.get("status") != "failed":
            errors.append("infrastructure_failed outcome requires failed status")
    if "blocker_kind" in data:
        blocker_kind = data.get("blocker_kind")
        if blocker_kind == "runner_git_commit":
            errors.append(
                "blocker_kind runner_git_commit is invalid because Git closeout is runner-owned"
            )
        elif outcome == "needs_human":
            if blocker_kind not in HUMAN_BLOCKER_KINDS:
                errors.append(
                    "needs_human requires blocker_kind to be one of: "
                    + ", ".join(sorted(HUMAN_BLOCKER_KINDS))
                )
            open_questions = data.get("open_questions")
            if isinstance(open_questions, list) and not open_questions:
                errors.append("needs_human requires at least one open question")
        elif blocker_kind is not None:
            errors.append("blocker_kind must be null unless outcome is needs_human")
    for key in ("experiments", "files_changed", "artifacts", "commits", "open_questions"):
        value = data.get(key)
        if value is not None and (
            not isinstance(value, list) or any(not isinstance(item, str) for item in value)
        ):
            errors.append(f"{key} must be a list of strings")
    verification = data.get("verification")
    if verification is not None and (
        not isinstance(verification, list)
        or any(
            not isinstance(item, dict)
            or not isinstance(item.get("command"), str)
            or not item.get("command", "").strip()
            or not isinstance(item.get("result"), str)
            or not item.get("result", "").strip()
            for item in verification
        )
    ):
        errors.append("verification must contain command/result objects")
    elif data.get("status") == "completed" and not verification:
        errors.append("completed run verification must not be empty")
    if "summary" in data and (
        not isinstance(data.get("summary"), str) or not data.get("summary", "").strip()
    ):
        errors.append("summary must be a non-empty string")
    if "budget_used" in data and not isinstance(data.get("budget_used"), dict):
        errors.append("budget_used must be an object")
    elif data.get("status") == "completed" and isinstance(data.get("budget_used"), dict):
        budget = data["budget_used"]
        wall = budget.get("wall_seconds")
        experiment_count = budget.get("experiments")
        if isinstance(wall, bool) or not isinstance(wall, (int, float)) or wall < 0:
            errors.append("budget_used.wall_seconds must be non-negative")
        if not _non_negative_int(experiment_count):
            errors.append("budget_used.experiments must be a non-negative integer")
    if data.get("next_direction") is not None and not isinstance(
        data.get("next_direction"), str
    ):
        errors.append("next_direction must be a string or null")
    if "errors" in data and (
        not isinstance(data.get("errors"), list)
        or any(not isinstance(item, str) or not item for item in data.get("errors", []))
    ):
        errors.append("errors must be a list of non-empty strings")
    closeout = data.get("closeout_validation")
    if closeout is not None:
        if not isinstance(closeout, dict):
            errors.append("closeout_validation must be an object")
        elif not isinstance(closeout.get("ok"), bool) or not isinstance(
            closeout.get("errors"), list
        ):
            errors.append("closeout_validation requires boolean ok and list errors")
    return errors
