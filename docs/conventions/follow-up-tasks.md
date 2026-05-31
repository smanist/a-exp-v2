# Follow-Up Tasks

Agents may propose follow-up tasks during closeout, review, diagnosis, or
reporting.

Follow-up tasks must be written back to `projects/<project>/TASKS.md` and must
not be executed in the same chain unless the human explicitly requested
continued work.

Each follow-up task should include:

```markdown
- [ ] Imperative task title
  Why: Why this matters.
  Done when: Mechanically verifiable completion condition.
  Priority: high|medium|low
```
