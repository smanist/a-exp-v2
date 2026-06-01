# Design

`a-exp-v2` is a repo-local memory and operations layer for recurring
Codex-assisted work. The repository is the interface: project state, tasks,
approvals, budgets, reports, experiments, and artifacts are ordinary files.

`a-exp-v2` does not implement a daemon and does not own cadence. An external
scheduler decides when to call the command. `a-exp-v2` decides whether runnable
work exists in the current repo and, when asked, executes one project work lane.

## Concepts

- A `task` is the durable repo-level unit of work, stored in
  `projects/<project>/TASKS.md`.
- A `project work lane` is a project-level queue of tasks.
- An enabled lane is eligible for `run-once`.
- A disabled lane remains visible in status but is excluded from selection.
- A `job` is the scheduler-facing JSON term for a project work lane.
- A conventional session and a goal-mode task are execution modes selected by
  the agent workflow, not durable queue types.

## Boundary

The external scheduler owns:

- when to call `a-exp-v2 status --json`;
- when to call `a-exp-v2 run-once`;
- retries or alerting around command exit codes.

`a-exp-v2` owns:

- workspace initialization;
- durable project lane configuration;
- runnable task discovery;
- deterministic lane ordering;
- one-run-at-a-time locking;
- run records;
- live-streamed run logs;
- closeout validation;
- deterministic kanban summaries.

The workflow skill owns:

- orienting on project memory;
- triaging conventional vs goal-mode vs approval vs defer;
- executing the selected task;
- closing out into durable repo memory.

## Repo Layout

```text
.a-exp/
  config.yaml
  kit.lock.yaml
  logs/
  running/
  runs/

.agents/
  skills/

docs/
projects/
  <project>/
    README.md
    TASKS.md
    budget.yaml
    ledger.yaml
    experiments/
      <experiment-id>/
        EXPERIMENT.md
        progress.json
modules/
  registry.yaml
  <module>/
    artifacts/
reports/
APPROVAL_QUEUE.md
```

`projects/**`, `reports/**`, `APPROVAL_QUEUE.md`, and budget/experiment records
are durable memory. `.a-exp/runs/*.json`, `.a-exp/logs/**`, and
`.a-exp/running/**` are runtime provenance.
