"""Generate a prioritized follow-up observation schedule for high-priority NEO candidates.

Usage:
    python Skills/generate_obs_schedule.py <scored_neos.json>
        [--min-priority 0.5] [--max-objects 10]
        [--obs-window-hr 8] [--format text|json] [--out PATH]

Reads a list of ScoredNEO-compatible dicts, ranks them, and outputs an
observation schedule with estimated target coordinates, recommended exposure
time, and urgency tier.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from schemas import ScoredNEO  # noqa: E402
from score import rank_candidates  # noqa: E402

_URGENCY_TIERS = {
    "pha_candidate": ("URGENT", 300),       # 5-min exposures
    "close_approach": ("HIGH", 180),
    "nominal": ("NORMAL", 120),
    "unknown": ("LOW", 90),
}

_MIN_PRIORITY_DEFAULT = 0.3


def _urgency(neo: ScoredNEO) -> tuple[str, int]:
    return _URGENCY_TIERS.get(neo.hazard.hazard_flag, ("LOW", 90))


def build_schedule(
    neos: list[ScoredNEO],
    min_priority: float = _MIN_PRIORITY_DEFAULT,
    max_objects: int = 20,
) -> list[dict]:
    """Build a ranked observation schedule from a list of scored NEOs."""
    ranked = rank_candidates(neos)
    schedule: list[dict] = []
    for neo in ranked:
        if neo.metadata.discovery_priority < min_priority:
            continue
        if len(schedule) >= max_objects:
            break
        urgency_label, exp_sec = _urgency(neo)
        last_obs = neo.tracklet.observations[-1]
        schedule.append({
            "rank": len(schedule) + 1,
            "object_id": neo.tracklet.object_id,
            "urgency": urgency_label,
            "hazard_flag": neo.hazard.hazard_flag,
            "alert_pathway": neo.hazard.alert_pathway,
            "discovery_priority": round(neo.metadata.discovery_priority, 4),
            "last_ra_deg": round(last_obs.ra_deg, 5),
            "last_dec_deg": round(last_obs.dec_deg, 5),
            "last_jd": round(last_obs.jd, 4),
            "motion_rate_arcsec_hr": round(neo.tracklet.motion_rate_arcsec_per_hour, 2),
            "motion_pa_deg": round(neo.tracklet.motion_pa_degrees, 1),
            "arc_days": round(neo.tracklet.arc_days, 3),
            "recommended_exp_sec": exp_sec,
            "moid_au": neo.hazard.moid_au,
            "neo_class": neo.hazard.neo_class,
        })
    return schedule


def _format_text(schedule: list[dict]) -> str:
    if not schedule:
        return "No targets meet the priority threshold.\n"
    lines = [
        f"{'Rank':<5} {'Object':<20} {'Urgency':<8} {'RA':>10} {'Dec':>9} "
        f"{'Rate':>8} {'Exp':>5} {'Priority':>9}",
        "-" * 80,
    ]
    for row in schedule:
        lines.append(
            f"{row['rank']:<5} {row['object_id']:<20} {row['urgency']:<8} "
            f"{row['last_ra_deg']:>10.4f} {row['last_dec_deg']:>9.4f} "
            f"{row['motion_rate_arcsec_hr']:>8.2f} {row['recommended_exp_sec']:>5}s "
            f"{row['discovery_priority']:>9.4f}"
        )
    lines.append(f"\n{len(schedule)} target(s) scheduled.")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Generate NEO follow-up schedule.")
    parser.add_argument("input", help="Scored NEOs JSON file")
    parser.add_argument("--min-priority", type=float, default=_MIN_PRIORITY_DEFAULT)
    parser.add_argument("--max-objects", type=int, default=20)
    parser.add_argument("--format", choices=["text", "json"], default="text")
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    data = json.loads(Path(args.input).read_text())
    neos = [ScoredNEO(**item) for item in data]
    schedule = build_schedule(neos, min_priority=args.min_priority,
                              max_objects=args.max_objects)

    if args.format == "json":
        content = json.dumps(schedule, indent=2) + "\n"
    else:
        content = _format_text(schedule)

    if args.out:
        Path(args.out).write_text(content)
        print(f"Schedule written to {args.out} ({len(schedule)} target(s)).")
    else:
        sys.stdout.write(content)


if __name__ == "__main__":
    main()
