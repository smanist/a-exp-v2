from __future__ import annotations

import json
import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CodexRunResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str
    events: list[dict[str, Any]] = field(default_factory=list)
    thread_id: str | None = None
    turn_started: bool = False
    timed_out: bool = False
    duration_seconds: int = 0
    closeout: dict[str, Any] | None = None
    closeout_error: str | None = None


def summarize_events(
    events: list[dict[str, Any]], *, timed_out: bool, returncode: int
) -> dict[str, Any]:
    turn_events = [
        str(event.get("type"))
        for event in events
        if str(event.get("type", "")).startswith("turn.")
    ]
    commands: list[dict[str, Any]] = []
    usage: dict[str, Any] | None = None
    for event in events:
        if isinstance(event.get("usage"), dict):
            usage = dict(event["usage"])
        item = event.get("item") if isinstance(event.get("item"), dict) else {}
        if item.get("type") == "command_execution":
            commands.append(
                {
                    key: item[key]
                    for key in ("command", "status", "exit_code")
                    if key in item
                }
            )
    if timed_out:
        terminal_status = "timed_out"
    elif turn_events:
        terminal_status = turn_events[-1].removeprefix("turn.")
    else:
        terminal_status = "completed" if returncode == 0 else "failed"
    return {
        "thread_started": next(
            (
                event.get("thread_id")
                for event in events
                if event.get("type") == "thread.started"
            ),
            None,
        ),
        "turn_events": turn_events,
        "commands": commands,
        "usage": usage,
        "terminal_status": terminal_status,
    }


def build_codex_command(
    *,
    prompt: str,
    output_schema: Path,
    output_message: Path,
    model: str | None,
    sandbox: str,
    approval_policy: str,
    thread_id: str | None,
) -> list[str]:
    common = [
        "--json",
        "--output-schema",
        str(output_schema),
        "--output-last-message",
        str(output_message),
        "-c",
        f'sandbox_mode="{sandbox}"',
        "-c",
        f'approval_policy="{approval_policy}"',
    ]
    if model:
        common.extend(["--model", model])
    if thread_id:
        return ["codex", "exec", "resume", *common, thread_id, prompt]
    return ["codex", "exec", *common, prompt]


class JsonlBriefWriter:
    def __init__(self, handle: Any) -> None:
        self.handle = handle

    def start(self, study: str, timeout_seconds: int, resumed: bool) -> None:
        self.handle.write(
            "# codex exec brief log\n\n"
            f"Study: {study}\n"
            f"Timeout: {timeout_seconds}s\n"
            f"Resumed: {'yes' if resumed else 'no'}\n\n"
        )
        self.handle.flush()

    def event(self, event: dict[str, Any]) -> None:
        event_type = str(event.get("type", "event"))
        if event_type == "thread.started":
            self.handle.write(f"- Thread: {event.get('thread_id', 'unknown')}\n")
        elif event_type.startswith("turn."):
            usage = event.get("usage")
            suffix = f" usage={json.dumps(usage, sort_keys=True)}" if isinstance(usage, dict) else ""
            self.handle.write(f"- {event_type}{suffix}\n")
        elif event_type.startswith("item."):
            item = event.get("item") if isinstance(event.get("item"), dict) else {}
            item_type = item.get("type", "item")
            detail = item.get("command") or item.get("text") or item.get("status") or ""
            detail_text = " ".join(str(detail).split())
            if len(detail_text) > 280:
                detail_text = detail_text[:277] + "..."
            self.handle.write(f"- {event_type} {item_type}: {detail_text}\n")
        elif event_type == "error":
            self.handle.write(f"- error: {event.get('message') or event}\n")
        self.handle.flush()

    def stderr(self, line: str) -> None:
        text = " ".join(line.strip().split())
        if text:
            self.handle.write(f"- stderr: {text[:280]}\n")
            self.handle.flush()

    def finish(self, result: CodexRunResult) -> None:
        self.handle.write(
            "\n## Summary\n"
            f"Duration: {result.duration_seconds}s\n"
            f"Exit code: {result.returncode}\n"
            f"Timed out: {'yes' if result.timed_out else 'no'}\n"
        )
        if result.closeout_error:
            self.handle.write(f"Closeout error: {result.closeout_error}\n")
        self.handle.flush()


