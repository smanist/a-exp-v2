"""Create a dependency-free SVG convergence overlay plot from CSV data."""

from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path


COLORS = ["#2563eb", "#dc2626", "#16a34a", "#9333ea", "#ea580c", "#0891b2"]


def make_svg(
    rows: list[dict[str, str]],
    *,
    method_column: str,
    refinement_column: str,
    value_column: str,
    std_column: str | None = None,
    width: int = 900,
    height: int = 560,
) -> str:
    series: dict[str, list[tuple[float, float, float | None]]] = defaultdict(list)
    for row in rows:
        try:
            refinement = float(row[refinement_column])
            value = float(row[value_column])
            std = float(row[std_column]) if std_column and row.get(std_column, "") else None
        except (KeyError, TypeError, ValueError):
            continue
        if refinement > 0 and value > 0 and math.isfinite(refinement) and math.isfinite(value):
            series[row.get(method_column, "method")].append((refinement, value, std))

    if not series:
        raise ValueError("no plottable positive data found")
    for values in series.values():
        values.sort()

    x_values = [x for values in series.values() for x, _, _ in values]
    y_values = [y for values in series.values() for _, y, _ in values]
    for values in series.values():
        for _, y, std in values:
            if std is not None and std > 0:
                y_values.extend([max(y - std, 1e-300), y + std])

    margin_left, margin_right, margin_top, margin_bottom = 86, 34, 40, 76
    plot_w = width - margin_left - margin_right
    plot_h = height - margin_top - margin_bottom
    x_min, x_max = math.log10(min(x_values)), math.log10(max(x_values))
    y_min, y_max = math.log10(min(y_values)), math.log10(max(y_values))
    if x_min == x_max:
        x_min -= 0.5
        x_max += 0.5
    if y_min == y_max:
        y_min -= 0.5
        y_max += 0.5

    def sx(x: float) -> float:
        return margin_left + (math.log10(x) - x_min) / (x_max - x_min) * plot_w

    def sy(y: float) -> float:
        return margin_top + (y_max - math.log10(y)) / (y_max - y_min) * plot_h

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<rect x="{margin_left}" y="{margin_top}" width="{plot_w}" height="{plot_h}" fill="#fafafa" stroke="#d4d4d4"/>',
        f'<text x="{width / 2}" y="24" text-anchor="middle" font-family="sans-serif" font-size="18">Convergence Overlay</text>',
        f'<text x="{width / 2}" y="{height - 18}" text-anchor="middle" font-family="sans-serif" font-size="13">refinement level (log scale)</text>',
        f'<text x="18" y="{height / 2}" text-anchor="middle" transform="rotate(-90 18 {height / 2})" font-family="sans-serif" font-size="13">metric (log scale)</text>',
    ]
    for index, (method, values) in enumerate(sorted(series.items())):
        color = COLORS[index % len(COLORS)]
        points = " ".join(f"{sx(x):.2f},{sy(y):.2f}" for x, y, _ in values)
        parts.append(f'<polyline fill="none" stroke="{color}" stroke-width="2.2" points="{points}"/>')
        for x, y, std in values:
            cx, cy = sx(x), sy(y)
            parts.append(f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="4" fill="{color}"/>')
            if std is not None and std > 0:
                y0 = sy(max(y - std, 1e-300))
                y1 = sy(y + std)
                parts.append(f'<line x1="{cx:.2f}" x2="{cx:.2f}" y1="{y0:.2f}" y2="{y1:.2f}" stroke="{color}" stroke-width="1.2"/>')
        legend_y = margin_top + 20 + index * 22
        parts.append(f'<line x1="{width - 180}" x2="{width - 150}" y1="{legend_y}" y2="{legend_y}" stroke="{color}" stroke-width="2.2"/>')
        parts.append(f'<text x="{width - 142}" y="{legend_y + 4}" font-family="sans-serif" font-size="12">{_escape(method)}</text>')

    for value in _nice_log_ticks(10**x_min, 10**x_max):
        x = sx(value)
        parts.append(f'<line x1="{x:.2f}" x2="{x:.2f}" y1="{margin_top + plot_h}" y2="{margin_top + plot_h + 5}" stroke="#737373"/>')
        parts.append(f'<text x="{x:.2f}" y="{margin_top + plot_h + 20}" text-anchor="middle" font-family="sans-serif" font-size="11">{value:g}</text>')
    for value in _nice_log_ticks(10**y_min, 10**y_max):
        y = sy(value)
        parts.append(f'<line x1="{margin_left - 5}" x2="{margin_left}" y1="{y:.2f}" y2="{y:.2f}" stroke="#737373"/>')
        parts.append(f'<text x="{margin_left - 8}" y="{y + 4:.2f}" text-anchor="end" font-family="sans-serif" font-size="11">{value:g}</text>')

    parts.append("</svg>")
    return "\n".join(parts)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _nice_log_ticks(low: float, high: float) -> list[float]:
    start = math.floor(math.log10(low))
    stop = math.ceil(math.log10(high))
    return [10.0**power for power in range(start, stop + 1) if low <= 10.0**power <= high]


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a convergence overlay SVG from CSV data.")
    parser.add_argument("input_csv")
    parser.add_argument("output_svg")
    parser.add_argument("--method", default="method")
    parser.add_argument("--refinement", default="refinement")
    parser.add_argument("--value", default="mean")
    parser.add_argument("--std", default="std")
    args = parser.parse_args()

    svg = make_svg(
        read_csv(Path(args.input_csv)),
        method_column=args.method,
        refinement_column=args.refinement,
        value_column=args.value,
        std_column=args.std,
    )
    Path(args.output_svg).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output_svg).write_text(svg, encoding="utf-8")


if __name__ == "__main__":
    main()
