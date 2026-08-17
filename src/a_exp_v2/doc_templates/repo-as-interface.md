# Repository as Interface

Committed files are the durable interface among humans, interactive Codex
sessions, autonomous sessions, and schedulers.

1. Shape the objective and autonomy envelope in `GOAL.md`.
2. Record durable context in `README.md`, `PLAN.md`, `DECISIONS.md`, experiment
   records, and artifacts.
3. Add current instructions in `STEERING.md`.
4. Run read-only `$reconcile` after GPU work, then explicitly invoke
   `$handoff-continue` for an unchanged goal or `$handoff-change` for a changed
   goal. The skill commits `CONTEXT.yaml`, an append-only handoff, and
   `STATE.yaml` with `state: ready`.
5. `run-once` consumes that revision, selects one study, runs one long Codex
   turn, and commits a session closeout plus the requested lifecycle transition.
6. Use `needs_human` only for a scientific decision, approval, or unavailable
   external resource that a human must resolve; classify it with
   `blocker_kind`, make `open_questions` concrete, and use `APPROVAL_QUEUE.md`
   for explicit approvals. Runner-owned Git closeout is not a human blocker.

Thread IDs, logs, active markers, and raw run records under `.a-exp/` are local
operational aids. They do not replace committed project memory and may differ
between machines.

Material computations performed interactively through Remote Project use the
same `experiments/` convention and declare `producer: interactive`; autonomous
GPU evidence declares `producer: autonomous`. Handoffs reference this evidence
and summarize its steering implications. They do not embed results or create an
interactive session YAML.
