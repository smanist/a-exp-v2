# Convergence Study Playbook

## Purpose

Use this playbook when a study asks how a numerical result changes as a
resolution, data amount, discretization parameter, tolerance, model capacity, or
other approximation level is refined.

The playbook is method and problem agnostic. It does not assume a particular
equation, domain, geometry, sampling distribution, model family, solver,
regularization scheme, or method comparison. It applies to single-method
studies and comparative studies.

The core rule is:

```text
Do not interpret a convergence result from the final refinement level alone.
First inspect raw results, the selected asymptotic window, fitted trend or rate,
and any suspicious behavior.
```

## Required Study Definition

Before running the study, write:

- the fixed problem being solved or approximated;
- the refinement variable and its units or meaning;
- the ordered refinement levels;
- the quantity of interest;
- the reference solution, truth source, residual definition, or validation
  criterion;
- the primary metric and any secondary metrics;
- what is held fixed across refinement levels;
- whether the study compares methods or studies one method;
- whether any method parameters are tuned, and the tuning budget in number of
  runs;
- whether any stochastic element requires repeated trials;
- reproducibility commands and artifact locations.

## Standard Workflow

1. Define the convergence question and the expected qualitative direction of
   improvement.
2. Specify the refinement levels and the rationale for the planned asymptotic
   window.
3. Define the reference or truth source and verify that it is accurate enough
   for the claimed refinement range.
4. Define primary and secondary metrics, including units, scale, and degenerate
   cases.
5. Record all fixed parameters, tuned parameters, tuning budgets, solver
   tolerances, random seeds, and realization policies.
6. Run a small smoke case to verify execution, metrics, artifacts, and plots.
7. Run the planned sweep.
8. Inspect raw results before interpreting summaries or plots.
9. Compute convergence trends or rates over the stated fit window when
   appropriate.
10. Compare the observed trend with the expected trend if one is known.
11. Flag unexplained reversals, unstable fitted rates, reference-solution
   limits, solver failures, parameter-selection shifts, or raw/summary/plot
   mismatches.
12. If suspicious behavior appears, mark conclusions provisional and debug one
   representative anchor case first.
13. Patch only the identified root cause, then rerun the anchor case.
14. Rerun the full study when a code or protocol fix changes the result.
15. Mark earlier artifacts as superseded, confirmed, partially confirmed, or
   provisional.

## Comparison Studies

Method comparison is optional. If the study compares methods, keep the
comparison fair by recording:

- the same problem instances or a documented reason for differences;
- the same dataset and train/test split when those concepts apply;
- the same metric definitions;
- the same reference or truth source;
- the same refinement levels, or an explicit mismatch rationale;
- method-specific parameters and tuning rules;
- failed runs, boundary selections, solver tolerances, or stabilization terms.

Do not report a winner from only the finest level unless the full convergence
trend supports that interpretation.

## Parameter Tuning

When a method has tuned parameters, count only the parameters actually selected
from data or validation results. Record the search space, metric, budget, and
selected values.

Use this default policy unless the project gives a justified alternative:

- If the number of tuned parameters is `<= 3`, run a budgeted grid search first,
  then refine with a Nelder-Mead-like local optimizer.
- If the number of tuned parameters is `> 3`, run a budgeted random search over
  the parameter space, then refine with a Nelder-Mead-like optimizer initialized
  from the top-k candidates.

For grid and random search, the budget is the number of method evaluations or
validation runs. Record the refinement budget separately. For stochastic
studies, record whether the tuning objective uses a fixed split, averaged
trials, or another policy.

The protocol includes `helpers/tuning_plan.py` for generating budgeted initial
search plans and for reusing a small bounded Nelder-Mead-like refinement
routine when project code wants a generic implementation. Check
`helpers/USAGE.md` and `helper_applicability` in `protocol.yaml` before using
the helper.

## Repeated Trials

For each refinement level, run multiple trials when stochastic elements can
change the result, including data sampling, train/test split sampling, random
initialization, randomized algorithms, or stochastic solvers.

Record the number of trials, seed or realization ids, and the per-trial raw
results. Report mean and standard deviation for the primary metric and any
secondary metrics used for interpretation. When raw per-trial results are CSV
rows with scalar numeric metrics, `helpers/aggregate_trials.py` can generate
`trial_statistics.csv`.

## Convergence Sanity

Choose the asymptotic window per study and record the rationale. A useful
window usually excludes smoke levels, pre-asymptotic levels, and levels where
the reference solution, solver tolerance, roundoff, sampling noise, or resource
limits dominate.

For each method or condition, check:

- whether the primary metric improves in the expected direction;
- whether the fitted rate or trend is stable under reasonable window changes;
- whether raw results, summary tables, and plots agree;
- whether failures or outliers were excluded and why;
- whether parameter or solver behavior changes with refinement;
- whether the reference quantity is accurate enough for the claimed error.

When the convergence model is linear or log-log over numeric refinement levels,
`helpers/fit_convergence.py` can generate a reusable convergence-rate report.

## Required Plots

Include these plots when they apply:

- convergence plots with all methods overlayed, including statistics when
  repeated trials are present;
- a typical parameter-search result from one run at one refinement level:
  - 1D search spaces should use validation-metric curves;
  - 2D search spaces should use validation-metric contours or heatmaps;
  - higher-dimensional search spaces should use search-history plots;
- typical method output from one run at one refinement level, such as
  predictions or numerical solutions;
- when truth is available, a combined display of method output, truth, and
  error;
- setup plots that explain the domain, data distribution, geometry, boundary
  conditions, or other problem context.

When aggregated convergence rows are available and log-scale axes are
appropriate, `helpers/plot_convergence.py` can generate a dependency-free SVG
overlay plot. Parameter-search and method-output plots are often domain
specific; use the protocol requirements as the plot recipe when generic code
does not apply.

## Anchor-Case Debugging

When a systematic anomaly appears, select one anchor case before rerunning the
whole study. The anchor case should:

- be central to the main question;
- be simple enough to audit;
- reproduce the anomaly clearly;
- be cheap enough for extra diagnostics;
- include all relevant compared methods or conditions when comparison matters.

Debug the anchor case first. Useful diagnostics include metric recomputation,
reference-solution checks, intermediate refinement levels, fixed-parameter
variants, solver tolerance sweeps, repeated random realizations, and
raw/summary/plot consistency checks.

## Closeout

A convergence study closeout must say:

- whether the convergence sanity check passed;
- the refinement variable and levels used;
- the primary metric and reference source;
- the selected fit window and observed rate or trend;
- the trial count, means, and standard deviations when stochastic elements are
  present;
- the tuning strategy, grid/random budget, refinement budget, and selected
  parameters when tuning is used;
- which required plots were produced or why a plot was not applicable;
- whether conclusions are final or provisional;
- which anchor case was debugged, if any;
- the root cause of any anomaly, if found;
- what changed after any fix;
- whether old artifacts were superseded, confirmed, partially confirmed, or
  left provisional;
- the final interpretation and remaining caveats.

Before closeout, `helpers/validate_protocol_artifacts.py` can check file and
section completeness. It does not validate scientific correctness.
