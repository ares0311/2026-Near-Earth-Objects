"""Batch compute aphelion distances for tracklets from a JSON file."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Batch compute aphelion distance Q = a(1+e) for tracklets."
    )
    parser.add_argument("input", help="Path to JSON file with tracklets or ScoredNEOs")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of table")
    args = parser.parse_args()

    from orbit import compute_aphelion_distance
    from schemas import OrbitalElements

    data = json.loads(Path(args.input).read_text())
    if not isinstance(data, list):
        data = [data]

    results = []
    for item in data:
        # Support both raw element dicts and nested ScoredNEO structures
        if "hazard" in item and "orbital_elements" in (item.get("hazard") or {}):
            elems_dict = item["hazard"]["orbital_elements"] or {}
            object_id = item.get("tracklet", {}).get("object_id", "unknown")
        elif "orbital_elements" in item:
            elems_dict = item["orbital_elements"] or {}
            object_id = item.get("object_id", "unknown")
        else:
            elems_dict = item
            object_id = item.get("object_id", "unknown")

        if not elems_dict:
            results.append({"object_id": object_id, "aphelion_au": None})
            continue

        try:
            elements = OrbitalElements(**{k: v for k, v in elems_dict.items()
                                          if k in OrbitalElements.model_fields})
            q = compute_aphelion_distance(elements)
        except Exception:
            q = None
        results.append({"object_id": object_id, "aphelion_au": q})

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(f"{'Object ID':<30} {'Q (AU)':>12}")
        print("-" * 44)
        for r in results:
            q_str = f"{r['aphelion_au']:.6f}" if r["aphelion_au"] is not None else "N/A"
            print(f"{r['object_id']:<30} {q_str:>12}")


if __name__ == "__main__":
    main()
