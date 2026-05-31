---
name: workflow
description: Run one a-exp-v2 task lifecycle selected by a-exp-v2 run-once.
---

# Workflow

Use this skill when `a-exp-v2 run-once` asks you to run one project task.

The lifecycle is:

```text
orient -> triage -> execute -> closeout or handoff
```

## Inputs

The prompt names:

- `Project: <project>`
- `Selected task: <task title>`

Do not switch to another task unless the selected task is no longer present or
is now blocked. If that happens, write a handoff note and stop.

## Steps

1. Read `AGENTS.md`.
2. Read `projects/<project>/README.md` and `projects/<project>/TASKS.md`.
3. Read any directly relevant plans, experiment records, reports, artifacts,
   budget files, and approval queue entries.
4. Triage the selected task as `conventional`, `goal-mode`, `approval`, or
   `defer`.
5. Execute only the selected task, or write the approval/defer/handoff record.
6. Close out into durable memory.

## Triage

Use `conventional` for small, deterministic, low-risk work.

Use `goal-mode` for multi-step, uncertain, debugging-heavy,
implementation-heavy, or experiment-heavy work.

Use `approval` when the task needs human approval, credentials, major compute,
budget commitment, governance changes, substantial deletion, or irreversible
operations.

Use `defer` when the task is blocked, underspecified, duplicative, low priority,
or not currently actionable.

## Closeout Requirement

Before finishing, update durable memory under `projects/<project>/`, `reports/`,
or `APPROVAL_QUEUE.md`.

The closeout must mention the selected task title and include:

```markdown
## Task closeout

Task: <selected task title>
Mode: conventional | goal-mode | approval | defer
Status: completed | blocked | deferred | failed | partial
Summary:
Verification:
- Command:
- Result:
Files changed:
Artifacts:
Open questions:
Follow-up tasks:
```

If a field is not applicable, write `none`. Do not omit `Verification`; for
approval/defer/handoff, use `Command: not run` and explain the result.

Do not automatically execute follow-up tasks. Add them to `TASKS.md`.
