"""Batch brightness-trend slope computation from tracklet JSON.

Usage:
    python Skills/compute_brightness_trends.py data/sample_tracklets.json
    python Skills/compute_brightness_trends.py data/sample_tracklets.json --json
"""

from __future__ import annotations

import argparse
import json
import sys

sys.path.insert(0, "src")

from link import compute_tracklet_brightness_trend


def _load_tracklets(path: str) -> list[dict]:
    with open(path) as fh:
        data = json.load(fh)
    if isinstance(data, list):
        return data
    return data.get("tracklets", [])


class _Obs:
    def __init__(self, d: dict) -> None:
        for k, v in d.items():
            setattr(self, k, v)


class _Tracklet:
    def __init__(self, observations: list) -> None:
        self.observations = tuple(observations)


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch brightness trend slopes")
    parser.add_argument("input", help="Path to tracklet JSON file")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    tracklets = _load_tracklets(args.input)
    rows = []
    for trk in tracklets:
        oid = trk.get("object_id", "unknown")
        obs_list = [_Obs(o) for o in trk.get("observations", [])]
        t = _Tracklet(obs_list)
        slope = compute_tracklet_brightness_trend(t)
        rows.append({
            "object_id": oid,
            "n_obs": len(obs_list),
            "brightness_slope_mag_per_day": round(slope, 6) if slope is not None else None,
        })

    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        print(f"{'Object ID':<40} {'N obs':>6} {'Slope (mag/day)':>16}")
        print("-" * 66)
        for row in rows:
            s = row["brightness_slope_mag_per_day"]
            slope_str = f"{s:+.6f}" if s is not None else "N/A"
            print(f"{row['object_id']:<40} {row['n_obs']:>6} {slope_str:>16}")


if __name__ == "__main__":
    main()
