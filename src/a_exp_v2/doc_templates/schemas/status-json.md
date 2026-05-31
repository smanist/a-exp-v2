# Status JSON Schema

Command:

```bash
a-exp-v2 status --json
```

Example:

```json
{
  "health": "ok",
  "sessions": {"active": 0},
  "experiments": {"running": 0},
  "approvals": {"pending": 0},
  "jobs": {
    "total": 1,
    "enabled": 1,
    "disabled": 0,
    "runnable": 1,
    "blocked": 0,
    "running": 0,
    "empty": 0,
    "invalid": 0,
    "items": [
      {
        "id": "conv",
        "kind": "project",
        "project": "conv",
        "enabled": true,
        "priority": 100,
        "state": "runnable",
        "running": false,
        "active_run_id": null,
        "open_tasks": 1,
        "blocked_tasks": 0,
        "runnable_tasks": 1,
        "last_run_at": null,
        "run_count": 0
      }
    ]
  }
}
```

## Health

- `ok`: all discovered lanes are valid.
- `degraded`: at least one configured lane is invalid, usually because its
  `TASKS.md` is missing.

## Job State

- `disabled`: lane is disabled.
- `running`: active run marker exists for the lane.
- `runnable`: lane has at least one runnable task.
- `blocked`: lane has open tasks, but all are blocked or approval-needed.
- `empty`: lane has no open tasks.
- `invalid`: lane is malformed or missing required files.

`jobs.runnable` counts runnable lanes, not runnable tasks.
