---
name: handoff-change
description: Explicitly replace an a-exp-v2 study's autonomous GPU context after a byte-level GOAL.md change. Separates retained and superseded context, records interactive evidence, and commits a clean replace handoff.
---

# Handoff Change

Use only when the human explicitly invokes `$handoff-change`. This skill changes the study objective and requests one GPU thread replacement for the new context revision.

## Confirm scope

Read `AGENTS.md`, `docs/schemas/context-handoff.md`, the study files, latest handoff, autonomous sessions since it, and referenced experiment evidence. If the new objective is unrelated rather than a revision of the current study, recommend creating a new study and stop. Revision 0 has no active goal to replace; use `$handoff-continue` for its initial activation.

Require a byte-level change to `GOAL.md` relative to the latest handoff. If the hash is unchanged, stop and recommend `$handoff-continue`. There is no editorial override.

## Preserve interactive evidence

Record every material interactive computation—including negative and failed results—under `experiments/` with `producer: interactive`, reproducible commands and configuration, the context revision under which it was run, environment/GPU details, metrics, artifacts, findings, caveats, and verification. Follow applicable protocols and keep processes in the foreground. Disposable probes that affect no decision may remain uncommitted.

Update `GOAL.md`, `STEERING.md`, and `DECISIONS.md`. Explicitly separate retained evidence/constraints from superseded assumptions; explain why each superseded item no longer controls the work. Commit these changes and material experiments by exact path, leave a clean checkout, and record that HEAD as `source_commit`.

## Write the replacement handoff

Create one append-only record at `handoffs/<handoff-id>.yaml`, advance `CONTEXT.yaml` by one, and follow every field and invariant in `docs/schemas/context-handoff.md`.

- Use `change_class: major_change` and `thread_policy: replace`.
- Set `previous_handoff` to the prior handoff and require non-empty `superseded_assumptions`.
- Hash the exact current bytes of `GOAL.md` and `STEERING.md`; the goal hash must differ from the prior record.
- Set `based_on_run_id` to the last autonomous run actually inspected.
- Reference experiment IDs and artifacts without embedding full results.
- Never include raw transcripts, secrets, or embedded logs; keep the record under 64 KiB.

Update `STATE.yaml` to `state: ready`, set `ready_after: null`, and summarize the replacement direction. Commit only the exact new handoff, context, state, and intentionally updated memory paths. Finish clean and report the new revision, replacement request, superseded context, evidence IDs, source commit, and handoff commit.