def run_codex(
    *,
    root: Path,
    study: str,
    run_id: str,
    prompt: str,
    output_schema: Path,
    log_path: Path,
    brief_log_path: Path,
    output_message: Path,
    timeout_seconds: int,
    model: str | None,
    sandbox: str,
    approval_policy: str,
    thread_id: str | None,
    append: bool = False,
    terminate_grace_seconds: float = 60,
) -> CodexRunResult:
    command = build_codex_command(
        prompt=prompt,
        output_schema=output_schema,
        output_message=output_message,
        model=model,
        sandbox=sandbox,
        approval_policy=approval_policy,
        thread_id=thread_id,
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    output_message.parent.mkdir(parents=True, exist_ok=True)
    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []
    events: list[dict[str, Any]] = []
    lock = threading.Lock()
    started = time.monotonic()
    mode = "a" if append else "w"

    with log_path.open(mode, encoding="utf-8") as full, brief_log_path.open(mode, encoding="utf-8") as brief:
        if append:
            full.write(json.dumps({"type": "a_exp.resume_fallback"}) + "\n")
            brief.write("\n# resume fallback\n")
        writer = JsonlBriefWriter(brief)
        writer.start(study, timeout_seconds, thread_id is not None)
        try:
            process = subprocess.Popen(
                command,
                cwd=root,
                env={**os.environ, "A_EXP_STUDY": study, "A_EXP_RUN_ID": run_id},
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=1,
                start_new_session=True,
            )
        except FileNotFoundError as exc:
            result = CodexRunResult(
                command=command,
                returncode=127,
                stdout="",
                stderr=f"command not found: {exc.filename}",
                duration_seconds=0,
                closeout_error=f"command not found: {exc.filename}",
            )
            writer.finish(result)
            return result

        def read_stdout() -> None:
            assert process.stdout is not None
            for line in process.stdout:
                stdout_chunks.append(line)
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    event = {"type": "unparsed", "text": line.rstrip("\n")}
                if isinstance(event, dict):
                    events.append(event)
                    with lock:
                        full.write(line)
                        full.flush()
                        writer.event(event)
            process.stdout.close()

        def read_stderr() -> None:
            assert process.stderr is not None
            for line in process.stderr:
                stderr_chunks.append(line)
                with lock:
                    full.write(json.dumps({"stream": "stderr", "text": line.rstrip("\n")}) + "\n")
                    full.flush()
                    writer.stderr(line)
            process.stderr.close()

        stdout_thread = threading.Thread(target=read_stdout, daemon=True)
        stderr_thread = threading.Thread(target=read_stderr, daemon=True)
        stdout_thread.start()
        stderr_thread.start()

        timed_out = False
        received_signals: list[int] = []
        previous_handlers: dict[int, Any] = {}

        def forward_signal(signum: int, _frame: Any) -> None:
            received_signals.append(signum)
            forwarded = signum if len(received_signals) == 1 else signal.SIGKILL
            try:
                os.killpg(process.pid, forwarded)
            except ProcessLookupError:
                pass

        if threading.current_thread() is threading.main_thread():
            for signum in (signal.SIGINT, signal.SIGTERM):
                previous_handlers[signum] = signal.getsignal(signum)
                signal.signal(signum, forward_signal)
        try:
            try:
                returncode = process.wait(timeout=max(1, timeout_seconds))
            except subprocess.TimeoutExpired:
                timed_out = True
                returncode = 124
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=max(0.01, terminate_grace_seconds))
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.wait()
        finally:
            for signum, handler in previous_handlers.items():
                signal.signal(signum, handler)

        stdout_thread.join(timeout=5)
        stderr_thread.join(timeout=5)
        duration = round(time.monotonic() - started)
        parsed_events = [item for item in events if isinstance(item, dict)]
        found_thread = next(
            (
                str(item["thread_id"])
                for item in parsed_events
                if item.get("type") == "thread.started" and item.get("thread_id")
            ),
            None,
        )
        turn_started = any(item.get("type") == "turn.started" for item in parsed_events)
        closeout: dict[str, Any] | None = None
        closeout_error: str | None = None
        if output_message.exists():
            try:
                value = json.loads(output_message.read_text(encoding="utf-8"))
                if isinstance(value, dict):
                    closeout = value
                else:
                    closeout_error = "final response must be a JSON object"
            except (OSError, json.JSONDecodeError) as exc:
                closeout_error = f"invalid final response: {exc}"
        else:
            closeout_error = "missing final response"

        result = CodexRunResult(
            command=command,
            returncode=returncode,
            stdout="".join(stdout_chunks),
            stderr="".join(stderr_chunks),
            events=parsed_events,
            thread_id=found_thread,
            turn_started=turn_started,
            timed_out=timed_out,
            duration_seconds=duration,
            closeout=closeout,
            closeout_error=closeout_error,
        )
        writer.finish(result)
        return result
