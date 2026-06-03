# Convergence Study Checklist

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
- [ ] Solver tolerances or stopping rules are recorded, if any.
- [ ] Random seeds or realization policy are recorded, if randomness matters.
- [ ] Artifact directory and reproducibility commands are written.

## Comparison Controls

Use this section when comparing methods or conditions.

- [ ] Compared methods or conditions are listed.
- [ ] Same problem instances are used, or differences are justified.
- [ ] Same refinement levels are used, or differences are justified.
- [ ] Same reference source is used.
- [ ] Same metric definitions are used.
- [ ] Tuning budgets or selection rules are comparable or explicitly different.
- [ ] Method-specific stabilization, failures, or caveats are recorded.

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

## Convergence Sanity Check

- [ ] Raw results are inspected before claims are made.
- [ ] Asymptotic or fit window is selected and justified.
- [ ] Fitted rate or trend is recorded when appropriate.
- [ ] Expected rate or trend is compared when known.
- [ ] Window-sensitivity is checked when the conclusion depends on a fitted
  rate.
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
- [ ] Final interpretation and caveats are recorded.
