"""Compute eccentric anomaly E from mean anomaly M and eccentricity e.

Usage::

    python Skills/compute_eccentric_anomaly.py data/sample_tracklets.json
    python Skills/compute_eccentric_anomaly.py data/sample_tracklets.json --json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from orbit import compute_eccentric_anomaly  # noqa: E402


def _get_orbital_params(item: dict) -> tuple[float, float] | None:
    """Extract (mean_anomaly_deg, eccentricity) from a tracklet or ScoredNEO dict."""
    # Try orbital_elements sub-dict (ScoredNEO or tracklet with elements)
    elems = (
        item.get("orbital_elements")
        or item.get("elements")
        or (item.get("hazard") or {}).get("orbital_elements")
    )
    if elems and isinstance(elems, dict):
        m_deg = elems.get("mean_anomaly_deg")
        ecc = elems.get("eccentricity")
        if m_deg is not None and ecc is not None:
            return float(m_deg), float(ecc)

    # Fallback: look for top-level keys
    m_deg = item.get("mean_anomaly_deg")
    ecc = item.get("eccentricity")
    if m_deg is not None and ecc is not None:
        return float(m_deg), float(ecc)

    return None


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Compute eccentric anomaly E for NEO tracklets."
    )
    parser.add_argument("input", help="Path to JSON file (list of tracklets or ScoredNEO dicts)")
    parser.add_argument(
        "--json", action="store_true", dest="json_out", help="Output JSON instead of table"
    )
    args = parser.parse_args(argv)

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
        params = _get_orbital_params(item)
        if params is None:
            warnings.warn(f"Skipping '{obj_id}': no orbital elements found.", stacklevel=2)
            continue

        m_deg, ecc = params
        m_rad = math.radians(m_deg)

        try:
            e_rad = compute_eccentric_anomaly(m_rad, ecc)
            e_deg = math.degrees(e_rad)
            results.append({
                "object_id": obj_id,
                "M_deg": round(m_deg, 6),
                "eccentricity": round(ecc, 6),
                "E_deg": round(e_deg, 6),
            })
        except ValueError as exc:
            warnings.warn(f"Skipping '{obj_id}': {exc}", stacklevel=2)

    if args.json_out:
        print(json.dumps(results, indent=2))
    else:
        header = f"{'Object ID':<25}  {'M (deg)':>12}  {'e':>10}  {'E (deg)':>12}"
        print(header)
        print("-" * len(header))
        for r in results:
            print(
                f"{r['object_id']:<25}  {r['M_deg']:>12.6f}  "
                f"{r['eccentricity']:>10.6f}  {r['E_deg']:>12.6f}"
            )


if __name__ == "__main__":
    main()
    sys.exit(0)
