from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


HELPER_PATH = (
    Path(__file__).parents[1]
    / "src"
    / "a_exp_v2"
    / "protocol_templates"
    / "protocols"
    / "numerics"
    / "convergence-study"
    / "v1"
    / "helpers"
    / "tuning_plan.py"
)


def load_helper(name: str = "tuning_plan"):
    path = HELPER_PATH.parent / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_initial_search_plan_uses_grid_for_three_or_fewer_parameters() -> None:
    helper = load_helper()
    parameters = [
        helper.Parameter.from_mapping({"name": "alpha", "bounds": [0.0, 1.0]}),
        helper.Parameter.from_mapping({"name": "beta", "values": [1, 2, 3]}),
    ]

    plan = helper.initial_search_plan(parameters, 5)

    assert plan["strategy"] == "grid"
    assert plan["initial_budget_runs"] == 5
    assert plan["candidate_count"] == 5
    assert plan["refinement"]["algorithm"] == "nelder-mead-like"
    assert all({"alpha", "beta"} == set(candidate) for candidate in plan["candidates"])


def test_initial_search_plan_uses_random_for_more_than_three_parameters() -> None:
    helper = load_helper()
    parameters = [
        helper.Parameter.from_mapping({"name": f"p{i}", "bounds": [1.0, 10.0], "scale": "log"})
        for i in range(4)
    ]

    plan = helper.initial_search_plan(parameters, 7, seed=123, top_k=2)

    assert plan["strategy"] == "random"
    assert plan["candidate_count"] == 7
    assert plan["refinement"]["top_k"] == 2
    assert plan["candidates"] == helper.initial_search_plan(parameters, 7, seed=123, top_k=2)["candidates"]


def test_initial_search_plan_respects_parameter_domain_constraints() -> None:
    helper = load_helper()
    parameters = [
        helper.Parameter.from_mapping({"name": "tol", "bounds": [1e-16, 1e1], "scale": "log"}),
        helper.Parameter.from_mapping({"name": "degree", "bounds": [1, 9], "type": "int", "parity": "odd"}),
        helper.Parameter.from_mapping({"name": "theta", "bounds": [0.0, 1.0], "step": 0.25}),
    ]

    plan = helper.initial_search_plan(parameters, 12)

    assert plan["strategy"] == "grid"
    assert plan["parameter_domains"][1]["type"] == "int"
    assert plan["parameter_domains"][1]["parity"] == "odd"
    assert plan["parameter_domains"][2]["step"] == 0.25
    assert all(1e-16 <= candidate["tol"] <= 1e1 for candidate in plan["candidates"])
    assert all(candidate["degree"] % 2 == 1 for candidate in plan["candidates"])
    assert {candidate["theta"] for candidate in plan["candidates"]}.issubset({0.0, 0.25, 0.5, 0.75, 1.0})
    assert "project integer" in plan["refinement"]["constraint_note"]


def test_random_search_projects_integer_and_step_constraints() -> None:
    helper = load_helper()
    parameters = [
        helper.Parameter.from_mapping({"name": f"continuous_{i}", "bounds": [0.0, 1.0]})
        for i in range(3)
    ]
    parameters.extend(
        [
            helper.Parameter.from_mapping({"name": "width", "bounds": [2, 12], "type": "int", "parity": "even"}),
            helper.Parameter.from_mapping({"name": "mix", "bounds": [0.0, 1.0], "step": 0.2}),
        ]
    )

    plan = helper.initial_search_plan(parameters, 20, seed=11)

    assert plan["strategy"] == "random"
    assert all(candidate["width"] % 2 == 0 for candidate in plan["candidates"])
    assert all(2 <= candidate["width"] <= 12 for candidate in plan["candidates"])
    assert {candidate["mix"] for candidate in plan["candidates"]}.issubset({0.0, 0.2, 0.4, 0.6, 0.8, 1.0})


def test_parameter_rejects_impossible_integer_constraints() -> None:
    helper = load_helper()

    try:
        helper.Parameter.from_mapping({"name": "width", "bounds": [1, 9], "type": "int", "step": 2, "parity": "even"})
    except ValueError as exc:
        assert "admit no values" in str(exc)
    else:
        raise AssertionError("expected impossible integer constraints to fail")


