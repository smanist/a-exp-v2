# Approval Budget

Every study `GOAL.md` separates its autonomy contract into:

- **Scientific Invariants:** equations, scientific and evaluation parameters,
  observations and data boundaries, estimands, metric definitions, thresholds,
  sample requirements, benchmark membership, fairness rules, and claim scope
  that autonomous work must preserve.
- **Authorized Contingencies:** bounded operational responses that may be taken
  without another approval.
- **Human-Only Decisions:** scientific changes, evidence weakening, sealed-data
  access, scope expansion, and exhaustion or ambiguity of an authorized
  contingency.

The authorized contingencies are the study's **approval budget**. Each entry
must state:

```text
ID:
Failure mode and exact trigger:
Allowed response:
Per-case attempt cap:
Cumulative attempt or compute cap:
Scientific invariants that must remain unchanged:
Required record and evidence:
Escalate when:
```

Use `None` explicitly when no contingency is authorized. Do not infer authority
from examples, broad goals, or a similar failure. A value's scientific role,
not whether it is called a parameter, controls its classification.

Implementation fixes are autonomous only when code disagrees with an
unambiguous frozen specification. Bounded retries preserve the declared
configuration and follow any predeclared replacement rule. Extra diagnostics
must remain non-selecting. A truth-only coverage extension is autonomous only
when predeclared, inside its cap, and isolated from training, selection,
failure rescue, benchmark membership, and claims. Opening sealed
confirmation/test data remains human-only.

Record each contingency's ID, trigger evidence, action, per-run use, cumulative
use, outcome, and affected artifacts in an experiment record or durable study
memory. Usage is cumulative across sessions and context revisions; a retry or
new handoff does not reset it. Keep `GOAL.md` authoritative. Handoffs summarize
active IDs and usage in `constraints` and reference the authoritative goal and
usage records instead of duplicating the budget.
