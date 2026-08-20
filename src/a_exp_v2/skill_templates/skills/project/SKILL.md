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
objective, evidence criteria, autonomy envelope, and stop conditions. Within
the autonomy envelope, use explicit `Scientific Invariants`, `Authorized
Contingencies`, and `Human-Only Decisions` sections. Complete the approval
budget required by `docs/conventions/approval-budget.md`; do not leave generic
permission such as "retry as needed." Initialize strict state as:

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

Before freezing an experiment-heavy design, run every applicable protocol's
pre-freeze feasibility check. Use structural, reference-only, or design data;
do not inspect sealed confirmation/test performance. Resolve infeasible sample
counts, degenerate metrics, insufficient reference coverage, invalid artifact
paths, and compute estimates during shaping. Map remaining anticipated failure
modes to bounded contingencies or explicit human-only decisions.

Keep the goal stable unless the human changes it. Agent-initiated study
proposals remain in `reports/project/` or `APPROVAL_QUEUE.md` until accepted.
There is no project-creation CLI command and no study-level scheduling queue.

Revision 0 is valid only while shaping. When shaping is complete, explicitly
invoke `$handoff-continue`; its initial handoff advances context to revision 1,
marks the study ready, commits all changes, and leaves the checkout clean.
Direct manual ready transitions are unsupported.
