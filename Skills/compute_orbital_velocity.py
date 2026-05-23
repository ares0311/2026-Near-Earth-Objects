"""Batch orbital velocity computation from tracklet or ScoredNEO JSON."""

from __future__ import annotations

import argparse
import json
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compute orbital velocity at a given heliocentric distance."
    )
    parser.add_argument("input", help="Path to JSON file (list of tracklet or ScoredNEO dicts).")
    parser.add_argument("--r-au", type=float, default=1.0,
                        help="Heliocentric distance in AU (default: 1.0).")
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
        from orbit import compute_orbital_velocity
    except ImportError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    from types import SimpleNamespace

    rows = []
    for item in data:
        object_id = (
            item.get("tracklet", {}).get("object_id")
            or item.get("object_id", "unknown")
        )
        orb = (
            item.get("hazard", {}).get("orbital_elements")
            or item.get("orbital_elements")
            or item
        )
        if isinstance(orb, dict):
            el = SimpleNamespace(
                semi_major_axis_au=float(orb.get("semi_major_axis_au", 0.0) or 0.0),
            )
        else:
            el = orb
        v = compute_orbital_velocity(el, args.r_au)
        rows.append({"object_id": object_id, "r_au": args.r_au, "velocity_km_s": v})

    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        if not rows:
            print("No items.")
        else:
            print(f"{'Object':<24s} {'r (AU)':>8s} {'v (km/s)':>12s}")
            print("-" * 48)
            for r in rows:
                v_str = f"{r['velocity_km_s']:.4f}" if r["velocity_km_s"] is not None else "N/A"
                print(f"{r['object_id']:<24s} {r['r_au']:>8.3f} {v_str:>12s}")
        print(f"\n{len(rows)} item(s).")

    sys.exit(0)


if __name__ == "__main__":
    main()
