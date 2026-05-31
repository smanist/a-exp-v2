---
name: packet
description: Create implementation handoff packets from a-exp-v2 projects.
---

# Packet

Use this skill to transfer a prototype, experiment, or project result into an
external package.

Invocation concept:

```text
packet <project> <target-package-path> [additional instructions]
```

Read target package instructions first, then read a-exp project memory:

- `projects/<project>/README.md`
- `projects/<project>/TASKS.md`
- `projects/<project>/plans/**`
- `projects/<project>/experiments/**/EXPERIMENT.md`
- `projects/<project>/reports/**`
- `reports/**` when relevant
- `modules/<project>/**` and artifact manifests when relevant

Write an implementation-ready Markdown packet under `reports/packet/`.

The packet should identify:

- purpose;
- mathematical/computational contract;
- prototype location;
- verified behavior;
- target package integration points;
- dependencies;
- edge cases;
- test plan;
- example usage;
- implementation risks.

Do not use `packet` for internal goal-mode execution. The workflow skill decides
whether to use goal mode.
