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

No run record is written for skipped scheduler calls such as no runnable work or
an already active run.

## Logs

- `log_file`: full live-streamed `codex exec` stdout/stderr.
- `brief_log_file`: concise live-streamed progress view that keeps agent
  updates, command/result boundaries, token counts, and final output while
  folding lengthy command output such as file contents, generated code, and
  diffs.
