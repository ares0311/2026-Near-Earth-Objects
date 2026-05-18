#!/usr/bin/env python3
"""Export per-field detection summary from a pipeline run JSON to CSV or HTML."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from io import StringIO


def _load_neos(path: str) -> list:
    with open(path) as f:
        data = json.load(f)
    if not isinstance(data, list):
        data = [data]
    return data


def _build_rows(neos: list) -> list[dict]:
    rows = []
    for d in neos:
        tracklet = d.get("tracklet", {})
        hazard = d.get("hazard", {})
        metadata = d.get("metadata", {})
        obs = tracklet.get("observations", [])
        n_obs = len(obs)
        surveys = list({o.get("mission", "unknown") for o in obs})
        rows.append({
            "object_id": tracklet.get("object_id", "unknown"),
            "arc_days": tracklet.get("arc_days", 0.0),
            "n_observations": n_obs,
            "surveys": "+".join(sorted(surveys)),
            "hazard_flag": hazard.get("hazard_flag", "unknown"),
            "alert_pathway": hazard.get("alert_pathway", "unknown"),
            "moid_au": hazard.get("moid_au"),
            "absolute_magnitude_h": hazard.get("absolute_magnitude_h"),
            "neo_class": hazard.get("neo_class", "unknown"),
            "discovery_priority": metadata.get("discovery_priority", 0.0),
        })
    rows.sort(key=lambda r: r["discovery_priority"], reverse=True)
    return rows


def export_summary(input_path: str, output_path: str | None, fmt: str) -> int:
    neos = _load_neos(input_path)
    rows = _build_rows(neos)

    if not rows:
        print("No candidates found in input.")
        return 1

    if fmt == "csv":
        buf = StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
        content = buf.getvalue()
    else:  # html
        header = "".join(f"<th>{k}</th>" for k in rows[0].keys())
        body_rows = []
        for r in rows:
            cells = "".join(f"<td>{v}</td>" for v in r.values())
            body_rows.append(f"<tr>{cells}</tr>")
        content = (
            "<html><body><table border='1'>"
            f"<tr>{header}</tr>"
            + "\n".join(body_rows)
            + "</table></body></html>"
        )

    if output_path:
        with open(output_path, "w") as f:
            f.write(content)
        print(f"Survey summary exported to: {output_path} ({len(rows)} candidates)")
    else:
        print(content)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export per-candidate detection summary from pipeline run JSON to CSV or HTML."
    )
    parser.add_argument("input", help="Path to scored NEO JSON file (list or single object)")
    parser.add_argument("--output", "-o", default=None, help="Output file path (default: stdout)")
    parser.add_argument(
        "--format",
        choices=["csv", "html"],
        default="csv",
        help="Output format: csv or html (default: csv)",
    )
    args = parser.parse_args()

    sys.exit(export_summary(args.input, args.output, fmt=args.format))


if __name__ == "__main__":
    main()
