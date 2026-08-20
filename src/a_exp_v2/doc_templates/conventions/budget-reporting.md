# Budget Reporting

Budget support is lightweight and repo-local.

- `projects/<project>/budget.yaml` declares limits.
- `projects/<project>/ledger.yaml` records declared usage.
- Reports may summarize these files.
- `a-exp-v2` does not audit external providers.
- `a-exp-v2` does not enforce provider-backed spend.

Studies that require significant budget or compute outside their autonomy
envelope should move to `needs_human` and write a request to
`APPROVAL_QUEUE.md`.

This provider/compute budget is distinct from the approval budget in
`docs/conventions/approval-budget.md`. A preauthorized contingency may consume
compute only inside both budgets; exceeding either cap requires human input.
