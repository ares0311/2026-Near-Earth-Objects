"""Batch-compute Tisserand parameter for tracklets and flag comet-like objects.

Reads a JSON file of tracklets (or ScoredNEO dicts), fits a preliminary orbit
for each, computes T_J, and prints a summary table. Objects with T_J < threshold
are flagged as comet-like (dynamically).

Usage:
    python Skills/check_tisserand.py data/sample_tracklets.json
    python Skills/check_tisserand.py data/sample_tracklets.json --threshold 3.0
    python Skills/check_tisserand.py data/sample_tracklets.json --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from orbit import fit_orbit, tisserand_parameter


def _observations_from_dict(obs_list: list[dict]) -> list:
    from schemas import Observation

    result = []
    for o in obs_list:
        try:
            result.append(Observation(**o))
        except Exception:
            pass
    return result


def compute_tisserand_for_record(record: dict) -> dict:
    """Return a result dict for one tracklet or ScoredNEO dict."""
    if "tracklet" in record:
        tracklet_dict = record["tracklet"]
    else:
        tracklet_dict = record

    obj_id = tracklet_dict.get("object_id", "unknown")
    obs_dicts = tracklet_dict.get("observations", [])
    observations = _observations_from_dict(obs_dicts)

    t_j: float | None = None
    a: float | None = None
    e: float | None = None
    i_deg: float | None = None
    comet_like = False

    if len(observations) >= 2:
        try:
            orbit_result = fit_orbit(tuple(observations))
            if orbit_result is not None and orbit_result.semi_major_axis_au > 0:
                t_j = tisserand_parameter(orbit_result)
                a = orbit_result.semi_major_axis_au
                e = orbit_result.eccentricity
                i_deg = orbit_result.inclination_deg
        except Exception:
            pass

    return {
        "object_id": obj_id,
        "tisserand_parameter": round(t_j, 4) if t_j is not None else None,
        "semi_major_axis_au": round(a, 4) if a is not None else None,
        "eccentricity": round(e, 4) if e is not None else None,
        "inclination_deg": round(i_deg, 2) if i_deg is not None else None,
        "comet_like": comet_like,
    }


def check_tisserand(records: list[dict], threshold: float = 3.0) -> list[dict]:
    """Compute T_J for all records and flag those with T_J < threshold."""
    results = []
    for rec in records:
        row = compute_tisserand_for_record(rec)
        t_j = row["tisserand_parameter"]
        row["comet_like"] = (t_j is not None and t_j < threshold)
        results.append(row)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check Tisserand parameter for tracklets"
    )
    parser.add_argument("input", help="JSON file with tracklet or ScoredNEO dicts")
    parser.add_argument(
        "--threshold", type=float, default=3.0,
        help="T_J < threshold → comet-like (default 3.0)"
    )
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="output as JSON instead of table")
    args = parser.parse_args()

    data_path = Path(args.input)
    if not data_path.exists():
        print(f"ERROR: {data_path} not found", file=sys.stderr)
        sys.exit(1)

    with data_path.open() as f:
        records = json.load(f)

    if not isinstance(records, list):
        print("ERROR: JSON file must contain a list", file=sys.stderr)
        sys.exit(1)

    results = check_tisserand(records, threshold=args.threshold)
    n_comet = sum(1 for r in results if r["comet_like"])

    if args.as_json:
        print(json.dumps(results, indent=2))
    else:
        print(f"{'Object ID':<20} {'T_J':>7} {'a (AU)':>8} {'e':>6} {'i (deg)':>8} {'Comet?':>7}")
        print("-" * 62)
        for r in results:
            tj = r["tisserand_parameter"]
            tj_str = f"{tj:7.3f}" if tj is not None else "    N/A"
            aa = r["semi_major_axis_au"]
            a_str = f"{aa:8.3f}" if aa is not None else "     N/A"
            ee = r["eccentricity"]
            e_str = f"{ee:6.3f}" if ee is not None else "   N/A"
            ii = r["inclination_deg"]
            i_str = f"{ii:8.2f}" if ii is not None else "     N/A"
            comet_str = "YES" if r["comet_like"] else "no"
            print(f"{r['object_id']:<20} {tj_str} {a_str} {e_str} {i_str} {comet_str:>7}")

        print()
        print(f"Total: {len(results)}  Comet-like (T_J < {args.threshold}): {n_comet}")


if __name__ == "__main__":
    main()
