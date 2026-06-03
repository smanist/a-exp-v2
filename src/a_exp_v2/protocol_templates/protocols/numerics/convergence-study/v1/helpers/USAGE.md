# Helper Usage

These helpers are optional protocol support code. Use them when their input
assumptions match the experiment. If a helper does not apply, record why in the
experiment closeout and satisfy the protocol manually.

## Applicability Rule

Use a helper only when all three are true:

- the experiment has the required inputs;
- the helper assumptions match the method and problem;
- the helper output satisfies a protocol-required artifact.

## Tuning Plan

Generate a budgeted initial search plan:

```text
python protocols/numerics/convergence-study/v1/helpers/tuning_plan.py params.json --budget 20 --top-k 3
```

`params.json`:

```json
{
  "parameters": [
    {"name": "alpha", "bounds": [0.001, 10.0], "scale": "log"},
    {"name": "degree", "values": [1, 2, 3, 4]}
  ]
}
```

## Trial Aggregation

Aggregate repeated trials into `trial_statistics.csv`:

```text
python protocols/numerics/convergence-study/v1/helpers/aggregate_trials.py raw_results.csv trial_statistics.csv --group method,refinement,metric --value value
```

## Convergence Fit

Fit log-log convergence rates from aggregated trial statistics:

```text
python protocols/numerics/convergence-study/v1/helpers/fit_convergence.py trial_statistics.csv convergence_rates.json --group method --refinement refinement --value mean
```

Use `--window 128,256,512` to fit only a selected asymptotic window.

## Artifact Validation

Check whether required files and sections are present:

```text
python protocols/numerics/convergence-study/v1/helpers/validate_protocol_artifacts.py artifacts/run-001 --experiment-md projects/demo/experiments/run-001/EXPERIMENT.md --stochastic --tuned
```

## Convergence Plot

Generate a dependency-free SVG convergence overlay plot:

```text
python protocols/numerics/convergence-study/v1/helpers/plot_convergence.py trial_statistics.csv plots/convergence.svg --method method --refinement refinement --value mean --std std
```

Parameter-search plots and method-output plots are usually method/problem
specific. Use the protocol plot policy to decide which representation applies:
1D validation curves, 2D contours or heatmaps, or higher-dimensional search
history.
