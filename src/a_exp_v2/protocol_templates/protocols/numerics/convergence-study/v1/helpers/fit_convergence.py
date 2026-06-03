"""Fit convergence rates from CSV data.

The default model is log(error) = intercept + slope * log(refinement), useful
when larger refinement values should reduce error. The reported order is
``-slope``.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path


def fit_convergence(
    rows: list[dict[str, str]],
    *,
    group_columns: list[str],
    refinement_column: str,
    value_column: str,
    window: list[float] | None = None,
    loglog: bool = True,
) -> list[dict[str, object]]:
    groups: dict[tuple[str, ...], list[tuple[float, float]]] = defaultdict(list)
    for row in rows:
        try:
            refinement = float(row[refinement_column])
            value = float(row[value_column])
        except (KeyError, TypeError, ValueError):
            continue
        if not math.isfinite(refinement) or not math.isfinite(value):
            continue
        if refinement <= 0 or (loglog and value <= 0):
            continue
        if window is not None and refinement not in set(window):
            continue
        groups[tuple(row.get(column, "") for column in group_columns)].append((refinement, value))

    output: list[dict[str, object]] = []
    for key in sorted(groups):
        points = sorted(groups[key])
        x_values = [math.log(x) if loglog else x for x, _ in points]
        y_values = [math.log(y) if loglog else y for _, y in points]
        slope, intercept = _least_squares_line(x_values, y_values)
        fitted = [intercept + slope * x for x in x_values]
        output.append(
            {
                **{column: key[index] for index, column in enumerate(group_columns)},
                "n_points": len(points),
                "fit_window": [x for x, _ in points],
                "slope": slope,
                "intercept": intercept,
                "order": -slope if loglog else slope,
                "r2": _r2(y_values, fitted),
                "monotone_decreasing": all(points[i + 1][1] <= points[i][1] for i in range(len(points) - 1)),
            }
        )
    return output


def _least_squares_line(x_values: list[float], y_values: list[float]) -> tuple[float, float]:
    if len(x_values) < 2:
        raise ValueError("at least two points are required to fit convergence")
    x_mean = sum(x_values) / len(x_values)
    y_mean = sum(y_values) / len(y_values)
    denom = sum((x - x_mean) ** 2 for x in x_values)
    if denom == 0:
        raise ValueError("refinement values must not all be equal")
    slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, y_values, strict=True)) / denom
    intercept = y_mean - slope * x_mean
    return slope, intercept


def _r2(y_values: list[float], fitted: list[float]) -> float:
    mean = sum(y_values) / len(y_values)
    total = sum((y - mean) ** 2 for y in y_values)
    if total == 0:
        return 1.0
    residual = sum((y - fit) ** 2 for y, fit in zip(y_values, fitted, strict=True))
    return 1.0 - residual / total


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    parser = argparse.ArgumentParser(description="Fit convergence rates from CSV data.")
    parser.add_argument("input_csv")
    parser.add_argument("output_json")
    parser.add_argument("--group", default="method", help="Comma-separated grouping columns")
    parser.add_argument("--refinement", default="refinement")
    parser.add_argument("--value", default="mean")
    parser.add_argument("--window", default="", help="Comma-separated refinement values")
    parser.add_argument("--linear", action="store_true", help="Use linear fit instead of log-log fit")
    args = parser.parse_args()

    window = [float(item) for item in args.window.split(",") if item.strip()] or None
    result = fit_convergence(
        read_csv(Path(args.input_csv)),
        group_columns=[item.strip() for item in args.group.split(",") if item.strip()],
        refinement_column=args.refinement,
        value_column=args.value,
        window=window,
        loglog=not args.linear,
    )
    Path(args.output_json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output_json).write_text(json.dumps(result, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
