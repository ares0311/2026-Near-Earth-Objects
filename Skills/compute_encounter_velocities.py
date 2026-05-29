"""Batch compute Earth-encounter velocities for NEO candidates from JSON."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from orbit import compute_encounter_velocity


def _get_elements(entry: dict) -> object:
    elements = entry.get("orbital_elements") or entry.get("elements") or {}
    return SimpleNamespace(
        a_au=elements.get("a_au"),
        e=elements.get("e"),
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Batch compute Earth-encounter velocities from scored NEO JSON."
    )
    parser.add_argument("input", help="Path to scored NEO or tracklet JSON file")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    data = json.loads(Path(args.input).read_text())
    if isinstance(data, dict):
        data = [data]

    rows = []
    for entry in data:
        object_id = (
            entry.get("tracklet", {}).get("object_id", entry.get("object_id", "unknown"))
        )
        elements = _get_elements(entry)
        v_enc = compute_encounter_velocity(elements)
        rows.append({"object_id": object_id, "encounter_velocity_km_s": v_enc})

    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        print(f"{'object_id':<30} {'encounter_vel_km_s':>20}")
        print("-" * 52)
        for row in rows:
            v = row["encounter_velocity_km_s"]
            v_str = f"{v:.4f}" if v is not None else "N/A"
            print(f"{row['object_id']:<30} {v_str:>20}")


if __name__ == "__main__":
    main()
