"""Compute sky centroids for tracklets from a JSON file.

Usage:
    python Skills/compute_tracklet_centroids.py --input data/sample_tracklets.json
    python Skills/compute_tracklet_centroids.py --input data/sample_tracklets.json --json
"""

import argparse
import json
import sys

sys.path.insert(0, "src")

from link import compute_tracklet_centroid


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compute sky centroids for tracklets.")
    parser.add_argument("--input", required=True, help="Path to tracklet JSON file.")
    parser.add_argument("--json", action="store_true", help="Output as JSON.")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    with open(args.input) as f:
        data = json.load(f)

    tracklets = data if isinstance(data, list) else data.get("tracklets", [])

    results = []
    for item in tracklets:
        object_id = item.get("object_id", "unknown")
        observations_raw = item.get("observations", [])

        class _Obs:
            def __init__(self, d: dict) -> None:
                self.ra = float(d.get("ra", 0.0))
                self.dec = float(d.get("dec", 0.0))

        class _Tracklet:
            def __init__(self, obs_list: list) -> None:
                self.observations = tuple(_Obs(o) for o in obs_list)

        tracklet = _Tracklet(observations_raw)
        centroid = compute_tracklet_centroid(tracklet)
        results.append({
            "object_id": object_id,
            "ra_deg": centroid["ra_deg"] if centroid else None,
            "dec_deg": centroid["dec_deg"] if centroid else None,
        })

    if args.json:
        print(json.dumps(results, indent=2))
        return

    print(f"{'object_id':<24}  {'ra_deg':>10}  {'dec_deg':>10}")
    print("-" * 50)
    for row in results:
        ra = f"{row['ra_deg']:.4f}" if row["ra_deg"] is not None else "N/A"
        dec = f"{row['dec_deg']:.4f}" if row["dec_deg"] is not None else "N/A"
        print(f"{row['object_id']:<24}  {ra:>10}  {dec:>10}")


if __name__ == "__main__":
    main()
