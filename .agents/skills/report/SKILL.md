---
name: report
description: Generate human-facing summaries from a-exp-v2 memory.
---

# Report

Use this skill to create durable human-facing summaries.

Report types:

- project status;
- research digest;
- experiment comparison;
- operational summary;
- implementation-transfer summary.

Read:

- project README and tasks;
- experiment records and progress;
- `.a-exp/runs/*.json`;
- reports;
- artifacts paths;
- budgets and ledgers when relevant.

Write reports under `reports/` unless the human requests another location.

Reports should not change project state unless explicitly requested. If a report
discovers follow-up work, add tasks only when asked or when the workflow task
requires closeout into project memory.
