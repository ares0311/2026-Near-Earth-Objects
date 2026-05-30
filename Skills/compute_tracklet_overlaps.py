"""Compute pairwise tracklet overlap fractions from a tracklet JSON file.

For each pair of tracklets (first vs all others), computes
``compute_tracklet_overlap_fraction`` and prints a table of pairs with
non-zero overlap.

Usage
-----
    python Skills/compute_tracklet_overlaps.py data/sample_tracklets.json
    python Skills/compute_tracklet_overlaps.py data/sample_tracklets.json --json
"""

from __future__ import annotations

import argparse
import json
import sys

sys.path.insert(0, "src")

from link import compute_tracklet_overlap_fraction
from schemas import Observation, Tracklet


def _load_tracklets(path: str) -> list[Tracklet]:
    with open(path) as fh:
        raw = json.load(fh)
    if isinstance(raw, dict):
        raw = [raw]
    tracklets: list[Tracklet] = []
    for item in raw:
        obs_raw = item.get("observations", [])
        obs = tuple(
            Observation(
                obs_id=o.get("obs_id", f"obs_{j}"),
                jd=float(o["jd"]),
                ra_deg=float(o["ra_deg"]),
                dec_deg=float(o["dec_deg"]),
                mag=float(o.get("mag", 19.0)),
                mag_err=float(o.get("mag_err", 0.05)),
                filter_band=o.get("filter_band", "r"),
                mission=o.get("mission", "ZTF"),
            )
            for j, o in enumerate(obs_raw)
        )
        tracklets.append(
            Tracklet(
                object_id=item.get("object_id", f"T{len(tracklets)}"),
                observations=obs,
                arc_days=float(item.get("arc_days", 0.0)),
                motion_rate_arcsec_per_hour=float(
                    item.get("motion_rate_arcsec_per_hour", 0.0)
                ),
                motion_pa_degrees=float(item.get("motion_pa_degrees", 0.0)),
            )
        )
    return tracklets


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute pairwise tracklet overlaps.")
    parser.add_argument("input", help="Path to tracklet JSON file")
    parser.add_argument(
        "--json", action="store_true", dest="as_json", help="Output JSON instead of table"
    )
    args = parser.parse_args()

    tracklets = _load_tracklets(args.input)
    rows: list[dict] = []

    for i, t1 in enumerate(tracklets):
        for j, t2 in enumerate(tracklets):
            if j <= i:
                continue
            frac = compute_tracklet_overlap_fraction(t1, t2)
            if frac > 0.0:
                rows.append(
                    {
                        "tracklet_1": t1.object_id,
                        "tracklet_2": t2.object_id,
                        "overlap_fraction": round(frac, 6),
                    }
                )

    if args.as_json:
        print(json.dumps(rows, indent=2))
    else:
        if not rows:
            print("No overlapping tracklet pairs found.")
            return
        print(f"{'tracklet_1':<20s}  {'tracklet_2':<20s}  overlap_fraction")
        print("-" * 55)
        for row in rows:
            print(
                f"{row['tracklet_1']:<20s}  {row['tracklet_2']:<20s}"
                f"  {row['overlap_fraction']:.6f}"
            )


if __name__ == "__main__":
    main()
