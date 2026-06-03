"""Reusable tuning helpers for convergence-study experiments.

The helpers intentionally do not know how to run a project method. They provide
the protocol-standard search plan and a small bounded Nelder-Mead-like
refinement routine that project code can call around its own validation metric.
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Parameter:
    name: str
    bounds: tuple[float, float] | None = None
    values: tuple[Any, ...] | None = None
    scale: str = "linear"
    value_type: str = "float"
    step: float | None = None
    parity: str | None = None

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> "Parameter":
        if "name" not in raw:
            raise ValueError("parameter missing required field: name")
        values = tuple(raw["values"]) if "values" in raw else None
        if values is not None and len(values) == 0:
            raise ValueError(f"{raw['name']}: values must not be empty")
        bounds = None
        if "bounds" in raw:
            if len(raw["bounds"]) != 2:
                raise ValueError(f"{raw['name']}: bounds must have two values")
            bounds = (float(raw["bounds"][0]), float(raw["bounds"][1]))
            if bounds[0] > bounds[1]:
                raise ValueError(f"{raw['name']}: lower bound must be <= upper bound")
        if values is None and bounds is None:
            raise ValueError(f"{raw['name']}: provide either values or bounds")
        scale = str(raw.get("scale", "linear"))
        if scale not in {"linear", "log"}:
            raise ValueError(f"{raw['name']}: scale must be linear or log")
        if scale == "log" and bounds is not None and (bounds[0] <= 0 or bounds[1] <= 0):
            raise ValueError(f"{raw['name']}: log bounds must be positive")
        value_type = str(raw.get("type", raw.get("value_type", "float")))
        if value_type == "integer":
            value_type = "int"
        if value_type not in {"float", "int"}:
            raise ValueError(f"{raw['name']}: type must be float or int")
        step = float(raw["step"]) if "step" in raw else None
        if step is not None and step <= 0:
            raise ValueError(f"{raw['name']}: step must be positive")
        if value_type == "int" and step is not None and not float(step).is_integer():
            raise ValueError(f"{raw['name']}: integer step must be an integer")
        parity = raw.get("parity")
        if parity is not None:
            parity = str(parity)
            if parity not in {"even", "odd"}:
                raise ValueError(f"{raw['name']}: parity must be even or odd")
            if value_type != "int":
                raise ValueError(f"{raw['name']}: parity requires type int")
        param = cls(
            name=str(raw["name"]),
            bounds=bounds,
            values=values,
            scale=scale,
            value_type=value_type,
            step=step,
            parity=parity,
        )
        if values is None and value_type == "int" and not _has_integer_admissible_value(param):
            raise ValueError(f"{raw['name']}: integer constraints admit no values")
        return param

    @property
    def is_discrete(self) -> bool:
        return self.values is not None or self.value_type == "int" or self.step is not None

    def domain_summary(self) -> dict[str, Any]:
        summary: dict[str, Any] = {
            "name": self.name,
            "scale": self.scale,
            "type": self.value_type,
        }
        if self.bounds is not None:
            summary["bounds"] = list(self.bounds)
        if self.values is not None:
            summary["values"] = list(self.values)
        if self.step is not None:
            summary["step"] = self.step
        if self.parity is not None:
            summary["parity"] = self.parity
        return summary


def initial_search_plan(
    parameters: Sequence[Parameter],
    budget: int,
    *,
    seed: int = 0,
    top_k: int = 3,
) -> dict[str, Any]:
    """Return a protocol-standard initial tuning plan.

    Uses budgeted grid search for <=3 parameters and random search for >3
    parameters. The returned candidates are dictionaries keyed by parameter
    name. Budgets are counts of method evaluations or validation runs.
    """

    if not parameters:
        raise ValueError("at least one parameter is required")
    if budget <= 0:
        raise ValueError("budget must be positive")
    if top_k <= 0:
        raise ValueError("top_k must be positive")

    if len(parameters) <= 3:
        candidates = _grid_candidates(parameters, budget)
        strategy = "grid"
        refinement = "nelder-mead-like"
    else:
        candidates = _random_candidates(parameters, budget, seed)
        strategy = "random"
        refinement = "nelder-mead-like-from-top-k"

    return {
        "strategy": strategy,
        "initial_budget_runs": budget,
        "candidate_count": len(candidates),
        "parameter_domains": [parameter.domain_summary() for parameter in parameters],
        "candidates": candidates,
        "refinement": {
            "algorithm": refinement,
            "top_k": min(top_k, len(candidates)) if strategy == "random" else 1,
            "budget_runs": "record per experiment",
            "constraint_note": (
                "project integer, parity, step, or values-only parameters back to their admissible domain"
                if any(parameter.is_discrete for parameter in parameters)
                else "continuous bounded refinement"
            ),
        },
    }


def nelder_mead_like(
    objective: Callable[[list[float]], float],
    start: Sequence[float],
    *,
    step: Sequence[float] | float = 1.0,
    bounds: Sequence[tuple[float, float]] | None = None,
    max_evals: int = 100,
    tol: float = 1e-8,
) -> dict[str, Any]:
    """Minimize ``objective`` with a compact bounded Nelder-Mead-like search."""

    if max_evals <= 0:
        raise ValueError("max_evals must be positive")
    x0 = [float(x) for x in start]
    dim = len(x0)
    if dim == 0:
        raise ValueError("start must contain at least one value")
    if bounds is not None and len(bounds) != dim:
        raise ValueError("bounds length must match start length")
    steps = [float(step)] * dim if isinstance(step, int | float) else [float(s) for s in step]
    if len(steps) != dim:
        raise ValueError("step length must match start length")

    simplex = [_clip(x0, bounds)]
    for axis, width in enumerate(steps):
        point = list(x0)
        point[axis] += width
        simplex.append(_clip(point, bounds))

    values = [objective(point) for point in simplex]
    evals = len(values)
    history = [{"x": point, "value": value} for point, value in zip(simplex, values, strict=True)]

    while evals < max_evals:
        order = sorted(range(len(simplex)), key=lambda i: values[i])
        simplex = [simplex[i] for i in order]
        values = [values[i] for i in order]
        if max(abs(values[i] - values[0]) for i in range(1, len(values))) <= tol:
            break

        centroid = _centroid(simplex[:-1])
        worst = simplex[-1]
        reflected = _clip(_combine(centroid, worst, 2.0, -1.0), bounds)
        reflected_value = objective(reflected)
        evals += 1
        history.append({"x": reflected, "value": reflected_value})

        if reflected_value < values[0] and evals < max_evals:
            expanded = _clip(_combine(centroid, worst, 3.0, -2.0), bounds)
            expanded_value = objective(expanded)
            evals += 1
            history.append({"x": expanded, "value": expanded_value})
            simplex[-1], values[-1] = (
                (expanded, expanded_value)
                if expanded_value < reflected_value
                else (reflected, reflected_value)
            )
        elif reflected_value < values[-2]:
            simplex[-1], values[-1] = reflected, reflected_value
        elif evals < max_evals:
            contracted = _clip(_combine(centroid, worst, 0.5, 0.5), bounds)
            contracted_value = objective(contracted)
            evals += 1
            history.append({"x": contracted, "value": contracted_value})
            if contracted_value < values[-1]:
                simplex[-1], values[-1] = contracted, contracted_value
            else:
                best = simplex[0]
                for i in range(1, len(simplex)):
                    if evals >= max_evals:
                        break
                    simplex[i] = _clip([(a + b) / 2.0 for a, b in zip(best, simplex[i], strict=True)], bounds)
                    values[i] = objective(simplex[i])
                    evals += 1
                    history.append({"x": simplex[i], "value": values[i]})

    best_index = min(range(len(simplex)), key=lambda i: values[i])
    return {
        "x": simplex[best_index],
        "value": values[best_index],
        "evaluations": evals,
        "history": history,
    }


def _grid_candidates(parameters: Sequence[Parameter], budget: int) -> list[dict[str, Any]]:
    counts = _grid_counts(parameters, budget)
    axes = [_values_for_parameter(param, count) for param, count in zip(parameters, counts, strict=True)]
    candidates = [
        {param.name: value for param, value in zip(parameters, values, strict=True)}
        for values in itertools.product(*axes)
    ]
    return candidates[:budget]


def _grid_counts(parameters: Sequence[Parameter], budget: int) -> list[int]:
    counts = [1] * len(parameters)
    limits = [_axis_limit(param, budget) for param in parameters]
    while math.prod(counts) < budget:
        expandable = [i for i, count in enumerate(counts) if count < limits[i]]
        if not expandable:
            break
        axis = min(expandable, key=lambda i: counts[i])
        counts[axis] += 1
    return counts


def _values_for_parameter(param: Parameter, count: int) -> list[Any]:
    if param.values is not None:
        return list(param.values[:count])
    assert param.bounds is not None
    if param.value_type == "int":
        return _integer_values_for_parameter(param, count)
    if param.step is not None:
        return _stepped_float_values_for_parameter(param, count)
    lo, hi = param.bounds
    if count == 1:
        return [_project_value(param, (lo + hi) / 2.0 if param.scale == "linear" else math.sqrt(lo * hi))]
    if param.scale == "log":
        log_lo = math.log(lo)
        log_hi = math.log(hi)
        return [_project_value(param, math.exp(log_lo + (log_hi - log_lo) * i / (count - 1))) for i in range(count)]
    return [_project_value(param, lo + (hi - lo) * i / (count - 1)) for i in range(count)]


def _random_candidates(parameters: Sequence[Parameter], budget: int, seed: int) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    candidates = []
    for _ in range(budget):
        item = {}
        for param in parameters:
            if param.values is not None:
                item[param.name] = rng.choice(param.values)
                continue
            assert param.bounds is not None
            lo, hi = param.bounds
            if param.scale == "log":
                value = math.exp(rng.uniform(math.log(lo), math.log(hi)))
            else:
                value = rng.uniform(lo, hi)
            item[param.name] = _project_value(param, value)
        candidates.append(item)
    return candidates


def _axis_limit(param: Parameter, budget: int) -> int:
    if param.values is not None:
        return len(param.values)
    if param.value_type == "int":
        return min(_integer_value_count(param), budget)
    if param.step is not None:
        return min(_stepped_float_value_count(param), budget)
    return budget


def _integer_values_for_parameter(param: Parameter, count: int) -> list[int]:
    total = _integer_value_count(param)
    if total <= 0:
        return []
    indexes = _selected_indexes(total, min(count, total), scale=param.scale)
    return [_integer_value_at_index(param, index) for index in indexes]


def _stepped_float_values_for_parameter(param: Parameter, count: int) -> list[float]:
    total = _stepped_float_value_count(param)
    if total <= 0:
        return []
    indexes = _selected_indexes(total, min(count, total), scale=param.scale)
    return [_clean_float(_stepped_float_value_at_index(param, index)) for index in indexes]


def _selected_indexes(total: int, count: int, *, scale: str) -> list[int]:
    if count <= 1:
        return [total // 2]
    if scale == "log" and total > 1:
        raw = [round((total - 1) ** (i / (count - 1))) for i in range(count)]
    else:
        raw = [round((total - 1) * i / (count - 1)) for i in range(count)]
    indexes = []
    for index in raw:
        clipped = min(max(int(index), 0), total - 1)
        if clipped not in indexes:
            indexes.append(clipped)
    candidate = 0
    while len(indexes) < count and candidate < total:
        if candidate not in indexes:
            indexes.append(candidate)
        candidate += 1
    return sorted(indexes)


def _integer_value_count(param: Parameter) -> int:
    assert param.bounds is not None
    lo, hi = param.bounds
    anchor = math.ceil(lo)
    upper = math.floor(hi)
    if anchor > upper:
        return 0
    step = int(param.step) if param.step is not None else 1
    count = ((upper - anchor) // step) + 1
    if param.parity is None:
        return count
    if step % 2 == 0:
        return count if _matches_parity(anchor, param.parity) else 0
    return (count + 1) // 2 if _matches_parity(anchor, param.parity) else count // 2


def _integer_value_at_index(param: Parameter, admissible_index: int) -> int:
    assert param.bounds is not None
    lo, hi = param.bounds
    anchor = math.ceil(lo)
    upper = math.floor(hi)
    step = int(param.step) if param.step is not None else 1
    if param.parity is None or step % 2 == 0:
        value = anchor + admissible_index * step
    elif _matches_parity(anchor, param.parity):
        value = anchor + 2 * admissible_index * step
    else:
        value = anchor + (2 * admissible_index + 1) * step
    if value > upper or (param.parity is not None and not _matches_parity(value, param.parity)):
        raise ValueError(f"{param.name}: integer constraints admit no value at index {admissible_index}")
    return value


def _stepped_float_value_count(param: Parameter) -> int:
    assert param.bounds is not None
    assert param.step is not None
    lo, hi = param.bounds
    return max(0, math.floor((hi - lo) / param.step) + 1)


def _stepped_float_value_at_index(param: Parameter, index: int) -> float:
    assert param.bounds is not None
    assert param.step is not None
    return min(param.bounds[0] + index * param.step, param.bounds[1])


def _project_value(param: Parameter, value: float) -> Any:
    if param.values is not None:
        return min(param.values, key=lambda candidate: abs(float(candidate) - value))
    assert param.bounds is not None
    clipped = min(max(float(value), param.bounds[0]), param.bounds[1])
    if param.value_type == "int":
        return _project_integer(param, clipped)
    if param.step is not None:
        index = round((clipped - param.bounds[0]) / param.step)
        return _clean_float(_stepped_float_value_at_index(param, int(index)))
    return clipped


def _project_integer(param: Parameter, value: float) -> int:
    total = _integer_value_count(param)
    if total <= 0:
        raise ValueError(f"{param.name}: integer constraints admit no values")
    assert param.bounds is not None
    lo, hi = param.bounds
    step = int(param.step) if param.step is not None else 1
    anchor = math.ceil(lo)
    upper = math.floor(hi)
    nearest_grid_value = anchor + round((round(value) - anchor) / step) * step
    candidates = []
    for offset in range(-8, 9):
        candidate = nearest_grid_value + offset * step
        if anchor <= candidate <= upper and (param.parity is None or _matches_parity(candidate, param.parity)):
            candidates.append(candidate)
    if not candidates:
        candidates = [_integer_value_at_index(param, 0), _integer_value_at_index(param, total - 1)]
    return min(candidates, key=lambda candidate: (abs(candidate - value), candidate))


def _has_integer_admissible_value(param: Parameter) -> bool:
    return _integer_value_count(param) > 0


def _matches_parity(value: int, parity: str) -> bool:
    return value % 2 == (0 if parity == "even" else 1)


def _clean_float(value: float) -> float:
    return round(float(value), 12)


def _clip(point: Sequence[float], bounds: Sequence[tuple[float, float]] | None) -> list[float]:
    if bounds is None:
        return [float(x) for x in point]
    return [min(max(float(x), lo), hi) for x, (lo, hi) in zip(point, bounds, strict=True)]


def _centroid(points: Sequence[Sequence[float]]) -> list[float]:
    dim = len(points[0])
    return [sum(point[j] for point in points) / len(points) for j in range(dim)]


def _combine(a: Sequence[float], b: Sequence[float], a_weight: float, b_weight: float) -> list[float]:
    return [a_weight * x + b_weight * y for x, y in zip(a, b, strict=True)]


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a convergence-study tuning search plan.")
    parser.add_argument("spec", help="JSON file with a parameters list")
    parser.add_argument("--budget", type=int, required=True, help="Initial search budget in runs")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args()

    with open(args.spec, encoding="utf-8") as handle:
        spec = json.load(handle)
    parameters = [Parameter.from_mapping(item) for item in spec["parameters"]]
    print(json.dumps(initial_search_plan(parameters, args.budget, seed=args.seed, top_k=args.top_k), indent=2))


if __name__ == "__main__":
    main()
