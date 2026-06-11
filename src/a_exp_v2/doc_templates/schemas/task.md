# Task Schema

Tasks live in:

```text
projects/<project>/TASKS.md
```

`TASKS.md` is the visible scheduler queue. New tasks should point at a
canonical task or goal spec so the original prompt and hard execution mode are
preserved.

Legacy shape:

```markdown
- [ ] Imperative task title
  Why: Why this matters.
  Done when: Mechanically verifiable completion condition.
  Priority: high|medium|low
```

Spec-backed shape:

```markdown
- [ ] Imperative task title
  Spec: `projects/<project>/tasks/<task-id>.md`
  Execution mode: conventional|goal
  Mode policy: hard
  Priority: high|medium|low
```

Goal-mode queue entries should point at `projects/<project>/goals/<goal-id>.md`.

Spec files start with frontmatter:

```yaml
---
execution_mode: conventional|goal
mode_policy: hard
source: direct|scheduled|project-augment
original_prompt_sha256: <sha256>
---
```

Root task and goal specs preserve the original prompt under:

````markdown
## Original user prompt

```text
...
```
````

Before recording or hashing the prompt, normalize skill invocation links that
point at `SKILL.md` files to skill-name aliases. For example,
`[$project](/path/to/skills/project/SKILL.md)` is stored as `[project]`.
Preserve all other prompt text verbatim.

Completed tasks use `[x]`.

A task is runnable when it is unchecked and the task title does not contain:

- `[blocked-by: ...]`
- `[approval-needed]`
- `[approval-needed: ...]`

Only top-level task lines are counted. Nested acceptance checkboxes are not
separate tasks.
