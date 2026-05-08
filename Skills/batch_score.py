#!/usr/bin/env python
"""Score a list of tracklets from a JSON file and print a ranked summary table.

Reads tracklets from the same JSON format as data/sample_tracklets.json and
runs the full classify → orbit → score pipeline on each.

Usage:
    PYTHONPATH=src python Skills/batch_score.py --input data/sample_tracklets.json
    PYTHONPATH=src python Skills/batch_score.py --input data/sample_tracklets.json --top 10
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from classify import classify, extract_features
from orbit import fit_orbit
from schemas import Observation, Tracklet
from score import score


def load_tracklets(path: Path) -> list[Tracklet]:
    with path.open() as f:
        data = json.load(f)
    tracklets = []
    for entry in data:
        obs = tuple(Observation(**o) for o in entry["observations"])
        t = Tracklet(
            object_id=entry.get("object_id", f"T{len(tracklets):03d}"),
            observations=obs,
            arc_days=entry.get("arc_days", 0.0),
            motion_rate_arcsec_per_hour=entry.get("motion_rate_arcsec_per_hour", 0.0),
            motion_pa_degrees=entry.get("motion_pa_degrees", 0.0),
        )
        tracklets.append(t)
    return tracklets


def score_tracklet(t: Tracklet) -> dict:
    features = extract_features(t)
    orbital = fit_orbit(t)
    features_cls, posterior = classify(t, features)
    scored = score(t, features_cls, posterior, orbital)
    return {
        "object_id": t.object_id,
        "neo_prob": scored.posterior.neo_candidate,
        "hazard_flag": scored.hazard.hazard_flag,
        "alert_pathway": scored.hazard.alert_pathway,
        "moid_au": scored.hazard.moid_au,
        "h_mag": scored.hazard.absolute_magnitude_h,
        "arc_days": t.arc_days,
        "n_obs": len(t.observations),
    }


def print_table(rows: list[dict], top: int | None) -> None:
    rows_sorted = sorted(rows, key=lambda r: r["neo_prob"], reverse=True)
    if top is not None:
        rows_sorted = rows_sorted[:top]

    header = f"{'ID':15s} {'NEO%':>6s} {'Hazard':14s} {'Alert':22s} {'MOID(AU)':>9s} {'H':>5s}"
    print(header)
    print("-" * len(header))
    for r in rows_sorted:
        moid_str = f"{r['moid_au']:.4f}" if r["moid_au"] is not None else "  N/A "
        h_str = f"{r['h_mag']:.1f}" if r["h_mag"] is not None else " N/A"
        print(
            f"{r['object_id']:15s} "
            f"{r['neo_prob']:>6.1%} "
            f"{r['hazard_flag']:14s} "
            f"{r['alert_pathway']:22s} "
            f"{moid_str:>9s} "
            f"{h_str:>5s}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch score NEO candidates")
    parser.add_argument("--input", type=Path, required=True, help="JSON tracklets file")
    parser.add_argument("--top", type=int, default=None, help="Show only top N candidates")
    args = parser.parse_args()

    tracklets = load_tracklets(args.input)
    print(f"Loaded {len(tracklets)} tracklets from {args.input}")
    print("Scoring...")

    results = []
    for t in tracklets:
        try:
            results.append(score_tracklet(t))
        except Exception as e:
            print(f"  Error scoring {t.object_id}: {e}", file=sys.stderr)

    print(f"\nRanked NEO candidates ({len(results)} scored):\n")
    print_table(results, top=args.top)


if __name__ == "__main__":
    main()
