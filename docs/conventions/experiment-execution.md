# Experiment Execution

Experiments are recorded under:

```text
projects/<project>/experiments/<experiment-id>/EXPERIMENT.md
```

Heavy outputs belong under:

```text
modules/<module>/artifacts/<experiment-id>/
```

Before planning or running a recurring experiment type, check
`protocols/registry.yaml`. If a protocol applies, use its playbook, template,
and checklist, then record the protocol id in `EXPERIMENT.md` and closeout.

## Inline Execution

Goal-mode tasks may run and wait for experiments inline when the expected
duration fits the Codex execution budget. The same task should inspect results,
write findings, and close out.

## Detached Execution

Long mechanical experiments may be launched as detached non-agent processes.
Detached execution is a convention/tool, not daemon or subagent orchestration.

A detached experiment should write `progress.json`, logs, and artifacts. A
later task can inspect completed results and close out findings.

`a-exp-v2 status` reports running experiments by scanning `progress.json` files
with `status` equal to `running`, `retrying`, or `stopping`.