def test_nelder_mead_like_refines_quadratic() -> None:
    helper = load_helper()

    result = helper.nelder_mead_like(
        lambda x: (x[0] - 2.0) ** 2 + (x[1] + 1.0) ** 2,
        [0.0, 0.0],
        step=0.5,
        bounds=[(-5.0, 5.0), (-5.0, 5.0)],
        max_evals=80,
    )

    assert result["value"] < 1e-3
    assert abs(result["x"][0] - 2.0) < 0.1
    assert abs(result["x"][1] + 1.0) < 0.1


def test_aggregate_trials_computes_mean_and_sample_std() -> None:
    helper = load_helper("aggregate_trials")
    rows = [
        {"method": "a", "refinement": "10", "metric": "err", "value": "1.0"},
        {"method": "a", "refinement": "10", "metric": "err", "value": "3.0"},
        {"method": "b", "refinement": "10", "metric": "err", "value": "2.0"},
    ]

    result = helper.aggregate_trials(rows, group_columns=["method", "refinement", "metric"], value_column="value")

    assert result[0]["method"] == "a"
    assert result[0]["count"] == "2"
    assert result[0]["mean"] == "2"
    assert result[0]["std"] == "1.41421356237"
    assert result[1]["method"] == "b"
    assert result[1]["std"] == "0"


def test_fit_convergence_reports_loglog_order_and_monotonicity() -> None:
    helper = load_helper("fit_convergence")
    rows = [
        {"method": "a", "refinement": "10", "mean": "0.1"},
        {"method": "a", "refinement": "20", "mean": "0.025"},
        {"method": "a", "refinement": "40", "mean": "0.00625"},
    ]

    result = helper.fit_convergence(
        rows,
        group_columns=["method"],
        refinement_column="refinement",
        value_column="mean",
    )

    assert len(result) == 1
    assert result[0]["method"] == "a"
    assert abs(result[0]["order"] - 2.0) < 1e-10
    assert result[0]["monotone_decreasing"] is True


def test_validate_protocol_artifacts_checks_conditional_files_and_sections(tmp_path: Path) -> None:
    helper = load_helper("validate_protocol_artifacts")
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    for name in [
        "run_config.yaml",
        "raw_results.csv",
        "convergence_summary.csv",
        "convergence_rates.csv",
        "trial_statistics.csv",
        "parameter_search_history.csv",
    ]:
        (artifacts / name).write_text("ok\n", encoding="utf-8")
    (artifacts / "plots").mkdir()
    experiment = tmp_path / "EXPERIMENT.md"
    experiment.write_text(
        "\n".join(
            [
                "## Question",
                "## Problem Definition",
                "## Refinement Variable",
                "## Reference or Truth Source",
                "## Parameter Tuning",
                "## Metrics",
                "## Protocol",
                "## Convergence Sanity Check",
                "## Results",
                "## Plots",
                "## Interpretation",
                "## Closeout",
            ]
        ),
        encoding="utf-8",
    )

    result = helper.validate_artifacts(
        artifacts_dir=artifacts,
        experiment_md=experiment,
        stochastic=True,
        tuned=True,
    )

    assert result["ok"] is True


def test_plot_convergence_generates_svg() -> None:
    helper = load_helper("plot_convergence")
    rows = [
        {"method": "a", "refinement": "10", "mean": "0.1", "std": "0.01"},
        {"method": "a", "refinement": "20", "mean": "0.05", "std": "0.005"},
        {"method": "b", "refinement": "10", "mean": "0.2", "std": "0.02"},
        {"method": "b", "refinement": "20", "mean": "0.1", "std": "0.01"},
    ]

    svg = helper.make_svg(
        rows,
        method_column="method",
        refinement_column="refinement",
        value_column="mean",
        std_column="std",
    )

    assert svg.startswith("<svg")
    assert "Convergence Overlay" in svg
    assert "<polyline" in svg
