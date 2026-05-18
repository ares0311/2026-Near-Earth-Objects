"""Batch apparent magnitude computation from tracklet JSON.

Usage
-----
    python Skills/compute_apparent_magnitudes.py data/sample_tracklets.json \\
        --jd 2461000.5 --albedo 0.14

    python Skills/compute_apparent_magnitudes.py data/sample_tracklets.json \\
        --jd 2461000.5 --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def _make_elements(tracklet_dict: dict):
    from schemas import OrbitalElements

    orbit = tracklet_dict.get("orbital_elements") or {}
    if not orbit:
        return None
    try:
        return OrbitalElements(**orbit)
    except Exception:
        return None


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Compute apparent magnitudes for tracklets at a given JD."
    )
    parser.add_argument("input", help="Path to scored-NEO or tracklet JSON file")
    parser.add_argument(
        "--jd",
        type=float,
        default=2461000.5,
        help="Julian Date at which to evaluate apparent magnitude (default: 2461000.5)",
    )
    parser.add_argument(
        "--albedo",
        type=float,
        default=0.14,
        help="Geometric albedo for H-magnitude estimation (default: 0.14)",
    )
    parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Output as JSON array instead of a table",
    )
    args = parser.parse_args(argv)

    from orbit import compute_apparent_magnitude

    with open(args.input) as f:
        data = json.load(f)

    if isinstance(data, dict):
        data = [data]

    rows = []
    for item in data:
        # Support both raw tracklet dicts and ScoredNEO dicts
        tracklet = item.get("tracklet", item)
        object_id = tracklet.get("object_id", "unknown")
        elements = _make_elements(tracklet)

        if elements is None:
            v_mag = float("nan")
        else:
            v_mag = compute_apparent_magnitude(elements, args.jd, args.albedo)

        rows.append({
            "object_id": object_id,
            "jd": args.jd,
            "v_mag": v_mag,
            "albedo": args.albedo,
        })

    if args.as_json:
        print(json.dumps(rows, indent=2))
    else:
        header = f"{'object_id':<20} {'jd':>14} {'V_mag':>8} {'albedo':>8}"
        print(header)
        print("-" * len(header))
        for row in rows:
            v = f"{row['v_mag']:.3f}" if row["v_mag"] == row["v_mag"] else "   NaN"
            print(f"{row['object_id']:<20} {row['jd']:>14.2f} {v:>8} {row['albedo']:>8.2f}")


if __name__ == "__main__":
    main()
