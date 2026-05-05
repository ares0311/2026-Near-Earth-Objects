#!/usr/bin/env python3
"""Skills/run_pipeline.py — End-to-end NEO pipeline runner.

Usage:
    python Skills/run_pipeline.py \
        --ra 180.0 --dec 10.0 --radius 1.0 \
        --start-jd 2460000.0 --end-jd 2460010.0 \
        [--surveys ZTF] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fetch import fetch
from preprocess import preprocess
from detect import detect
from link import link
from classify import classify, extract_features
from orbit import fit_orbit
from score import score
from alert import process_alert, summarise


def run_pipeline(
    ra_deg: float,
    dec_deg: float,
    radius_deg: float,
    start_jd: float,
    end_jd: float,
    surveys: tuple[str, ...] = ("ZTF",),
    dry_run: bool = True,
) -> list[dict]:
    print(f"[fetch] Querying {surveys} at RA={ra_deg}, Dec={dec_deg}, r={radius_deg}°")
    fetch_result = fetch(
        ra_deg=ra_deg,
        dec_deg=dec_deg,
        radius_deg=radius_deg,
        start_jd=start_jd,
        end_jd=end_jd,
        surveys=surveys,  # type: ignore[arg-type]
    )
    print(f"[fetch] Retrieved {len(fetch_result.alerts)} alerts")

    print("[preprocess] Validating and normalising sources")
    prep_result = preprocess(fetch_result.alerts, apply_astrometry=False)
    print(f"[preprocess] {prep_result.provenance.n_sources_out}/{prep_result.provenance.n_sources_in} sources passed")

    print("[detect] Identifying moving object candidates")
    det_result = detect(prep_result.sources)
    print(f"[detect] {det_result.provenance.n_candidates} candidates, {det_result.provenance.n_known_matches} known matches")

    print("[link] Linking candidates across nights")
    link_result = link(det_result.candidates)
    print(f"[link] {link_result.provenance.n_tracklets} tracklets formed")

    results: list[dict] = []
    for tracklet in link_result.tracklets:
        print(f"[classify] Classifying tracklet {tracklet.object_id}")
        features, posterior = classify(tracklet)

        print(f"[orbit] Fitting orbit for {tracklet.object_id}")
        orbital = fit_orbit(tracklet)

        print(f"[score] Scoring {tracklet.object_id}")
        scored = score(tracklet, features, posterior, orbital)

        print(f"[alert] Processing alert for {tracklet.object_id}")
        alert_result = process_alert(scored, dry_run=dry_run)

        print(summarise(scored))
        results.append({
            "object_id": tracklet.object_id,
            "neo_probability": scored.posterior.neo_candidate,
            "hazard_flag": scored.hazard.hazard_flag,
            "alert_pathway": scored.hazard.alert_pathway,
            "moid_au": scored.hazard.moid_au,
            "discovery_priority": scored.metadata.discovery_priority,
            "alert_actions": alert_result["actions"],
        })

    print(f"\nPipeline complete. {len(results)} NEO candidate(s) processed.")
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="NEO detection pipeline")
    parser.add_argument("--ra", type=float, required=True)
    parser.add_argument("--dec", type=float, required=True)
    parser.add_argument("--radius", type=float, default=1.0)
    parser.add_argument("--start-jd", type=float, required=True)
    parser.add_argument("--end-jd", type=float, required=True)
    parser.add_argument("--surveys", nargs="+", default=["ZTF"])
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--output", type=str, default=None)
    args = parser.parse_args()

    results = run_pipeline(
        ra_deg=args.ra,
        dec_deg=args.dec,
        radius_deg=args.radius,
        start_jd=args.start_jd,
        end_jd=args.end_jd,
        surveys=tuple(args.surveys),
        dry_run=args.dry_run,
    )

    if args.output:
        Path(args.output).write_text(json.dumps(results, indent=2))
        print(f"Results written to {args.output}")
    else:
        print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
