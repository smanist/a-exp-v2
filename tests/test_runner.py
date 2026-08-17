from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from a_exp_v2.runner import build_codex_command, run_codex, summarize_events


def closeout() -> dict[str, object]:
    return {
        "outcome": "completed",
        "next_state": "completed",
        "blocker_kind": None,
        "summary": "done",
        "experiments": ["one", "two"],
        "verification": [{"command": "check", "result": "passed"}],
        "files_changed": [],
        "artifacts": [],
        "next_direction": None,
        "open_questions": [],
        "budget_used": {"wall_seconds": 1, "experiments": 2},
    }


def test_command_applies_overrides_to_initial_and_resume(tmp_path: Path) -> None:
    common = dict(
        prompt="advance",
        output_schema=tmp_path / "schema.json",
        output_message=tmp_path / "last.json",
        model="gpt-test",
        sandbox="danger-full-access",
        approval_policy="never",
    )
    initial = build_codex_command(**common, thread_id=None)
    resumed = build_codex_command(**common, thread_id="thread-1")
    assert initial[:2] == ["codex", "exec"]
    assert resumed[:3] == ["codex", "exec", "resume"]
    for command in (initial, resumed):
        assert 'sandbox_mode="danger-full-access"' in command
        assert 'approval_policy="never"' in command
        assert ["--model", "gpt-test"] == command[command.index("--model") : command.index("--model") + 2]
    assert resumed[-2:] == ["thread-1", "advance"]


def write_fake_codex(bin_dir: Path) -> Path:
    path = bin_dir / "codex"
    payload = json.dumps(closeout())
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import json, pathlib, sys\n"
        "args = sys.argv[1:]\n"
        "target = pathlib.Path(args[args.index('--output-last-message') + 1])\n"
        f"target.write_text({payload!r})\n"
        "print(json.dumps({'type': 'thread.started', 'thread_id': 'thread-fake'}), flush=True)\n"
        "print(json.dumps({'type': 'turn.started'}), flush=True)\n"
        "print(json.dumps({'type': 'item.completed', 'item': {'type': 'command_execution', 'command': 'python experiment.py'}}), flush=True)\n"
        "print(json.dumps({'type': 'turn.completed', 'usage': {'input_tokens': 4, 'output_tokens': 5}}), flush=True)\n",
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


def test_run_codex_parses_jsonl_thread_closeout_and_brief_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_fake_codex(bin_dir)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    schema = tmp_path / "schema.json"
    schema.write_text("{}\n", encoding="utf-8")
    result = run_codex(
        root=tmp_path,
        study="demo",
        run_id="run",
        prompt="advance",
        output_schema=schema,
        log_path=tmp_path / ".a-exp/logs/run.jsonl",
        brief_log_path=tmp_path / ".a-exp/logs/run.brief.jsonl",
        output_message=tmp_path / ".a-exp/output/run.json",
        timeout_seconds=5,
        model=None,
        sandbox="workspace-write",
        approval_policy="never",
        thread_id="old-thread",
    )
    assert result.returncode == 0
    assert result.thread_id == "thread-fake"
    assert result.turn_started is True
    assert result.closeout == closeout()
    assert [event["type"] for event in result.events] == [
        "thread.started",
        "turn.started",
        "item.completed",
        "turn.completed",
    ]
    brief = (tmp_path / ".a-exp/logs/run.brief.jsonl").read_text(encoding="utf-8")
    assert "python experiment.py" in brief
    assert "Thread: thread-fake" in brief
    summary = summarize_events(result.events, timed_out=False, returncode=0)
    assert summary["usage"] == {"input_tokens": 4, "output_tokens": 5}
    assert summary["commands"] == [{"command": "python experiment.py"}]
    assert summary["terminal_status"] == "completed"


def test_run_codex_timeout_terminates_process_group(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    path = bin_dir / "codex"
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import signal, time\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "time.sleep(30)\n",
        encoding="utf-8",
    )
    path.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    schema = tmp_path / "schema.json"
    schema.write_text("{}\n", encoding="utf-8")
    started = time.monotonic()
    result = run_codex(
        root=tmp_path,
        study="demo",
        run_id="timeout",
        prompt="advance",
        output_schema=schema,
        log_path=tmp_path / "run.jsonl",
        brief_log_path=tmp_path / "brief.jsonl",
        output_message=tmp_path / "last.json",
        timeout_seconds=1,
        model=None,
        sandbox="workspace-write",
        approval_policy="never",
        thread_id=None,
        terminate_grace_seconds=0.05,
    )
    assert result.returncode == 124
    assert result.timed_out is True
    assert time.monotonic() - started < 5
    assert result.closeout_error == "missing final response"


def test_external_signal_force_kills_codex_group_after_grace(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    pid_path = tmp_path / "codex.pid"
    fake_codex = bin_dir / "codex"
    fake_codex.write_text(
        "#!/usr/bin/env python3\n"
        "import os, signal, time\n"
        "from pathlib import Path\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        f"Path({str(pid_path)!r}).write_text(str(os.getpid()))\n"
        "while True:\n"
        "    time.sleep(0.05)\n",
        encoding="utf-8",
    )
    fake_codex.chmod(0o755)
    schema = tmp_path / "schema.json"
    schema.write_text("{}\n", encoding="utf-8")
    wrapper = (
        "from pathlib import Path\n"
        "from a_exp_v2.runner import run_codex\n"
        f"root = Path({str(tmp_path)!r})\n"
        "run_codex(root=root, study='demo', run_id='signal', prompt='advance', "
        "output_schema=root/'schema.json', log_path=root/'run.jsonl', "
        "brief_log_path=root/'brief.jsonl', output_message=root/'last.json', "
        "timeout_seconds=30, model=None, sandbox='workspace-write', "
        "approval_policy='never', thread_id=None, "
        "external_signal_grace_seconds=0.2)\n"
    )
    source = Path(__file__).resolve().parents[1] / "src"
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{source}{os.pathsep}{env.get('PYTHONPATH', '')}"
    env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
    proc = subprocess.Popen([sys.executable, "-c", wrapper], cwd=tmp_path, env=env)
    deadline = time.monotonic() + 5
    while not pid_path.exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert pid_path.exists()
    codex_pid = int(pid_path.read_text(encoding="utf-8"))

    os.kill(proc.pid, signal.SIGTERM)

    assert proc.wait(timeout=3) == 0
    with pytest.raises(ProcessLookupError):
        os.kill(codex_pid, 0)
