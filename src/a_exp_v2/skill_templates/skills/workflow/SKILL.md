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
- `Execution mode: conventional|goal`, or `legacy agent triage`
- `Mode policy: hard`, for spec-backed or explicitly mode-tagged tasks
- `Task spec:` or `Goal spec:`, when present

Do not switch to another task unless the selected task is no longer present or
is now blocked. If that happens, write a handoff note and stop.

When the prompt includes `Mode policy: hard`, do not silently switch between
`conventional` and `goal`. You may stop for approval, defer, or mark blocked
when required.

## Steps

1. Read `AGENTS.md`.
2. Read `projects/<project>/README.md` and `projects/<project>/TASKS.md`.
3. Read any directly relevant plans, experiment records, reports, artifacts,
   budget files, and approval queue entries.
4. For experiment-heavy work, check `protocols/registry.yaml` for an applicable
   protocol. If one matches, read its playbook, `protocol.yaml`, experiment
   template, and checklist before execution.
5. For legacy tasks, triage the selected task as `conventional`, `goal-mode`,
   `approval`, or `defer`. For hard-mode tasks, follow the selected execution
   mode exactly.
6. Execute only the selected task or goal, or write the approval/defer/handoff
   record.
7. Close out into durable memory.

## Triage

Use `conventional` for small, deterministic, low-risk work.

Use `goal-mode` for multi-step, uncertain, debugging-heavy,
implementation-heavy, or experiment-heavy work.

For hard goal-mode work, create or resume bounded child task specs under the
selected goal. After each meaningful child task, write fixed child closeout
with `Mode: goal-mode-child` and `Parent goal: <selected task title>`, then
finish with `## Goal closeout`.

Use `approval` when the task needs human approval, credentials, major compute,
budget commitment, governance changes, substantial deletion, or irreversible
operations.

Use `defer` when the task is blocked, underspecified, duplicative, low priority,
or not currently actionable.

## Protocol Use

When a protocol applies:

- reference the protocol id and version in the experiment record or closeout;
- use the protocol template/checklist to shape the experiment record;
- treat missing required protocol fields as incomplete closeout unless the
  task is explicitly a partial handoff;
- record protocol-specific sanity checks, artifacts, caveats, and debug anchors
  when the protocol asks for them.

When protocol-backed work includes method parameter tuning, use the
`parameter-tuning` skill if available.

If no protocol exists but the work reveals a recurring experiment pattern,
record a follow-up task or proposal to extract one. Do not invent a new protocol
inside an unrelated execution task unless the selected task asks for it.

## Closeout Requirement

Before finishing, update durable memory under `projects/<project>/`, `reports/`,
or `APPROVAL_QUEUE.md`.

The closeout must mention the selected task title and include:

```markdown
## Task closeout

Task: <selected task title>
Mode: conventional | goal | goal-mode | goal-mode-child | approval | defer
Mode policy: hard | none
Parent goal: <selected task title, or none>
Protocol: <protocol id and version, or none>
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

## Git Closeout

After writing repo changes, run `git status --short`, commit the intended
changes, and leave the workspace clean except for intentionally ignored files.
