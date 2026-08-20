# AGENTS.md

This repository implements `a-exp-v2`, a repo-local operating layer for
durable Codex-assisted studies and bounded autonomous sessions.

## Source Map

- `src/a_exp_v2/cli.py`: `init`, `status`, `run-once`, `enable`, `disable`, and
  `kanban`.
- `src/a_exp_v2/core.py`: study discovery, state validation, atomic claims,
  run closeout, Git safety, and status.
- `src/a_exp_v2/runner.py`: Codex JSONL execution, resumption, timeout, signal
  forwarding, and log parsing.
- `src/a_exp_v2/config.py`: layout-version-3 configuration.
- `src/a_exp_v2/kanban.py`: lifecycle-oriented Markdown summaries.
- `src/a_exp_v2/validators.py`: status and run-record contract checks.
- `src/a_exp_v2/schemas/`: structured Codex final-response schemas.
- `src/a_exp_v2/doc_templates/`, `protocol_templates/`, and
  `skill_templates/`: material copied into initialized workspaces.
- `tests/`: package and CLI behavior.

## Generated Workspace Map

`a-exp-v2 init` creates infrastructure but no study. The `project` skill creates
`projects/<study>/README.md`, `GOAL.md`, `STATE.yaml`, `CONTEXT.yaml`, and an
empty `handoffs/` directory in `shaping` state. Optional study memory includes
`PLAN.md`, `DECISIONS.md`, `STEERING.md`, `experiments/`, and `sessions/`.
Every new `GOAL.md` separates scientific invariants, bounded authorized
contingencies, and human-only decisions as defined by the approval-budget
convention.

Machine-local runtime state lives under ignored `.a-exp/` directories. The
repository is authoritative: committed study files determine what future
interactive or autonomous Codex sessions know.

## Work Cycle

Interactive sessions shape or steer a study by editing and committing its
files. After GPU work, use read-only `$reconcile`. Explicit
`$handoff-continue` preserves the goal and requests resume; explicit
`$handoff-change` changes the goal and requests replacement. Those skills own
interactive ready transitions and append a committed context handoff.

Material interactive computations use the experiment convention with
`producer: interactive`; autonomous computations use `producer: autonomous`.
Handoffs reference evidence rather than duplicating it, and interactive work
does not create session records.

For scheduler-triggered work, use the `workflow` skill. One `run-once` selects
one ready, eligible study and runs or resumes one bounded Codex turn. The turn
may implement code and run multiple foreground experiments. It must not edit
`STATE.yaml`; the runner validates structured closeout and owns the state
transition and session record.

Before requesting `needs_human`, autonomous work checks for an exact matching
authorized contingency with remaining cumulative capacity, executes and
records it when safe, and returns `ready` when more work remains. Scientific
changes, ambiguity, sealed-data access, evidence weakening, and exhausted caps
remain human-owned.

Autonomous turns must not edit `GOAL.md`, `STEERING.md`, `CONTEXT.yaml`,
`handoffs/`, `STATE.yaml`, or `sessions/`, and must not edit files under another
study.

For experiment-heavy work, consult `protocols/registry.yaml` and any applicable
playbook, template, and checklist.

## Git Rule

Interactive work commits every material experiment or coherent code change and
leaves the checkout clean except for ignored runtime files. During an
autonomous run (`A_EXP_RUN_ID` is set), do not run `git add` or `git commit`:
leave intended study changes in the worktree and declare every changed path.
The outer runner validates and commits those changes with the runner-owned
state/session files. Read-only `.git` access is expected and is not a reason to
request `needs_human`.
