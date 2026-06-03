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


def load_helper():
    spec = importlib.util.spec_from_file_location("tuning_plan", HELPER_PATH)
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
