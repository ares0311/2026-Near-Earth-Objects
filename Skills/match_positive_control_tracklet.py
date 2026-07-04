#!/usr/bin/env python
"""Gate Z3 -- identify which (if any) tracklet in a
Skills/run_archive_positive_control.py report actually matches a known
object's real reported sky position, instead of accepting tracklet count
or motion-rate proximity alone as confirmation.

`link()` has no chi-square orbit-consistency check for exactly-2-
observation arcs (that check only applies at >=3 observations), so in a
crowded field, many 2-observation tracklets can be spurious combinatorial
pairings of unrelated real sources that happen to share a similar motion
rate to the real target. This script ranks tracklets by angular offset
from a pair of known real reference positions (e.g. from an MPC
observation history lookup) to find the tracklet that is actually close
to the object, not just kinematically plausible.

This is diagnostic only -- it does not classify, score, or submit
anything, and it must never claim "confirmed NEO".

Usage:
    uv run --python 3.14 python Skills/match_positive_control_tracklet.py \\
        Logs/pipeline_runs/run_archive_positive_control/report_min2.json \\
        --ref1 257.0809 -10.7456 \\
        --ref2 257.5497 -10.9843
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def separation_arcsec(ra1: float, dec1: float, ra2: float, dec2: float) -> float:
    """Angular separation in arcsec using a flat-sky (small-angle) approximation
    with a cos(dec) correction for RA -- adequate for the sub-degree offsets
    expected here, not intended for large-angle astrometry."""
    mean_dec_rad = math.radians((dec1 + dec2) / 2)
    dra_arcsec = (ra2 - ra1) * math.cos(mean_dec_rad) * 3600
    ddec_arcsec = (dec2 - dec1) * 3600
    return math.hypot(dra_arcsec, ddec_arcsec)


def rank_tracklets(report: dict, ref1: tuple[float, float], ref2: tuple[float, float]) -> list[dict]:
    """Rank each 2-observation tracklet in the report by total angular offset
    from the two reference positions (sorted by observation JD, so
    observations[0] is compared to ref1 and observations[1] to ref2)."""
    scored = []
    for trk in report.get("tracklets", []):
        obs = trk.get("observations", [])
        if len(obs) != 2:
            continue
        o1, o2 = obs[0], obs[1]
        d1 = separation_arcsec(ref1[0], ref1[1], o1["ra_deg"], o1["dec_deg"])
        d2 = separation_arcsec(ref2[0], ref2[1], o2["ra_deg"], o2["dec_deg"])
        scored.append(
            {
                "object_id": trk["object_id"],
                "offset1_arcsec": round(d1, 2),
                "offset2_arcsec": round(d2, 2),
                "total_offset_arcsec": round(d1 + d2, 2),
                "motion_rate_arcsec_per_hour": trk.get("motion_rate_arcsec_per_hour"),
                "motion_pa_degrees": trk.get("motion_pa_degrees"),
            }
        )
    scored.sort(key=lambda r: r["total_offset_arcsec"])
    return scored


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("report_path", type=Path, help="Path to a run_archive_positive_control.py JSON report")
    parser.add_argument(
        "--ref1", nargs=2, type=float, required=True, metavar=("RA_DEG", "DEC_DEG"),
        help="Known real reference position (RA Dec, degrees) for the first night's observation."
    )
    parser.add_argument(
        "--ref2", nargs=2, type=float, required=True, metavar=("RA_DEG", "DEC_DEG"),
        help="Known real reference position (RA Dec, degrees) for the second night's observation."
    )
    parser.add_argument("--top-n", type=int, default=5, help="Number of closest tracklets to print (default: 5)")
    args = parser.parse_args()

    report = json.loads(args.report_path.read_text())
    ranked = rank_tracklets(report, tuple(args.ref1), tuple(args.ref2))

    if not ranked:
        print("No 2-observation tracklets found in report -- nothing to rank.", flush=True)
        return

    print(f"Ranked {len(ranked)} tracklet(s) by offset from the real reference positions.", flush=True)
    print(f"Top {min(args.top_n, len(ranked))} closest matches:", flush=True)
    for row in ranked[: args.top_n]:
        print(
            f"  {row['object_id']}: total_offset={row['total_offset_arcsec']:.1f} arcsec "
            f"(night1={row['offset1_arcsec']:.1f}, night2={row['offset2_arcsec']:.1f}), "
            f"rate={row['motion_rate_arcsec_per_hour']:.2f} arcsec/hr, "
            f"PA={row['motion_pa_degrees']:.1f} deg",
            flush=True,
        )

    best = ranked[0]
    print(
        f"\nBest candidate: {best['object_id']} with total offset "
        f"{best['total_offset_arcsec']:.1f} arcsec from the real reference positions. "
        "This is diagnostic only -- it does not confirm object identity.",
        flush=True,
    )


if __name__ == "__main__":
    main()
