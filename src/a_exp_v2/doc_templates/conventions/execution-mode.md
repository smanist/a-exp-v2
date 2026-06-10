# Execution Mode

Execution mode is a hard directive for spec-backed tasks and an agent-side
triage decision only for legacy TASKS-only entries.

Spec-backed queue entries and their spec frontmatter must use:

```yaml
execution_mode: conventional|goal
mode_policy: hard
```

The executing agent may stop for approval, defer, or mark blocked, but it must
not silently switch between `conventional` and `goal`.

## Conventional

Use for small, deterministic, low-risk work that is easy to verify immediately.

## Goal

Use for multi-step, uncertain, debugging-heavy, implementation-heavy, or
experiment-heavy work that may require repeated test and repair loops.

A goal-mode run is one scheduler-selected parent unit. It may create bounded
child task specs, but each child task must receive fixed closeout before the
goal continues.

## Approval

Use when the task needs human approval, significant budget or compute, external
credentials, governance changes, deletion of substantial work, or other
irreversible/high-risk operations.

## Defer

Use when the task is blocked, underspecified, duplicative, low priority, or not
currently actionable.
