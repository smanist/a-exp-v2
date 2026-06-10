# Design

`a-exp-v2` is a repo-local memory and operations layer for recurring
Codex-assisted work. The repository is the interface: project state, tasks,
approvals, budgets, reports, experiments, and artifacts are ordinary files.

`a-exp-v2` does not implement a daemon and does not own cadence. An external
scheduler decides when to call the command. `a-exp-v2` decides whether runnable
work exists in the current repo and, when asked, executes one project work lane.

## Concepts

- A `task` is the durable repo-level unit of work. `TASKS.md` is the visible
  project queue; spec-backed tasks preserve full execution intent under
  `projects/<project>/tasks/` or `projects/<project>/goals/`.
- A `project work lane` is a project-level queue of tasks.
- An enabled lane is eligible for `run-once`.
- A disabled lane remains visible in status but is excluded from selection.
- A `job` is the scheduler-facing JSON term for a project work lane.
- `conventional` and `goal` are execution modes. For spec-backed tasks the mode
  is a hard directive stored in the task or goal spec; legacy TASKS-only items
  remain agent-triaged for backward compatibility.
- A `protocol` is a reusable playbook and requirements pack for a recurring
  experiment type, stored under `protocols/` and referenced by experiment
  records when applicable.

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
- full and brief live-streamed run logs;
- closeout validation;
- deterministic kanban summaries.

The workflow skill owns:

- orienting on project memory;
- following hard execution mode for spec-backed tasks, or triaging legacy tasks
  as conventional vs goal-mode vs approval vs defer;
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
protocols/
  registry.yaml
  <domain>/
    <protocol>/
      <version>/
        PLAYBOOK.md
        protocol.yaml
        EXPERIMENT.template.md
        checklist.md
projects/
  <project>/
    README.md
    TASKS.md
    tasks/
      <task-id>.md
    goals/
      <goal-id>.md
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
