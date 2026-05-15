#!/usr/bin/env python
"""Check a list of candidates against the MPC known object catalog.

Reads candidate observations from a JSON file (same format as data/sample_tracklets.json)
and queries the MPC to identify which are already known objects.  Can also check NEOCP
for confirmation status of candidate object IDs.

Usage:
    PYTHONPATH=src python Skills/check_mpc_known.py --input data/sample_tracklets.json
    PYTHONPATH=src python Skills/check_mpc_known.py --ra 180.0 --dec 10.0 --radius 0.5
    PYTHONPATH=src python Skills/check_mpc_known.py --neocp ID001 ID002 ID003
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from alert import _monitor_neocp
from schemas import Observation


def check_candidates_against_mpc(
    observations: list[Observation],
    radius_deg: float = 1.0,
) -> list[dict]:
    """Cross-match observations against the MPC catalog.

    Returns list of dicts with match info for each observation.
    Requires network access.
    """
    results = []
    for obs in observations:
        result: dict = {
            "obs_id": obs.obs_id,
            "ra_deg": obs.ra_deg,
            "dec_deg": obs.dec_deg,
            "jd": obs.jd,
            "mpc_match": None,
            "separation_arcsec": None,
        }
        try:
            import astropy.units as u
            from astropy.coordinates import SkyCoord
            from astroquery.mpc import MPC  # type: ignore[import]

            center = SkyCoord(ra=obs.ra_deg, dec=obs.dec_deg, unit="deg")
            matches = MPC.query_objects_in_region(center, radius_deg * u.deg)
            if matches is not None and len(matches) > 0:
                first = matches[0]
                result["mpc_match"] = str(first.get("designation", "unknown"))
                result["separation_arcsec"] = float(
                    center.separation(
                        SkyCoord(
                            ra=float(first["RA"]),
                            dec=float(first["Dec"]),
                            unit="deg",
                        )
                    ).arcsec
                )
        except Exception as e:
            result["error"] = str(e)
        results.append(result)
    return results


def load_tracklets_from_json(path: Path) -> list[list[Observation]]:
    """Load tracklets from JSON file. Returns list of observation lists."""
    with path.open() as f:
        data = json.load(f)
    tracklets = []
    for entry in data:
        obs_list = [Observation(**o) for o in entry["observations"]]
        tracklets.append(obs_list)
    return tracklets


def check_neocp(object_ids: list[str]) -> list[dict]:
    """Check a list of object IDs against NEOCP for confirmation status.

    Returns a list of dicts with keys ``object_id``, ``status``, ``confirmed``,
    and optionally ``error``.  Requires network access to MPC.
    """
    results = []
    for oid in object_ids:
        result = _monitor_neocp(oid)
        results.append({"object_id": oid, **result})
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Check NEO candidates against MPC catalog")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--input", type=Path, help="JSON tracklets file")
    group.add_argument("--ra", type=float, help="RA (deg) for single position check")
    group.add_argument("--neocp", nargs="+", metavar="OBJECT_ID",
                       help="Check these object IDs against NEOCP (requires network)")
    parser.add_argument("--dec", type=float, help="Dec (deg) for single position check")
    parser.add_argument("--radius", type=float, default=1.0, help="Search radius (deg)")
    args = parser.parse_args()

    if args.neocp:
        print(f"Checking {len(args.neocp)} object ID(s) against NEOCP (requires network)")
        print("-" * 60)
        results = check_neocp(args.neocp)
        for r in results:
            status = r.get("status", "unknown")
            confirmed = r.get("confirmed", False)
            error = r.get("error", "")
            if error:
                print(f"  {r['object_id']:20s}  error: {error}")
            else:
                print(f"  {r['object_id']:20s}  status={status}  confirmed={confirmed}")
        print("-" * 60)
        return

    if args.input:
        tracklets = load_tracklets_from_json(args.input)
        print(f"Loaded {len(tracklets)} tracklets from {args.input}")
        observations = [obs for t in tracklets for obs in t]
    else:
        if args.dec is None:
            parser.error("--dec required with --ra")
        observations = [
            Observation(
                obs_id="query_pos",
                ra_deg=args.ra,
                dec_deg=args.dec,
                jd=2460000.5,
                mag=20.0,
                mag_err=0.1,
                filter_band="r",
                mission="ZTF",
            )
        ]

    print(f"Checking {len(observations)} observations against MPC (radius={args.radius} deg)")
    print("Note: requires network access to MPC")
    print("-" * 60)

    results = check_candidates_against_mpc(observations, radius_deg=args.radius)
    n_matched = sum(1 for r in results if r["mpc_match"] is not None)

    for r in results:
        sep = r["separation_arcsec"]
        status = f"MATCHED: {r['mpc_match']} ({sep:.1f}\")" if r["mpc_match"] else "new"
        if "error" in r:
            status = f"error: {r['error']}"
        print(f"  {r['obs_id']:20s}  RA={r['ra_deg']:.4f}  Dec={r['dec_deg']:.4f}  → {status}")

    print("-" * 60)
    print(f"Matched: {n_matched}/{len(results)} observations to known MPC objects")


if __name__ == "__main__":
    main()
