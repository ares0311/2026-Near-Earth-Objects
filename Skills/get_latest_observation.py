"""Get the latest observation from a fetch-result JSON file.

Usage:
    python Skills/get_latest_observation.py fetch_result.json [--json]

Reads a fetch-result JSON file (list of observations or a dict with an
"alerts" key) and prints the observation with the most recent JD using
get_latest_observation from fetch.py.
"""
import json
import sys
from types import SimpleNamespace

sys.path.insert(0, "src")

from fetch import get_latest_observation


def _load_obs(d: dict) -> SimpleNamespace:
    return SimpleNamespace(
        obs_id=d.get("obs_id", "unknown"),
        ra_deg=d.get("ra_deg", 0.0),
        dec_deg=d.get("dec_deg", 0.0),
        jd=d.get("jd", float("nan")),
        mag=d.get("mag", 99.0),
        mag_err=d.get("mag_err", 0.0),
        filter_band=d.get("filter_band", "r"),
        real_bogus_score=d.get("real_bogus_score"),
        mission=d.get("mission", "ZTF"),
        cutout_science=None,
        cutout_reference=None,
        cutout_difference=None,
    )


def main(argv: list[str]) -> None:
    as_json = "--json" in argv
    paths = [a for a in argv if not a.startswith("--")]

    if not paths:
        print("Usage: get_latest_observation.py <fetch_result.json> [--json]",
              file=sys.stderr)
        sys.exit(1)

    with open(paths[0]) as fh:
        data = json.load(fh)

    if isinstance(data, list):
        alerts = [_load_obs(d) for d in data]
    elif isinstance(data, dict):
        alerts = [_load_obs(d) for d in data.get("alerts", [])]
    else:
        alerts = []

    fetch_result = SimpleNamespace(alerts=alerts, provenance=None)
    obs = get_latest_observation(fetch_result)

    if obs is None:
        if as_json:
            print(json.dumps({"latest_observation": None}))
        else:
            print("No valid observations found.")
        return

    if as_json:
        print(json.dumps({
            "obs_id": obs.obs_id,
            "jd": obs.jd,
            "ra_deg": obs.ra_deg,
            "dec_deg": obs.dec_deg,
            "mag": obs.mag,
            "mission": obs.mission,
        }, indent=2))
    else:
        print(f"Latest observation: {obs.obs_id}")
        print(f"  JD:      {obs.jd:.5f}")
        print(f"  RA/Dec:  {obs.ra_deg:.5f}  {obs.dec_deg:.5f}")
        print(f"  Mag:     {obs.mag:.2f}")
        print(f"  Mission: {obs.mission}")


if __name__ == "__main__":
    main(sys.argv[1:])
