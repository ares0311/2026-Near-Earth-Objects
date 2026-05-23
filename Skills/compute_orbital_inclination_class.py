"""Batch orbital inclination classification for tracklets or ScoredNEO dicts from JSON."""

from __future__ import annotations

import argparse
import json
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Classify orbital inclination (prograde/polar/retrograde) from tracklet JSON."
    )
    parser.add_argument("input", help="Path to JSON file (list of tracklet or ScoredNEO dicts).")
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
        from orbit import compute_orbital_inclination_class
    except ImportError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    rows = []
    for item in data:
        # Support both ScoredNEO dicts and plain dicts with orbital elements
        object_id = (
            item.get("tracklet", {}).get("object_id")
            or item.get("object_id", "unknown")
        )
        # Try to extract inclination from nested structures
        elements = (
            item.get("hazard", {})
            or item.get("orbital_elements", {})
            or item
        )
        inc = elements.get("inclination_deg") or item.get("inclination_deg") or 0.0

        from types import SimpleNamespace
        el = SimpleNamespace(inclination_deg=float(inc))
        cls = compute_orbital_inclination_class(el)
        rows.append({"object_id": object_id, "inclination_deg": float(inc), "class": cls})

    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        if not rows:
            print("No items.")
        else:
            print(f"{'Object':<24s} {'Inclination (°)':>16s} {'Class'}")
            print("-" * 50)
            for r in rows:
                print(f"{r['object_id']:<24s} {r['inclination_deg']:>16.2f} {r['class']}")
        print(f"\n{len(rows)} item(s).")

    sys.exit(0)


if __name__ == "__main__":
    main()
