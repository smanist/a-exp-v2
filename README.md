# a-exp-v2

`a-exp-v2` is a repo-local operating layer for durable numerical studies. An
external scheduler decides when to call it; `a-exp-v2` selects one committed,
ready study and runs or resumes one bounded Codex session. A session may make
coherent code changes and run multiple foreground experiments.

```bash
a-exp init /path/to/workspace
a-exp status --json
a-exp run-once
```

`init` creates only workspace infrastructure. Use the generated `project`
skill, or create the documented files directly, to add a study in `shaping`.
Interactive Codex sessions and humans steer by editing and committing study
files. A committed `state: ready` in `STATE.yaml` is the scheduling handoff.

## Scheduler Contract

Call `a-exp run-once` when `a-exp status --json` reports:

```text
health == "ok"
sessions.active == 0
work.runnable > 0
```

Each machine is independent. Host capabilities come from
`~/.config/a-exp/host.yaml`, or the path in `A_EXP_HOST_CONFIG`.

## Documentation

- [Design](docs/design.md)
- [Repository Interface](docs/repo-as-interface.md)
- [Workflow](docs/sop/workflow.md)
- [Scheduler Status](docs/sop/scheduler-status.md)
- [Configuration](docs/schemas/config.md)
- [Status JSON](docs/schemas/status-json.md)
- [Run and Session Records](docs/schemas/run-record.md)

## Opt-in Real Codex Smoke Test

Normal tests use fake Codex processes. To verify the installed CLI, JSONL and
schema output, explicit sandbox/approval overrides, foreground process waiting,
and thread resumption against a real account, run:

```bash
python scripts/smoke_real_codex.py --foreground-seconds 65
```

The script incurs a real Codex run and retains its temporary workspace and logs.
