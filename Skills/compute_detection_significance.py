"""Batch compute detection significance scores for observations from JSON."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from detect import compute_detection_significance


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Batch compute detection significance from observation JSON."
    )
    parser.add_argument("input", help="Path to observation or tracklet JSON file")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    data = json.loads(Path(args.input).read_text())
    if isinstance(data, dict):
        data = [data]

    rows = []
    for entry in data:
        obs_id = entry.get("obs_id", entry.get("object_id", "unknown"))
        obs = SimpleNamespace(
            mag=entry.get("mag"),
            limiting_mag=entry.get("limiting_mag"),
        )
        sig = compute_detection_significance(obs)
        rows.append({"obs_id": obs_id, "detection_significance": sig})

    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        print(f"{'obs_id':<30} {'significance':>14}")
        print("-" * 46)
        for row in rows:
            v = row["detection_significance"]
            v_str = f"{v:.4f}" if v is not None else "N/A"
            print(f"{row['obs_id']:<30} {v_str:>14}")


if __name__ == "__main__":
    main()
