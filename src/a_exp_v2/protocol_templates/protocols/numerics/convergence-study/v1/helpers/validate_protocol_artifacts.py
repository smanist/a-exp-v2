"""Validate convergence-study artifact completeness.

This helper checks presence of required files and required experiment sections.
It is intentionally a completeness check, not a scientific correctness check.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


BASE_REQUIRED_FILES = [
    "run_config.yaml",
    "raw_results.csv",
    "convergence_summary.csv",
    "convergence_rates.csv",
]

BASE_REQUIRED_SECTIONS = [
    "Question",
    "Problem Definition",
    "Refinement Variable",
    "Reference or Truth Source",
    "Metrics",
    "Protocol",
    "Convergence Sanity Check",
    "Results",
    "Interpretation",
    "Closeout",
]


def validate_artifacts(
    *,
    artifacts_dir: Path,
    experiment_md: Path | None = None,
    stochastic: bool = False,
    tuned: bool = False,
    plots_required: bool = True,
) -> dict[str, object]:
    required_files = list(BASE_REQUIRED_FILES)
    if stochastic:
        required_files.append("trial_statistics.csv")
    if tuned:
        required_files.append("parameter_search_history.csv")
    if plots_required:
        required_files.append("plots")

    missing_files = []
    for name in required_files:
        path = artifacts_dir / name
        if not path.exists():
            missing_files.append(str(path))

    missing_sections: list[str] = []
    if experiment_md is not None:
        text = experiment_md.read_text(encoding="utf-8")
        for section in BASE_REQUIRED_SECTIONS:
            if f"## {section}" not in text:
                missing_sections.append(section)
        if tuned and "## Parameter Tuning" not in text:
            missing_sections.append("Parameter Tuning")
        if plots_required and "## Plots" not in text:
            missing_sections.append("Plots")

    return {
        "ok": not missing_files and not missing_sections,
        "missing_files": missing_files,
        "missing_sections": missing_sections,
        "checked_files": required_files,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate convergence-study artifact completeness.")
    parser.add_argument("artifacts_dir")
    parser.add_argument("--experiment-md")
    parser.add_argument("--stochastic", action="store_true")
    parser.add_argument("--tuned", action="store_true")
    parser.add_argument("--no-plots-required", action="store_true")
    args = parser.parse_args()

    result = validate_artifacts(
        artifacts_dir=Path(args.artifacts_dir),
        experiment_md=Path(args.experiment_md) if args.experiment_md else None,
        stochastic=args.stochastic,
        tuned=args.tuned,
        plots_required=not args.no_plots_required,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
