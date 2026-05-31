# a-exp-v2

`a-exp-v2` is a small repo-local operating layer for recurring Codex-assisted
work. An external scheduler decides when to call it; `a-exp-v2` decides whether
the repo has runnable work and runs one project work lane at a time.

Installable commands:

```bash
a-exp-v2 status --json
a-exp-v2 run-once
```

The package also exposes `a-exp` as a compatibility command alias.

## Scheduler Contract

External schedulers should call:

```bash
a-exp-v2 status --json
```

and then call:

```bash
a-exp-v2 run-once
```

when:

```text
health == "ok"
sessions.active == 0
jobs.runnable > 0
```

No due-time or daemon state is part of the `a-exp-v2` execution gate.

## Docs

- [Design](docs/design.md)
- [Scheduler Status](docs/sop/scheduler-status.md)
- [Config Schema](docs/schemas/config.md)
- [Status JSON Schema](docs/schemas/status-json.md)
- [Run Record Schema](docs/schemas/run-record.md)
