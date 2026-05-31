# Config Schema

Path:

```text
.a-exp/config.yaml
```

Example:

```yaml
layout_version: 1
defaults:
  model: strong
  max_duration_ms: 1800000
projects:
  conv:
    enabled: true
    priority: 10
    model: strong
    max_duration_ms: 1800000
  paused-project:
    enabled: false
    priority: 100
```

## Fields

- `layout_version`: config layout version.
- `defaults.model`: default model label passed to the agent environment.
- `defaults.max_duration_ms`: default agent command timeout.
- `projects.<project>.enabled`: when false, exclude the lane from `run-once`.
- `projects.<project>.priority`: lower numbers run earlier.
- `projects.<project>.model`: optional project override.
- `projects.<project>.max_duration_ms`: optional project timeout override.

Projects with `projects/<project>/TASKS.md` are discovered automatically. A
discovered project is enabled unless config explicitly sets `enabled: false`.
