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

## Propose

Agent-initiated proposals require human approval before activation. Write the
proposal under `reports/project/` or add an entry to `APPROVAL_QUEUE.md`.

## Task Shape

```markdown
- [ ] Imperative task title
  Why: Why this matters.
  Done when: Mechanically verifiable completion condition.
  Priority: high|medium|low
```
