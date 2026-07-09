#!/usr/bin/env python
"""Run Astrometrics canonical regression eval suites.

Usage:
    PYTHONPATH=src uv run --python 3.14 python Skills/run_canonical_evals.py \
        data_selection/canonical_evals/example_suite.json \
        --out Logs/reports/canonical_eval_report.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from canonical_eval import evaluate_suite, load_json  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Run canonical regression evals")
    parser.add_argument("suite", type=Path, help="canonical eval suite JSON")
    parser.add_argument("--out", type=Path, help="optional report output path")
    args = parser.parse_args()

    try:
        suite = load_json(args.suite)
        report = evaluate_suite(suite, suite_dir=args.suite.parent)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)

    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered + "\n")
        print(f"Canonical eval report written: {args.out}")
        print(f"passed={report['passed']} cases={report['n_cases']} checks={report['n_checks']}")
    else:
        print(rendered)

    sys.exit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
