"""Batch-compute weighted priority scores for ScoredNEO candidates from JSON."""

from __future__ import annotations

import argparse
import json
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compute weighted priority scores for ScoredNEO candidates from JSON."
    )
    parser.add_argument("input", help="Path to JSON file containing a list of ScoredNEO dicts.")
    parser.add_argument(
        "--weights",
        default=None,
        help=(
            "Comma-separated key=value weight overrides, e.g. "
            "'discovery=0.5,threat=0.3,observation=0.1,close_approach=0.1'."
        ),
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.0,
        help="Minimum weighted priority to include in output (default: 0.0).",
    )
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

    # Parse weight overrides
    weights: dict[str, float] | None = None
    if args.weights:
        weights = {}
        for pair in args.weights.split(","):
            try:
                k, v = pair.strip().split("=", 1)
                weights[k.strip()] = float(v.strip())
            except ValueError:
                print(f"ERROR: invalid weight spec '{pair}'", file=sys.stderr)
                sys.exit(1)

    # Reconstruct ScoredNEO objects
    sys.path.insert(0, "src")
    try:
        from schemas import ScoredNEO
        from score import compute_weighted_priority
    except ImportError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    rows = []
    errors = 0
    for item in data:
        try:
            neo = ScoredNEO.model_validate(item)
            wp = compute_weighted_priority(neo, weights=weights)
            rows.append({
                "object_id": neo.tracklet.object_id,
                "weighted_priority": wp,
                "hazard_flag": neo.hazard.hazard_flag,
                "alert_pathway": neo.hazard.alert_pathway,
            })
        except Exception as exc:
            print(f"WARN: skipping item: {exc}", file=sys.stderr)
            errors += 1

    rows = [r for r in rows if r["weighted_priority"] >= args.threshold]
    rows.sort(key=lambda r: r["weighted_priority"], reverse=True)

    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        if not rows:
            print("No candidates above threshold.")
        else:
            print(f"{'Object':<22s} {'Wtd Priority':>12s} {'Flag':<16s} {'Pathway'}")
            print("-" * 80)
            for r in rows:
                print(
                    f"{r['object_id']:<22s} {r['weighted_priority']:>12.4f} "
                    f"{r['hazard_flag']:<16s} {r['alert_pathway']}"
                )
        print(f"\n{len(rows)} candidate(s) shown, {errors} error(s).")

    sys.exit(0)


if __name__ == "__main__":
    main()
