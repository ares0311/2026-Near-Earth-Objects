#!/usr/bin/env python3
"""Fetch ATLAS forced photometry for a sky position and print results."""

from __future__ import annotations

import argparse
import json
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch ATLAS forced photometry for a given RA/Dec position and date range."
    )
    parser.add_argument("ra", type=float, help="Right ascension in degrees")
    parser.add_argument("dec", type=float, help="Declination in degrees")
    parser.add_argument("start_jd", type=float, help="Start Julian date")
    parser.add_argument("end_jd", type=float, help="End Julian date")
    parser.add_argument(
        "--token",
        default=None,
        help="ATLAS API token (or set ATLAS_TOKEN environment variable)",
    )
    parser.add_argument("--force-refresh", action="store_true", help="Bypass on-disk cache")
    parser.add_argument("--json", action="store_true", help="Output raw JSON list of observations")
    args = parser.parse_args()

    sys.path.insert(0, "src")
    from fetch import fetch_atlas_forced  # type: ignore[import]

    observations = fetch_atlas_forced(
        ra_deg=args.ra,
        dec_deg=args.dec,
        start_jd=args.start_jd,
        end_jd=args.end_jd,
        atlas_token=args.token,
        force_refresh=args.force_refresh,
    )

    if args.json:
        rows = [
            {
                "obs_id": o.obs_id,
                "ra_deg": o.ra_deg,
                "dec_deg": o.dec_deg,
                "jd": o.jd,
                "mag": o.mag,
                "mag_err": o.mag_err,
                "filter_band": o.filter_band,
                "mission": o.mission,
            }
            for o in observations
        ]
        print(json.dumps(rows, indent=2))
        return

    if not observations:
        print("No ATLAS observations returned (check token, coordinates, or date range).")
        return

    hdr = f"{'obs_id':<24} {'JD':>13} {'RA':>10} {'Dec':>10} {'mag':>7} {'err':>6} {'band':>5}"
    print(hdr)
    print("-" * len(hdr))
    for o in observations:
        print(
            f"{o.obs_id:<24} {o.jd:>13.5f} {o.ra_deg:>10.5f} {o.dec_deg:>10.5f}"
            f" {o.mag:>7.3f} {o.mag_err:>6.3f} {o.filter_band:>5}"
        )


if __name__ == "__main__":
    main()
