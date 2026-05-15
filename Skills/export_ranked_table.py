"""Export a ranked table of ScoredNEOs to CSV or HTML.

Usage:
    python Skills/export_ranked_table.py <scored_neos.json> [--format csv|html] [--out PATH]

The input JSON must be a list of ScoredNEO-compatible dicts (as produced by
Skills/batch_score.py with --json flag or equivalent).  When no --out path is
given the output is written to stdout.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Resolve src/ on PYTHONPATH when run directly.
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from score import rank_candidates  # noqa: E402
from schemas import (  # noqa: E402
    CandidateFeatures,
    HazardAssessment,
    NEOPosterior,
    ScoredNEO,
    ScoringMetadata,
    Tracklet,
    Observation,
)


def _load_scored_neos(path: Path) -> list[ScoredNEO]:
    data = json.loads(path.read_text())
    neos: list[ScoredNEO] = []
    for item in data:
        neos.append(ScoredNEO(**item))
    return neos


def _row(neo: ScoredNEO) -> dict:
    return {
        "object_id": neo.tracklet.object_id,
        "arc_days": round(neo.tracklet.arc_days, 3),
        "n_obs": len(neo.tracklet.observations),
        "motion_rate": round(neo.tracklet.motion_rate_arcsec_per_hour, 2),
        "neo_candidate_prob": round(neo.posterior.neo_candidate, 4),
        "hazard_flag": neo.hazard.hazard_flag,
        "alert_pathway": neo.hazard.alert_pathway,
        "moid_au": neo.hazard.moid_au,
        "neo_class": neo.hazard.neo_class,
        "discovery_priority": round(neo.metadata.discovery_priority, 4),
        "followup_value": round(neo.metadata.followup_value, 4),
        "scientific_interest": round(neo.metadata.scientific_interest, 4),
    }


def export_csv(rows: list[dict]) -> str:
    if not rows:
        return ""
    headers = list(rows[0].keys())
    lines = [",".join(headers)]
    for row in rows:
        lines.append(",".join(str(row[h]) for h in headers))
    return "\n".join(lines) + "\n"


def export_html(rows: list[dict]) -> str:
    if not rows:
        return "<table></table>\n"
    headers = list(rows[0].keys())
    lines = ["<table border='1'>", "<thead><tr>"]
    for h in headers:
        lines.append(f"  <th>{h}</th>")
    lines.append("</tr></thead>", )
    lines.append("<tbody>")
    for row in rows:
        lines.append("<tr>")
        for h in headers:
            val = row[h]
            if h == "hazard_flag" and val == "pha_candidate":
                lines.append(f"  <td style='background:#ffcccc'>{val}</td>")
            else:
                lines.append(f"  <td>{val}</td>")
        lines.append("</tr>")
    lines.append("</tbody></table>")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Export ranked NEO table.")
    parser.add_argument("input", help="Path to scored NEOs JSON file")
    parser.add_argument("--format", choices=["csv", "html"], default="csv",
                        help="Output format (default: csv)")
    parser.add_argument("--out", default=None, help="Output file path (default: stdout)")
    args = parser.parse_args(argv)

    neos = _load_scored_neos(Path(args.input))
    ranked = rank_candidates(neos)
    rows = [_row(neo) for neo in ranked]

    if args.format == "html":
        content = export_html(rows)
    else:
        content = export_csv(rows)

    if args.out:
        Path(args.out).write_text(content)
        print(f"Wrote {len(rows)} rows to {args.out}")
    else:
        sys.stdout.write(content)


if __name__ == "__main__":
    main()
