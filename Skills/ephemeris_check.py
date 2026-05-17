"""Predict sky positions for tracklets at a user-specified Julian Date.

Reads a JSON file of tracklets (or ScoredNEO dicts), fits a preliminary orbit
for each, and predicts geocentric (RA, Dec, heliocentric distance) at the
requested JD. Prints an observer-ready table.

Usage:
    python Skills/ephemeris_check.py data/sample_tracklets.json --jd 2460100.5
    python Skills/ephemeris_check.py data/sample_tracklets.json --jd 2460100.5 --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from orbit import fit_orbit, predict_ephemeris


def _observations_from_dict(obs_list: list[dict]) -> list:
    from schemas import Observation

    result = []
    for o in obs_list:
        try:
            result.append(Observation(**o))
        except Exception:
            pass
    return result


def predict_for_record(record: dict, target_jd: float) -> dict:
    """Predict ephemeris at target_jd for one tracklet or ScoredNEO dict."""
    if "tracklet" in record:
        tracklet_dict = record["tracklet"]
    else:
        tracklet_dict = record

    obj_id = tracklet_dict.get("object_id", "unknown")
    obs_dicts = tracklet_dict.get("observations", [])
    observations = _observations_from_dict(obs_dicts)

    ra: float | None = None
    dec: float | None = None
    dist: float | None = None
    error: str | None = None

    if len(observations) >= 2:
        try:
            orbit = fit_orbit(tuple(observations))
            if orbit is not None and orbit.semi_major_axis_au > 0:
                eph = predict_ephemeris(orbit, target_jd)
                ra = eph.get("ra_deg")
                dec = eph.get("dec_deg")
                dist = eph.get("helio_dist_au")
            else:
                error = "orbit fit failed"
        except Exception as exc:
            error = str(exc)
    else:
        error = f"too few observations ({len(observations)})"

    return {
        "object_id": obj_id,
        "target_jd": target_jd,
        "ra_deg": round(ra, 5) if ra is not None else None,
        "dec_deg": round(dec, 5) if dec is not None else None,
        "helio_dist_au": round(dist, 4) if dist is not None else None,
        "error": error,
    }


def ephemeris_check(records: list[dict], target_jd: float) -> list[dict]:
    """Predict ephemerides for all records at target_jd."""
    return [predict_for_record(rec, target_jd) for rec in records]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Predict sky positions for tracklets at a given JD"
    )
    parser.add_argument("input", help="JSON file with tracklet or ScoredNEO dicts")
    parser.add_argument(
        "--jd", type=float, required=True,
        help="Target Julian Date for prediction"
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

    results = ephemeris_check(records, args.jd)

    if args.as_json:
        print(json.dumps(results, indent=2))
    else:
        print(f"\nEphemeris predictions at JD {args.jd:.1f}")
        print()
        print(f"{'Object ID':<20} {'RA (deg)':>10} {'Dec (deg)':>10} {'r (AU)':>8} {'Note'}")
        print("-" * 62)
        for r in results:
            ra_s = f"{r['ra_deg']:10.5f}" if r["ra_deg"] is not None else "       N/A"
            dec_s = f"{r['dec_deg']:10.5f}" if r["dec_deg"] is not None else "       N/A"
            dist_s = f"{r['helio_dist_au']:8.4f}" if r["helio_dist_au"] is not None else "     N/A"
            note = r["error"] or "ok"
            print(f"{r['object_id']:<20} {ra_s} {dec_s} {dist_s}  {note}")
        print()
        n_ok = sum(1 for r in results if r["error"] is None)
        print(f"Total: {len(results)}  Predicted: {n_ok}  Failed: {len(results) - n_ok}")


if __name__ == "__main__":
    main()
