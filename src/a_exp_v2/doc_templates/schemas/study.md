# Study Schema

A valid study has `projects/<study>/README.md`, `GOAL.md`, and `STATE.yaml`.

`GOAL.md` defines the objective, evidence criteria, autonomy envelope, and stop
conditions. `README.md` orients the environment. Optional `PLAN.md`,
`DECISIONS.md`, and `STEERING.md` hold evolving strategy and instructions.

```yaml
schema_version: 1
state: shaping
ready_after: null
summary: Initial shaping
next_direction: null
open_questions: []
requires: []
last_run_id: null
consecutive_failures: 0
```

Durable states are `shaping`, `ready`, `needs_human`, `paused`, `blocked`,
`failed`, and `completed`. `running` is never persisted. `ready_after` is an ISO
8601 timestamp or null. `requires` lists host capabilities.
