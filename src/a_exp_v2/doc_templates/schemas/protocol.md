# Protocol Schema

Protocols are reusable playbooks and requirements packs for recurring
experiment types:

```text
protocols/<domain>/<protocol>/<version>/
```

Each protocol pack should contain:

```text
PLAYBOOK.md
protocol.yaml
EXPERIMENT.template.md
checklist.md
examples/
```

`protocols/registry.yaml` lists available protocols:

```yaml
protocols:
  numerics.convergence-study.v1:
    title: Convergence Study Protocol
    status: active
    path: protocols/numerics/convergence-study/v1
    playbook: protocols/numerics/convergence-study/v1/PLAYBOOK.md
    protocol: protocols/numerics/convergence-study/v1/protocol.yaml
    experiment_template: protocols/numerics/convergence-study/v1/EXPERIMENT.template.md
    checklist: protocols/numerics/convergence-study/v1/checklist.md
```

Experiment records may reference a protocol in frontmatter or body text:

```yaml
---
id: example-v1
status: planned
project: my-project
protocol: numerics.convergence-study.v1
---
```

Protocols should stay method and project agnostic. Put concrete examples under
`examples/` or project experiment records, not in the protocol requirements.
