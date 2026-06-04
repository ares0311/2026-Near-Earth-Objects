"""Batch size estimate range computation from scored NEO JSON.

Usage:
    python Skills/compute_size_ranges.py data/sample_tracklets.json [--json]
"""

from __future__ import annotations

import argparse
import json
import sys

sys.path.insert(0, "src")

import score


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch size estimate ranges for scored NEOs.")
    parser.add_argument("input", help="Path to scored NEO JSON file")
    parser.add_argument(
        "--albedo-min", type=float, default=0.05, help="Minimum albedo (default: 0.05)"
    )
    parser.add_argument(
        "--albedo-max", type=float, default=0.25, help="Maximum albedo (default: 0.25)"
    )
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    with open(args.input) as f:
        data = json.load(f)

    neos = data if isinstance(data, list) else data.get("neos", [])

    rows = []
    for neo_dict in neos:
        hazard = neo_dict.get("hazard", {})
        h_mag = hazard.get("absolute_magnitude_h") if hazard else None

        class FakeHazard:
            absolute_magnitude_h = h_mag

        class FakeNEO:
            pass

        obj = FakeNEO()
        obj.hazard = FakeHazard()  # type: ignore[attr-defined]

        rng = score.compute_size_estimate_range(obj, (args.albedo_min, args.albedo_max))
        oid = neo_dict.get("tracklet", {}).get("object_id", "?")
        rows.append(
            {
                "object_id": oid,
                "h_mag": h_mag,
                "min_m": rng["min_m"],
                "max_m": rng["max_m"],
            }
        )

    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        print(f"{'object_id':<20} {'H_mag':>6} {'min_diam_m':>12} {'max_diam_m':>12}")
        print("-" * 52)
        for r in rows:
            h = f"{r['h_mag']:.1f}" if r["h_mag"] is not None else "N/A"
            mn = f"{r['min_m']:.1f}" if r["min_m"] is not None else "N/A"
            mx = f"{r['max_m']:.1f}" if r["max_m"] is not None else "N/A"
            print(f"{r['object_id']:<20} {h:>6} {mn:>12} {mx:>12}")


if __name__ == "__main__":
    main()
