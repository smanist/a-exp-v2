# Budget Reporting

Budget support is lightweight and repo-local.

- `projects/<project>/budget.yaml` declares limits.
- `projects/<project>/ledger.yaml` records declared usage.
- Reports may summarize these files.
- `a-exp-v2` does not audit external providers.
- `a-exp-v2` does not enforce provider-backed spend.

Tasks that require significant budget or compute should use approval triage and
write a request to `APPROVAL_QUEUE.md`.
