#!/usr/bin/env python3
"""Opt-in smoke test for the installed Codex CLI contract used by a-exp-v2."""

from __future__ import annotations

import argparse
import shutil
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Any


def prepare_workspace(requested: Path | None) -> Path:
    if requested is None:
        return Path(tempfile.mkdtemp(prefix="a-exp-codex-smoke-")).resolve()
    root = requested.expanduser().resolve()
    if root.exists():
        if not root.is_dir():
            raise ValueError(f"workspace exists and is not a directory: {root}")
        if any(root.iterdir()):
            raise ValueError(f"workspace must be nonexistent or empty: {root}")
    root.mkdir(parents=True, exist_ok=True)
    return root


def handoff_record(
    core: Any,
    *,
    root: Path,
    study: Path,
    revision: int,
    previous: str | None,
    change_class: str,
    thread_policy: str,
    source_commit: str,
    based_on_run_id: str | None,
    interactive_experiments: list[str],
    superseded_assumptions: list[str],
) -> Any:
    handoff_id = f"r{revision:04d}-smoke"
    return core.Handoff(
        handoff_id=handoff_id,
        study="smoke",
        created_at=core.utc_now(),
        context_revision=revision,
        previous_handoff=previous,
        source_commit=source_commit,
        based_on_run_id=based_on_run_id,
        change_class=change_class,
        thread_policy=thread_policy,
        goal_sha256=core.content_hash(study / "GOAL.md"),
        steering_sha256=None,
        summary=f"Real Codex smoke handoff revision {revision}",
        decisions=["Exercise the requested context transition"],
        constraints=["Keep every computation in the foreground"],
        retained_evidence=["Interactive baseline remains applicable"],
        superseded_assumptions=superseded_assumptions,
        rejected_alternatives=[],
        next_direction=f"Execute smoke revision {revision}",
        open_questions=[],
        relevant_paths=["projects/smoke/GOAL.md"],
        interactive_experiments=interactive_experiments,
        interactive_commits=[source_commit],
        artifacts=[],
        source_thread_id=None,
        path=f"projects/smoke/handoffs/{handoff_id}.yaml",
    )


def commit_handoff(core: Any, root: Path, study: Path, handoff: Any) -> None:
    handoff_path = core.write_handoff_record(root, study, handoff)
    core.write_study_context(
        study / "CONTEXT.yaml",
        core.StudyContext(
            revision=handoff.context_revision,
            latest_handoff=handoff.handoff_id,
        ),
    )
    state = core.load_study_state(study / "STATE.yaml")
    core.write_study_state(
        study / "STATE.yaml",
        replace(
            state,
            state="ready",
            ready_after=None,
            summary=handoff.summary,
            next_direction=handoff.next_direction,
        ),
    )
    core.commit_workspace_changes(
        root,
        f"Commit smoke handoff revision {handoff.context_revision}",
        [
            handoff_path.relative_to(root),
            study.joinpath("CONTEXT.yaml").relative_to(root),
            study.joinpath("STATE.yaml").relative_to(root),
        ],
    )


