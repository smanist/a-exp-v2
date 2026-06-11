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
projects/<project>/tasks/ or projects/<project>/goals/ when adding runnable work
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
in the task or goal spec. Split into multiple top-level tasks only when the
pieces should be independently scheduled, retried, blocked, approved, or closed
out.

When either shape is reasonable and the choice materially changes how the
project will be operated, ask the human whether they prefer a single goal-mode
task or a broken-down task series.

New runnable work should be spec-backed. Put the visible queue item in
`TASKS.md`, and preserve the full original prompt and hard execution mode in a
canonical spec file.

```markdown
- [ ] Imperative task title
  Spec: `projects/<project>/tasks/<task-id>.md`
  Execution mode: conventional|goal
  Mode policy: hard
  Priority: high|medium|low
```

Use `projects/<project>/tasks/<task-id>.md` for `conventional` work and
`projects/<project>/goals/<goal-id>.md` for `goal` work. Root specs must start
with:

```yaml
---
execution_mode: conventional|goal
mode_policy: hard
source: direct|scheduled|project-augment
original_prompt_sha256: <sha256 of original prompt>
---
```

Root specs must include:

````markdown
## Original user prompt

```text
<recorded original prompt>
```
````

When recording the original prompt, normalize skill invocation links before
writing the prompt or hashing it: collapse links that point at a `SKILL.md`
file to a skill-name alias. For example,
`[$project](/path/to/skills/project/SKILL.md)` becomes `[project]`. Preserve all
other prompt text verbatim.

## Git Closeout

After writing repo changes, run `git status --short`, commit the intended
changes, and leave the workspace clean except for intentionally ignored files.
