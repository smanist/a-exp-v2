---
name: reconcile
description: Read-only reconciliation of autonomous a-exp-v2 work against the latest interactive handoff and evidence baseline. Use after GPU runs finish, before deciding whether to continue the current goal or replace it.
---

# Reconcile

Use this skill after autonomous GPU work returns control to an interactive Codex task. It is read-only: do not edit files, change lifecycle state, create handoffs, or commit.

## Establish the baseline

Read `AGENTS.md`, the study's `README.md`, `GOAL.md`, `STATE.yaml`, `CONTEXT.yaml`, and the handoff named by `latest_handoff`. Validate the handoff against `docs/schemas/context-handoff.md`. Current committed files outrank the handoff, older records, and remembered thread context.

Read every interactive experiment named by the handoff. These records are the evidence baseline; do not rely only on the handoff summary. Include positive, negative, and failed material evidence.

## Compare GPU work

Starting after the handoff's `based_on_run_id`, read the runner-owned session records in order and follow their experiment IDs, commits, verification, artifacts, deviations, and questions. Include a same-revision retry or continuation only once per run ID. Do not treat a failed record as context consumption.

Report:

- what changed relative to the handoff baseline;
- evidence that confirms, weakens, or contradicts the current direction;
- deviations, failures, caveats, and unresolved questions;
- the current and last consumed context revisions;
- whether any interactive probe that affected steering still lacks a committed experiment record.

Recommend `$handoff-continue` when the byte content of `GOAL.md` should remain unchanged. Recommend `$handoff-change` when any goal edit is needed, and explain which assumptions should be retained or superseded. Recommend a new study instead when the proposed objective is unrelated.

Do not invoke either mutating handoff skill automatically.
