#!/usr/bin/env python3
"""Derive A7 promotion-report inputs from already-committed real evidence.

`Skills/build_promotion_report.py` requires an injection-recovery-curves
report and a false-discovery report as standalone JSON files. Both facts
already exist as real, committed evidence -- nested inside
`data/injection_recovery_image_level_n200.json` (A6) and inside
`Logs/reports/ranking_baseline.json` (Gate Z4) -- but not in the exact
top-level shape the promotion-report builder expects. This script performs a
pure extraction/derivation: it does not run any new query, inject any new
data, or estimate anything not already present in the source file.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def extract_injection_recovery_report(source: Path) -> dict[str, Any]:
    """Pull the nested `recovery_curves` object out of an injection-recovery run.

    `Skills/injection_recovery.py --image-level` already embeds a
    schema-tagged `recovery_curves` sub-object (schema_version
    `injection-recovery-curves-v1`) inside its top-level report. This just
    lifts that sub-object to the top level so it matches what
    `build_promotion_report.py --injection-recovery-report` expects.
    """
    payload = json.loads(source.read_text(encoding="utf-8"))
    curves = payload.get("recovery_curves")
    if not isinstance(curves, dict):
        raise ValueError(f"{source} has no nested 'recovery_curves' object")
    if curves.get("schema_version") != "injection-recovery-curves-v1":
        raise ValueError(f"{source} recovery_curves has unexpected schema_version")
    return {**curves, "source_report": str(source)}


def extract_false_discovery_report(source: Path, *, model_name: str) -> dict[str, Any]:
    """Derive a false-discovery-rate report from a real ranking-baseline evaluation.

    `Skills/evaluate_ranking_baseline.py` already records exactly-observed
    `n_flagged`/`n_false_positive` counts at a fixed threshold (Gate Z4, real
    archived-negative + synthetic-positive evaluation). The false discovery
    rate is simply that ratio; nothing here is estimated or invented.
    """
    payload = json.loads(source.read_text(encoding="utf-8"))
    burden = payload.get("false_positive_review_burden")
    if not isinstance(burden, dict):
        raise ValueError(f"{source} has no 'false_positive_review_burden' object")
    n_flagged = burden.get("n_flagged")
    n_false_positive = burden.get("n_false_positive")
    if not isinstance(n_flagged, int) or not isinstance(n_false_positive, int) or n_flagged <= 0:
        raise ValueError(f"{source} false_positive_review_burden is missing required counts")
    model = payload.get(model_name)
    if not isinstance(model, dict):
        raise ValueError(f"{source} has no '{model_name}' evaluation block")
    return {
        "schema_version": "false-discovery-report-v1",
        "false_discovery_rate": n_false_positive / n_flagged,
        "n_flagged": n_flagged,
        "n_false_positive": n_false_positive,
        "threshold": burden.get("threshold"),
        "model_evaluated": model_name,
        "n_positive": payload.get("n_positive"),
        "n_negative": payload.get("n_negative"),
        "source_report": str(source),
        "limitations": [
            "Derived from Gate Z4's real archived-negative + synthetic-positive "
            "evaluation, not from a live production run.",
            "n_negative reflects only the archived negative tracklets available "
            "at Gate Z4 closure time, not a full survey population.",
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--injection-recovery-source",
        type=Path,
        help="injection_recovery.py --image-level report to extract recovery_curves from",
    )
    parser.add_argument("--injection-recovery-out", type=Path)
    parser.add_argument(
        "--ranking-baseline-source",
        type=Path,
        help="evaluate_ranking_baseline.py report to derive a false-discovery rate from",
    )
    parser.add_argument(
        "--ranking-baseline-model",
        default="logistic_regression_handcrafted",
        help="which evaluated model block to cite (default: the handcrafted baseline)",
    )
    parser.add_argument("--false-discovery-out", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    wrote_any = False

    if args.injection_recovery_source and args.injection_recovery_out:
        report = extract_injection_recovery_report(args.injection_recovery_source)
        args.injection_recovery_out.parent.mkdir(parents=True, exist_ok=True)
        args.injection_recovery_out.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"Injection-recovery report written: {args.injection_recovery_out}")
        wrote_any = True

    if args.ranking_baseline_source and args.false_discovery_out:
        report = extract_false_discovery_report(
            args.ranking_baseline_source, model_name=args.ranking_baseline_model
        )
        args.false_discovery_out.parent.mkdir(parents=True, exist_ok=True)
        args.false_discovery_out.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"False-discovery report written: {args.false_discovery_out}")
        print(f"false_discovery_rate={report['false_discovery_rate']}")
        wrote_any = True

    if not wrote_any:
        print("Nothing to do: pass a source+out pair for at least one extraction.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
