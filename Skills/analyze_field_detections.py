"""Analyse all observations across tracklets in a JSON file.

Computes aggregate statistics over all observations from all tracklets,
including counts by filter and mission, magnitude statistics, and real/bogus
summary.

Usage::

    python Skills/analyze_field_detections.py data/sample_tracklets.json
    python Skills/analyze_field_detections.py data/sample_tracklets.json --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def _collect_observations(data: list[dict]) -> list[dict]:
    """Extract raw observation dicts from a list of tracklet dicts."""
    obs_list: list[dict] = []
    for item in data:
        # Tracklet shape: {"object_id": ..., "observations": [...]}
        obs_raw = item.get("observations")
        if obs_raw and isinstance(obs_raw, list):
            obs_list.extend(obs_raw)
        # ScoredNEO shape: {"tracklet": {"observations": [...]}}
        tracklet = item.get("tracklet")
        if tracklet and isinstance(tracklet, dict):
            inner = tracklet.get("observations")
            if inner and isinstance(inner, list):
                obs_list.extend(inner)
    return obs_list


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Analyse field detections from a tracklet JSON file."
    )
    parser.add_argument("input", help="Path to JSON file (list of tracklets or ScoredNEO dicts)")
    parser.add_argument(
        "--json", action="store_true", dest="json_out", help="Output JSON instead of table"
    )
    args = parser.parse_args(argv)

    data = json.loads(Path(args.input).read_text())
    if not isinstance(data, list):
        data = [data]

    n_tracklets = len(data)
    obs_list = _collect_observations(data)
    total_obs = len(obs_list)

    # Per-filter and per-mission counts
    obs_by_filter: dict[str, int] = {}
    obs_by_mission: dict[str, int] = {}

    mags: list[float] = []
    rb_scores: list[float] = []

    for obs in obs_list:
        fb = obs.get("filter_band") or "unknown"
        obs_by_filter[fb] = obs_by_filter.get(fb, 0) + 1

        mission = obs.get("mission") or "unknown"
        obs_by_mission[mission] = obs_by_mission.get(mission, 0) + 1

        mag = obs.get("mag")
        if mag is not None and float(mag) < 90.0:
            mags.append(float(mag))

        # real_bogus or deep_real_bogus
        rb = obs.get("deep_real_bogus")
        if rb is None:
            rb = obs.get("real_bogus")
        if rb is not None:
            rb_scores.append(float(rb))

    mean_mag = round(sum(mags) / len(mags), 4) if mags else None
    mag_range = round(max(mags) - min(mags), 4) if len(mags) >= 2 else None
    mean_rb = round(sum(rb_scores) / len(rb_scores), 4) if rb_scores else None

    summary = {
        "n_tracklets": n_tracklets,
        "total_obs": total_obs,
        "obs_by_filter": obs_by_filter,
        "obs_by_mission": obs_by_mission,
        "mean_mag": mean_mag,
        "mag_range": mag_range,
        "mean_real_bogus": mean_rb,
    }

    if args.json_out:
        print(json.dumps(summary, indent=2))
    else:
        print(f"Tracklets          : {n_tracklets}")
        print(f"Total observations : {total_obs}")
        print(f"Mean magnitude     : {mean_mag if mean_mag is not None else 'N/A'}")
        print(f"Magnitude range    : {mag_range if mag_range is not None else 'N/A'}")
        print(f"Mean real/bogus    : {mean_rb if mean_rb is not None else 'N/A'}")
        print()
        print("Observations by filter:")
        for filt, count in sorted(obs_by_filter.items()):
            print(f"  {filt:<10}  {count}")
        print()
        print("Observations by mission:")
        for mission, count in sorted(obs_by_mission.items()):
            print(f"  {mission:<12}  {count}")


if __name__ == "__main__":
    main()
    sys.exit(0)
