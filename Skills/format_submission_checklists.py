"""Generate submission checklists for scored NEO candidates.

Prints or exports the alert-protocol submission checklist for each candidate
that meets a minimum discovery priority threshold.

Usage
-----
    python Skills/format_submission_checklists.py data/scored_neos.json

    python Skills/format_submission_checklists.py data/scored_neos.json \\
        --min-priority 0.5 --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Generate submission checklists for scored NEO candidates."
    )
    parser.add_argument("input", help="Path to scored-NEO JSON file")
    parser.add_argument(
        "--min-priority",
        type=float,
        default=0.0,
        dest="min_priority",
        help="Minimum discovery_priority to include (default: 0.0)",
    )
    parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Output as JSON array with checklist text per candidate",
    )
    args = parser.parse_args(argv)

    from alert import format_submission_checklist
    from schemas import ScoredNEO

    with open(args.input) as f:
        raw = json.load(f)

    if isinstance(raw, dict):
        raw = [raw]

    results = []
    for item in raw:
        try:
            neo = ScoredNEO(**item)
        except Exception:
            continue
        priority = getattr(neo.metadata, "discovery_priority", 0.0) or 0.0
        if priority < args.min_priority:
            continue
        checklist = format_submission_checklist(neo)
        results.append({
            "object_id": neo.tracklet.object_id,
            "discovery_priority": priority,
            "checklist": checklist,
        })

    if not results:
        print("No candidates meet the minimum priority threshold.")
        return

    if args.as_json:
        print(json.dumps(results, indent=2))
        return

    for entry in results:
        print("=" * 60)
        print(entry["checklist"])
        print()


if __name__ == "__main__":
    main()
