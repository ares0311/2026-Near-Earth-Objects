#!/usr/bin/env python
"""Gate Z3 -- find the nearest real raw observation(s) to a known reference
position within a single night's Skills/ztf_alert_archive_ingest.py
checkpoint, independent of detect()/link().

Skills/match_positive_control_tracklet.py checks whether any *linked
tracklet* is near a known object's real reported position. That test can
give a false negative even when the archive genuinely captured the object:
link() only checks motion-rate consistency between candidate pairs, never
positional proximity, so in a crowded field the object's own two real
detections may simply never be paired together by the linker (a many-to-
one greedy-pairing ambiguity), independent of whether ZTF actually imaged
it. This script answers a narrower, prior question: within a single
night's *raw kept observations* (before detect()/link() ever run), is
there a real detection close to the known position at all?

Reads the same checkpoint JSON format written by
Skills/ztf_alert_archive_ingest.py (a dict with a top-level "observations"
list of dicts with at least ra_deg/dec_deg/jd). No network access; no
pipeline re-run.

This is diagnostic only -- it does not classify, score, or submit
anything, and it must never claim "confirmed NEO".

Usage:
    uv run --python 3.14 python Skills/find_nearest_raw_observation.py \\
        Logs/pipeline_runs/ztf_alert_archive_ingest/20220817.json \\
        --ref 257.0809 -10.7456 \\
        --top-n 5
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


def rank_observations(checkpoint: dict, ref: tuple[float, float]) -> list[dict]:
    """Rank every real kept observation in the checkpoint by angular offset
    from the reference position."""
    scored = []
    for obs in checkpoint.get("observations", []):
        d = separation_arcsec(ref[0], ref[1], obs["ra_deg"], obs["dec_deg"])
        scored.append(
            {
                "obs_id": obs.get("obs_id"),
                "ra_deg": obs["ra_deg"],
                "dec_deg": obs["dec_deg"],
                "jd": obs.get("jd"),
                "real_bogus": obs.get("real_bogus"),
                "offset_arcsec": round(d, 2),
            }
        )
    scored.sort(key=lambda r: r["offset_arcsec"])
    return scored


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "checkpoint_path",
        type=Path,
        help="Path to a ztf_alert_archive_ingest.py night checkpoint JSON",
    )
    parser.add_argument(
        "--ref", nargs=2, type=float, required=True, metavar=("RA_DEG", "DEC_DEG"),
        help="Known real reference position (RA Dec, degrees) to search near.",
    )
    parser.add_argument(
        "--top-n", type=int, default=5, help="Number of closest observations to print (default: 5)"
    )
    args = parser.parse_args()

    checkpoint = json.loads(args.checkpoint_path.read_text())
    ranked = rank_observations(checkpoint, tuple(args.ref))

    if not ranked:
        print("No observations found in checkpoint -- nothing to rank.", flush=True)
        return

    print(
        f"Ranked {len(ranked)} real observation(s) by offset from the reference position.",
        flush=True,
    )
    print(f"Top {min(args.top_n, len(ranked))} closest:", flush=True)
    for row in ranked[: args.top_n]:
        rb = row["real_bogus"]
        rb_str = f"{rb:.2f}" if rb is not None else "None"
        print(
            f"  {row['obs_id']}: offset={row['offset_arcsec']:.1f} arcsec, "
            f"ra={row['ra_deg']:.5f} dec={row['dec_deg']:.5f}, real_bogus={rb_str}",
            flush=True,
        )

    best = ranked[0]
    print(
        f"\nClosest real observation: {best['obs_id']} at offset "
        f"{best['offset_arcsec']:.1f} arcsec. This is diagnostic only -- it does "
        "not confirm object identity.",
        flush=True,
    )


if __name__ == "__main__":
    main()
