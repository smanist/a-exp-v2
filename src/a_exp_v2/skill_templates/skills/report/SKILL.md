---
name: report
description: Generate human-facing summaries from a-exp-v2 memory.
---

# Report

Use this skill to create durable human-facing summaries.

Report types:

- study status;
- research digest;
- experiment comparison;
- operational summary;
- implementation-transfer summary.

Read:

- study README, goal, state, steering, plans, decisions, and sessions;
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

Reports should not change study state unless explicitly requested. Record newly
discovered directions or questions in study memory when requested.

## Git Closeout

After writing repo changes, run `git status --short`. If `A_EXP_RUN_ID` is set,
do not stage or commit: leave intended changes in the worktree and declare them
for the outer runner. Otherwise commit the intended changes and leave the
workspace clean except for intentionally ignored files.
