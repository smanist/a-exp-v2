# Design

`a-exp-v2` coordinates durable studies rather than pre-sized work units. The
repository holds goals, evidence, decisions, experiment history, and lifecycle
state. A machine-local Codex thread ID can improve continuity but is never the
source of truth.

## Units

- A **study** is `projects/<study>/` with `README.md`, `GOAL.md`, and
  `STATE.yaml`.
- A **session** is one bounded `codex exec` turn selected by `run-once`. It may
  implement code and run multiple coherent foreground experiments.
- An **experiment** is durable study evidence under `experiments/`.
- A **thread record** is ignored machine-local resumption metadata. Losing it
  causes a replacement thread, not loss of the study.

## Lifecycle

Persisted states are `shaping`, `ready`, `needs_human`, `paused`, `blocked`,
`failed`, and `completed`. `running` is derived from a live marker. Disabled,
ineligible, and invalid are effective scheduling states.

Interactive work can shape and steer any study by editing repository files.
Committing `state: ready` hands it to the scheduler. `run-once` atomically
selects a ready study, verifies a clean checkout, starts or resumes Codex,
validates declared changes and structured closeout, commits the session record
and state transition, and returns.

## Safety Boundaries

- Default sandbox: `workspace-write`; default approval policy: `never`.
- `danger-full-access` is permitted only as an explicit per-study override.
- Experiments remain foreground processes in this revision.
- Claims are protected by a workspace lock and active markers.
- A dirty or ambiguous recovery state degrades health and stops scheduling.
- Closeout stages only declared paths plus runner-owned `STATE.yaml` and session
  record files.

## Layout

```text
.a-exp/config.yaml
.a-exp/{runs,logs,running,threads,output,recovery}/   # ignored runtime
projects/<study>/
  README.md
  GOAL.md
  STATE.yaml
  PLAN.md                 # optional
  DECISIONS.md            # optional
  STEERING.md             # optional
  experiments/            # optional
  sessions/               # committed closeouts
protocols/
reports/
APPROVAL_QUEUE.md
```
