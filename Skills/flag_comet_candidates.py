"""Flag comet candidates using combined Tisserand + orbital element criteria.

Reads a JSON file of tracklets (or ScoredNEO dicts), fits a preliminary orbit
for each, computes T_J, eccentricity, and inclination, and applies a combined
comet-candidate test: T_J < threshold AND e >= min_ecc. Prints a report.

Usage:
    python Skills/flag_comet_candidates.py data/sample_tracklets.json
    python Skills/flag_comet_candidates.py data/sample_tracklets.json \\
        --threshold 3.0 --min-ecc 0.3
    python Skills/flag_comet_candidates.py data/sample_tracklets.json --json
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


def flag_comet_candidates(
    records: list[dict],
    threshold: float = 3.0,
    min_ecc: float = 0.3,
) -> list[dict]:
    """Evaluate comet candidacy for each record.

    A record is flagged as a comet candidate when *both* conditions hold:
    - T_J < *threshold* (Jupiter-family or long-period comet regime)
    - eccentricity >= *min_ecc* (elongated orbit)

    Returns a list of result dicts with keys ``object_id``, ``tisserand_parameter``,
    ``eccentricity``, ``inclination_deg``, ``semi_major_axis_au``,
    ``comet_candidate``, and ``reason``.
    """
    results = []
    for rec in records:
        if "tracklet" in rec:
            tracklet_dict = rec["tracklet"]
        else:
            tracklet_dict = rec

        obj_id = tracklet_dict.get("object_id", "unknown")
        obs_dicts = tracklet_dict.get("observations", [])
        observations = _observations_from_dict(obs_dicts)

        t_j: float | None = None
        a: float | None = None
        e: float | None = None
        i_deg: float | None = None
        comet_candidate = False
        reason = "insufficient observations"

        if len(observations) >= 2:
            try:
                orbit = fit_orbit(tuple(observations))
                if orbit is not None and orbit.semi_major_axis_au > 0:
                    t_j = tisserand_parameter(orbit)
                    a = orbit.semi_major_axis_au
                    e = orbit.eccentricity
                    i_deg = orbit.inclination_deg

                    tj_flag = t_j < threshold
                    ecc_flag = e >= min_ecc

                    if tj_flag and ecc_flag:
                        comet_candidate = True
                        reason = f"T_J={t_j:.3f} < {threshold} AND e={e:.3f} >= {min_ecc}"
                    elif tj_flag:
                        reason = f"T_J={t_j:.3f} < {threshold} but e={e:.3f} < {min_ecc}"
                    elif ecc_flag:
                        reason = f"e={e:.3f} >= {min_ecc} but T_J={t_j:.3f} >= {threshold}"
                    else:
                        reason = f"T_J={t_j:.3f} >= {threshold} and e={e:.3f} < {min_ecc}"
                else:
                    reason = "orbit fit failed or hyperbolic"
            except Exception as exc:
                reason = f"error: {exc}"

        results.append({
            "object_id": obj_id,
            "tisserand_parameter": round(t_j, 4) if t_j is not None else None,
            "semi_major_axis_au": round(a, 4) if a is not None else None,
            "eccentricity": round(e, 4) if e is not None else None,
            "inclination_deg": round(i_deg, 2) if i_deg is not None else None,
            "comet_candidate": comet_candidate,
            "reason": reason,
        })

    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Flag comet candidates using Tisserand + eccentricity criteria"
    )
    parser.add_argument("input", help="JSON file with tracklet or ScoredNEO dicts")
    parser.add_argument(
        "--threshold", type=float, default=3.0,
        help="T_J < threshold is required for comet candidacy (default 3.0)"
    )
    parser.add_argument(
        "--min-ecc", type=float, default=0.3,
        help="minimum eccentricity for comet candidacy (default 0.3)"
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

    results = flag_comet_candidates(records, threshold=args.threshold, min_ecc=args.min_ecc)
    n_comet = sum(1 for r in results if r["comet_candidate"])

    if args.as_json:
        print(json.dumps(results, indent=2))
    else:
        print(f"{'Object ID':<20} {'T_J':>7} {'e':>6} {'i (deg)':>8} {'Comet?':>8}  Reason")
        print("-" * 80)
        for r in results:
            tj = r["tisserand_parameter"]
            ec = r["eccentricity"]
            ii = r["inclination_deg"]
            tj_s = f"{tj:7.3f}" if tj is not None else "    N/A"
            e_s = f"{ec:6.3f}" if ec is not None else "   N/A"
            i_s = f"{ii:8.2f}" if ii is not None else "     N/A"
            comet_s = "YES" if r["comet_candidate"] else "no"
            print(f"{r['object_id']:<20} {tj_s} {e_s} {i_s} {comet_s:>8}  {r['reason']}")

        print()
        print(
            f"Total: {len(results)}  "
            f"Comet candidates (T_J < {args.threshold} AND e >= {args.min_ecc}): {n_comet}"
        )


if __name__ == "__main__":
    main()
