"""Batch true anomaly computation for tracklets with orbital elements.

Usage:
    python Skills/compute_true_anomaly.py data/sample_tracklets.json [--json]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Batch compute true anomaly from tracklet JSON.")
    parser.add_argument("input", help="Path to tracklet or ScoredNEO JSON file.")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of table.")
    args = parser.parse_args(argv)

    path = Path(args.input)
    if not path.exists():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        sys.exit(1)

    data = json.loads(path.read_text())
    if not isinstance(data, list):
        data = [data]

    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
    from orbit import compute_eccentric_anomaly, compute_true_anomaly

    rows = []
    for item in data:
        obj_id = (
            item.get("object_id")
            or item.get("tracklet", {}).get("object_id", "unknown")
        )
        el = item.get("orbital_elements") or item.get("elements") or {}
        M_deg = el.get("mean_anomaly_deg")
        e = el.get("eccentricity")
        if M_deg is None or e is None:
            rows.append({"object_id": obj_id, "M_deg": None, "e": None,
                         "E_deg": None, "nu_deg": None, "note": "no orbital elements"})
            continue
        try:
            M_rad = math.radians(float(M_deg))
            e_val = float(e)
            E_rad = compute_eccentric_anomaly(M_rad, e_val)
            nu_rad = compute_true_anomaly(E_rad, e_val)
            rows.append({
                "object_id": obj_id,
                "M_deg": round(float(M_deg), 4),
                "e": round(e_val, 6),
                "E_deg": round(math.degrees(E_rad), 4),
                "nu_deg": round(math.degrees(nu_rad), 4),
                "note": "ok",
            })
        except Exception as exc:
            rows.append({"object_id": obj_id, "M_deg": M_deg, "e": e,
                         "E_deg": None, "nu_deg": None, "note": str(exc)})

    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        header = f"{'object_id':<20} {'M_deg':>10} {'e':>8} {'E_deg':>10} {'nu_deg':>10}  note"
        print(header)
        print("-" * len(header))
        for r in rows:
            m = f"{r['M_deg']:>10.4f}" if r["M_deg"] is not None else f"{'N/A':>10}"
            ev = f"{r['e']:>8.6f}" if r["e"] is not None else f"{'N/A':>8}"
            e_ = f"{r['E_deg']:>10.4f}" if r["E_deg"] is not None else f"{'N/A':>10}"
            n = f"{r['nu_deg']:>10.4f}" if r["nu_deg"] is not None else f"{'N/A':>10}"
            print(f"{r['object_id']:<20} {m} {ev} {e_} {n}  {r['note']}")

    sys.exit(0)


if __name__ == "__main__":
    main()
