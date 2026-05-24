"""Batch compute variability index (reduced chi²) for tracklets from a JSON file."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Batch compute reduced-chi² variability index for tracklets."
    )
    parser.add_argument("input", help="Path to JSON file with tracklets or ScoredNEOs")
    parser.add_argument("--threshold", type=float, default=None,
                        help="Only show tracklets with variability index above threshold")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of table")
    args = parser.parse_args()

    from detect import compute_variability_index

    data = json.loads(Path(args.input).read_text())
    if not isinstance(data, list):
        data = [data]

    results = []
    for item in data:
        if "tracklet" in item:
            tracklet = item["tracklet"] or {}
            object_id = tracklet.get("object_id", "unknown")
            obs_list = tracklet.get("observations") or []
        else:
            object_id = item.get("object_id", "unknown")
            obs_list = item.get("observations") or []

        class _Obs:
            def __init__(self, d: dict) -> None:
                self.mag = d.get("mag", 99.0)
                self.mag_err = d.get("mag_err", 0.1)

        obs_objects = [_Obs(o) for o in obs_list]
        vi = compute_variability_index(obs_objects)

        if args.threshold is not None and (vi is None or vi < args.threshold):
            continue
        results.append({"object_id": object_id, "variability_index": vi})

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(f"{'Object ID':<30} {'Var. Index':>12}")
        print("-" * 44)
        for r in results:
            vi = r['variability_index']
            vi_str = f"{vi:.4f}" if vi is not None else "N/A"
            print(f"{r['object_id']:<30} {vi_str:>12}")


if __name__ == "__main__":
    main()
