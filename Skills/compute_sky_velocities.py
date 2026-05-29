"""Batch sky-plane velocity computation for tracklets.

Reads a tracklet JSON file and computes the sky-plane velocity between the
first and last observations of each tracklet using ``compute_sky_plane_velocity``
from the detect module.  Prints a table with object_id, dra, ddec, and speed.

Usage
-----
    python Skills/compute_sky_velocities.py data/sample_tracklets.json
    python Skills/compute_sky_velocities.py data/sample_tracklets.json --json
"""

from __future__ import annotations

import argparse
import json
import sys

sys.path.insert(0, "src")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Batch sky-plane velocity from tracklet JSON"
    )
    parser.add_argument("input", help="Path to tracklet JSON file")
    parser.add_argument(
        "--json", action="store_true", help="Output as JSON instead of table"
    )
    args = parser.parse_args()

    from detect import compute_sky_plane_velocity

    with open(args.input) as f:
        raw = json.load(f)

    results = []
    for item in raw:
        obs_list = item.get("observations", [])
        if len(obs_list) < 2:
            continue
        object_id = item.get("object_id", "UNKNOWN")

        class _Obs:
            def __init__(self, d: dict) -> None:
                self.ra = float(d.get("ra_deg", d.get("ra", 0.0)))
                self.dec = float(d.get("dec_deg", d.get("dec", 0.0)))
                self.jd = float(d.get("jd", 0.0))

        obs_sorted = sorted(obs_list, key=lambda o: float(o.get("jd", 0.0)))
        first = _Obs(obs_sorted[0])
        last = _Obs(obs_sorted[-1])
        vel = compute_sky_plane_velocity(first, last)
        results.append(
            {
                "object_id": object_id,
                "dra_arcsec_hr": vel["dra_arcsec_hr"],
                "ddec_arcsec_hr": vel["ddec_arcsec_hr"],
                "speed_arcsec_hr": vel["speed_arcsec_hr"],
            }
        )

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        col4 = "speed(arcsec/hr)"
        header = f"{'object_id':<30} {'dra(arcsec/hr)':>16} {'ddec(arcsec/hr)':>16} {col4:>17}"
        print(header)
        print("-" * len(header))
        for r in results:
            print(
                f"{r['object_id']:<30} "
                f"{r['dra_arcsec_hr']:>16.4f} "
                f"{r['ddec_arcsec_hr']:>16.4f} "
                f"{r['speed_arcsec_hr']:>17.4f}"
            )
        if not results:
            print("No tracklets with ≥2 observations found.")


if __name__ == "__main__":
    main()
