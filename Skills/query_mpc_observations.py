"""
query_mpc_observations.py — Query MPC observation history for a designation.

Usage:
    python Skills/query_mpc_observations.py 2020 XL5
    python Skills/query_mpc_observations.py 433 --json

Exit 0 on success; exit 1 on error.
"""
from __future__ import annotations

import argparse
import json
import sys

PYTHONPATH_SRC = __import__("pathlib").Path(__file__).resolve().parents[1] / "src"
if str(PYTHONPATH_SRC) not in sys.path:
    sys.path.insert(0, str(PYTHONPATH_SRC))

from fetch import fetch_mpc_observations  # noqa: E402


def query_observations(designation: str, as_json: bool = False) -> int:
    obs_list = fetch_mpc_observations(designation)
    if not obs_list:
        msg = (
            f"No observations returned for '{designation}' "
            "(network unavailable or unknown object)."
        )
        if as_json:
            print(json.dumps({
                "designation": designation,
                "n_obs": 0,
                "observations": [],
                "note": msg,
            }))
        else:
            print(msg, file=sys.stderr)
        return 0  # not a fatal error; could be network unavailable

    if as_json:
        records = []
        for o in obs_list:
            records.append(
                {
                    "obs_id": o.obs_id,
                    "ra_deg": o.ra_deg,
                    "dec_deg": o.dec_deg,
                    "jd": o.jd,
                    "magnitude": o.magnitude,
                    "band": o.band,
                    "survey": o.survey,
                }
            )
        print(
            json.dumps(
                {"designation": designation, "n_obs": len(records), "observations": records},
                indent=2,
            )
        )
    else:
        print(f"MPC observations for '{designation}': {len(obs_list)} records\n")
        hdr = f"{'Obs ID':<20} {'RA (deg)':>10} {'Dec (deg)':>10} {'JD':>14} {'Mag':>6} {'Band':>5}"
        print(hdr)
        print("-" * 70)
        for o in obs_list[:50]:
            print(
                f"{o.obs_id:<20} {o.ra_deg:>10.5f} {o.dec_deg:>10.5f} "
                f"{o.jd:>14.5f} {o.magnitude:>6.2f} {o.band:>5}"
            )
        if len(obs_list) > 50:
            print(f"  ... ({len(obs_list) - 50} more observations not shown)")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Query MPC observation history for a minor planet designation."
    )
    parser.add_argument("designation", nargs="+", help="MPC designation (e.g. '2020 XL5' or '433')")
    parser.add_argument(
        "--json", action="store_true", dest="as_json", help="Output as JSON"
    )
    args = parser.parse_args()
    designation = " ".join(args.designation)
    sys.exit(query_observations(designation, as_json=args.as_json))


if __name__ == "__main__":
    main()
