---
name: project
description: Scaffold, shape, or augment durable a-exp-v2 studies.
---

# Project

Use this skill for interactive creation and shaping under `projects/`.

For a new study, create only:

```text
projects/<study>/README.md
projects/<study>/GOAL.md
projects/<study>/STATE.yaml
```

`README.md` records environment and orientation. `GOAL.md` must state the
objective, evidence criteria, autonomy envelope, and stop conditions. Initialize
strict state as:

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

Add `PLAN.md`, `DECISIONS.md`, `STEERING.md`, `experiments/`, or `sessions/`
only when useful. For experiment-heavy studies, consult
`protocols/registry.yaml` and reference applicable protocols.

Keep the goal stable unless the human changes it. Agent-initiated study
proposals remain in `reports/project/` or `APPROVAL_QUEUE.md` until accepted.
There is no project-creation CLI command and no study-level scheduling queue.

When shaping is complete, set `state: ready` only with human intent or explicit
authorization, then commit all changes and leave the checkout clean.
