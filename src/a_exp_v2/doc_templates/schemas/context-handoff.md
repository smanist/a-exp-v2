# Interactive Context and Handoff Schema

Every layout-version-3 study has `CONTEXT.yaml` and an append-only `handoffs/`
directory. The context pointer is small and strict:

```yaml
schema_version: 1
revision: 0
latest_handoff: null
```

Use `handoffs/.gitkeep` so the revision-0 directory survives Git clones; it is
not a handoff record and may remain after activation.

Use `handoffs/.gitkeep` so the revision-0 directory survives Git clones; it is
not a handoff record and may remain after activation.

Revision 0 is permitted only while shaping. A ready study requires revision 1
or later and a valid latest handoff. Handoff IDs are safe single-component IDs;
`latest_handoff` stores the ID without `.yaml`.

Each `handoffs/<handoff-id>.yaml` uses all of these fields:

```yaml
schema_version: 1
handoff_id: r0001-20260802T120000Z
study: example
created_at: 2026-08-02T12:00:00Z
context_revision: 1
previous_handoff: null
source_commit: 0123456789abcdef0123456789abcdef01234567
based_on_run_id: null
change_class: initial
thread_policy: resume
goal_sha256: 64-lowercase-hex-characters
steering_sha256: null
summary: Initial interactive direction
decisions: []
constraints: []
retained_evidence: []
superseded_assumptions: []
rejected_alternatives: []
next_direction: Run the first bounded experiment
open_questions: []
relevant_paths: []
interactive_experiments: []
interactive_commits: []
artifacts: []
source_thread_id: null
```

The first record is `initial` with `resume`; it starts a new GPU thread when no
mapping exists. A `continuation` requires an unchanged byte-level `GOAL.md`
hash and `resume`. A `major_change` requires a changed goal hash, `replace`, and
a non-empty list of superseded assumptions. Revisions and previous-handoff
links form one contiguous chain. The latest goal and steering hashes must match
the current committed files.

Paths are repository-relative and may not escape the workspace. Records are
limited to 64 KiB and must not contain raw Codex transcripts, embedded logs, or
secrets. Full results belong in referenced experiment records. Current
committed study files outrank the latest handoff, which outranks older handoffs
and sessions, which outrank thread memory.

`source_commit` identifies the clean interactive evidence/memory commit on
which the handoff was based; it does not identify the later commit that adds
the handoff itself. `based_on_run_id` is the last autonomous run actually
observed during interactive reconciliation. `source_thread_id` is optional
provenance and never replaces repository memory.
