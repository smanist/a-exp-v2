---
name: project
description: Scaffold, augment, or propose a-exp-v2 projects.
---

# Project

Use this skill to create, propose, or augment projects under `projects/`.

Modes:

- `scaffold`: human requested a new project.
- `augment`: human requested additional context, tasks, plans, budgets, or
  experiments for an existing project.
- `propose`: agent identified an evidence-backed project candidate.

## Scaffold

Create:

```text
projects/<project>/README.md
projects/<project>/TASKS.md
```

Add `budget.yaml`, `ledger.yaml`, `plans/`, or `experiments/` only when the
project needs them.

## Augment

Keep the project mission stable unless the human explicitly changes it. Add
context, plans, tasks, budgets, or experiment records that directly support the
requested scope.

For experiment-heavy projects or tasks, check `protocols/registry.yaml`. If an
existing protocol fits, reference its id in the task, plan, or experiment
record. Prefer protocol-backed experiment records for recurring experiment
types such as convergence studies.

Do not create a new protocol for one-off work. If repeated project experience
suggests a reusable pattern, write a proposal or follow-up task to extract a
protocol.

## Propose

Agent-initiated proposals require human approval before activation. Write the
proposal under `reports/project/` or add an entry to `APPROVAL_QUEUE.md`.

## Task Shape

Top-level tasks are scheduler and closeout units, not implementation steps.
Prefer one top-level task for a coherent goal-mode unit. Put internal steps
under `Done when` or in a plan. Split into multiple top-level tasks only when
the pieces should be independently scheduled, retried, blocked, approved, or
closed out.

When either shape is reasonable and the choice materially changes how the
project will be operated, ask the human whether they prefer a single goal-mode
task or a broken-down task series.

```markdown
- [ ] Imperative task title
  Why: Why this matters.
  Done when: Mechanically verifiable completion condition.
  Priority: high|medium|low
```

## Git Closeout

After writing repo changes, run `git status --short`, commit the intended
changes, and leave the workspace clean except for intentionally ignored files.
