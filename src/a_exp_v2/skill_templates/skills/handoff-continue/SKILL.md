---
name: handoff-continue
description: Explicitly return an a-exp-v2 study to autonomous GPU work without changing GOAL.md. Records interactive evidence, advances context with resume policy, marks the study ready, and commits a clean handoff.
---

# Handoff Continue

Use only when the human explicitly invokes `$handoff-continue`. This skill mutates durable study control files and returns the ownership baton to the GPU runner.

## Preconditions

Read `AGENTS.md`, `docs/schemas/context-handoff.md`, and the study's committed files. Require a clean starting checkout or isolate and commit already-authorized interactive work first. Load and validate `CONTEXT.yaml` and the complete handoff chain.

Validate the `Scientific Invariants`, `Authorized Contingencies`, and
`Human-Only Decisions` sections of `GOAL.md` against
`docs/conventions/approval-budget.md`. For a revision-0 study, require a
complete approval budget before activation. For an older active study that
lacks one, stop and recommend adding it through `$handoff-change`; do not
invent authority during continuation.

Refuse continuation if the current byte-level SHA-256 of `GOAL.md` differs from the latest handoff's `goal_sha256`. For revision 0, create an `initial` handoff instead; there is no prior goal hash to compare. Never classify a goal edit as editorial.

Find every interactive computation that influenced steering, a decision, the goal, or the next direction, including useful failures and negative evidence. Ensure each has a committed `experiments/<id>/EXPERIMENT.md` with `producer: interactive`, commands, configuration, context revision, environment/GPU, metrics, artifacts, findings, caveats, and verification. Follow applicable protocols. Omit disposable probes that affected no decision. Interactive processes must remain foreground children of this Codex turn.

## Prepare the source commit

Update `STEERING.md` and `DECISIONS.md` as needed. Commit each material experiment or coherent interactive change by exact path. Confirm the checkout is clean. Record this HEAD as `source_commit`; do not claim that the later handoff commit is its own source.

## Write the handoff

Create exactly one new append-only `handoffs/<handoff-id>.yaml` and advance `CONTEXT.yaml` by one revision. Use every field and invariant in `docs/schemas/context-handoff.md`.

- For revision 1, use `change_class: initial`, `previous_handoff: null`, and `thread_policy: resume`.
- Otherwise use `change_class: continuation`, the previous handoff ID, and `thread_policy: resume`.
- Hash the exact current bytes of `GOAL.md` and `STEERING.md`; use null for an absent steering file.
- Set `based_on_run_id` to the last autonomous run actually inspected, or null when none exists.
- Reference interactive experiment IDs and artifact paths; summarize implications without duplicating full results.
- List relevant interactive commits, retained evidence, decisions, constraints, rejected alternatives, next direction, and questions. Use empty lists when a category is genuinely empty.
- In `constraints`, summarize the active contingency IDs and their cumulative usage or remaining caps. Include `GOAL.md` and the usage records in `relevant_paths`; do not duplicate the full approval budget in the handoff.
- Never include raw transcripts, secrets, or embedded logs. Keep the record under 64 KiB.

Update `STATE.yaml` to `state: ready`, preserve its schema version, reset `ready_after` to null, and describe the handed-off direction. Commit only the exact handoff, context, state, and any intentionally updated control-memory paths. Finish with a clean checkout and report the revision, handoff ID, source commit, evidence IDs, and commit.
