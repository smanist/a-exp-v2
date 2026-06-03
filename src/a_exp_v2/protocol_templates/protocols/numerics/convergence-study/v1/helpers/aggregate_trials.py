"""Aggregate repeated-trial convergence results.

Input is a CSV with grouping columns such as method/refinement/metric and one
numeric value column. Output is a CSV with count, mean, sample standard
deviation, min, and max for each group.
"""

from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Summary:
    values: list[float]

    @property
    def count(self) -> int:
        return len(self.values)

    @property
    def mean(self) -> float:
        return sum(self.values) / len(self.values)

    @property
    def std(self) -> float:
        if len(self.values) < 2:
            return 0.0
        mean = self.mean
        return math.sqrt(sum((value - mean) ** 2 for value in self.values) / (len(self.values) - 1))


def aggregate_trials(
    rows: list[dict[str, str]],
    *,
    group_columns: list[str],
    value_column: str,
) -> list[dict[str, str]]:
    groups: dict[tuple[str, ...], list[float]] = defaultdict(list)
    for row in rows:
        try:
            value = float(row[value_column])
        except (KeyError, TypeError, ValueError):
            continue
        if not math.isfinite(value):
            continue
        key = tuple(row.get(column, "") for column in group_columns)
        groups[key].append(value)

    output = []
    for key in sorted(groups):
        values = groups[key]
        summary = Summary(values)
        item = {column: key[index] for index, column in enumerate(group_columns)}
        item.update(
            {
                "count": str(summary.count),
                "mean": _format_float(summary.mean),
                "std": _format_float(summary.std),
                "min": _format_float(min(values)),
                "max": _format_float(max(values)),
            }
        )
        output.append(item)
    return output


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _format_float(value: float) -> str:
    return f"{value:.12g}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate repeated-trial result CSV rows.")
    parser.add_argument("input_csv")
    parser.add_argument("output_csv")
    parser.add_argument("--group", required=True, help="Comma-separated grouping columns")
    parser.add_argument("--value", default="value", help="Numeric value column")
    args = parser.parse_args()

    group_columns = [item.strip() for item in args.group.split(",") if item.strip()]
    rows = aggregate_trials(read_csv(Path(args.input_csv)), group_columns=group_columns, value_column=args.value)
    write_csv(Path(args.output_csv), rows, [*group_columns, "count", "mean", "std", "min", "max"])


if __name__ == "__main__":
    main()
