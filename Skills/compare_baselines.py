#!/usr/bin/env python
"""Compare two injection-recovery baseline JSON files and report deltas.

Reads two JSON files produced by Skills/injection_recovery.py and prints
a side-by-side comparison of detection/link/score rates with absolute and
relative differences.

Usage:
    PYTHONPATH=src python Skills/compare_baselines.py baseline_a.json baseline_b.json
    PYTHONPATH=src python Skills/compare_baselines.py --json a.json b.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_RATE_KEYS = ["detection_rate", "link_rate", "score_rate"]
_COUNT_KEYS = ["n_injected", "n_detected", "n_linked", "n_scored"]


def load_baseline(path: Path) -> dict:
    with path.open() as f:
        return json.load(f)


def compare_baselines(a: dict, b: dict, label_a: str = "A", label_b: str = "B") -> dict:
    """Return a comparison summary dict."""
    rate_deltas = {}
    for key in _RATE_KEYS:
        va = a.get(key)
        vb = b.get(key)
        if va is None and vb is None:
            continue
        va_f = float(va) if va is not None else float("nan")
        vb_f = float(vb) if vb is not None else float("nan")
        delta = vb_f - va_f
        rel = (delta / va_f * 100.0) if va_f != 0.0 else float("nan")
        rate_deltas[key] = {
            label_a: round(va_f, 4),
            label_b: round(vb_f, 4),
            "delta": round(delta, 4),
            "delta_pct": round(rel, 2),
            "improved": delta > 0,
            "regressed": delta < 0,
        }

    count_deltas = {}
    for key in _COUNT_KEYS:
        va = a.get(key)
        vb = b.get(key)
        if va is None and vb is None:
            continue
        count_deltas[key] = {label_a: va, label_b: vb, "delta": (vb or 0) - (va or 0)}

    hazard_a = a.get("hazard_flag_counts", {})
    hazard_b = b.get("hazard_flag_counts", {})
    hazard_deltas = {}
    for flag in set(hazard_a) | set(hazard_b):
        va_c = hazard_a.get(flag, 0)
        vb_c = hazard_b.get(flag, 0)
        hazard_deltas[flag] = {label_a: va_c, label_b: vb_c, "delta": vb_c - va_c}

    overall_improvement = all(
        v.get("delta", 0) >= 0 for v in rate_deltas.values()
    )
    any_regression = any(v.get("regressed", False) for v in rate_deltas.values())

    return {
        "label_a": label_a,
        "label_b": label_b,
        "rate_deltas": rate_deltas,
        "count_deltas": count_deltas,
        "hazard_flag_deltas": hazard_deltas,
        "overall_improvement": overall_improvement,
        "any_regression": any_regression,
    }


def print_comparison(cmp: dict) -> None:
    la, lb = cmp["label_a"], cmp["label_b"]
    print(f"\nBaseline Comparison: {la}  →  {lb}\n")

    # Rates
    print(f"  {'Metric':<25} {la:>10} {lb:>10} {'Delta':>10} {'Δ%':>8}  {'':>4}")
    print("  " + "-" * 65)
    for key, v in cmp["rate_deltas"].items():
        arrow = "↑" if v["improved"] else ("↓" if v["regressed"] else "=")
        print(
            f"  {key:<25} {v[la]:>10.4f} {v[lb]:>10.4f} "
            f"{v['delta']:>+10.4f} {v['delta_pct']:>+7.2f}%  {arrow}"
        )

    # Counts
    print(f"\n  {'Count':<25} {la:>10} {lb:>10} {'Delta':>10}")
    print("  " + "-" * 50)
    for key, v in cmp["count_deltas"].items():
        print(f"  {key:<25} {v[la] or 0:>10} {v[lb] or 0:>10} {v['delta']:>+10}")

    # Hazard flags
    if cmp["hazard_flag_deltas"]:
        print(f"\n  {'Hazard flag':<25} {la:>10} {lb:>10} {'Delta':>10}")
        print("  " + "-" * 50)
        for flag, v in sorted(cmp["hazard_flag_deltas"].items()):
            print(f"  {flag:<25} {v[la]:>10} {v[lb]:>10} {v['delta']:>+10}")

    verdict = "IMPROVED" if cmp["overall_improvement"] else ("REGRESSED" if cmp["any_regression"] else "UNCHANGED")
    print(f"\n  Verdict: {verdict}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare two injection-recovery baselines")
    parser.add_argument("baseline_a", type=Path, help="Path to first (reference) baseline JSON")
    parser.add_argument("baseline_b", type=Path, help="Path to second (new) baseline JSON")
    parser.add_argument("--json", action="store_true", help="Output comparison as JSON")
    args = parser.parse_args()

    for p in (args.baseline_a, args.baseline_b):
        if not p.exists():
            print(f"ERROR: file not found: {p}", file=sys.stderr)
            sys.exit(1)

    a = load_baseline(args.baseline_a)
    b = load_baseline(args.baseline_b)
    cmp = compare_baselines(a, b, label_a=args.baseline_a.name, label_b=args.baseline_b.name)

    if args.json:
        print(json.dumps(cmp, indent=2))
    else:
        print_comparison(cmp)

    sys.exit(1 if cmp["any_regression"] else 0)


if __name__ == "__main__":
    main()
