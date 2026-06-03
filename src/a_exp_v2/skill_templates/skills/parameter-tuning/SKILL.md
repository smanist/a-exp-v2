---
name: parameter-tuning
description: Plan and document protocol-standard parameter tuning for convergence studies.
---

# Parameter Tuning

Use this skill when a convergence-study protocol or experiment task needs a
method parameter or hyperparameter selection plan.

## Inputs

Read the experiment record, protocol pack, and method definitions. Identify:

- tuned parameters and their bounds, scales, constraints, or discrete values;
- each parameter domain, including whether it is continuous, log-scaled,
  integer-valued, parity-constrained, step/grid-constrained, or values-only;
- validation or selection metric;
- initial search budget in number of runs;
- refinement budget in number of runs;
- stochastic elements and whether tuning uses fixed splits or averaged trials.
- whether `helper_applicability` permits using the protocol helper.

## Policy

If the number of tuned parameters is `<= 3`, use a budgeted grid search first,
then refine with a Nelder-Mead-like local optimizer.

If the number of tuned parameters is `> 3`, use a budgeted random search first,
then refine with a Nelder-Mead-like optimizer from the top-k candidates.

For grid and random search, budget means number of method evaluations or
validation runs. Record top-k, seed, failed evaluations, boundary hits, and the
selected parameters.

Treat the parameter domain as part of the tuning protocol, not as an
implementation detail. Use log-spaced candidates for positive log-scale
parameters, project integer parameters to integers, enforce `even`/`odd`
parity where declared, and evaluate only admissible `step`/grid or explicit
`values` candidates. If local refinement is used with constrained parameters,
record how candidates were projected back to the admissible domain or why
refinement was skipped in favor of exhaustive/budgeted grid evaluation.

## Helper

When useful, reuse:

```text
protocols/numerics/convergence-study/v1/helpers/tuning_plan.py
```

The helper can generate initial grid/random candidates from a JSON parameter
spec with `bounds`, `values`, `scale`, `type`, `step`, and `parity` fields, and
exposes a bounded `nelder_mead_like` function for project code.
If the helper assumptions do not fit, record why and implement the tuning plan
manually.

## Output

Record in the experiment:

- parameter count and search space;
- parameter domains and constraints;
- grid or random search budget;
- refinement budget and top-k if applicable;
- validation metric;
- search history artifact;
- selected parameters;
- representative parameter-search plot;
- caveats about stochastic tuning, boundaries, failures, or unresolved
  sensitivity.

## Git Closeout

After writing repo changes, run `git status --short`, commit the intended
changes, and leave the workspace clean except for intentionally ignored files.
