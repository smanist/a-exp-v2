# Configuration Schema

Path: `.a-exp/config.yaml`

```yaml
layout_version: 2
defaults:
  model: null
  max_run_duration_ms: 43200000
  cooldown_seconds: 60
  retry_backoff_seconds: 300
  sandbox: workspace-write
  approval_policy: never
projects:
  study-id:
    enabled: true
    priority: 100
    model: null
    max_run_duration_ms: 43200000
    cooldown_seconds: 60
    retry_backoff_seconds: 300
    sandbox: workspace-write
    approval_policy: never
```

Lower priority numbers run earlier. Per-study fields override defaults when
present. `model: null` omits the model CLI flag. Sandbox values are `read-only`,
`workspace-write`, and `danger-full-access`; the last is rejected in defaults
and requires an explicit project override. Approval policies are `untrusted`,
`on-failure`, `on-request`, and `never`.

A study directory is discovered even when omitted from `projects`. It is
enabled with priority 100 by default.

## Host Capabilities

Path: `~/.config/a-exp/host.yaml`, overridden by `A_EXP_HOST_CONFIG`.

```yaml
capabilities:
  - cuda
```

`cpu` and the current platform (`linux` or `macos`) are automatic. Configured
capabilities are additive. Every capability in a study's `STATE.yaml.requires`
must be available for scheduling.
