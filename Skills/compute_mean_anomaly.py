"""Batch mean anomaly computation from tracklet or ScoredNEO JSON."""

from __future__ import annotations

import argparse
import json
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compute mean anomaly at a given JD from tracklet/ScoredNEO JSON."
    )
    parser.add_argument("input", help="Path to JSON file (list of tracklet or ScoredNEO dicts).")
    parser.add_argument("--jd", type=float, default=2460000.5,
                        help="Target Julian Date (default: 2460000.5).")
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
        from orbit import compute_mean_anomaly_at_jd
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
                eccentricity=float(orb.get("eccentricity", 0.0) or 0.0),
                mean_anomaly_deg=float(orb.get("mean_anomaly_deg", 0.0) or 0.0),
                epoch_jd=float(orb.get("epoch_jd", 2451545.0) or 2451545.0),
            )
        else:
            el = orb
        m = compute_mean_anomaly_at_jd(el, args.jd)
        rows.append({"object_id": object_id, "jd": args.jd,
                     "mean_anomaly_rad": m})

    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        if not rows:
            print("No items.")
        else:
            print(f"{'Object':<24s} {'JD':>14s} {'M (rad)':>12s}")
            print("-" * 54)
            for r in rows:
                m_val = r["mean_anomaly_rad"]
                m_str = f"{m_val:.6f}" if m_val is not None else "N/A"
                print(f"{r['object_id']:<24s} {r['jd']:>14.2f} {m_str:>12s}")
        print(f"\n{len(rows)} item(s).")

    sys.exit(0)


if __name__ == "__main__":
    main()
