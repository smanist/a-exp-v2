# Experiment Schema

Experiment records live at:

```text
projects/<study>/experiments/<experiment-id>/EXPERIMENT.md
```

```markdown
---
id: example-v1
status: planned
date: 2026-08-01
study: my-study
protocol: optional.protocol-id.v1
---

# example-v1

## Question
## Design
## Execution
## Results
## Findings
## Verification
## Reproducibility
```

Record commands, configuration, code revision, environment, metrics, artifact
paths, findings, caveats, and applicable protocol. A session may update
`progress.json` while a foreground experiment runs; active values are
`running`, `retrying`, and `stopping`. No process represented there may outlive
the owning Codex turn in this revision.
