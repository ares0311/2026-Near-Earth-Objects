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

from alert import monitor_neocp, process_alert, summarise
from classify import classify
from detect import detect
from fetch import fetch
from link import link
from orbit import fit_orbit
from preprocess import preprocess
from score import score


def run_pipeline(
    ra_deg: float,
    dec_deg: float,
    radius_deg: float,
    start_jd: float,
    end_jd: float,
    surveys: tuple[str, ...] = ("ZTF",),
    dry_run: bool = True,
    atlas_token: str | None = None,
    force_refresh: bool = False,
    neocp_timeout_hours: float = 0.0,
    neocp_poll_interval_hours: float = 1.0,
) -> list[dict]:
    print(f"[fetch] Querying {surveys} at RA={ra_deg}, Dec={dec_deg}, r={radius_deg}°")
    fetch_result = fetch(
        ra_deg=ra_deg,
        dec_deg=dec_deg,
        radius_deg=radius_deg,
        start_jd=start_jd,
        end_jd=end_jd,
        surveys=surveys,  # type: ignore[arg-type]
        atlas_token=atlas_token,
        force_refresh=force_refresh,
    )
    print(f"[fetch] Retrieved {len(fetch_result.alerts)} alerts")

    print("[preprocess] Validating and normalising sources")
    prep_result = preprocess(fetch_result.alerts, apply_astrometry=False)
    n_out = prep_result.provenance.n_sources_out
    n_in = prep_result.provenance.n_sources_in
    print(f"[preprocess] {n_out}/{n_in} sources passed")

    print("[detect] Identifying moving object candidates")
    det_result = detect(prep_result.sources)
    n_cands = det_result.provenance.n_candidates
    n_known = det_result.provenance.n_known_matches
    print(f"[detect] {n_cands} candidates, {n_known} known matches")

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

        if neocp_timeout_hours > 0:
            print(f"[neocp] Monitoring NEOCP for {tracklet.object_id} "
                  f"(timeout={neocp_timeout_hours}h)")
            neocp_result = monitor_neocp(
                tracklet.object_id,
                max_wait_hr=neocp_timeout_hours,
                poll_interval_hr=neocp_poll_interval_hours,
            )
            alert_result["neocp_monitor"] = neocp_result
            print(f"[neocp] status={neocp_result['status']}, "
                  f"confirmed={neocp_result.get('confirmed', False)}")

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
    parser.add_argument("--atlas-token", type=str, default=None,
                        help="ATLAS authentication token (or set ATLAS_TOKEN env var)")
    parser.add_argument("--force-refresh", action="store_true", default=False,
                        help="Bypass on-disk cache and re-fetch all survey data")
    parser.add_argument("--neocp-timeout-hours", type=float, default=0.0,
                        help="Hours to poll NEOCP for independent confirmation (0 = skip)")
    parser.add_argument("--neocp-poll-interval", type=float, default=1.0,
                        help="NEOCP poll interval in hours (default 1)")
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
        atlas_token=args.atlas_token,
        force_refresh=args.force_refresh,
        neocp_timeout_hours=args.neocp_timeout_hours,
        neocp_poll_interval_hours=args.neocp_poll_interval,
    )

    if args.output:
        Path(args.output).write_text(json.dumps(results, indent=2))
        print(f"Results written to {args.output}")
    else:
        print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
