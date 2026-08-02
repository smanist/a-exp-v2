# Repository as Interface

Committed files are the durable interface among humans, interactive Codex
sessions, autonomous sessions, and schedulers.

1. Shape the objective and autonomy envelope in `GOAL.md`.
2. Record durable context in `README.md`, `PLAN.md`, `DECISIONS.md`, experiment
   records, and artifacts.
3. Add current instructions in `STEERING.md`.
4. Commit `STATE.yaml` with `state: ready` when autonomous continuation is
   appropriate.
5. `run-once` selects one study, runs one long Codex turn, and commits a session
   closeout plus the requested lifecycle transition.
6. Use `needs_human` and `open_questions` for study-level interaction; use
   `APPROVAL_QUEUE.md` for explicit approvals.

Thread IDs, logs, active markers, and raw run records under `.a-exp/` are local
operational aids. They do not replace committed project memory and may differ
between machines.
