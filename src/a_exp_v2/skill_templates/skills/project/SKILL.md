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
projects/<study>/CONTEXT.yaml
projects/<study>/handoffs/.gitkeep
```

Initialize context as:

```yaml
schema_version: 1
revision: 0
latest_handoff: null
```

`.gitkeep` makes the semantically empty handoff directory durable in Git. It
may remain after the first YAML handoff is added.

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
only when useful. Keep `sessions/` reserved for runner-owned autonomous
closeouts. For experiment-heavy studies, consult
`protocols/registry.yaml` and reference applicable protocols.

Keep the goal stable unless the human changes it. Agent-initiated study
proposals remain in `reports/project/` or `APPROVAL_QUEUE.md` until accepted.
There is no project-creation CLI command and no study-level scheduling queue.

Revision 0 is valid only while shaping. When shaping is complete, explicitly
invoke `$handoff-continue`; its initial handoff advances context to revision 1,
marks the study ready, commits all changes, and leaves the checkout clean.
Direct manual ready transitions are unsupported.
