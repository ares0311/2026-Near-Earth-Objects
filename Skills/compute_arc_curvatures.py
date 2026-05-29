"""Batch compute arc curvature (RMS linear residual in arcsec) for tracklets from JSON."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from link import compute_arc_curvature
from schemas import Observation, Tracklet


def _build_tracklet(entry: dict) -> object | None:
    try:
        obs_list = [Observation(**o) for o in entry.get("observations", [])]
        return Tracklet(
            object_id=entry.get("object_id", "unknown"),
            observations=tuple(obs_list),
            arc_days=float(entry.get("arc_days", 0.0)),
            motion_rate_arcsec_per_hour=float(entry.get("motion_rate_arcsec_per_hour", 0.0)),
            motion_pa_degrees=float(entry.get("motion_pa_degrees", 0.0)),
        )
    except Exception:
        return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Batch compute arc curvature (RMS linear residual) from tracklet JSON."
    )
    parser.add_argument("input", help="Path to tracklet JSON file")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    data = json.loads(Path(args.input).read_text())
    if isinstance(data, dict):
        data = [data]

    rows = []
    for entry in data:
        tracklet = _build_tracklet(entry)
        curvature = compute_arc_curvature(tracklet) if tracklet else 0.0
        rows.append({
            "object_id": entry.get("object_id", "unknown"),
            "arc_curvature_arcsec": curvature,
        })

    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        print(f"{'object_id':<30} {'arc_curvature_arcsec':>22}")
        print("-" * 54)
        for row in rows:
            print(f"{row['object_id']:<30} {row['arc_curvature_arcsec']:>22.6f}")


if __name__ == "__main__":
    main()
