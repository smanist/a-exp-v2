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
- validation or selection metric;
- initial search budget in number of runs;
- refinement budget in number of runs;
- stochastic elements and whether tuning uses fixed splits or averaged trials.

## Policy

If the number of tuned parameters is `<= 3`, use a budgeted grid search first,
then refine with a Nelder-Mead-like local optimizer.

If the number of tuned parameters is `> 3`, use a budgeted random search first,
then refine with a Nelder-Mead-like optimizer from the top-k candidates.

For grid and random search, budget means number of method evaluations or
validation runs. Record top-k, seed, failed evaluations, boundary hits, and the
selected parameters.

## Helper

When useful, reuse:

```text
protocols/numerics/convergence-study/v1/helpers/tuning_plan.py
```

The helper can generate initial grid/random candidates from a JSON parameter
spec and exposes a bounded `nelder_mead_like` function for project code.

## Output

Record in the experiment:

- parameter count and search space;
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
