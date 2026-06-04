"""Batch inter-night gap statistics from a tracklet JSON file.

Usage:
    python Skills/compute_night_gap_stats.py data/sample_tracklets.json [--json]

Reads a tracklet JSON file and prints statistics on the gaps between
consecutive observing nights across all tracklets.
"""
import json
import sys

sys.path.insert(0, "src")

from link import compute_night_gap_statistics
from schemas import Observation, Tracklet


def _load_tracklets(path: str) -> list[Tracklet]:
    with open(path) as fh:
        data = json.load(fh)
    records = data if isinstance(data, list) else [data]
    tracklets = []
    for r in records:
        obs_list = []
        for o in r.get("observations", []):
            try:
                obs_list.append(
                    Observation(
                        obs_id=o["obs_id"],
                        ra_deg=o["ra_deg"],
                        dec_deg=o["dec_deg"],
                        jd=o["jd"],
                        mag=o.get("mag", 99.0),
                        mag_err=o.get("mag_err", 0.1),
                        filter_band=o.get("filter_band", "r"),
                        mission=o.get("mission", "ZTF"),
                    )
                )
            except Exception:
                continue
        if len(obs_list) < 2:
            continue
        try:
            t = Tracklet(
                object_id=r["object_id"],
                observations=tuple(obs_list),
                arc_days=r.get("arc_days", 0.0),
                motion_rate_arcsec_per_hour=r.get("motion_rate_arcsec_per_hour", 0.0),
                motion_pa_degrees=r.get("motion_pa_degrees", 0.0),
            )
            tracklets.append(t)
        except Exception:
            continue
    return tracklets


def main(argv: list[str]) -> None:
    as_json = "--json" in argv
    paths = [a for a in argv if not a.startswith("--")]
    if not paths:
        print("Usage: compute_night_gap_stats.py <tracklets.json> [--json]", file=sys.stderr)
        sys.exit(1)

    tracklets = _load_tracklets(paths[0])
    stats = compute_night_gap_statistics(tracklets)

    if as_json:
        print(json.dumps(stats, indent=2))
    else:
        print(f"Tracklets      : {stats['n_tracklets']}")
        print(f"Mean gap (nts) : {stats['mean_gap_nights']}")
        print(f"Max gap (nts)  : {stats['max_gap_nights']}")


if __name__ == "__main__":
    main(sys.argv[1:])
