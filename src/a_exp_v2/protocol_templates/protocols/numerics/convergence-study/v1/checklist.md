# Convergence Study Checklist

## Pre-Freeze Feasibility

Complete this gate before freezing the evidence-producing design. Use
structural, reference-only, or design data, not sealed confirmation/test
performance or method rankings.

- [ ] Every planned anchor is enumerated and exercised by a bounded feasibility
  probe.
- [ ] Required sample, trial, event, and return counts are attainable at every
  anchor without weakening a requirement.
- [ ] Primary and decision-relevant secondary metrics are finite,
  nondegenerate, and discriminative on their intended support.
- [ ] Reference or truth coverage spans every planned anchor and evaluation
  window with an explicit accuracy margin.
- [ ] Artifact paths resolve, are distinct where required, and have explicit
  overwrite and supersession behavior.
- [ ] Smoke, full-run, retry, and diagnostic compute are estimated and fit the
  study's compute envelope.
- [ ] Anticipated feasibility failures map to an authorized contingency with
  attempt and compute caps, or to an explicit human-only decision.
- [ ] The feasibility probe did not open sealed confirmation/test outputs, tune
  a threshold from method performance, or change benchmark membership.

## Before Running

- [ ] Convergence question is written.
- [ ] Fixed problem definition is written.
- [ ] Refinement variable, meaning, units, and levels are written.
- [ ] Expected direction of improvement is written.
- [ ] Quantity of interest is written.
- [ ] Reference or truth source is defined.
- [ ] Primary metric formula, scale, and units are defined.
- [ ] Degenerate metric cases are handled explicitly.
- [ ] Fixed parameters are recorded.
- [ ] Tuned parameters and selection policy are recorded, if any.
- [ ] Initial tuning search budget is recorded in number of runs, if tuning is
  used.
- [ ] Refinement tuning budget is recorded in number of runs, if tuning is
  used.
- [ ] Solver tolerances or stopping rules are recorded, if any.
- [ ] Random seeds or realization policy are recorded, if randomness matters.
- [ ] Trial count per refinement level is recorded when stochastic elements are
  present.
- [ ] Artifact directory and reproducibility commands are written.
- [ ] Helper applicability is checked in `protocol.yaml` and `helpers/USAGE.md`
  before using helper code.

## Comparison Controls

Use this section when comparing methods or conditions.

- [ ] Compared methods or conditions are listed.
- [ ] Same problem instances are used, or differences are justified.
- [ ] Same dataset is used when applicable, or differences are justified.
- [ ] Same train/test split is used when applicable, or differences are
  justified.
- [ ] Same refinement levels are used, or differences are justified.
- [ ] Same reference source is used.
- [ ] Same metric definitions are used.
- [ ] Tuning budgets or selection rules are comparable or explicitly different.
- [ ] Method-specific stabilization, failures, or caveats are recorded.

## Parameter Tuning

- [ ] Tuned parameter count is recorded.
- [ ] For `<= 3` tuned parameters, budgeted grid search is run first.
- [ ] For `> 3` tuned parameters, budgeted random search is run first.
- [ ] Random-search top-k candidate count is recorded when applicable.
- [ ] Nelder-Mead-like refinement is run after initial search when applicable.
- [ ] Initial search and refinement budgets are recorded in number of runs.
- [ ] Validation or selection metric is defined.
- [ ] `tuning_plan.py` is used when its assumptions fit, or non-use is
  explained.
- [ ] Search history is recorded.
- [ ] Selected parameters and boundary/failed evaluations are recorded.

## Repeated Trials

- [ ] Multiple trials are run at each refinement level when stochastic elements
  are present.
- [ ] Seed or realization ids are recorded.
- [ ] Per-trial raw results are recorded.
- [ ] Mean and standard deviation are reported for interpreted metrics.
- [ ] `aggregate_trials.py` is used when raw per-trial CSV rows match its
  assumptions, or non-use is explained.

## Smoke Run

- [ ] Small run completes.
- [ ] Raw outputs are generated.
- [ ] Summary outputs are generated.
- [ ] Plot or table generation works, if planned.
- [ ] Raw metrics are on the intended scale.
- [ ] Reference values are available and plausible.
- [ ] Failed or undefined cases are handled as planned.

## Full Run

- [ ] All planned refinement levels complete, or failures are recorded.
- [ ] Raw results have expected row counts.
- [ ] Summaries match raw results.
- [ ] Plots match summaries.
- [ ] Resource usage or runtime is recorded if relevant.
- [ ] Parameter selections, solver tolerances, and stabilization terms are
  recorded if relevant.
- [ ] Trial statistics are generated when repeated trials are present.
- [ ] Parameter-search summaries are generated when tuning is used.
- [ ] Required plots are generated when applicable.

## Plots

- [ ] Convergence plot overlays all compared methods.
- [ ] Convergence plot shows statistics when repeated trials are present.
- [ ] `plot_convergence.py` is used when aggregated positive rows and log axes
  match its assumptions, or non-use is explained.
- [ ] A representative parameter-search plot is included when tuning is used.
- [ ] 1D parameter searches use validation-metric curves.
- [ ] 2D parameter searches use contours or heatmaps.
- [ ] Higher-dimensional parameter searches use search-history plots.
- [ ] A representative method-output plot is included.
- [ ] If truth is available, output, truth, and error are shown together.
- [ ] Problem setup, domain, geometry, data, or boundary-condition plots are
  included when they clarify the study.

## Convergence Sanity Check

- [ ] Raw results are inspected before claims are made.
- [ ] Asymptotic or fit window is selected and justified.
- [ ] Fitted rate or trend is recorded when appropriate.
- [ ] Expected rate or trend is compared when known.
- [ ] Window-sensitivity is checked when the conclusion depends on a fitted
  rate.
- [ ] `fit_convergence.py` is used when numeric levels and linear/log-log fits
  match its assumptions, or non-use is explained.
- [ ] Finest-level result agrees with the overall trend, or disagreement is
  explained.
- [ ] Outliers and failed runs are explained.
- [ ] Parameter or solver behavior across refinement is reviewed.
- [ ] Reference accuracy is sufficient over the selected window.
- [ ] Conclusions are marked provisional if sanity checks remain unresolved.

## If Suspicious

- [ ] One representative anchor case is selected.
- [ ] Anchor case selection rationale is written.
- [ ] The anomaly is reproduced on the anchor case.
- [ ] Raw results, summaries, and plots are checked for consistency.
- [ ] Metric formula and reference source are checked.
- [ ] Intermediate or finer refinement levels are added when useful.
- [ ] Solver tolerance or stopping behavior is checked when relevant.
- [ ] Fixed-parameter or parameter-sensitivity checks are run when relevant.
- [ ] Repeated realizations are run when randomness may dominate.
- [ ] Root cause is identified or genuine behavior is documented.

## After Fix or Diagnosis

- [ ] Minimal code, protocol, or interpretation issue is patched.
- [ ] Anchor case is rerun.
- [ ] Corrected anchor behavior is verified.
- [ ] Full study is rerun when the fix changes the results.
- [ ] Original artifacts are marked superseded, confirmed, partially confirmed,
  or provisional.
- [ ] Durable project memory is updated.
- [ ] `validate_protocol_artifacts.py` is used for completeness checking when
  applicable, or non-use is explained.
- [ ] Final interpretation and caveats are recorded.
