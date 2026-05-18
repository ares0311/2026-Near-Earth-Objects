"""Urgency-sorted triage table for scored NEO candidates.

Usage
-----
    python Skills/triage_candidates.py data/sample_tracklets.json

    python Skills/triage_candidates.py data/sample_tracklets.json \\
        --urgency URGENT HIGH --pathway mpc_submission nasa_pdco_notify

    python Skills/triage_candidates.py data/sample_tracklets.json --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

_URGENCY_ORDER = {"URGENT": 0, "HIGH": 1, "MEDIUM": 2, "ROUTINE": 3}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Print urgency-sorted triage table for scored NEO candidates."
    )
    parser.add_argument("input", help="Path to scored-NEO JSON file")
    parser.add_argument(
        "--urgency",
        nargs="+",
        metavar="TIER",
        help="Filter to specific urgency tiers (URGENT HIGH MEDIUM ROUTINE)",
    )
    parser.add_argument(
        "--pathway",
        nargs="+",
        metavar="PATHWAY",
        help="Filter to specific alert pathways (e.g. mpc_submission nasa_pdco_notify)",
    )
    parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Output as JSON array",
    )
    args = parser.parse_args(argv)

    from schemas import ScoredNEO
    from score import compute_followup_urgency

    with open(args.input) as f:
        raw = json.load(f)

    if isinstance(raw, dict):
        raw = [raw]

    neos = []
    for item in raw:
        try:
            neos.append(ScoredNEO(**item))
        except Exception:
            continue

    rows = []
    for neo in neos:
        urgency = compute_followup_urgency(neo)
        pathway = neo.hazard.alert_pathway
        moid = neo.hazard.moid_au
        priority = getattr(neo.metadata, "discovery_priority", None)
        rows.append({
            "object_id": neo.tracklet.object_id,
            "urgency": urgency,
            "alert_pathway": pathway,
            "hazard_flag": neo.hazard.hazard_flag,
            "moid_au": moid,
            "discovery_priority": priority,
        })

    # Apply filters
    if args.urgency:
        allowed = {u.upper() for u in args.urgency}
        rows = [r for r in rows if r["urgency"] in allowed]
    if args.pathway:
        allowed_p = set(args.pathway)
        rows = [r for r in rows if r["alert_pathway"] in allowed_p]

    # Sort by urgency tier then discovery priority (descending)
    rows.sort(key=lambda r: (
        _URGENCY_ORDER.get(r["urgency"], 99),
        -(r["discovery_priority"] or 0.0),
    ))

    if args.as_json:
        print(json.dumps(rows, indent=2))
        return

    if not rows:
        print("No candidates match the specified filters.")
        return

    hdr = (
        f"{'object_id':<20} {'urgency':<10} {'pathway':<22}"
        f" {'flag':<16} {'moid_au':>9} {'priority':>9}"
    )
    print(hdr)
    print("-" * len(hdr))
    for row in rows:
        moid_str = f"{row['moid_au']:.4f}" if row["moid_au"] is not None else "    N/A"
        disc = row["discovery_priority"]
        prio_str = f"{disc:.3f}" if disc is not None else "    N/A"
        print(
            f"{row['object_id']:<20} {row['urgency']:<10} {row['alert_pathway']:<22}"
            f" {row['hazard_flag']:<16} {moid_str:>9} {prio_str:>9}"
        )


if __name__ == "__main__":
    main()
