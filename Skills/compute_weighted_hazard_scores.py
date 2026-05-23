"""Batch weighted hazard score computation from scored NEO JSON."""

from __future__ import annotations

import argparse
import json
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compute weighted hazard scores from a scored NEO JSON file."
    )
    parser.add_argument("input", help="Path to JSON file (list of ScoredNEO dicts).")
    parser.add_argument("--threshold", type=float, default=0.0,
                        help="Only show items with score >= threshold (default: 0.0).")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of a table.")
    args = parser.parse_args()

    try:
        with open(args.input) as fh:
            data = json.load(fh)
    except Exception as exc:
        print(f"ERROR: could not read {args.input}: {exc}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(data, list):
        data = [data]

    sys.path.insert(0, "src")
    try:
        from schemas import ScoredNEO
        from score import compute_weighted_hazard_score
    except ImportError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    rows = []
    for item in data:
        try:
            neo = ScoredNEO.model_validate(item)
            score = compute_weighted_hazard_score(neo)
            if score >= args.threshold:
                rows.append({
                    "object_id": neo.tracklet.object_id,
                    "weighted_hazard_score": score,
                    "hazard_flag": neo.hazard.hazard_flag,
                    "moid_au": neo.hazard.moid_au,
                })
        except Exception:
            pass

    rows.sort(key=lambda r: r["weighted_hazard_score"], reverse=True)

    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        if not rows:
            print("No items above threshold.")
        else:
            print(f"{'Object':<24s} {'Score':>8s} {'Flag':<18s} {'MOID (AU)'}")
            print("-" * 68)
            for r in rows:
                moid = f"{r['moid_au']:.4f}" if r["moid_au"] is not None else "N/A"
                print(f"{r['object_id']:<24s} {r['weighted_hazard_score']:>8.4f}"
                      f" {r['hazard_flag']:<18s} {moid}")
        print(f"\n{len(rows)} item(s).")

    sys.exit(0)


if __name__ == "__main__":
    main()
