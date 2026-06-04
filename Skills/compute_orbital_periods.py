"""Batch orbital period computation from tracklet JSON.

Usage:
    python Skills/compute_orbital_periods.py data/sample_tracklets.json [--json]

Reads a tracklet JSON file and prints the Keplerian orbital period in days
for each tracklet that has orbital elements, using compute_orbital_period
from orbit.py.
"""
import json
import sys
from types import SimpleNamespace

sys.path.insert(0, "src")

from orbit import compute_orbital_period


def _load_elements(d: dict) -> SimpleNamespace:
    el = d.get("orbital_elements", {}) or {}
    return SimpleNamespace(**el) if isinstance(el, dict) else SimpleNamespace()


def main(argv: list[str]) -> None:
    as_json = "--json" in argv
    paths = [a for a in argv if not a.startswith("--")]

    if not paths:
        print("Usage: compute_orbital_periods.py <tracklets.json> [--json]",
              file=sys.stderr)
        sys.exit(1)

    with open(paths[0]) as fh:
        data = json.load(fh)
    tracklets = data if isinstance(data, list) else [data]

    rows = []
    for t in tracklets:
        obj_id = t.get("object_id", "unknown")
        elements = _load_elements(t)
        period_days = compute_orbital_period(elements)
        rows.append({"object_id": obj_id, "period_days": period_days})

    if as_json:
        print(json.dumps(rows, indent=2))
    else:
        print(f"{'Object ID':<20}  {'Period (days)':>14}")
        print("-" * 36)
        for row in rows:
            p = row["period_days"]
            p_str = f"{p:.2f}" if p is not None else "N/A"
            print(f"{row['object_id']:<20}  {p_str:>14}")


if __name__ == "__main__":
    main(sys.argv[1:])
