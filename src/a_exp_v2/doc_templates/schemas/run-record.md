# Run and Session Records

Committed session closeout:

```text
projects/<study>/sessions/<run-id>.yaml
```

Schema version 2 records timestamps, study/run IDs, Codex thread and any
replaced thread, goal/steering hashes, outcome, previous and next states,
summary, experiments, verification, declared files, artifacts, budget usage,
commits, next direction, and open questions. It also records
`context_revision`, `handoff_id`, requested thread policy, applied thread action
(`new`, `resume`, `replace`, or `resume_fallback`), and `context_consumed`.
Infrastructure failures with a safe worktree also receive a committed failure
session with `context_consumed: false`.

The YAML filename must match `run_id`, `study` must match the containing study,
and the start/end timestamps must be valid and ordered. The handoff ID, policy,
and goal/steering hashes must match the referenced context revision. No other
files belong in `sessions/`. A completed run always has a Codex thread ID; a
completed replacement must identify a different thread from the superseded
one.

Ignored machine-local runtime provenance:

```text
.a-exp/runs/<run-id>.json
```

The runtime record adds process exit code, timeout and duration, raw and brief
log paths, the final closeout commit, and closeout validation errors. No record
is written when no study is claimed.

Raw Codex JSONL and parsed brief logs live in `.a-exp/logs/`. Thread resumption
records live in `.a-exp/threads/`; schema version 1 stores the active thread ID
and mapped context revision. They are replaceable machine-local state.

Context is consumed only when a completed session record with
`context_consumed: true` is committed successfully. A failed record preserves
attempt metadata but a retry re-reads the same handoff.
