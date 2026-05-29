"""Batch compute arc completeness scores for ScoredNEOs from JSON."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from schemas import CandidateFeatures
from score import compute_arc_completeness_score


def _arc_completeness(entry: dict) -> float | None:
    features_dict = entry.get("features")
    if not features_dict:
        return None
    try:
        features = CandidateFeatures(**features_dict)
    except Exception:
        return None
    return compute_arc_completeness_score(features)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Batch compute arc completeness scores from ScoredNEO JSON."
    )
    parser.add_argument("input", help="Path to ScoredNEO JSON file")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    data = json.loads(Path(args.input).read_text())
    if isinstance(data, dict):
        data = [data]

    rows = []
    for entry in data:
        object_id = entry.get("tracklet", {}).get("object_id", entry.get("object_id", "unknown"))
        score = _arc_completeness(entry)
        rows.append({"object_id": object_id, "arc_completeness_score": score})

    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        print(f"{'object_id':<30} {'arc_completeness_score':>22}")
        print("-" * 54)
        for row in rows:
            sc = row["arc_completeness_score"]
            sc_str = f"{sc:.6f}" if sc is not None else "N/A"
            print(f"{row['object_id']:<30} {sc_str:>22}")


if __name__ == "__main__":
    main()
