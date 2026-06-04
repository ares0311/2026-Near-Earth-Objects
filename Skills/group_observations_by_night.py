"""Group tracklet observations by integer night (floor of JD).

Usage:
    python Skills/group_observations_by_night.py data/sample_tracklets.json [--json]

Reads a tracklet JSON file, builds a FetchResult from all observations, and
prints a per-night summary table showing count and magnitude range per night.
"""
import json
import sys

sys.path.insert(0, "src")

from fetch import group_observations_by_night
from schemas import FetchProvenance, FetchResult, Observation


def _build_fetch_result(tracklets: list) -> FetchResult:
    observations = []
    for t in tracklets:
        for obs in t.get("observations", []):
            try:
                observations.append(
                    Observation(
                        obs_id=obs["obs_id"],
                        ra_deg=obs["ra_deg"],
                        dec_deg=obs["dec_deg"],
                        jd=obs["jd"],
                        mag=obs.get("mag", 99.0),
                        mag_err=obs.get("mag_err", 0.1),
                        filter_band=obs.get("filter_band", "r"),
                        mission=obs.get("mission", "ZTF"),
                    )
                )
            except Exception:
                continue
    provenance = FetchProvenance(
        surveys=["ZTF"],
        query_ra_deg=0.0,
        query_dec_deg=0.0,
        query_radius_deg=1.0,
        start_jd=0.0,
        end_jd=0.0,
    )
    return FetchResult(alerts=observations, provenance=provenance)


def main(argv: list[str]) -> None:
    as_json = "--json" in argv
    paths = [a for a in argv if not a.startswith("--")]

    if not paths:
        print("Usage: group_observations_by_night.py <tracklets.json> [--json]",
              file=sys.stderr)
        sys.exit(1)

    with open(paths[0]) as fh:
        data = json.load(fh)
    tracklets = data if isinstance(data, list) else [data]
    fetch_result = _build_fetch_result(tracklets)
    groups = group_observations_by_night(fetch_result)

    if as_json:
        summary = {
            str(night): {
                "n_obs": len(obs_list),
                "mag_min": min(o.mag for o in obs_list),
                "mag_max": max(o.mag for o in obs_list),
            }
            for night, obs_list in sorted(groups.items())
        }
        print(json.dumps(summary, indent=2))
    else:
        print(f"Nights observed: {len(groups)}, total obs: {sum(len(v) for v in groups.values())}")
        print(f"{'Night (JD)':>12}  {'N obs':>6}  {'Mag range'}")
        print("-" * 36)
        for night, obs_list in sorted(groups.items()):
            mags = [o.mag for o in obs_list if o.mag < 90.0]
            mag_str = f"{min(mags):.1f}–{max(mags):.1f}" if mags else "N/A"
            print(f"{night:>12}  {len(obs_list):>6}  {mag_str}")


if __name__ == "__main__":
    main(sys.argv[1:])
