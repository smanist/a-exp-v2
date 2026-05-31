# Task Schema

Tasks live in:

```text
projects/<project>/TASKS.md
```

Shape:

```markdown
- [ ] Imperative task title
  Why: Why this matters.
  Done when: Mechanically verifiable completion condition.
  Priority: high|medium|low
```

Completed tasks use `[x]`.

A task is runnable when it is unchecked and the task title does not contain:

- `[blocked-by: ...]`
- `[approval-needed]`
- `[approval-needed: ...]`

Only top-level task lines are counted. Nested acceptance checkboxes are not
separate tasks.
