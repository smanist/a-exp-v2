# Run Record Schema

Path:

```text
.a-exp/runs/<run-id>.json
```

Run records are runtime provenance. They do not replace durable project
closeout.

Example:

```json
{
  "run_id": "20260531T120000Z-1a2b3c4d",
  "project": "conv",
  "task": "Implement status schema",
  "mode": "workflow-selected",
  "execution_mode": "conventional",
  "mode_policy": "hard",
  "task_spec": "projects/conv/tasks/implement-status-schema.md",
  "status": "completed",
  "started_at": "2026-05-31T12:00:00Z",
  "ended_at": "2026-05-31T12:10:00Z",
  "exit_code": 0,
  "log_file": ".a-exp/logs/conv-20260531T120000Z-1a2b3c4d.log",
  "brief_log_file": ".a-exp/logs/conv-20260531T120000Z-1a2b3c4d.brief.log",
  "closeout_validation": {
    "ok": true,
    "checks": {
      "durable_memory_changed": true,
      "task_mentioned": true,
      "outcome_recorded": true,
      "verification_recorded": true
    },
    "changed_durable_memory_files": [
      "projects/conv/README.md"
    ],
    "message": "durable memory updated"
  }
}
```

## Status

- `completed`: agent exited successfully and closeout validation passed.
- `failed`: agent exited nonzero or closeout validation failed.

## Execution Mode

- `execution_mode`: `conventional`, `goal`, or `null` for legacy TASKS-only
  entries that still use agent triage.
- `mode_policy`: `hard` for spec-backed or explicitly mode-tagged entries, or
  `null` for legacy entries.
- `task_spec`: repo-relative task or goal spec path, or `null` for legacy
  entries.

No run record is written for skipped scheduler calls such as no runnable work or
an already active run.

## Logs

- `log_file`: full live-streamed `codex exec` stdout/stderr.
- `brief_log_file`: concise live-streamed progress view that keeps agent
  updates, command/result boundaries, token counts, and final output while
  folding lengthy command output such as file contents, generated code, and
  diffs.
