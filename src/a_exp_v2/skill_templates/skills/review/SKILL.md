---
name: review
description: Validate experiment design, metrics, findings, and closeout.
---

# Review

Use this skill to decide whether experiment design, metrics, findings, or
closeout support the claims being made.

Modes:

- `design`
- `metrics`
- `findings`
- `closeout`

## Checks

- Can the design answer the stated question?
- Are metrics non-degenerate and discriminative?
- Do metric implementations match their definitions?
- Are denominators, filters, and sample sizes explicit?
- Are findings supported by results?
- Are claims attributed to the correct layer: model, workflow, interface,
  methodology, or human/ground truth?
- If the experiment references a protocol, are the protocol design fields,
  sanity checks, artifacts, caveats, and closeout requirements satisfied?
- Does closeout record verification, artifacts, next direction, and questions?

If protocol requirements are missing, mark affected claims provisional or
incomplete rather than treating the protocol reference as sufficient evidence.

If results are unexpected or confusing, recommend `diagnose`.

Write review output under project memory or `reports/` when the review should
persist.

## Git Closeout

After writing repo changes, run `git status --short`, commit the intended
changes, and leave the workspace clean except for intentionally ignored files.
