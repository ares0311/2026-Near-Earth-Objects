"""Assess survey field coverage from a SurveyField JSON list.

Reads a JSON file containing a list of SurveyField records and reports:
- Total fields observed
- Total sky area covered (approximate, ignoring overlaps)
- Median limiting magnitude
- Number of fields per survey night (unique JD rounded to nearest day)

Usage::

    python Skills/assess_survey_coverage.py data/survey_fields.json
    python Skills/assess_survey_coverage.py data/survey_fields.json --json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from schemas import SurveyField


def _area_deg2(radius_deg: float) -> float:
    """Solid angle of a circular field in square degrees."""
    return math.pi * radius_deg ** 2


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Assess survey field coverage from SurveyField JSON."
    )
    parser.add_argument("input", help="Path to JSON file (list of SurveyField dicts)")
    parser.add_argument(
        "--json", action="store_true", dest="json_out", help="Output JSON instead of table"
    )
    args = parser.parse_args()

    raw = json.loads(Path(args.input).read_text())
    if not isinstance(raw, list):
        raw = [raw]

    fields: list[SurveyField] = []
    for item in raw:
        try:
            fields.append(SurveyField(**item))
        except Exception as exc:
            print(f"Warning: skipping malformed record: {exc}", file=sys.stderr)

    if not fields:
        print("No valid SurveyField records found.")
        sys.exit(1)

    total_area = sum(_area_deg2(f.radius_deg) for f in fields)
    lim_mags = sorted(f.limiting_mag for f in fields)
    n = len(lim_mags)
    median_lim = lim_mags[n // 2] if n % 2 == 1 else (lim_mags[n // 2 - 1] + lim_mags[n // 2]) / 2
    total_sources = sum(f.n_sources for f in fields)

    nights: dict[int, int] = {}
    for f in fields:
        night = int(round(f.jd))
        nights[night] = nights.get(night, 0) + 1

    summary = {
        "n_fields": len(fields),
        "total_area_deg2": round(total_area, 3),
        "median_limiting_mag": round(median_lim, 2),
        "total_sources": total_sources,
        "n_nights": len(nights),
        "fields_per_night": {str(k): v for k, v in sorted(nights.items())},
    }

    if args.json_out:
        print(json.dumps(summary, indent=2))
    else:
        print(f"Fields observed      : {summary['n_fields']}")
        print(f"Total area (approx)  : {summary['total_area_deg2']:.2f} deg²")
        print(f"Median limiting mag  : {summary['median_limiting_mag']:.2f}")
        print(f"Total sources        : {summary['total_sources']}")
        print(f"Nights               : {summary['n_nights']}")
        print("\nFields per night (JD rounded):")
        for night, count in sorted(nights.items()):
            print(f"  JD {night}: {count} field(s)")


if __name__ == "__main__":
    main()
