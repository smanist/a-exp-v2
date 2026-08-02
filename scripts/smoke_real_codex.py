#!/usr/bin/env python3
"""Opt-in smoke test for the installed Codex CLI contract used by a-exp-v2."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any


def run(command: list[str], *, cwd: Path, log_path: Path) -> tuple[list[dict[str, Any]], float]:
    started = time.monotonic()
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)
    elapsed = time.monotonic() - started
    log_path.write_text(result.stdout, encoding="utf-8")
    if result.stderr:
        log_path.with_suffix(".stderr.log").write_text(result.stderr, encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError(
            f"Codex exited {result.returncode}; inspect {log_path} and "
            f"{log_path.with_suffix('.stderr.log')}"
        )
    events: list[dict[str, Any]] = []
    for number, line in enumerate(result.stdout.splitlines(), 1):
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"non-JSONL output at {log_path}:{number}: {exc}") from exc
        if not isinstance(value, dict):
            raise RuntimeError(f"non-object JSONL event at {log_path}:{number}")
        events.append(value)
    return events, elapsed


def common_args(schema: Path, output: Path) -> list[str]:
    return [
        "--json",
        "--output-schema",
        str(schema),
        "--output-last-message",
        str(output),
        "-c",
        'sandbox_mode="workspace-write"',
        "-c",
        'approval_policy="never"',
    ]


def verify_turn(events: list[dict[str, Any]], output: Path) -> str:
    thread_id = next(
        (
            str(event["thread_id"])
            for event in events
            if event.get("type") == "thread.started" and event.get("thread_id")
        ),
        "",
    )
    if not thread_id:
        raise RuntimeError("thread.started with a thread ID was not observed")
    types = [event.get("type") for event in events]
    if "turn.started" not in types or "turn.completed" not in types:
        raise RuntimeError(f"turn lifecycle incomplete: {types}")
    value = json.loads(output.read_text(encoding="utf-8"))
    if value != {"ok": True}:
        raise RuntimeError(f"structured final response did not match: {value!r}")
    return thread_id


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
    if shutil.which("codex") is None:
        raise SystemExit("codex is not installed or not on PATH")

    root = (args.workspace or Path(tempfile.mkdtemp(prefix="a-exp-codex-smoke-"))).resolve()
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    (root / "AGENTS.md").write_text(
        "# Smoke Workspace\n\nFollow the prompt exactly. Do not modify unrelated files.\n",
        encoding="utf-8",
    )
    (root / ".gitignore").write_text(".smoke/\nforeground.txt\n", encoding="utf-8")
    subprocess.run(["git", "add", "AGENTS.md", ".gitignore"], cwd=root, check=True)
    commit_env = os.environ.copy()
    commit_env.update(
        {
            "GIT_AUTHOR_NAME": "a-exp smoke",
            "GIT_AUTHOR_EMAIL": "smoke@example.local",
            "GIT_COMMITTER_NAME": "a-exp smoke",
            "GIT_COMMITTER_EMAIL": "smoke@example.local",
        }
    )
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "commit", "-m", "Initialize smoke workspace"],
        cwd=root,
        env=commit_env,
        check=True,
        capture_output=True,
    )
    smoke_dir = root / ".smoke"
    smoke_dir.mkdir()
    schema = smoke_dir / "response.schema.json"
    schema.write_text(
        json.dumps(
            {
                "type": "object",
                "additionalProperties": False,
                "required": ["ok"],
                "properties": {"ok": {"type": "boolean", "const": True}},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    initial_output = smoke_dir / "initial-final.json"
    prompt = (
        "Run exactly one foreground shell command that invokes Python to sleep for "
        f"{args.foreground_seconds!r} seconds and then writes the text 'done' to "
        "foreground.txt in this repository. Wait for it to finish. Verify the file, "
        "then return exactly the schema-shaped JSON object with ok=true."
    )
    initial_events, elapsed = run(
        ["codex", "exec", *common_args(schema, initial_output), prompt],
        cwd=root,
        log_path=smoke_dir / "initial.jsonl",
    )
    thread_id = verify_turn(initial_events, initial_output)
    if elapsed + 0.25 < args.foreground_seconds:
        raise RuntimeError(
            f"turn returned in {elapsed:.2f}s, before the requested foreground duration"
        )
    if (root / "foreground.txt").read_text(encoding="utf-8") != "done":
        raise RuntimeError("workspace-write foreground command did not create expected file")
    command_text = json.dumps(initial_events)
    if "foreground.txt" not in command_text:
        raise RuntimeError("no JSONL command event referenced the foreground output")

    resume_output = smoke_dir / "resume-final.json"
    resume_events, _ = run(
        [
            "codex",
            "exec",
            "resume",
            *common_args(schema, resume_output),
            thread_id,
            "Confirm foreground.txt contains 'done', then return exactly {\"ok\":true}.",
        ],
        cwd=root,
        log_path=smoke_dir / "resume.jsonl",
    )
    resumed_thread_id = verify_turn(resume_events, resume_output)
    if resumed_thread_id != thread_id:
        raise RuntimeError(f"resume changed thread ID: {thread_id} -> {resumed_thread_id}")

    print(f"ok: Codex JSONL/schema/sandbox/approval/foreground/resume smoke passed in {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
