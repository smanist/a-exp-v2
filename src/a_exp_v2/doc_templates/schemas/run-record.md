# Run and Session Records

Committed session closeout:

```text
projects/<study>/sessions/<run-id>.yaml
```

It records schema version, timestamps, study/run IDs, Codex thread and any
replaced thread, goal/steering hashes, outcome, previous and next states,
summary, experiments, verification, declared files, artifacts, budget usage,
commits, next direction, and open questions. Infrastructure failures with a
safe worktree also receive a committed failure session.

Ignored machine-local runtime provenance:

```text
.a-exp/runs/<run-id>.json
```

The runtime record adds process exit code, timeout and duration, raw and brief
log paths, the final closeout commit, and closeout validation errors. No record
is written when no study is claimed.

Raw Codex JSONL and parsed brief logs live in `.a-exp/logs/`. Thread resumption
records live in `.a-exp/threads/`; they are replaceable machine-local state.
