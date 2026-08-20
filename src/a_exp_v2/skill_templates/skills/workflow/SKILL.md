---
name: workflow
description: Advance one a-exp-v2 study in a bounded autonomous Codex session.
---

# Workflow

Use this skill when `a-exp run-once` selects a study.

## Orient

Read `AGENTS.md`, the selected study's `README.md`, `GOAL.md`, `CONTEXT.yaml`,
the validated latest handoff, and `STATE.yaml`. Current committed files outrank
the handoff, older records, and thread memory. Then read any `STEERING.md`, `PLAN.md`, `DECISIONS.md`, prior sessions,
experiments, reports, budgets, artifacts, and approval entries that affect the
current direction. Consult `protocols/registry.yaml`; when a protocol applies,
read its playbook, schema, template, checklist, and relevant helper guidance.
Read the approval budget in `GOAL.md`, any narrower current steering, and all
records that account for prior contingency use.

## Advance

Advance the goal within its evidence criteria, autonomy envelope, and stop
conditions. You may implement code and run multiple coherent foreground
experiments. Do not launch unmanaged detached processes. Use the `packet` skill
for separately scoped implementation intended for an `a-dev` workflow.

Every GPU-produced experiment must declare `producer: autonomous` and record
its context revision. Do not run `git add` or `git commit`. Leave every intended
study change in the worktree and declare it in `files_changed`; the outer runner
validates and commits those changes during closeout. Read-only `.git` access is
expected and is not a reason to request `needs_human`. Never edit `GOAL.md`,
`STEERING.md`, `CONTEXT.yaml`, `handoffs/`, `STATE.yaml`, or `sessions/`;
interactive skills and the runner own those control paths. Do not edit files
under another study's `projects/<study>/` directory.

## Handle Deviations

Before requesting `needs_human`, identify the blocker and compare it with the
approval budget. Execute a contingency only when its trigger matches exactly,
its cumulative attempt and compute caps have capacity, and the response
preserves every scientific invariant and human-only boundary. Do not broaden a
contingency by analogy.

Record the contingency ID, trigger evidence, action, per-run use, cumulative
use, outcome, and affected artifacts in editable study memory. Apply an
authorized implementation fix, bounded retry, extra diagnostic, or predeclared
truth-only coverage extension autonomously. A truth-only extension must remain
isolated from training, selection, failure rescue, benchmark membership, and
claims. If more work remains afterward, request `ready`; if the evidence
criteria are satisfied, request `completed`.

Request human input when no contingency matches, a cap is exhausted, the
scientific effect is ambiguous, or the response would change an equation,
scientific or evaluation parameter, observation, estimand, metric, threshold,
sample requirement, benchmark membership, sealed-data boundary, compute
envelope, or claim scope. An implementation/specification ambiguity is a
scientific decision; a code defect relative to an unambiguous specification is
not.

## Finish

Verify the work and return the structured object required by the runner. It
must include:

- outcome and matching requested next state;
- blocker kind, which is null unless the next state is `needs_human`;
- concise summary;
- experiment IDs;
- non-empty command/result verification entries;
- every changed repo path;
- artifact paths;
- next direction and open questions;
- wall time and experiment count.

Allowed next states are `ready`, `needs_human`, `paused`, `blocked`, and
`completed`. Choose `needs_human` only for a concrete human-owned blocker and
classify it as `scientific_decision`, `approval_required`, or
`external_resource_unavailable`; make the questions concrete. Runner-owned Git
closeout and transient infrastructure failures do not qualify. Infrastructure
`failed` is runner-owned. State which approval-budget check failed when
requesting `needs_human`.

Before answering, inspect `git status --short`. The runner will reject
undeclared paths, scheduler-owned `.a-exp` paths, and any modification to the
forbidden control paths above.
