# Experiment Schema

Experiment record:

```text
projects/<project>/experiments/<experiment-id>/EXPERIMENT.md
```

Minimal shape:

```markdown
---
id: example-v1
status: planned
date: 2026-05-31
project: my-project
protocol: optional.protocol-id.v1
---

# example-v1

## Question

What will this experiment answer?

## Design

Inputs, method, expected outputs, and resource assumptions.

## Results

Filled after completion.

## Findings

Findings with provenance.

## Reproducibility

Commands, configs, and artifact paths.
```

Omit `protocol` when no reusable protocol applies. When present, the value
should match an entry in `protocols/registry.yaml`.

Detached or long-running experiments may also write:

```text
projects/<project>/experiments/<experiment-id>/progress.json
```

Minimal `progress.json` fields:

```json
{
  "status": "running",
  "started_at": "2026-05-31T12:00:00Z",
  "updated_at": "2026-05-31T12:05:00Z",
  "command": ["python", "experiment.py"],
  "log_file": "modules/my-module/artifacts/example-v1/output.log",
  "artifacts_dir": "modules/my-module/artifacts/example-v1"
}
```

Active statuses are `running`, `retrying`, and `stopping`.
