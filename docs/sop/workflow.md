# Workflow SOP

The agent workflow for one selected task is:

```text
orient -> triage -> execute -> closeout or handoff
```

## Orient

Read the project README, `TASKS.md`, relevant plans, experiment records,
reports, artifacts, budget files, and approval queue entries.

For experiment-heavy tasks, also check `protocols/registry.yaml`. If a matching
protocol exists, read its playbook, `protocol.yaml`, experiment template, and
checklist before triage or execution.

## Triage

Classify the selected task as one of:

- `conventional`
- `goal-mode`
- `approval`
- `defer`

Record the decision in durable project memory when it materially affects the
work.

If a protocol applies, record the selected protocol id and version in the
experiment record or closeout. If no protocol exists but the task reveals a
recurring experiment pattern, propose a follow-up task to extract one.

## Execute

Run conventional work directly, or use Codex goal mode for multi-step,
uncertain, debugging-heavy, implementation-heavy, or experiment-heavy work.

## Closeout

Every executed task must end with durable closeout. At minimum record:

- task;
- execution mode;
- protocol id and version, if applicable;
- status;
- summary;
- verification command and result;
- changed files or artifacts;
- follow-up tasks or open questions.

Follow-up tasks must return to `TASKS.md`; do not automatically chain into them
unless the human explicitly requested continued work.

## Handoff

If blocked, interrupted, or deferred, write the current state, blocker, and next
action to durable repo memory.
