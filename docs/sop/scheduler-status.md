# Scheduler Status SOP

The external scheduler uses only the public CLI contract:

```bash
a-exp-v2 status --json
```

It should call:

```bash
a-exp-v2 run-once
```

when all are true:

```text
health == "ok"
sessions.active == 0
jobs.runnable > 0
```

No due-time or schedule field is part of the `a-exp-v2` execution gate. Cadence
belongs to the external scheduler.

## Command Outcomes

- No runnable work: print `No runnable work.` and exit `0`.
- Existing active run: print `Run already active.` and exit `0`.
- Completed agent run: write `.a-exp/runs/<run-id>.json` and exit `0`.
- Failed agent run or failed closeout validation: write the run record and exit
  nonzero.
- Workspace or config error: exit nonzero.

The scheduler should not inspect `.a-exp/runs/`, `.a-exp/running/`, or project
files directly. `status --json` is the public API.
