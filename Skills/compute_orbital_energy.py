"""Compute specific orbital energy for tracklets or ScoredNEO dicts.

Usage::

    python Skills/compute_orbital_energy.py data/sample_tracklets.json
    python Skills/compute_orbital_energy.py data/sample_tracklets.json --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from orbit import orbital_energy
from schemas import OrbitalElements


def _elements_from_dict(d: dict) -> OrbitalElements | None:
    """Try to extract OrbitalElements from a tracklet or ScoredNEO dict."""
    # ScoredNEO shape: {"hazard": {"neo_class": ...}, "orbital_elements": {...}}
    elems_dict = d.get("orbital_elements") or d.get("elements")
    if not elems_dict and "hazard" in d:
        elems_dict = d.get("orbital_elements")
    if not elems_dict:
        return None
    try:
        return OrbitalElements(**elems_dict)
    except Exception:
        return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compute specific orbital energy for NEO candidates."
    )
    parser.add_argument("input", help="Path to JSON file (list of tracklets or ScoredNEO dicts)")
    parser.add_argument(
        "--json", action="store_true", dest="json_out", help="Output JSON instead of table"
    )
    args = parser.parse_args()

    data = json.loads(Path(args.input).read_text())
    if not isinstance(data, list):
        data = [data]

    results = []
    for item in data:
        obj_id = (
            item.get("object_id")
            or item.get("tracklet", {}).get("object_id")
            or "unknown"
        )
        elements = _elements_from_dict(item)
        if elements is None:
            energy = None
            label = "no elements"
        else:
            energy = orbital_energy(elements)
            if energy < 0:
                label = "bound"
            elif energy == 0.0:
                label = "parabolic"
            else:
                label = "hyperbolic"
        results.append({"object_id": obj_id, "energy_au2_yr2": energy, "orbit_type": label})

    if args.json_out:
        print(json.dumps(results, indent=2))
    else:
        print(f"{'Object ID':<25}  {'Energy (AU²/yr²)':>18}  {'Type'}")
        print("-" * 55)
        for r in results:
            e_str = f"{r['energy_au2_yr2']:.6f}" if r["energy_au2_yr2"] is not None else "N/A"
            print(f"{r['object_id']:<25}  {e_str:>18}  {r['orbit_type']}")


if __name__ == "__main__":
    main()
