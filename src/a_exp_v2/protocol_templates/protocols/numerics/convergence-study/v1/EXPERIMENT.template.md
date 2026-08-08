---
id: <experiment-id>
status: planned
date: YYYY-MM-DD
study: <study-id>
protocol: numerics.convergence-study.v1
producer: autonomous
context_revision: <context-revision>
run_id: <run-id>
---

# Experiment: <name>

Protocol: `numerics.convergence-study.v1`

## Question

State the convergence question. Define what behavior would support, weaken, or
leave unresolved the expected conclusion.

## Problem Definition

- Fixed problem, dataset, domain, equation, operator, target, or quantity:
- Boundary, geometry, sampling, forcing, initial condition, or data-generation
  details if relevant:
- What remains fixed across refinement levels:
- Dataset identity or generation policy:
- Train/test split policy:
- Known analytic, numerical, or empirical expectations:

## Refinement Variable

- Variable name:
- Meaning and units:
- Ordered refinement levels:
- Expected direction of improvement:
- Planned asymptotic or fit window:
- Rationale for excluding any levels from the fit:

## Reference or Truth Source

- Reference definition:
- Accuracy or reliability argument:
- Reference computation command or artifact:
- Reference limitations:
- Degenerate or zero-scale cases:

## Methods or Conditions

Use this section for one method or many methods.

For each method or condition, record:

- name:
- implementation or model form:
- fixed parameters:
- tuned parameters and selection policy:
- solver tolerance or stopping rule:
- numerical stabilization, if any:
- random seed or realization policy:
- known caveats:

## Parameter Tuning

Use this section when any method has tuned parameters.

- Tuned parameter count:
- Search space and admissible domains:
  - bounds:
  - scale (`linear` or `log`):
  - type (`float` or `int`):
  - step/grid spacing, if any:
  - parity (`even` or `odd`), if any:
  - explicit admissible values, if values-only:
- Validation or selection metric:
- Initial search policy: grid if `<= 3` tuned parameters, random if `> 3`
- Initial search budget, in runs:
- Refinement policy: Nelder-Mead-like
- Refinement budget, in runs:
- Top-k candidates for refinement, if random search is used:
- Constraint handling during refinement:
- Search history artifact:
- Selected parameters:
- Boundary, failed, or invalid evaluations:

## Metrics

- Primary metric:
- Formula:
- Scale and units:
- Secondary metrics:
- Cost, runtime, or resource metrics:
- Handling of failed, infinite, undefined, or degenerate values:

## Fairness Controls

Use this section when comparing methods or conditions.

- Same problem instances:
- Same dataset, if applicable:
- Same train/test split, if applicable:
- Same refinement levels:
- Same reference source:
- Same metrics:
- Same data, random seeds, or realizations where applicable:
- Same tuning budget or justified differences:
- Method-specific exceptions:

## Protocol

- Smoke run:
- Full run:
- Repeated realizations:
- Trial count per refinement level:
- Trial seeds or realization ids:
- Resource limits:
- Artifact directory:
- Reproducibility commands:

## Convergence Sanity Check

Record:

- raw results inspected:
- summaries and plots match raw results:
- selected asymptotic or fit window:
- fitted rate or trend:
- expected rate or trend, if known:
- window-sensitivity check:
- outliers or failed runs:
- finest-level result agrees with overall trend:
- parameter, solver, or stabilization behavior across refinement:
- reference accuracy is sufficient over the fit window:

## Debug Anchor

Use this section only if convergence looks suspicious.

- Anchor case:
- Why this anchor was chosen:
- Observed anomaly:
- First suspected cause:
- Extra diagnostics:
- Root cause:
- Fix or interpretation:
- Anchor rerun result:

## Results

- Raw result summary:
- Convergence summary:
- Rate or trend summary:
- Cost or resource summary:
- Comparison summary, if applicable:
- Trial mean/std summary, if stochastic:
- Parameter-search summary, if tuned:
- Failure or caveat table:

## Plots

Include paths and short notes.

- Convergence overlay plot:
- Statistics shown on convergence plot, if repeated trials are present:
- Parameter-search plot from one representative run/refinement level:
- Method-output plot from one representative run/refinement level:
- Output/truth/error plot, if truth is available:
- Problem setup, domain, geometry, or data plot:
- Additional explanatory plots:

## Interpretation

State whether the hypothesis is supported, weakened, unresolved, superseded, or
still provisional. Do not treat the final refinement level as decisive when it
conflicts with the convergence trend or unresolved sanity checks.

## Caveats

List limitations from reference accuracy, pre-asymptotic behavior, sample
variance, solver tolerance, conditioning, parameter selection, resource limits,
or metric degeneracy.

## Closeout

- Protocol version:
- Commands:
- Artifact directory:
- Original artifact status: superseded, confirmed, partially confirmed, or
  provisional
- Root cause if debugged:
- Fix applied:
- Durable-memory update:
