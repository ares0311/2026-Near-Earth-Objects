"""Batch compute detection confidence scores for ScoredNEOs from JSON."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from schemas import CandidateFeatures
from score import compute_detection_confidence


def _make_neo(entry: dict) -> object:
    feats_raw = entry.get("features") or {}

    def _opt(v: object) -> float | None:
        return float(v) if v is not None else None

    features = CandidateFeatures(
        real_bogus_score=_opt(feats_raw.get("real_bogus_score")),
        streak_score=_opt(feats_raw.get("streak_score")),
        psf_quality_score=_opt(feats_raw.get("psf_quality_score")),
        motion_consistency_score=_opt(feats_raw.get("motion_consistency_score")),
        arc_coverage_score=_opt(feats_raw.get("arc_coverage_score")),
        nights_observed_score=_opt(feats_raw.get("nights_observed_score")),
        brightness_score=_opt(feats_raw.get("brightness_score")),
        color_score=_opt(feats_raw.get("color_score")),
        lightcurve_variability_score=_opt(feats_raw.get("lightcurve_variability_score")),
        orbit_quality_score=_opt(feats_raw.get("orbit_quality_score")),
        moid_score=_opt(feats_raw.get("moid_score")),
        neo_class_confidence=_opt(feats_raw.get("neo_class_confidence")),
        pha_flag_confidence=_opt(feats_raw.get("pha_flag_confidence")),
        known_object_score=_opt(feats_raw.get("known_object_score")),
    )

    class _Neo:
        pass

    neo = _Neo()
    neo.features = features  # type: ignore[attr-defined]
    return neo


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Batch compute detection confidence from ScoredNEO JSON."
    )
    parser.add_argument("json_file", help="Path to scored NEO JSON file.")
    parser.add_argument(
        "--threshold", type=float, default=0.0,
        help="Only display candidates with confidence >= threshold."
    )
    parser.add_argument("--json", action="store_true", help="Output JSON instead of table.")
    args = parser.parse_args()

    data = json.loads(Path(args.json_file).read_text())
    if isinstance(data, dict):
        data = [data]

    rows: list[dict] = []
    for entry in data:
        oid = entry.get("object_id") or entry.get("tracklet", {}).get("object_id", "unknown")
        neo = _make_neo(entry)
        conf = compute_detection_confidence(neo)
        if conf >= args.threshold:
            rows.append({"object_id": oid, "detection_confidence": conf})

    rows.sort(key=lambda r: r["detection_confidence"], reverse=True)

    if args.json:
        print(json.dumps(rows, indent=2))
        return

    print(f"{'Object ID':<36}  {'Confidence':>12}")
    print("-" * 52)
    for row in rows:
        print(f"{row['object_id']:<36}  {row['detection_confidence']:>12.4f}")


if __name__ == "__main__":
    main()
