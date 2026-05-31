# AGENTS.md

This repository implements `a-exp-v2`, a repo-local operating layer for
recurring Codex-assisted work. Use this file for fast orientation before reading
deeper docs.

## Source Map

- `src/a_exp_v2/cli.py`: Typer command surface for `init`, `status`,
  `run-once`, `enable`, `disable`, and `kanban`.
- `src/a_exp_v2/core.py`: workspace initialization, project lane discovery,
  runnable-task selection, run records, lock markers, closeout validation, and
  agent launch.
- `src/a_exp_v2/config.py`: `.a-exp/config.yaml` dataclasses and YAML
  load/dump behavior.
- `src/a_exp_v2/kanban.py`: deterministic Markdown kanban generation from
  project memory, reports, and run records.
- `src/a_exp_v2/validators.py`: schema-style checks for status JSON and run
  records.
- `src/a_exp_v2/doc_templates/`: docs copied into initialized workspaces.
- `src/a_exp_v2/skill_templates/`: repo-local skills copied into initialized
  workspaces under `.agents/skills/`.
- `docs/`: human-facing design, SOP, schema, and convention references for
  this package.
- `tests/`: CLI and core behavior tests.

## Generated Workspace Map

`a-exp-v2 init` creates the files future agents usually need:

- `AGENTS.md`: first-read orientation for the initialized workspace.
- `.a-exp/config.yaml`: lane defaults and per-project enablement, priority,
  model, and timeout.
- `.a-exp/runs/*.json`: completed or failed run records.
- `.a-exp/logs/`: captured `codex exec` stdout/stderr for each run.
- `.a-exp/running/*.json`: active-run markers used to keep one run active at a
  time.
- `.agents/skills/`: workflow, project, review, report, packet, and diagnose
  skills.
- `projects/<project>/README.md`: durable project context, decisions, closeout
  notes, and artifact references.
- `projects/<project>/TASKS.md`: the project work lane. Unchecked tasks are
  open; `[blocked-by: ...]` and `[approval-needed: ...]` keep tasks from being
  runnable.
- `projects/<project>/plans/`: optional plans for larger work.
- `projects/<project>/experiments/<id>/EXPERIMENT.md`: experiment design,
  results, and findings.
- `projects/<project>/experiments/<id>/progress.json`: active experiment state;
  `running`, `retrying`, and `stopping` count as running.
- `projects/<project>/budget.yaml` and `ledger.yaml`: optional budget and spend
  memory.
- `modules/registry.yaml`: optional registry for reusable modules and artifacts.
- `reports/`: cross-project reports, packets, research, and generated kanban
  summaries.
- `APPROVAL_QUEUE.md`: durable human approval queue.

## Work Cycle

For scheduler-triggered work, use the `workflow` skill. Read `AGENTS.md`, then
the selected project `README.md` and `TASKS.md`. Execute only the selected task,
then close out into durable memory under `projects/<project>/`, `reports/`, or
`APPROVAL_QUEUE.md`.

For project creation, create only the files the project currently needs. The
minimum useful project is `projects/<project>/README.md` plus
`projects/<project>/TASKS.md`; add plans, experiments, budgets, ledgers, and
reports when the task actually needs them.
