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
producer: interactive
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

`producer` is required and is either `interactive` or `autonomous`. Record
commands, configuration, the context revision, code revision, environment and
GPU, metrics, artifact paths, findings, caveats, verification, and applicable
protocol. Material interactive results include useful failures and negative
evidence that influence steering; disposable probes that affect no decision
need not be committed. A session may update
`progress.json` while a foreground experiment runs; active values are
`running`, `retrying`, and `stopping`. No process represented there may outlive
the owning Codex turn in this revision.

The record must use the canonical path above. Its frontmatter `id` must match
the experiment directory and `study` must match the containing study.
