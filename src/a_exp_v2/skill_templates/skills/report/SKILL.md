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
- referenced protocols and protocol checklists;
- `.a-exp/runs/*.json`;
- reports;
- artifacts paths;
- budgets and ledgers when relevant.

Write reports under `reports/` unless the human requests another location.

When summarizing experiments, include protocol id/version when present and
separate protocol-backed findings from exploratory or protocol-incomplete
findings.

Reports should not change project state unless explicitly requested. If a report
discovers follow-up work, add tasks only when asked or when the workflow task
requires closeout into project memory.

## Git Closeout

After writing repo changes, run `git status --short`, commit the intended
changes, and leave the workspace clean except for intentionally ignored files.
