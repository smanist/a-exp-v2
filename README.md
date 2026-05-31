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
