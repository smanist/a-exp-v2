# Approval Queue Schema

Path:

```text
APPROVAL_QUEUE.md
```

Shape:

```markdown
# Approval Queue

## Pending

- [ ] approval-id: Short title
  Study: <study>
  Requested by: <run id or interactive session>
  Reason: <why approval is needed>
  Decision needed: <specific human decision>
  Risk: <risk or cost>
  Created: YYYY-MM-DD

## Completed

- [x] approval-id: Short title
  Decision: approved|denied
  Completed: YYYY-MM-DD
```

`status --json` counts unchecked top-level entries under `## Pending`.