def run_handoff_workflow(root: Path, foreground_seconds: float) -> None:
    from a_exp_v2 import core
    from a_exp_v2.config import dump_config, load_config

    core.init_workspace(root)
    config_path = root / ".a-exp" / "config.yaml"
    config = load_config(config_path)
    config.defaults["cooldown_seconds"] = 0
    dump_config(config, config_path)
    core.commit_workspace_changes(root, "Configure smoke cooldown", [config_path.relative_to(root)])

    study = root / "projects" / "smoke"
    study.mkdir(parents=True)
    (study / "README.md").write_text(
        "# Smoke\n\nReal Codex layout-3 routing smoke study.\n", encoding="utf-8"
    )
    (study / "GOAL.md").write_text(
        "# Goal\n\n"
        "## Objective\nExercise layout-3 handoff routing.\n\n"
        "## Evidence Criteria\n"
        "At context revision 1, run one foreground Python command that sleeps for "
        f"{foreground_seconds!r} seconds, then writes projects/smoke/revision-1.txt; "
        "request needs_human. At revision 2, verify revision-1.txt, write "
        "projects/smoke/revision-2.txt, and request needs_human.\n\n"
        "## Autonomy Envelope\nPerform only those file operations and verification.\n\n"
        "## Stop Conditions\nStop after the revision-specific file is verified.\n",
        encoding="utf-8",
    )
    core.write_study_state(
        study / "STATE.yaml",
        core.StudyState(
            state="shaping",
            ready_after=None,
            summary="Prepare smoke handoff",
            next_direction=None,
            open_questions=[],
            requires=[],
            last_run_id=None,
            consecutive_failures=0,
        ),
    )
    core.write_study_context(
        study / "CONTEXT.yaml", core.StudyContext(revision=0, latest_handoff=None)
    )
    (study / "handoffs").mkdir()
    (study / "handoffs" / ".gitkeep").write_text("", encoding="utf-8")
    experiment = study / "experiments" / "interactive-baseline"
    experiment.mkdir(parents=True)
    (experiment / "EXPERIMENT.md").write_text(
        "---\nid: interactive-baseline\nstatus: completed\ndate: 2026-08-02\n"
        "study: smoke\nprotocol: smoke.v1\nproducer: interactive\n---\n\n"
        "# Interactive baseline\n\n## Execution\n\nVerified Python and repository access.\n\n"
        "## Results\n\nThe environment is ready.\n\n## Findings\n\nProceed.\n\n"
        "## Caveats\n\nOpt-in smoke only.\n\n## Verification\n\nRepository write succeeded.\n",
        encoding="utf-8",
    )
    core.commit_workspace_changes(
        root,
        "Create interactive smoke evidence",
        [
            study.joinpath("README.md").relative_to(root),
            study.joinpath("GOAL.md").relative_to(root),
            study.joinpath("STATE.yaml").relative_to(root),
            study.joinpath("CONTEXT.yaml").relative_to(root),
            study.joinpath("handoffs/.gitkeep").relative_to(root),
            experiment.joinpath("EXPERIMENT.md").relative_to(root),
        ],
    )
    initial = handoff_record(
        core,
        root=root,
        study=study,
        revision=1,
        previous=None,
        change_class="initial",
        thread_policy="resume",
        source_commit=core.git_head(root),
        based_on_run_id=None,
        interactive_experiments=["interactive-baseline"],
        superseded_assumptions=[],
    )
    commit_handoff(core, root, study, initial)

    first = core.run_once(root)
    if first is None or first["context_revision"] != 1 or first["applied_thread_action"] != "new":
        raise RuntimeError(f"initial handoff did not start a new thread: {first!r}")
    first_thread = first["codex_thread_id"]
    if not first_thread or not (study / "revision-1.txt").is_file():
        raise RuntimeError("initial autonomous evidence or thread ID is missing")

    continuation = handoff_record(
        core,
        root=root,
        study=study,
        revision=2,
        previous=initial.handoff_id,
        change_class="continuation",
        thread_policy="resume",
        source_commit=core.git_head(root),
        based_on_run_id=first["run_id"],
        interactive_experiments=["interactive-baseline"],
        superseded_assumptions=[],
    )
    commit_handoff(core, root, study, continuation)
    second = core.run_once(root)
    if (
        second is None
        or second["applied_thread_action"] != "resume"
        or second["codex_thread_id"] != first_thread
        or not (study / "revision-2.txt").is_file()
    ):
        raise RuntimeError(f"continuation did not resume the mapped thread: {second!r}")

    (study / "GOAL.md").write_text(
        "# Goal\n\n## Objective\nExercise replacement after a major change.\n\n"
        "## Evidence Criteria\nWrite projects/smoke/revision-3.txt, verify it, and complete.\n\n"
        "## Autonomy Envelope\nPerform only that file operation and verification.\n\n"
        "## Stop Conditions\nStop when revision-3.txt exists.\n",
        encoding="utf-8",
    )
    core.commit_workspace_changes(
        root, "Prepare smoke major goal change", [study.joinpath("GOAL.md").relative_to(root)]
    )
    major = handoff_record(
        core,
        root=root,
        study=study,
        revision=3,
        previous=continuation.handoff_id,
        change_class="major_change",
        thread_policy="replace",
        source_commit=core.git_head(root),
        based_on_run_id=second["run_id"],
        interactive_experiments=["interactive-baseline"],
        superseded_assumptions=["The continuation objective remains active"],
    )
    commit_handoff(core, root, study, major)
    third = core.run_once(root)
    if (
        third is None
        or third["applied_thread_action"] != "replace"
        or third["replaced_thread_id"] != first_thread
        or third["codex_thread_id"] == first_thread
        or not third["context_consumed"]
        or not (study / "revision-3.txt").is_file()
    ):
        raise RuntimeError(f"major change did not replace the mapped thread once: {third!r}")
    if not core.git_clean(root):
        raise RuntimeError("handoff smoke left a dirty workspace")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--foreground-seconds",
        type=float,
        default=5,
        help="foreground sleep duration; use 65 or more for a long-command check",
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        help="directory to create and retain; defaults to a retained temporary directory",
    )
    args = parser.parse_args()
    if args.foreground_seconds < 0:
        parser.error("--foreground-seconds must be non-negative")
    try:
        root = prepare_workspace(args.workspace)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    if shutil.which("codex") is None:
        raise SystemExit("codex is not installed or not on PATH")

    run_handoff_workflow(root, args.foreground_seconds)
    print(
        "ok: interactive evidence/continuation resume/major replacement smoke "
        f"passed in {root}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
