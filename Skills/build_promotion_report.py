"""Build a fail-closed Astrometrics model promotion report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from promotion_report import PromotionInputs, build_promotion_report  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--model-type", required=True)
    parser.add_argument("--model-version", required=True)
    parser.add_argument("--dataset-manifest", action="append", type=Path, default=[])
    parser.add_argument("--grouped-split-report", type=Path, required=True)
    parser.add_argument("--canonical-eval-report", type=Path, required=True)
    parser.add_argument("--injection-recovery-report", type=Path, required=True)
    parser.add_argument("--calibration-report", type=Path, required=True)
    parser.add_argument("--false-discovery-report", type=Path, required=True)
    parser.add_argument("--pretrained-audit", type=Path, required=True)
    parser.add_argument("--benchmark-model-card", type=Path, required=True)
    parser.add_argument("--operator-signoff-id")
    parser.add_argument("--max-false-discovery-rate", type=float, default=0.05)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_promotion_report(
        PromotionInputs(
            model_id=args.model_id,
            model_type=args.model_type,
            model_version=args.model_version,
            dataset_manifests=tuple(args.dataset_manifest),
            grouped_split_report=args.grouped_split_report,
            canonical_eval_report=args.canonical_eval_report,
            injection_recovery_report=args.injection_recovery_report,
            calibration_report=args.calibration_report,
            false_discovery_report=args.false_discovery_report,
            pretrained_audit=args.pretrained_audit,
            benchmark_model_card=args.benchmark_model_card,
            operator_signoff_id=args.operator_signoff_id,
            max_false_discovery_rate=args.max_false_discovery_rate,
        )
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Promotion report written: {args.out}")
    print(f"promotion_allowed={str(report['promotion_allowed']).lower()}")
    if report["promotion_blockers"]:
        print("promotion_blockers=" + ",".join(report["promotion_blockers"]))
    return 0 if report["promotion_allowed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
