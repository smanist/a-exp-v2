# Status JSON Schema

`a-exp status --json` returns scheduler-readable lifecycle state:

```json
{
  "health": "ok",
  "warnings": [],
  "sessions": {"active": 0},
  "experiments": {"running": 0},
  "approvals": {"pending": 0},
  "work": {"runnable": 1},
  "studies": {
    "total": 1,
    "enabled": 1,
    "disabled": 0,
    "ready": 1,
    "running": 0,
    "needs_human": 0,
    "paused": 0,
    "blocked": 0,
    "failed": 0,
    "completed": 0,
    "ineligible": 0,
    "invalid": 0,
    "items": []
  }
}
```

Each item includes study ID, configured and effective state, enablement,
priority, eligibility and reason, `ready_after`, active run ID, last-run time,
run count, and consecutive failures.

Health is `degraded` when study/config validation fails, recovery is ambiguous,
or an idle workspace is dirty. Ineligible means required host capabilities are
missing; it does not persist `blocked` or `failed`. `work.runnable` counts ready,
eligible, enabled studies whose cooldown is due, and is zero while a session is
active or health is degraded.
