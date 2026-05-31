# Budget Schema

Budget file:

```text
projects/<project>/budget.yaml
```

Example:

```yaml
deadline: 2026-06-30
resources:
  llm_api_calls:
    limit: 10000
    unit: calls
  wall_time_hours:
    limit: 20
    unit: hours
```

Ledger file:

```text
projects/<project>/ledger.yaml
```

Example:

```yaml
entries:
  - date: 2026-05-31
    experiment: example-v1
    resource: llm_api_calls
    amount: 120
    note: Initial evaluation run
```

These files are informational. `a-exp-v2` may summarize them in reports, but
does not enforce spend or audit external providers.
