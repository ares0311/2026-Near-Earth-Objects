"""Batch discovery score computation from scored NEO JSON.

Usage
-----
    python Skills/compute_discovery_scores.py data/sample_tracklets.json

    python Skills/compute_discovery_scores.py data/sample_tracklets.json \\
        --threshold 0.3 --sort --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Compute discovery scores for scored NEO candidates."
    )
    parser.add_argument("input", help="Path to scored-NEO JSON file")
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.0,
        help="Minimum discovery score to include in output (default: 0.0)",
    )
    parser.add_argument(
        "--sort",
        action="store_true",
        help="Sort output by discovery score descending",
    )
    parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Output as JSON array",
    )
    args = parser.parse_args(argv)

    from schemas import ScoredNEO
    from score import compute_discovery_score

    with open(args.input) as f:
        raw = json.load(f)

    if isinstance(raw, dict):
        raw = [raw]

    rows = []
    for item in raw:
        try:
            neo = ScoredNEO(**item)
        except Exception:
            continue
        ds = compute_discovery_score(neo)
        if ds >= args.threshold:
            rows.append({
                "object_id": neo.tracklet.object_id,
                "discovery_score": ds,
                "hazard_flag": neo.hazard.hazard_flag,
                "alert_pathway": neo.hazard.alert_pathway,
                "moid_au": neo.hazard.moid_au,
            })

    if args.sort:
        rows.sort(key=lambda r: -r["discovery_score"])

    if args.as_json:
        print(json.dumps(rows, indent=2))
        return

    if not rows:
        print("No candidates above threshold.")
        return

    hdr = f"{'object_id':<20} {'score':>7} {'flag':<16} {'pathway':<22} {'moid_au':>9}"
    print(hdr)
    print("-" * len(hdr))
    for row in rows:
        moid_str = f"{row['moid_au']:.4f}" if row["moid_au"] is not None else "    N/A"
        print(
            f"{row['object_id']:<20} {row['discovery_score']:>7.4f}"
            f" {row['hazard_flag']:<16} {row['alert_pathway']:<22} {moid_str:>9}"
        )


if __name__ == "__main__":
    main()
