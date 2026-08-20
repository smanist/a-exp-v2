# Study Schema

A valid study has `projects/<study>/README.md`, `GOAL.md`, `STATE.yaml`,
`CONTEXT.yaml`, and `handoffs/`.

`GOAL.md` defines the objective, evidence criteria, autonomy envelope, and stop
conditions. Its autonomy envelope must distinguish scientific invariants,
authorized contingencies, and human-only decisions, with the approval budget
specified by `docs/conventions/approval-budget.md`. `README.md` orients the
environment. Optional `PLAN.md`,
`DECISIONS.md`, and `STEERING.md` hold evolving strategy and instructions.
Study files and the `handoffs/` and optional `sessions/` and `experiments/`
directories must be
regular repository entries, not symlinks. Scheduler-owned runtime directories
under `.a-exp/` follow the same rule.

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
