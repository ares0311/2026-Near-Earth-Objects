"""Compute time gaps between consecutive observations for each tracklet.

Usage::

    python Skills/compute_inter_observation_gaps.py --input data/sample_tracklets.json
    python Skills/compute_inter_observation_gaps.py --input data/sample_tracklets.json --json
"""

import argparse
import json
import sys

sys.path.insert(0, "src")

from link import compute_inter_observation_gaps
from schemas import Observation, Tracklet


def _load_tracklets(path: str) -> list[Tracklet]:
    with open(path) as f:
        data = json.load(f)
    if isinstance(data, dict):
        data = [data]
    tracklets = []
    for item in data:
        obs_raw = item.get("observations", [])
        obs = tuple(Observation(**o) for o in obs_raw)
        tracklets.append(
            Tracklet(
                object_id=item["object_id"],
                observations=obs,
                arc_days=float(item.get("arc_days", 0.0)),
                motion_rate_arcsec_per_hour=float(item.get("motion_rate_arcsec_per_hour", 0.0)),
                motion_pa_degrees=float(item.get("motion_pa_degrees", 0.0)),
            )
        )
    return tracklets


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compute inter-observation time gaps for tracklets."
    )
    parser.add_argument("--input", required=True, help="Path to tracklet JSON file")
    parser.add_argument(
        "--json", action="store_true", dest="as_json", help="Output as JSON"
    )
    args = parser.parse_args()

    tracklets = _load_tracklets(args.input)
    rows = []
    for t in tracklets:
        gaps = compute_inter_observation_gaps(t)
        n_gaps = len(gaps)
        mean_gap = sum(gaps) / n_gaps if n_gaps > 0 else 0.0
        max_gap = max(gaps) if n_gaps > 0 else 0.0
        rows.append(
            {
                "object_id": t.object_id,
                "n_gaps": n_gaps,
                "mean_gap_hours": round(mean_gap, 4),
                "max_gap_hours": round(max_gap, 4),
            }
        )

    if args.as_json:
        print(json.dumps(rows, indent=2))
    else:
        print(f"{'object_id':<20} {'n_gaps':>6} {'mean_gap_h':>12} {'max_gap_h':>12}")
        print("-" * 54)
        for row in rows:
            print(
                f"{row['object_id']:<20} {row['n_gaps']:>6} "
                f"{row['mean_gap_hours']:>12.4f} {row['max_gap_hours']:>12.4f}"
            )


if __name__ == "__main__":
    main()
