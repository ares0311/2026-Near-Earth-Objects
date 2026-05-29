"""Batch compute Hill sphere radii for tracklets with orbital elements from JSON."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orbit import compute_hill_sphere_radius


def _hill_radius(entry: dict) -> float | None:
    elems = entry.get("orbital_elements") or {}
    a = elems.get("a_au")
    e = elems.get("e")
    if a is None or e is None:
        return None

    class _E:
        pass

    obj = _E()
    obj.a_au = float(a)  # type: ignore[attr-defined]
    obj.e = float(e)  # type: ignore[attr-defined]
    h_val = elems.get("absolute_magnitude_h")
    if h_val is not None:
        obj.absolute_magnitude_h = float(h_val)  # type: ignore[attr-defined]
    return compute_hill_sphere_radius(obj)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Batch compute Hill sphere radii (AU) from tracklet JSON."
    )
    parser.add_argument("json_file", help="Path to tracklet or ScoredNEO JSON file.")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of table.")
    args = parser.parse_args()

    data = json.loads(Path(args.json_file).read_text())
    if isinstance(data, dict):
        data = [data]

    rows: list[dict] = []
    for entry in data:
        oid = entry.get("object_id") or entry.get("tracklet", {}).get("object_id", "unknown")
        r_h = _hill_radius(entry)
        rows.append({"object_id": oid, "hill_sphere_radius_au": r_h})

    if args.json:
        print(json.dumps(rows, indent=2))
        return

    print(f"{'Object ID':<36}  {'r_Hill (AU)':>14}")
    print("-" * 54)
    for row in rows:
        r_val = row["hill_sphere_radius_au"]
        r_str = f"{r_val:.8e}" if r_val is not None else "N/A"
        print(f"{row['object_id']:<36}  {r_str:>14}")


if __name__ == "__main__":
    main()
