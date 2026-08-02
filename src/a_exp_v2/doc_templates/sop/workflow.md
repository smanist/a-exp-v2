# Autonomous Study Workflow

One scheduler invocation performs one study session:

```text
claim -> orient -> advance -> verify -> structured closeout -> commit state
```

The agent reads repository guidance, `README.md`, `GOAL.md`, `CONTEXT.yaml`,
the validated latest handoff, `STATE.yaml`, and any steering, plan, decisions,
protocols, prior sessions, and experiments. Current committed files outrank the
handoff, older records, and thread memory. It
advances the study within the stated autonomy envelope, potentially through
multiple foreground experiments and coherent code changes. It commits after
each material experiment or code checkpoint.

`GOAL.md`, `STEERING.md`, `CONTEXT.yaml`, `handoffs/`, `STATE.yaml`, and
`sessions/` are forbidden during the autonomous turn. GPU experiments declare
`producer: autonomous`. The final response
must declare all changed paths and request one next state: `ready`,
`needs_human`, `paused`, `blocked`, or `completed`. The runner validates the
response and worktree, writes `sessions/<run-id>.yaml`, updates `STATE.yaml`,
and makes the final scoped closeout commit.

Infrastructure failure is retried once after backoff if the worktree is safe.
A second consecutive failure moves the study to `failed`. Dirty or ambiguous
failure preserves files, writes ignored recovery information, degrades health,
and requires human recovery.

After GPU work, `$reconcile` compares sessions since the last observed run with
the handoff's interactive evidence baseline. Explicit `$handoff-continue`
preserves the goal and requests resume; explicit `$handoff-change` changes the
goal, records superseded assumptions, and requests one idempotent replacement.
Only these handoff skills perform interactive ready transitions.
