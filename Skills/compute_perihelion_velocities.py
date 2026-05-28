"""Batch compute perihelion velocity for tracklets with orbital elements from JSON."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orbit import compute_perihelion_velocity


def _velocity(entry: dict) -> float | None:
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
    return compute_perihelion_velocity(obj)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Batch compute perihelion velocity (km/s) from tracklet JSON."
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
        v = _velocity(entry)
        rows.append({"object_id": oid, "perihelion_velocity_km_s": v})

    if args.json:
        print(json.dumps(rows, indent=2))
        return

    print(f"{'Object ID':<36}  {'v_perihelion (km/s)':>20}")
    print("-" * 60)
    for row in rows:
        v_km = row["perihelion_velocity_km_s"]
        v_str = f"{v_km:.3f}" if v_km is not None else "N/A"
        print(f"{row['object_id']:<36}  {v_str:>20}")


if __name__ == "__main__":
    main()
